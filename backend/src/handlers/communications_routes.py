"""Comunicações — orquestra cenários de ligação Sofia (outbound).

Endpoints:
    /api/communications/scenarios          (CRUD admin)
    /api/communications/dial               (POST — dispara ligação com scenario_id)
    /api/communications/active-calls       (GET — chamadas em curso)
    /api/communications/history            (GET — histórico)
    /api/communications/scheduled          (CRUD agendadas)

Permissões:
    /scenarios CRUD — super_admin + admin_tenant
    /dial      — medico, enfermeiro, admin_tenant, super_admin
    histórico  — qualquer role autenticada (filtra por escopo no backend)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
import psycopg2.extras
from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)
bp = Blueprint("communications", __name__)

VOICE_CALL_SERVICE_URL = os.getenv(
    "VOICE_CALL_SERVICE_URL", "http://voice-call-service:5040"
)
_client = httpx.Client(timeout=20.0)


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


# ───────────────────────── SCENARIOS (CRUD admin) ─────────────────────────

@bp.get("/api/communications/scenarios")
@require_role("super_admin", "admin_tenant")
def list_scenarios():
    rows = get_postgres().fetch_all(
        """SELECT id, code, label, direction, persona, description,
                  voice, allowed_tools, post_call_actions,
                  max_duration_seconds, active, updated_at
           FROM aia_health_call_scenarios
           ORDER BY direction, code"""
    )
    return jsonify({"status": "ok", "scenarios": [_serialize(r) for r in rows]})


@bp.get("/api/communications/scenarios/<sid>")
@require_role("super_admin", "admin_tenant")
def get_scenario(sid: str):
    row = get_postgres().fetch_one(
        "SELECT * FROM aia_health_call_scenarios WHERE id = %s", (sid,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    return jsonify({"status": "ok", "scenario": _serialize(row)})


@bp.post("/api/communications/scenarios")
@require_role("super_admin", "admin_tenant")
def create_scenario():
    body = request.get_json(silent=True) or {}
    required = ("code", "label", "direction", "persona", "system_prompt")
    if not all(body.get(k) for k in required):
        return jsonify({
            "status": "error", "reason": "missing_required",
            "fields": required,
        }), 400

    row = get_postgres().fetch_one(
        """INSERT INTO aia_health_call_scenarios
            (code, label, direction, persona, description, system_prompt,
             allowed_tools, post_call_actions, voice,
             pre_call_context_sql, max_duration_seconds, active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *""",
        (
            body["code"], body["label"], body["direction"], body["persona"],
            body.get("description"), body["system_prompt"],
            body.get("allowed_tools") or [],
            body.get("post_call_actions") or ["log_audit"],
            body.get("voice") or "ara",
            body.get("pre_call_context_sql"),
            int(body.get("max_duration_seconds") or 600),
            bool(body.get("active", True)),
        ),
    )
    audit_log(action="rule.scenario.create", details={
        "id": str(row["id"]), "code": body["code"],
    })
    return jsonify({"status": "ok", "scenario": _serialize(row)}), 201


@bp.patch("/api/communications/scenarios/<sid>")
@require_role("super_admin", "admin_tenant")
def update_scenario(sid: str):
    body = request.get_json(silent=True) or {}
    fields = []
    params = []
    for k in ("label", "description", "system_prompt", "allowed_tools",
              "post_call_actions", "voice", "pre_call_context_sql",
              "max_duration_seconds", "active"):
        if k in body:
            fields.append(f"{k} = %s")
            params.append(body[k])
    if not fields:
        return jsonify({"status": "error", "reason": "nothing_to_update"}), 400
    params.append(sid)
    row = get_postgres().fetch_one(
        f"UPDATE aia_health_call_scenarios SET {', '.join(fields)} "
        f"WHERE id = %s RETURNING *",
        tuple(params),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    audit_log(action="rule.scenario.update", details={
        "id": sid, "fields_changed": list(body.keys()),
    })
    return jsonify({"status": "ok", "scenario": _serialize(row)})


@bp.delete("/api/communications/scenarios/<sid>")
@require_role("super_admin")
def delete_scenario(sid: str):
    """Soft delete via active=FALSE pra preservar histórico."""
    row = get_postgres().fetch_one(
        "UPDATE aia_health_call_scenarios SET active = FALSE "
        "WHERE id = %s RETURNING id", (sid,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    audit_log(action="rule.scenario.delete", details={"id": sid})
    return jsonify({"status": "ok"})


# ───────────────────────── DIAL (com scenario_id) ─────────────────────────

@bp.post("/api/communications/dial")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def dial():
    """Origina ligação Sofia carregando contexto + prompt do scenario.

    Body:
        scenario_code: ex 'paciente_checkin_matinal'   (preferido)
        OU scenario_id: UUID
        destination: '5551996161700' (E.164 sem +)
        patient_id: opcional
        user_id: opcional (caller, pra carregar memória)
        full_name: nome de quem responde (override)
        extra_context: dict (passado como persona_ctx.extras)
    """
    from flask import g
    body = request.get_json(silent=True) or {}
    destination = (body.get("destination") or "").strip()
    if not destination:
        return jsonify({"status": "error", "reason": "destination_required"}), 400

    db = get_postgres()
    if body.get("scenario_id"):
        scenario = db.fetch_one(
            "SELECT * FROM aia_health_call_scenarios WHERE id = %s AND active = TRUE",
            (body["scenario_id"],),
        )
    elif body.get("scenario_code"):
        scenario = db.fetch_one(
            "SELECT * FROM aia_health_call_scenarios "
            "WHERE code = %s AND active = TRUE LIMIT 1",
            (body["scenario_code"],),
        )
    else:
        return jsonify({
            "status": "error", "reason": "scenario_id_or_code_required",
        }), 400

    if not scenario:
        return jsonify({"status": "error", "reason": "scenario_not_found"}), 404

    # Carrega contexto do paciente (se aplicável)
    patient_context = None
    if body.get("patient_id"):
        patient_context = db.fetch_one(
            """SELECT id, full_name, nickname, birth_date, conditions,
                      allergies, care_unit, room_number
               FROM aia_health_patients WHERE id = %s""",
            (body["patient_id"],),
        )

    # User caller (pra memória)
    caller_user_id = body.get("user_id") or (
        g.user.get("user_id") if hasattr(g, "user") and g.user else None
    )
    full_name = body.get("full_name")
    if not full_name and caller_user_id:
        u = db.fetch_one(
            "SELECT full_name FROM aia_health_users WHERE id = %s",
            (caller_user_id,),
        )
        if u:
            full_name = u["full_name"]

    payload = {
        "destination": destination,
        "persona": scenario["persona"],
        "user_id": caller_user_id,
        "patient_id": body.get("patient_id"),
        "full_name": full_name or "amigo(a)",
        "tenant_id": "connectaiacare_demo",
        # Tudo do scenario vai como override
        "scenario_id": str(scenario["id"]),
        "scenario_code": scenario["code"],
        "scenario_system_prompt": scenario["system_prompt"],
        "scenario_voice": scenario["voice"],
        "scenario_allowed_tools": scenario["allowed_tools"] or [],
        "extra_context": {
            **(body.get("extra_context") or {}),
            "patient": _serialize(patient_context) if patient_context else None,
            "scenario_label": scenario["label"],
        },
    }

    try:
        resp = _client.post(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/dial",
            json=payload, timeout=20.0,
        )
    except httpx.RequestError as exc:
        logger.warning("voice_call_unreachable: %s", exc)
        return jsonify({"status": "error", "reason": "voice_call_unreachable"}), 503

    if resp.status_code >= 400:
        return jsonify({
            "status": "error", "reason": f"upstream_{resp.status_code}",
            "detail": resp.text[:300],
        }), 502

    out = resp.json() or {}
    audit_log(action="communication.dial", details={
        "scenario_code": scenario["code"],
        "destination": destination,
        "patient_id": body.get("patient_id"),
        "call_id": out.get("call_id"),
    })
    return jsonify({**out, "scenario_code": scenario["code"]}), 200


@bp.post("/api/communications/hangup")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def hangup():
    body = request.get_json(silent=True) or {}
    if not body.get("call_id"):
        return jsonify({"status": "error", "reason": "call_id_required"}), 400
    try:
        resp = _client.post(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/hangup",
            json={"call_id": body["call_id"]}, timeout=10.0,
        )
    except httpx.RequestError:
        return jsonify({"status": "error", "reason": "voice_call_unreachable"}), 503
    return jsonify(resp.json()), resp.status_code


@bp.get("/api/communications/active-calls")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def active_calls():
    try:
        resp = _client.get(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/calls", timeout=5.0,
        )
        return jsonify(resp.json()), resp.status_code
    except httpx.RequestError:
        return jsonify({"status": "error", "reason": "voice_call_unreachable"}), 503


@bp.get("/api/communications/history")
def history():
    """Histórico de ligações (sessões de voice_call) com transcrições."""
    db = get_postgres()
    limit = max(1, min(int(request.args.get("limit", 50)), 200))
    patient_id = request.args.get("patient_id")
    user_id = request.args.get("user_id")

    where = ["s.channel = 'voice_call'"]
    params: list = []
    if patient_id:
        where.append("s.patient_id = %s")
        params.append(patient_id)
    if user_id:
        where.append("s.user_id = %s")
        params.append(user_id)

    rows = db.fetch_all(
        f"""SELECT s.id, s.persona, s.user_id, s.patient_id, s.phone,
                   s.created_at, s.last_active_at,
                   p.full_name AS patient_name, p.nickname AS patient_nickname,
                   u.full_name AS caller_name,
                   (SELECT COUNT(*) FROM aia_health_sofia_messages m
                    WHERE m.session_id = s.id) AS message_count
            FROM aia_health_sofia_sessions s
            LEFT JOIN aia_health_patients p ON p.id = s.patient_id
            LEFT JOIN aia_health_users u ON u.id = s.user_id
            WHERE {' AND '.join(where)}
            ORDER BY s.last_active_at DESC LIMIT {limit}""",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "history": [_serialize(r) for r in rows],
    })


@bp.get("/api/communications/history/<session_id>/transcript")
def history_transcript(session_id: str):
    rows = get_postgres().fetch_all(
        """SELECT role, content, created_at, tool_name
           FROM aia_health_sofia_messages
           WHERE session_id = %s
           ORDER BY created_at ASC""",
        (session_id,),
    )
    return jsonify({
        "status": "ok",
        "transcript": [_serialize(r) for r in rows],
    })
