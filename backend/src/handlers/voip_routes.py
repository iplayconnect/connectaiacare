"""Handler VoIP — endpoints `/api/voip/*` usados por painel de alertas
e prontuário ("Ligar família").

HISTÓRICO: este módulo originalmente proxiava pro container `voip-service:5010`
(Asterisk + Deepgram + ElevenLabs) que existe na ConnectaIA original. Na
ConnectaIACare esse container NÃO está deployado — só temos `voice-call-service`
(Sofia + Grok Voice Realtime + PJSIP).

CORREÇÃO 2026-04-27: redireciona `/api/voip/call` pra usar voice-call-service.
Tradução automática:
    voip-service.{destination, client_id, mode, metadata}
        → voice-call-service.{destination, scenario_code, patient_id,
                              full_name, extra_context}

Fallback de scenario_code: env VOIP_LEGACY_DEFAULT_SCENARIO (default
'familiar_aviso_evento' — usado pelo painel de alertas).
"""
from __future__ import annotations

import os
import uuid

import httpx
from flask import Blueprint, jsonify, request

from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("voip", __name__)


# ══════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════

VOIP_SERVICE_URL = os.getenv("VOIP_SERVICE_URL", "http://voip-service:5010")
# Blueprint do voip-service está montado em /api/v1/voip (ver voip_app.py)
VOIP_API_PREFIX = os.getenv("VOIP_API_PREFIX", "/api/v1/voip")
VOIP_TENANT_ID = os.getenv("VOIP_TENANT_ID", "connectaiacare_demo")
VOIP_TIMEOUT_S = 15.0

# Backend de voz REAL nesta instância (voip-service legado não existe)
VOICE_CALL_SERVICE_URL = os.getenv(
    "VOICE_CALL_SERVICE_URL", "http://voice-call-service:5040"
)
VOIP_LEGACY_DEFAULT_SCENARIO = os.getenv(
    "VOIP_LEGACY_DEFAULT_SCENARIO", "familiar_aviso_evento"
)

_client = httpx.Client(timeout=VOIP_TIMEOUT_S)


def _resolve_patient_full_name(patient_id: str | None) -> str:
    """Busca full_name do paciente pra usar como saudação. Falha → 'amigo(a)'."""
    if not patient_id:
        return "amigo(a)"
    try:
        from src.services.postgres import get_postgres
        row = get_postgres().fetch_one(
            "SELECT full_name FROM aia_health_patients WHERE id = %s",
            (patient_id,),
        )
        return (row or {}).get("full_name") or "amigo(a)"
    except Exception:
        return "amigo(a)"


# ══════════════════════════════════════════════════════════════════
# POST /api/voip/call — inicia chamada
# ══════════════════════════════════════════════════════════════════

@bp.post("/voip/call")
def make_call():
    """Inicia chamada pra familiar via VoIP service.

    Body esperado (frontend):
        {
            "destination": "5511987654321",      # telefone (DDD + número)
            "patient_id": "uuid-opcional",        # pra rastreio
            "alert_id": "uuid-opcional",          # se veio do painel de alertas
            "care_event_id": "uuid-opcional",     # se veio de um care event
            "mode": "ai_pipeline" | "manual"     # default ai_pipeline
        }

    Retorna:
        {status: "ok", call_id: "...", call_status: "initiated"}
        OU erro HTTP 400/503/502
    """
    body = request.get_json(silent=True) or {}
    destination = (body.get("destination") or "").strip()
    if not destination:
        return jsonify({"status": "error", "message": "destination obrigatório"}), 400

    client_id = body.get("patient_id") or str(uuid.uuid4())
    mode = body.get("mode", "ai_pipeline")

    # Metadata pra contextualizar a ligação (cuidador, motivo, etc.)
    metadata = {
        "origin": "connectaiacare",
        "alert_id": body.get("alert_id"),
        "care_event_id": body.get("care_event_id"),
        "patient_id": body.get("patient_id"),
        "alert_summary": body.get("alert_summary"),
        "caller_name": body.get("caller_name", "Equipe ConnectaIACare"),
    }

    # ── Roteamento pra voice-call-service (Sofia + Grok) ──
    # voip-service legado não existe na ConnectaIACare. Traduz payload
    # legado pro formato do voice-call-service e usa scenario default.
    db = None
    scenario = None
    try:
        from src.services.postgres import get_postgres
        db = get_postgres()
        scenario = db.fetch_one(
            """SELECT id, code, label, system_prompt, voice, allowed_tools,
                      post_call_actions, max_duration_seconds
               FROM aia_health_call_scenarios
               WHERE code = %s AND active = TRUE LIMIT 1""",
            (VOIP_LEGACY_DEFAULT_SCENARIO,),
        )
    except Exception as exc:
        logger.error("voip_scenario_lookup_failed", error=str(exc))

    if not scenario:
        return jsonify({
            "status": "error",
            "message": (
                f"Cenário default '{VOIP_LEGACY_DEFAULT_SCENARIO}' não "
                "configurado. Configure cenários em /admin/cenarios-sofia "
                "ou ajuste env VOIP_LEGACY_DEFAULT_SCENARIO."
            ),
            "reason": "no_scenario",
        }), 503

    full_name = body.get("caller_name") or _resolve_patient_full_name(
        body.get("patient_id")
    )

    voicecall_payload = {
        "destination": destination,
        "scenario_id": str(scenario["id"]),
        "scenario_code": scenario["code"],
        "scenario_system_prompt": scenario.get("system_prompt"),
        "scenario_voice": scenario.get("voice") or "ara",
        "scenario_allowed_tools": scenario.get("allowed_tools") or [],
        "patient_id": body.get("patient_id"),
        "tenant_id": VOIP_TENANT_ID,
        "full_name": full_name,
        "extra_context": {
            "scenario_label": scenario.get("label"),
            "alert_id": metadata.get("alert_id"),
            "care_event_id": metadata.get("care_event_id"),
            "alert_summary": metadata.get("alert_summary"),
            "trigger": "voip_legacy_alerts",
        },
    }

    try:
        resp = _client.post(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/dial",
            json=voicecall_payload,
            timeout=VOIP_TIMEOUT_S,
        )
    except httpx.RequestError as exc:
        logger.error(
            "voip_call_network_error",
            error=str(exc), destination=destination[-4:],
        )
        return jsonify({
            "status": "error",
            "message": "Sofia VoIP indisponível no momento.",
            "reason": "network",
        }), 502

    if resp.status_code >= 400:
        body_text = resp.text[:200] if resp.text else ""
        logger.warning(
            "voip_call_rejected",
            status=resp.status_code, body=body_text,
            destination=destination[-4:],
        )
        return jsonify({
            "status": "error",
            "message": f"Sofia rejeitou a chamada (HTTP {resp.status_code})",
            "reason": "rejected",
            "detail": body_text,
        }), 502

    voip_data = resp.json()
    logger.info(
        "voip_call_initiated",
        call_id=voip_data.get("call_id"),
        destination=destination[-4:],
        mode=mode,
        alert_id=metadata.get("alert_id"),
        scenario=scenario["code"],
    )
    return jsonify({
        "status": "ok",
        "call_id": voip_data.get("call_id"),
        "call_status": "initiated",
        "scenario_code": scenario["code"],
        "metadata": voip_data,
    }), 200


# ══════════════════════════════════════════════════════════════════
# GET /api/voip/call/<call_id>/status
# ══════════════════════════════════════════════════════════════════

@bp.get("/voip/call/<call_id>/status")
def call_status(call_id: str):
    """Consulta status de uma chamada em andamento (via voice-call-service)."""
    try:
        resp = _client.get(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/calls", timeout=5.0,
        )
    except httpx.RequestError as exc:
        logger.debug("voip_status_network_error", error=str(exc))
        return jsonify({"status": "error", "message": "Sofia VoIP indisponível"}), 502

    if resp.status_code >= 400:
        return jsonify({
            "status": "error",
            "message": f"Sofia retornou {resp.status_code}",
        }), 502

    data = resp.json() or {}
    active_calls = data.get("calls") or []
    is_active = call_id in active_calls
    return jsonify({
        "status": "ok",
        "call_id": call_id,
        "call_status": "active" if is_active else "ended",
        "active": is_active,
    }), 200


# ══════════════════════════════════════════════════════════════════
# POST /api/voip/call/<call_id>/hangup
# ══════════════════════════════════════════════════════════════════

@bp.post("/voip/call/<call_id>/hangup")
def hangup_call(call_id: str):
    """Encerra chamada em andamento (via voice-call-service)."""
    try:
        resp = _client.post(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/hangup",
            json={"call_id": call_id}, timeout=10.0,
        )
    except httpx.RequestError as exc:
        logger.debug("voip_hangup_network_error", error=str(exc))
        return jsonify({"status": "error", "message": "Sofia VoIP indisponível"}), 502

    if resp.status_code >= 400:
        return jsonify({"status": "error", "message": f"Sofia retornou {resp.status_code}"}), 502

    return jsonify({"status": "ok", "call_id": call_id, "call_status": "ended"}), 200


# ══════════════════════════════════════════════════════════════════
# GET /api/voip/status — saúde do serviço (útil pro frontend detectar disponibilidade)
# ══════════════════════════════════════════════════════════════════

@bp.get("/voip/status")
def voip_health():
    """Checa se voice-call-service (Sofia) está online + metadata."""
    try:
        resp = _client.get(f"{VOICE_CALL_SERVICE_URL}/health", timeout=3.0)
    except httpx.RequestError:
        return jsonify({"available": False, "reason": "unreachable"}), 200

    if resp.status_code != 200:
        return jsonify({"available": False, "reason": f"http_{resp.status_code}"}), 200

    data = resp.json() or {}
    return jsonify({
        "available": True,
        "sip_registered": data.get("sip_registered", True),
        "active_calls": data.get("active_calls", 0),
        "tenant_id": VOIP_TENANT_ID,
        "backend": "voice-call-service",
    }), 200


# ══════════════════════════════════════════════════════════════════
# voice-call-service — ligações via Sofia (Grok Realtime)
# Container DEDICADO (não confundir com o voip-service legado acima
# que usa Deepgram+ElevenLabs). Esse fluxo dá Sofia full: persona +
# memory + tools.
# ══════════════════════════════════════════════════════════════════

VOICE_CALL_SERVICE_URL = os.getenv(
    "VOICE_CALL_SERVICE_URL", "http://voice-call-service:5040"
)


@bp.post("/voice-call/dial")
def voice_call_dial():
    """Origina ligação Sofia↔paciente/familiar via Grok.

    Body:
        destination: "5551996161700" (E.164 sem +)
        persona: medico|enfermeiro|cuidador_pro|familia|paciente_b2c
        user_id: uuid (caller, pra carregar memória cross-session)
        full_name: "Dr. Alexandre"
        patient_id: uuid (opcional — paciente alvo da call)
        tenant_id: opcional (default connectaiacare_demo)
    """
    body = request.get_json(silent=True) or {}
    if not body.get("destination"):
        return jsonify({"status": "error", "reason": "destination_required"}), 400
    payload = {
        "destination": body["destination"],
        "persona": body.get("persona") or "medico",
        "user_id": body.get("user_id"),
        "full_name": body.get("full_name"),
        "patient_id": body.get("patient_id"),
        "tenant_id": body.get("tenant_id") or VOIP_TENANT_ID,
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
        return jsonify({"status": "error", "reason": f"upstream_{resp.status_code}",
                        "detail": resp.text[:300]}), 502
    return jsonify(resp.json()), 200


@bp.post("/voice-call/hangup")
def voice_call_hangup():
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


@bp.get("/voice-call/health")
def voice_call_health():
    try:
        resp = _client.get(f"{VOICE_CALL_SERVICE_URL}/health", timeout=3.0)
        return jsonify(resp.json()), resp.status_code
    except httpx.RequestError:
        return jsonify({"available": False, "reason": "unreachable"}), 200
