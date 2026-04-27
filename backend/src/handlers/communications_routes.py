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
    audit_log(action="rule.scenario.create", payload={
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
    audit_log(action="rule.scenario.update", payload={
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
    audit_log(action="rule.scenario.delete", payload={"id": sid})
    return jsonify({"status": "ok"})


# ───────────────────────── SCENARIO VERSIONING ─────────────────────────

@bp.get("/api/communications/scenarios/<sid>/versions")
@require_role("super_admin", "admin_tenant")
def list_scenario_versions(sid: str):
    """Lista todas as versões de um cenário, ordenadas por version_number desc."""
    db = get_postgres()
    scenario = db.fetch_one(
        "SELECT id, current_version_id FROM aia_health_call_scenarios WHERE id = %s",
        (sid,),
    )
    if not scenario:
        return jsonify({"status": "error", "reason": "scenario_not_found"}), 404

    rows = db.fetch_all(
        """SELECT id, scenario_id, version_number, status, label, description,
                  system_prompt, voice, allowed_tools, post_call_actions,
                  pre_call_context_sql, max_duration_seconds, golden_test_results,
                  notes, created_at, created_by_user_id, published_at,
                  published_by_user_id
           FROM aia_health_call_scenarios_versions
           WHERE scenario_id = %s
           ORDER BY version_number DESC""",
        (sid,),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
        "current_version_id": str(scenario["current_version_id"])
            if scenario.get("current_version_id") else None,
    })


@bp.post("/api/communications/scenarios/<sid>/versions")
@require_role("super_admin", "admin_tenant")
def create_scenario_version(sid: str):
    """Cria nova versão DRAFT. Se payload omitir campos, herda do scenario base."""
    from flask import g
    db = get_postgres()
    scenario = db.fetch_one(
        "SELECT * FROM aia_health_call_scenarios WHERE id = %s", (sid,),
    )
    if not scenario:
        return jsonify({"status": "error", "reason": "scenario_not_found"}), 404

    body = request.get_json(silent=True) or {}
    if not body.get("system_prompt"):
        return jsonify({
            "status": "error", "reason": "system_prompt_required",
        }), 400

    next_v = db.fetch_one(
        """SELECT COALESCE(MAX(version_number), 0) + 1 AS next_v
           FROM aia_health_call_scenarios_versions
           WHERE scenario_id = %s""", (sid,),
    )
    version_number = next_v["next_v"]

    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")

    row = db.fetch_one(
        """INSERT INTO aia_health_call_scenarios_versions
            (scenario_id, version_number, label, description, system_prompt,
             voice, allowed_tools, post_call_actions, pre_call_context_sql,
             max_duration_seconds, status, notes, created_by_user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s, %s)
        RETURNING *""",
        (
            sid, version_number,
            body.get("label") or scenario["label"],
            body.get("description") if "description" in body else scenario.get("description"),
            body["system_prompt"],
            body.get("voice") or scenario.get("voice") or "ara",
            body.get("allowed_tools") or scenario.get("allowed_tools") or [],
            body.get("post_call_actions") or scenario.get("post_call_actions") or ["log_audit"],
            body.get("pre_call_context_sql") if "pre_call_context_sql" in body
                else scenario.get("pre_call_context_sql"),
            int(body.get("max_duration_seconds") or scenario.get("max_duration_seconds") or 600),
            body.get("notes"),
            user_id,
        ),
    )
    audit_log(action="rule.scenario.version.create", payload={
        "scenario_id": sid, "version_id": str(row["id"]),
        "version_number": version_number,
    })
    return jsonify({"status": "ok", "version": _serialize(row)}), 201


@bp.post("/api/communications/scenarios/<sid>/versions/<vid>/promote")
@require_role("super_admin", "admin_tenant")
def promote_scenario_version(sid: str, vid: str):
    """Promove versão entre estados: draft → testing → published → archived.

    Quando promove para 'published':
    - Arquiva versão atualmente published do mesmo scenario
    - Atualiza scenario.current_version_id
    - Copia campos da versão para o scenario base (mantém compatibilidade
      com código de dial existente que lê direto do scenario)
    """
    from flask import g
    db = get_postgres()
    body = request.get_json(silent=True) or {}
    target = body.get("target")

    if target not in ("draft", "testing", "published", "archived"):
        return jsonify({"status": "error", "reason": "invalid_target"}), 400

    version = db.fetch_one(
        """SELECT * FROM aia_health_call_scenarios_versions
           WHERE id = %s AND scenario_id = %s""",
        (vid, sid),
    )
    if not version:
        return jsonify({"status": "error", "reason": "version_not_found"}), 404

    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")

    if target == "published":
        # Arquiva published anterior
        db.execute(
            """UPDATE aia_health_call_scenarios_versions
               SET status = 'archived'
               WHERE scenario_id = %s AND status = 'published' AND id <> %s""",
            (sid, vid),
        )
        # Promove esta
        row = db.fetch_one(
            """UPDATE aia_health_call_scenarios_versions
               SET status = 'published', published_at = NOW(),
                   published_by_user_id = %s
               WHERE id = %s
               RETURNING *""",
            (user_id, vid),
        )
        # Aponta scenario.current_version_id + copia campos
        db.execute(
            """UPDATE aia_health_call_scenarios
               SET current_version_id = %s,
                   label = %s, description = %s, system_prompt = %s,
                   voice = %s, allowed_tools = %s, post_call_actions = %s,
                   pre_call_context_sql = %s, max_duration_seconds = %s,
                   updated_at = NOW()
               WHERE id = %s""",
            (
                vid, version["label"], version["description"],
                version["system_prompt"], version["voice"],
                version["allowed_tools"], version["post_call_actions"],
                version["pre_call_context_sql"], version["max_duration_seconds"],
                sid,
            ),
        )
    else:
        row = db.fetch_one(
            """UPDATE aia_health_call_scenarios_versions
               SET status = %s
               WHERE id = %s
               RETURNING *""",
            (target, vid),
        )

    audit_log(action="rule.scenario.version.promote", payload={
        "scenario_id": sid, "version_id": vid, "target": target,
        "version_number": version["version_number"],
    })
    return jsonify({"status": "ok", "version": _serialize(row)})


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
    audit_log(action="communication.dial", payload={
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
                   s.started_at AS created_at, s.last_active_at,
                   s.closed_at,
                   EXTRACT(EPOCH FROM (
                       COALESCE(s.closed_at, s.last_active_at) - s.started_at
                   ))::int AS duration_seconds,
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
