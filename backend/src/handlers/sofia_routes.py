"""Proxy /api/sofia/* → sofia-service:5031.

Responsabilidades do proxy:
  • Validar JWT (já feito pelo before_request middleware).
  • Detectar persona via persona_detector.from_jwt(g.user).
  • Aplicar gate de availability (operadores fora do horário → resposta padrão).
  • Encaminhar request injetando persona no body (sofia-service confia).
  • Repassar response.

Endpoints expostos:
  POST /api/sofia/chat       — turno completo
  POST /api/sofia/greeting   — saudação inicial (sem LLM)
  GET  /api/sofia/sessions/<id> — histórico
  GET  /api/sofia/usage      — consumo do mês
  POST /api/sofia/tts        — TTS de texto

Notas:
  • Não logamos PHI no proxy (Sofia decide o que persistir, com audit).
  • Time window só bloqueia operadores (paciente/familiar 24/7).
"""
from __future__ import annotations

import os
from dataclasses import asdict

import httpx
from flask import Blueprint, g, jsonify, request

from src.services.jwt_utils import jwt_encode
from src.services.sofia import availability_service, persona_detector
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("sofia_proxy", __name__)


SOFIA_URL = os.getenv("SOFIA_SERVICE_URL", "http://sofia-service:5031").rstrip("/")
INTERNAL_KEY = os.getenv("SOFIA_INTERNAL_KEY", "")
DEFAULT_TIMEOUT = 60.0


def _persona_payload() -> dict:
    """Monta dict serializável da persona pra enviar pro sofia-service."""
    jwt_payload = getattr(g, "user", {}) or {}
    ctx = persona_detector.from_jwt(jwt_payload)
    payload = asdict(ctx)
    return payload


def _internal_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if INTERNAL_KEY:
        headers["X-Internal-Key"] = INTERNAL_KEY
    return headers


def _post_sofia(path: str, body: dict) -> tuple:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.post(f"{SOFIA_URL}{path}", json=body, headers=_internal_headers())
            return resp.json(), resp.status_code
    except httpx.HTTPError as exc:
        logger.error("sofia_proxy_http_error", path=path, error=str(exc))
        return {"status": "error", "reason": "sofia_unavailable"}, 503


def _get_sofia(path: str, params: dict | None = None) -> tuple:
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(f"{SOFIA_URL}{path}", params=params or {}, headers=_internal_headers())
            return resp.json(), resp.status_code
    except httpx.HTTPError as exc:
        logger.error("sofia_proxy_http_error", path=path, error=str(exc))
        return {"status": "error", "reason": "sofia_unavailable"}, 503


# ════════════════════════════════════════════════════
# POST /api/sofia/chat
# ════════════════════════════════════════════════════

@bp.post("/api/sofia/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"status": "error", "reason": "empty_message"}), 400

    persona_ctx = _persona_payload()

    # Time window guard pra operadores
    decision = availability_service.check(_to_namespace(persona_ctx))
    if not decision.allowed:
        return jsonify({
            "status": "ok",
            "blocked": True,
            "reason": decision.reason,
            "text": decision.message,
        })

    payload = {
        "message": message,
        "channel": body.get("channel") or "web",
        "persona": persona_ctx,
    }
    data, code = _post_sofia("/sofia/chat", payload)
    return jsonify(data), code


# ════════════════════════════════════════════════════
# POST /api/sofia/greeting
# ════════════════════════════════════════════════════

@bp.post("/api/sofia/greeting")
def greeting():
    persona_ctx = _persona_payload()
    payload = {"persona": persona_ctx}
    data, code = _post_sofia("/sofia/greeting", payload)
    return jsonify(data), code


# ════════════════════════════════════════════════════
# GET /api/sofia/sessions/<id>
# ════════════════════════════════════════════════════

@bp.get("/api/sofia/sessions/<session_id>")
def session_history(session_id: str):
    data, code = _get_sofia(f"/sofia/sessions/{session_id}")
    return jsonify(data), code


# ════════════════════════════════════════════════════
# GET /api/sofia/usage
# ════════════════════════════════════════════════════

@bp.get("/api/sofia/usage")
def usage():
    persona_ctx = _persona_payload()
    payload = {"persona": persona_ctx}
    data, code = _post_sofia("/sofia/usage", payload)
    return jsonify(data), code


# ════════════════════════════════════════════════════
# POST /api/sofia/tts
# ════════════════════════════════════════════════════

@bp.post("/api/sofia/voice/token")
def voice_token():
    """Emite JWT short-TTL pra browser conectar no sofia-voice WebSocket.

    Token contém persona já resolvida (server-trusted) + scope=sofia_voice
    + exp 5min. Browser usa em ?token=<JWT> na URL ws://sofia-voice.../voice/ws.

    Time window guard: mesmo do chat — operadores fora do horário não
    recebem token (Sofia voz fica indisponível pra eles).
    """
    persona_ctx = _persona_payload()
    if not persona_ctx.get("persona") or persona_ctx.get("persona") == "anonymous":
        return jsonify({"status": "error", "reason": "missing_persona"}), 401

    decision = availability_service.check(_to_namespace(persona_ctx))
    if not decision.allowed:
        return jsonify({
            "status": "error",
            "reason": decision.reason,
            "message": decision.message,
        }), 423

    secret = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or ""
    if not secret:
        return jsonify({"status": "error", "reason": "jwt_secret_not_configured"}), 500

    ttl = 300  # 5 minutos
    voice_token_jwt = jwt_encode(
        {
            "scope": "sofia_voice",
            "sub": persona_ctx.get("user_id") or "",
            "persona": persona_ctx,
        },
        secret,
        exp_seconds=ttl,
    )

    ws_host = os.getenv("SOFIA_VOICE_WS_HOST") or "sofia-voice.connectaia.com.br"
    ws_url = f"wss://{ws_host}/voice/ws?token={voice_token_jwt}"

    return jsonify({
        "status": "ok",
        "wsUrl": ws_url,
        "expiresInSeconds": ttl,
        "audio": {
            "inputSampleRate": 16000,
            "outputSampleRate": 24000,
            "format": "pcm_s16le",
        },
    })


@bp.post("/api/sofia/tts")
def tts():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"status": "error", "reason": "empty_text"}), 400
    payload = {
        "text": text,
        "voice": body.get("voice"),
        "persona": _persona_payload(),
    }
    data, code = _post_sofia("/sofia/tts", payload)
    return jsonify(data), code


# ────────────────────────────── helpers ──────────────────────────────

class _NS:
    """Mini-namespace pra availability_service (que espera obj com atributos)."""
    def __init__(self, d: dict):
        self.__dict__.update(d)
        self.is_operator = (d.get("persona") in {
            "medico", "enfermeiro", "admin_tenant", "super_admin",
        })


def _to_namespace(d: dict) -> _NS:
    return _NS(d)
