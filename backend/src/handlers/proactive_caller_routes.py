"""Proactive Caller — endpoints HTTP.

    GET    /api/proactive-caller/decisions        — log de decisões (admin)
    POST   /api/proactive-caller/trigger/<pid>    — força avaliação agora
    GET    /api/proactive-caller/patient/<pid>    — settings do paciente
    PATCH  /api/proactive-caller/patient/<pid>    — atualiza settings
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services import proactive_caller
from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)
bp = Blueprint("proactive_caller", __name__)


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
    return out


# ──────────── Log de decisões ────────────

@bp.get("/api/proactive-caller/decisions")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_decisions():
    """Lista decisões recentes. Filtra por tenant do user.

    Query params:
        patient_id  — filtra por paciente específico
        decision    — filtra por tipo (will_call, skip_*, failed_dispatch)
        limit       — default 100, max 500
    """
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"

    patient_id = request.args.get("patient_id")
    decision = request.args.get("decision")
    limit = min(int(request.args.get("limit", 100)), 500)

    where = ["d.tenant_id = %s"]
    params: list = [tenant_id]
    if patient_id:
        where.append("d.patient_id = %s")
        params.append(patient_id)
    if decision:
        where.append("d.decision = %s")
        params.append(decision)
    params.append(limit)

    rows = get_postgres().fetch_all(
        f"""SELECT d.id, d.tenant_id, d.patient_id, d.evaluated_at,
                   d.decision, d.trigger_score, d.breakdown, d.call_id,
                   d.error, d.notes,
                   p.full_name AS patient_name,
                   p.nickname AS patient_nickname
            FROM aia_health_proactive_call_decisions d
            LEFT JOIN aia_health_patients p ON p.id = d.patient_id
            WHERE {' AND '.join(where)}
            ORDER BY d.evaluated_at DESC
            LIMIT %s""",
        tuple(params),
    )
    return jsonify({
        "status": "ok", "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


# ──────────── Manual trigger ────────────

@bp.post("/api/proactive-caller/trigger/<patient_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def trigger_for_patient(patient_id: str):
    """Avalia esse paciente AGORA — ignora apenas o lock do worker, mas
    continua respeitando janela horária / DND / circuit breaker / score.

    Útil pra testar config do paciente ou pra forçar reavaliação após
    mudança de risk_score.

    Body opcional:
        force=true — bypassa janela horária + DND + threshold (super_admin only)
    """
    body = request.get_json(silent=True) or {}
    user_ctx = getattr(g, "user", None) or {}
    user_role = user_ctx.get("role")
    force = bool(body.get("force"))
    if force and user_role != "super_admin":
        return jsonify({
            "status": "error", "reason": "only_super_admin_can_force",
        }), 403

    db = get_postgres()
    patient = db.fetch_one(
        """SELECT id, tenant_id, full_name, nickname, care_level,
                  responsible, sofia_proactive_calls_enabled,
                  preferred_call_window_start, preferred_call_window_end,
                  min_hours_between_calls, do_not_disturb_until,
                  proactive_call_phone, proactive_scenario_code,
                  proactive_call_timezone
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    tenant_cfg = db.fetch_one(
        "SELECT proactive_caller_settings FROM aia_health_tenant_config "
        "WHERE tenant_id = %s",
        (patient["tenant_id"],),
    )
    settings = (tenant_cfg or {}).get("proactive_caller_settings") or {}
    threshold = (
        0 if force
        else int(settings.get("trigger_threshold")
                 or proactive_caller.DEFAULT_TRIGGER_THRESHOLD)
    )

    if force:
        # Bypassa DND e janela
        patient_dict = dict(patient)
        patient_dict["do_not_disturb_until"] = None
        from datetime import time as dtime
        patient_dict["preferred_call_window_start"] = dtime(0, 0)
        patient_dict["preferred_call_window_end"] = dtime(23, 59, 59)
    else:
        patient_dict = dict(patient)

    audit_log(action="proactive_caller.manual_trigger", payload={
        "patient_id": patient_id, "force": force,
        "actor": user_ctx.get("sub"),
    })

    decision = proactive_caller.evaluate_and_maybe_call(
        tenant_id=patient["tenant_id"],
        patient_row=patient_dict,
        tenant_settings=settings,
        threshold=threshold,
        now_utc=datetime.now(timezone.utc),
        circuit_open=False if force else _check_circuit_open(patient["tenant_id"]),
    )
    return jsonify({"status": "ok", "decision": decision})


def _check_circuit_open(tenant_id: str) -> bool:
    cb = get_postgres().fetch_one(
        """SELECT state, open_until FROM aia_health_safety_circuit_breaker
           WHERE tenant_id = %s""",
        (tenant_id,),
    )
    if not cb:
        return False
    return bool(
        cb.get("state") == "open"
        and (not cb.get("open_until") or cb["open_until"] > datetime.now(timezone.utc))
    )


# ──────────── Patient settings (preferências de chamada) ────────────

PATIENT_SETTINGS_FIELDS = {
    "sofia_proactive_calls_enabled": bool,
    "preferred_call_window_start": str,  # "HH:MM" ou "HH:MM:SS"
    "preferred_call_window_end": str,
    "min_hours_between_calls": int,
    "do_not_disturb_until": str,         # ISO 8601 ou None
    "proactive_call_phone": str,
    "proactive_scenario_code": str,
    "proactive_call_timezone": str,
}


@bp.get("/api/proactive-caller/patient/<patient_id>/settings")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro",
              "cuidador_pro", "familia")
def get_patient_settings(patient_id: str):
    row = get_postgres().fetch_one(
        """SELECT id, full_name,
                  sofia_proactive_calls_enabled,
                  preferred_call_window_start, preferred_call_window_end,
                  min_hours_between_calls, do_not_disturb_until,
                  proactive_call_phone, proactive_scenario_code,
                  proactive_call_timezone
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404
    return jsonify({"status": "ok", "settings": _serialize(row)})


@bp.patch("/api/proactive-caller/patient/<patient_id>/settings")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def update_patient_settings(patient_id: str):
    body = request.get_json(silent=True) or {}
    fields = []
    params: list = []
    for k, _ in PATIENT_SETTINGS_FIELDS.items():
        if k in body:
            fields.append(f"{k} = %s")
            v = body[k]
            # Aceita string vazia como null nos opcionais
            if v == "" and k in (
                "do_not_disturb_until", "proactive_call_phone",
                "proactive_scenario_code",
            ):
                v = None
            params.append(v)
    if not fields:
        return jsonify({"status": "error", "reason": "nothing_to_update"}), 400
    params.append(patient_id)

    row = get_postgres().fetch_one(
        f"UPDATE aia_health_patients SET {', '.join(fields)}, updated_at = NOW() "
        f"WHERE id = %s RETURNING id, sofia_proactive_calls_enabled, "
        f"preferred_call_window_start, preferred_call_window_end, "
        f"min_hours_between_calls, do_not_disturb_until, "
        f"proactive_call_phone, proactive_scenario_code, "
        f"proactive_call_timezone",
        tuple(params),
    )
    if not row:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    user_ctx = getattr(g, "user", None) or {}
    audit_log(action="proactive_caller.settings.update", payload={
        "patient_id": patient_id, "fields": list(body.keys()),
        "actor": user_ctx.get("sub"),
    })
    return jsonify({"status": "ok", "settings": _serialize(row)})


# ──────────── Stats ────────────

@bp.get("/api/proactive-caller/stats")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def stats():
    """Resumo das últimas 24h."""
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    # Atenção: psycopg2 usa % como placeholder. Pra LIKE com '%' literal,
    # precisa escapar como '%%' no SQL passado pra cur.execute(query, params).
    row = get_postgres().fetch_one(
        """SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE decision = 'will_call') AS will_call,
            COUNT(*) FILTER (WHERE decision = 'failed_dispatch') AS failed,
            COUNT(*) FILTER (WHERE decision LIKE 'skip\\_%%') AS skipped,
            AVG(trigger_score) FILTER (WHERE decision = 'will_call') AS avg_score_called,
            AVG(trigger_score) FILTER (WHERE decision LIKE 'skip\\_%%') AS avg_score_skipped
           FROM aia_health_proactive_call_decisions
           WHERE tenant_id = %s AND evaluated_at > NOW() - INTERVAL '24 hours'""",
        (tenant_id,),
    )
    out = dict(row) if row else {}
    for k, v in list(out.items()):
        if isinstance(v, (float,)):
            out[k] = round(v, 1)
    return jsonify({"status": "ok", "tenant_id": tenant_id, "stats": out})
