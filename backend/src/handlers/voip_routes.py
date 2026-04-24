"""Handler VoIP — proxy pro container voip-service (compartilhado com ConnectaIA).

O voip-service roda em container separado (network infra_proxy) com Asterisk +
Deepgram STT + ElevenLabs TTS. Expõe API HTTP em :5010:

    POST /call        — inicia chamada (destination, client_id, mode, tenant_id)
    POST /hangup      — encerra chamada (call_id)
    GET  /status      — chamadas ativas
    GET  /call-status/<call_id>
    GET  /health

Este módulo expõe 2 endpoints no backend ConnectaIACare que proxyam pro VoIP
com tenant padrão 'connectaiacare_demo' + autenticação de frontend preservada.

Usado pelo painel de alertas (/alertas) e por "Ligar família" no prontuário.
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
VOIP_TENANT_ID = os.getenv("VOIP_TENANT_ID", "connectaiacare_demo")
VOIP_TIMEOUT_S = 15.0

_client = httpx.Client(timeout=VOIP_TIMEOUT_S)


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

    payload = {
        "destination": destination,
        "client_id": client_id,
        "mode": mode,
        "tenant_id": VOIP_TENANT_ID,
        "metadata": {k: v for k, v in metadata.items() if v is not None},
    }

    try:
        resp = _client.post(f"{VOIP_SERVICE_URL}/call", json=payload)
    except httpx.RequestError as exc:
        logger.error("voip_call_network_error", error=str(exc), destination=destination[-4:])
        return jsonify({
            "status": "error",
            "message": "VoIP indisponível no momento. Tente novamente em alguns segundos.",
            "reason": "network",
        }), 502

    if resp.status_code >= 400:
        body_text = resp.text[:200] if resp.text else ""
        logger.warning(
            "voip_call_rejected",
            status=resp.status_code,
            body=body_text,
            destination=destination[-4:],
        )
        return jsonify({
            "status": "error",
            "message": f"VoIP rejeitou a chamada (HTTP {resp.status_code})",
            "reason": "rejected",
            "detail": body_text,
        }), 502

    voip_data = resp.json()
    logger.info(
        "voip_call_initiated",
        call_id=voip_data.get("call_id"),
        destination=destination[-4:],  # log só últimos 4 dígitos
        mode=mode,
        alert_id=metadata.get("alert_id"),
    )
    return jsonify({
        "status": "ok",
        "call_id": voip_data.get("call_id"),
        "call_status": voip_data.get("call_status", "initiated"),
        "metadata": voip_data,
    }), 200


# ══════════════════════════════════════════════════════════════════
# GET /api/voip/call/<call_id>/status
# ══════════════════════════════════════════════════════════════════

@bp.get("/voip/call/<call_id>/status")
def call_status(call_id: str):
    """Consulta status de uma chamada em andamento."""
    try:
        resp = _client.get(f"{VOIP_SERVICE_URL}/call-status/{call_id}")
    except httpx.RequestError as exc:
        logger.debug("voip_status_network_error", error=str(exc))
        return jsonify({"status": "error", "message": "VoIP indisponível"}), 502

    if resp.status_code == 404:
        return jsonify({"status": "not_found"}), 404
    if resp.status_code >= 400:
        return jsonify({
            "status": "error",
            "message": f"VoIP retornou {resp.status_code}",
        }), 502

    data = resp.json()
    return jsonify({
        "status": "ok",
        "call_id": call_id,
        **data,
    }), 200


# ══════════════════════════════════════════════════════════════════
# POST /api/voip/call/<call_id>/hangup
# ══════════════════════════════════════════════════════════════════

@bp.post("/voip/call/<call_id>/hangup")
def hangup_call(call_id: str):
    """Encerra chamada em andamento."""
    try:
        resp = _client.post(f"{VOIP_SERVICE_URL}/hangup", json={"call_id": call_id})
    except httpx.RequestError as exc:
        logger.debug("voip_hangup_network_error", error=str(exc))
        return jsonify({"status": "error", "message": "VoIP indisponível"}), 502

    if resp.status_code >= 400:
        return jsonify({"status": "error", "message": f"VoIP retornou {resp.status_code}"}), 502

    return jsonify({"status": "ok", "call_id": call_id, "call_status": "ended"}), 200


# ══════════════════════════════════════════════════════════════════
# GET /api/voip/status — saúde do serviço (útil pro frontend detectar disponibilidade)
# ══════════════════════════════════════════════════════════════════

@bp.get("/voip/status")
def voip_health():
    """Checa se voip-service está online + metadata pro frontend."""
    try:
        resp = _client.get(f"{VOIP_SERVICE_URL}/health", timeout=3.0)
    except httpx.RequestError:
        return jsonify({"available": False, "reason": "unreachable"}), 200

    if resp.status_code != 200:
        return jsonify({"available": False, "reason": f"http_{resp.status_code}"}), 200

    data = resp.json()
    return jsonify({
        "available": True,
        "sip_registered": data.get("sip_registered", False),
        "active_calls": data.get("active_calls", 0),
        "tenant_id": VOIP_TENANT_ID,
    }), 200
