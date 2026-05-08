"""Operator routes — painel da central ATENT 24/7.

Endpoints específicos pro operador (cross-tenant por design). Os
endpoints genéricos de handoff (claim, resolve, mensagens, send) ficam
em admin_handoff_routes.py — operador_central já está autorizado lá.

O que vive aqui:
    GET  /api/operator/me                      — estado do operador
    POST /api/operator/online                  — go online (start shift)
    POST /api/operator/offline                 — go offline (end shift)
    POST /api/operator/heartbeat               — keep-alive
    GET  /api/operator/queue                   — fila cross-tenant
    GET  /api/operator/queue/stats             — agregação SLA
    GET  /api/operator/handoff/<id>/patient-context  — leitura privilegiada
    POST /api/operator/handoff/<id>/escalate-clinical — escala pro médico

Acesso: super_admin, operador_central.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("operator", __name__)


# Tempo desde último heartbeat antes de considerar offline (auto-end shift)
HEARTBEAT_STALE_SECONDS = 300  # 5min


def _user_id() -> str | None:
    user = getattr(g, "user", None) or {}
    return user.get("sub")


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _log_action(
    handoff_id: str | None,
    action_type: str,
    payload: dict | None = None,
    patient_id: str | None = None,
) -> None:
    """Audit fino — toda ação relevante do operador é gravada."""
    operator_id = _user_id()
    if not operator_id:
        return
    try:
        get_postgres().execute(
            """INSERT INTO aia_health_operator_actions
                (operator_user_id, handoff_id, patient_id, action_type, payload)
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            (
                operator_id, handoff_id, patient_id, action_type,
                json.dumps(payload or {}),
            ),
        )
    except Exception:
        logger.warning("operator_action_audit_failed", exc_info=True)


# ════════════════════ STATE / SHIFT ═════════════════════════════════

@bp.get("/api/operator/me")
@require_role("super_admin", "operador_central")
def get_me():
    """Snapshot do estado atual do operador logado.

    Retorna: is_online, current_shift, current_handoff, stats do dia.
    """
    operator_id = _user_id()
    if not operator_id:
        return jsonify({"status": "error", "reason": "no_session"}), 401

    db = get_postgres()
    state = db.fetch_one(
        """SELECT user_id::text AS user_id, is_online, last_heartbeat_at,
                  current_shift_id::text AS current_shift_id,
                  current_handoff_id::text AS current_handoff_id,
                  handoffs_handled_today, notes,
                  created_at, updated_at
           FROM aia_health_operator_states WHERE user_id = %s""",
        (operator_id,),
    )

    shift = None
    if state and state.get("current_shift_id"):
        shift = db.fetch_one(
            """SELECT id::text AS id, started_at, ended_at,
                      handoffs_handled, duration_seconds
               FROM aia_health_operator_shifts WHERE id = %s""",
            (state["current_shift_id"],),
        )

    current_handoff = None
    if state and state.get("current_handoff_id"):
        current_handoff = db.fetch_one(
            """SELECT id::text AS id, phone, reason, priority, status,
                      handoff_type, context_summary, created_at, claimed_at
               FROM aia_health_human_handoff_queue WHERE id = %s""",
            (state["current_handoff_id"],),
        )

    return jsonify({
        "status": "ok",
        "operator": _serialize(state) if state else {
            "user_id": operator_id,
            "is_online": False,
            "handoffs_handled_today": 0,
        },
        "shift": _serialize(shift),
        "current_handoff": _serialize(current_handoff),
    })


@bp.post("/api/operator/online")
@require_role("super_admin", "operador_central")
def go_online():
    """Marca operador como online + abre nova shift se não tiver ativa.
    Idempotente: chamar 2x não duplica shifts.
    """
    operator_id = _user_id()
    if not operator_id:
        return jsonify({"status": "error", "reason": "no_session"}), 401

    db = get_postgres()

    # Garante row em operator_states (UPSERT)
    db.execute(
        """INSERT INTO aia_health_operator_states (user_id, is_online, last_heartbeat_at)
           VALUES (%s, TRUE, NOW())
           ON CONFLICT (user_id) DO UPDATE SET
                is_online = TRUE,
                last_heartbeat_at = NOW()""",
        (operator_id,),
    )

    # Verifica se tem shift aberta
    existing_shift = db.fetch_one(
        """SELECT id::text AS id FROM aia_health_operator_shifts
           WHERE user_id = %s AND ended_at IS NULL
           ORDER BY started_at DESC LIMIT 1""",
        (operator_id,),
    )

    if existing_shift:
        shift_id = existing_shift["id"]
        action = "go_online_existing_shift"
    else:
        shift_row = db.fetch_one(
            """INSERT INTO aia_health_operator_shifts (user_id)
               VALUES (%s) RETURNING id::text AS id""",
            (operator_id,),
        )
        shift_id = shift_row["id"] if shift_row else None
        action = "shift_start"

    if shift_id:
        db.execute(
            """UPDATE aia_health_operator_states
               SET current_shift_id = %s WHERE user_id = %s""",
            (shift_id, operator_id),
        )

    _log_action(None, action, {"shift_id": shift_id})
    return jsonify({"status": "ok", "shift_id": shift_id})


@bp.post("/api/operator/offline")
@require_role("super_admin", "operador_central")
def go_offline():
    """Marca operador como offline + fecha shift atual."""
    operator_id = _user_id()
    if not operator_id:
        return jsonify({"status": "error", "reason": "no_session"}), 401

    db = get_postgres()
    state = db.fetch_one(
        """SELECT current_shift_id::text AS current_shift_id,
                  current_handoff_id::text AS current_handoff_id
           FROM aia_health_operator_states WHERE user_id = %s""",
        (operator_id,),
    )

    if state and state.get("current_handoff_id"):
        return jsonify({
            "status": "error",
            "reason": "active_handoff",
            "message": "Resolva ou libere o atendimento ativo antes de sair.",
            "handoff_id": state["current_handoff_id"],
        }), 400

    if state and state.get("current_shift_id"):
        db.execute(
            """UPDATE aia_health_operator_shifts
               SET ended_at = NOW(),
                   handoffs_handled = (
                       SELECT COUNT(*) FROM aia_health_operator_actions
                       WHERE operator_user_id = %s
                         AND action_type = 'resolve_handoff'
                         AND created_at >= (
                             SELECT started_at
                             FROM aia_health_operator_shifts
                             WHERE id = %s
                         )
                   )
               WHERE id = %s AND ended_at IS NULL""",
            (operator_id, state["current_shift_id"], state["current_shift_id"]),
        )

    db.execute(
        """UPDATE aia_health_operator_states
           SET is_online = FALSE,
               current_shift_id = NULL,
               current_handoff_id = NULL,
               handoffs_handled_today = 0
           WHERE user_id = %s""",
        (operator_id,),
    )

    _log_action(None, "shift_end", {"shift_id": state.get("current_shift_id") if state else None})
    return jsonify({"status": "ok"})


@bp.post("/api/operator/heartbeat")
@require_role("super_admin", "operador_central")
def heartbeat():
    """Mantém operador como online — frontend dispara a cada 30-60s."""
    operator_id = _user_id()
    if not operator_id:
        return jsonify({"status": "error", "reason": "no_session"}), 401

    get_postgres().execute(
        """UPDATE aia_health_operator_states
           SET last_heartbeat_at = NOW(), is_online = TRUE
           WHERE user_id = %s""",
        (operator_id,),
    )
    return jsonify({"status": "ok", "at": datetime.now(timezone.utc).isoformat()})


# ════════════════════ QUEUE (cross-tenant) ═══════════════════════════

@bp.get("/api/operator/queue")
@require_role("super_admin", "operador_central")
def get_queue():
    """Lista a fila cross-tenant disponível pro operador.

    Query params:
        status: csv pending|claimed (default: 'pending,claimed')
        type: csv 'commercial,clinical,support,operator' (default: todos)
        priority: csv 'P1,P2,P3'
        mine: bool — só os reivindicados por mim
        limit: max 100, default 50
    """
    qs = request.args
    statuses = (qs.get("status") or "pending,claimed").split(",")
    types = (qs.get("type") or "").split(",") if qs.get("type") else []
    priorities = qs.get("priority", "").split(",") if qs.get("priority") else []
    mine = qs.get("mine", "").lower() in ("true", "1", "yes")
    limit = max(1, min(int(qs.get("limit") or 50), 100))

    where = ["1=1"]
    params: list = []
    statuses_clean = [s.strip() for s in statuses if s.strip() in
                      ("pending", "claimed", "resolved", "expired")]
    if statuses_clean:
        where.append("status = ANY(%s)")
        params.append(statuses_clean)

    types_clean = [t.strip() for t in types if t.strip() in
                   ("commercial", "clinical", "support", "operator")]
    if types_clean:
        where.append("handoff_type = ANY(%s)")
        params.append(types_clean)

    pri_clean = [p.strip() for p in priorities if p.strip() in ("P1", "P2", "P3")]
    if pri_clean:
        where.append("priority = ANY(%s)")
        params.append(pri_clean)

    if mine:
        where.append("claimed_by_user_id = %s")
        params.append(_user_id())

    rows = get_postgres().fetch_all(
        f"""SELECT id::text AS id, trace_id::text AS trace_id, phone, tenant_id,
                   channel, reason, context_summary, triggered_by, priority,
                   status, handoff_type,
                   patient_id::text AS patient_id, caregiver_id::text AS caregiver_id,
                   claimed_at, claimed_by_user_id::text AS claimed_by_user_id,
                   resolved_at, resolved_by_user_id::text AS resolved_by_user_id,
                   sla_target_seconds, sla_breached_at,
                   notified_central_at, created_at,
                   EXTRACT(EPOCH FROM (NOW() - created_at))::INT AS waiting_seconds
            FROM aia_health_human_handoff_queue
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
                created_at ASC
            LIMIT %s""",
        tuple(params + [limit]),
    )

    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.get("/api/operator/queue/stats")
@require_role("super_admin", "operador_central")
def queue_stats():
    """Stats agregadas da fila — pra dashboard do operador."""
    db = get_postgres()
    pending = db.fetch_one(
        """SELECT COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                  COUNT(*) FILTER (WHERE status = 'claimed') AS claimed,
                  COUNT(*) FILTER (WHERE priority = 'P1' AND status IN ('pending', 'claimed')) AS p1_open,
                  COUNT(*) FILTER (WHERE sla_breached_at IS NOT NULL) AS sla_breached,
                  COUNT(*) FILTER (WHERE status = 'resolved' AND resolved_at >= NOW() - INTERVAL '24 hours') AS resolved_24h
           FROM aia_health_human_handoff_queue""",
    ) or {}

    by_type = db.fetch_all(
        """SELECT handoff_type, COUNT(*) AS n
           FROM aia_health_human_handoff_queue
           WHERE status IN ('pending', 'claimed')
           GROUP BY handoff_type""",
    )
    type_counts = {r["handoff_type"]: int(r["n"]) for r in by_type}

    online_operators = db.fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_operator_states
           WHERE is_online = TRUE
             AND last_heartbeat_at >= NOW() - INTERVAL '5 minutes'""",
    )

    return jsonify({
        "status": "ok",
        "queue": {k: int(v or 0) for k, v in pending.items()},
        "by_type": type_counts,
        "operators_online": int((online_operators or {}).get("n") or 0),
    })


# ════════════════════ PATIENT CONTEXT (leitura privilegiada) ═════════

@bp.get("/api/operator/handoff/<handoff_id>/patient-context")
@require_role("super_admin", "operador_central")
def patient_context(handoff_id: str):
    """Contexto completo do paciente envolvido no handoff.

    Retorna pra montar o "rolex" do operador na sidebar do painel:
        • patient (full record + responsáveis)
        • recent care_events (últimos N)
        • recent vital_signs (últimos N por tipo)
        • active prescriptions (medicação vigente)
        • caregivers vinculados ao paciente
    """
    db = get_postgres()
    handoff = db.fetch_one(
        """SELECT id::text AS id, phone, tenant_id,
                  patient_id::text AS patient_id,
                  caregiver_id::text AS caregiver_id,
                  handoff_type, status, context_summary, conversation_log
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not handoff:
        return jsonify({"status": "error", "reason": "handoff_not_found"}), 404

    patient = None
    if handoff.get("patient_id"):
        patient = db.fetch_one(
            """SELECT id::text AS id, full_name, nickname, cpf, birth_date,
                      gender, care_unit, room_number, care_level,
                      conditions, medications, allergies, responsible,
                      preferred_form_of_address, is_self_reporting,
                      tecnosenior_patient_id, photo_url, notes,
                      created_at, updated_at
               FROM aia_health_patients WHERE id = %s""",
            (handoff["patient_id"],),
        )

    recent_events = []
    if handoff.get("patient_id"):
        recent_events = db.fetch_all(
            """SELECT id::text AS id, event_type, current_classification,
                      summary, reasoning, status, opened_at, resolved_at,
                      caregiver_phone, event_tags
               FROM aia_health_care_events
               WHERE patient_id = %s
               ORDER BY opened_at DESC LIMIT 10""",
            (handoff["patient_id"],),
        )

    recent_vitals = []
    if handoff.get("patient_id"):
        recent_vitals = db.fetch_all(
            """SELECT id::text AS id, vital_type, value_numeric,
                      value_secondary, unit, status, source,
                      measured_at, notes
               FROM aia_health_vital_signs
               WHERE patient_id = %s
               ORDER BY measured_at DESC LIMIT 30""",
            (handoff["patient_id"],),
        )

    caregivers = []
    if handoff.get("patient_id"):
        # Cuidadores que reportaram sobre esse paciente nos últimos 30 dias
        caregivers = db.fetch_all(
            """SELECT DISTINCT c.id::text AS id, c.full_name, c.phone,
                      c.role, c.created_at
               FROM aia_health_caregivers c
               LEFT JOIN aia_health_care_events ce
                    ON ce.caregiver_id = c.id
                    AND ce.patient_id = %s
                    AND ce.opened_at >= NOW() - INTERVAL '30 days'
               WHERE c.id IN (
                   SELECT caregiver_id FROM aia_health_care_events
                   WHERE patient_id = %s AND caregiver_id IS NOT NULL
                   GROUP BY caregiver_id
               )
               LIMIT 20""",
            (handoff["patient_id"], handoff["patient_id"]),
        )

    _log_action(
        handoff_id, "view_patient_context",
        {"patient_id": handoff.get("patient_id")},
        patient_id=handoff.get("patient_id"),
    )

    return jsonify({
        "status": "ok",
        "handoff": _serialize(handoff),
        "patient": _serialize(patient),
        "recent_events": [_serialize(e) for e in recent_events],
        "recent_vital_signs": [_serialize(v) for v in recent_vitals],
        "caregivers": [_serialize(c) for c in caregivers],
    })


# ════════════════════ ESCALATION ═════════════════════════════════════

@bp.post("/api/operator/handoff/<handoff_id>/escalate-clinical")
@require_role("super_admin", "operador_central")
def escalate_clinical(handoff_id: str):
    """Escala handoff atual pro plantão CLÍNICO.

    Cria novo handoff handoff_type='clinical' com priority elevada (P1),
    referencia o handoff_id atual no payload pra audit. Mantém o handoff
    do operador em 'claimed' até ele resolver formalmente.

    Body opcional: {reason, urgency: 'P1'|'P2'|'P3'}
    """
    body = request.get_json(silent=True) or {}
    reason = body.get("reason") or "operator_escalation"
    urgency = body.get("urgency") or "P1"
    if urgency not in ("P1", "P2", "P3"):
        urgency = "P1"

    db = get_postgres()
    src = db.fetch_one(
        """SELECT phone, tenant_id, patient_id::text AS patient_id,
                  caregiver_id::text AS caregiver_id,
                  context_summary, conversation_log, trace_id
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not src:
        return jsonify({"status": "error", "reason": "handoff_not_found"}), 404

    sla_seconds = {"P1": 300, "P2": 1800, "P3": 7200}[urgency]
    operator_id = _user_id()

    enriched_summary = (
        f"[ESCALATED FROM OPERATOR {operator_id[:8] if operator_id else '?'}]\n"
        f"Razão: {reason}\n\n"
        f"Contexto operador → {src.get('context_summary') or '(sem resumo)'}"
    )

    new_row = db.fetch_one(
        """INSERT INTO aia_health_human_handoff_queue (
            trace_id, phone, tenant_id, channel, reason,
            context_summary, conversation_log, triggered_by,
            priority, status, sla_target_seconds, handoff_type,
            patient_id, caregiver_id
        ) VALUES (
            %s, %s, %s, 'whatsapp', %s, %s, %s::jsonb, 'admin',
            %s, 'pending', %s, 'clinical', %s, %s
        )
        RETURNING id::text AS id""",
        (
            src.get("trace_id"), src["phone"], src.get("tenant_id"),
            f"escalation_from_operator: {reason}",
            enriched_summary,
            json.dumps(src.get("conversation_log") or []),
            urgency, sla_seconds,
            src.get("patient_id"), src.get("caregiver_id"),
        ),
    )

    _log_action(
        handoff_id, "escalate_clinical",
        {
            "to_handoff_id": new_row["id"] if new_row else None,
            "urgency": urgency,
            "reason": reason,
        },
        patient_id=src.get("patient_id"),
    )

    write_audit(
        action="operator_escalated_clinical",
        actor=operator_id or "operator",
        resource_type="handoff",
        resource_id=handoff_id,
        payload={
            "from_handoff": handoff_id,
            "to_handoff": new_row["id"] if new_row else None,
            "urgency": urgency,
            "reason": reason,
        },
    )

    return jsonify({
        "status": "ok",
        "from_handoff_id": handoff_id,
        "to_handoff_id": new_row["id"] if new_row else None,
        "urgency": urgency,
    })


# ════════════════════ ADMIN / SUPER ═══════════════════════════════════

@bp.get("/api/operator/operators")
@require_role("super_admin", "admin_tenant")
def list_operators():
    """Lista todos os operadores (super_admin / admin_tenant).
    Útil pra dashboard de gestão da central."""
    rows = get_postgres().fetch_all(
        """SELECT u.id::text AS id, u.full_name, u.email, u.phone,
                  u.active, u.created_at,
                  s.is_online, s.last_heartbeat_at,
                  s.handoffs_handled_today,
                  s.current_handoff_id::text AS current_handoff_id,
                  s.current_shift_id::text AS current_shift_id
           FROM aia_health_users u
           LEFT JOIN aia_health_operator_states s ON s.user_id = u.id
           WHERE u.role = 'operador_central'
           ORDER BY s.is_online DESC NULLS LAST, u.full_name""",
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })
