"""Sofia voice service — ASGI WebSocket bidirecional (porta 5032).

Browser conecta DIRETO via Traefik (sofia-voice.connectaia.com.br) usando
um JWT short-TTL emitido pelo backend api (rota /api/sofia/voice/token).

Protocolo (JSON sobre WebSocket):

  Client → Server (após token validado):
    {"type": "start"}                                início da sessão
    {"type": "audio", "data": "<base64 PCM 16kHz>"}  chunk de áudio do mic
    {"type": "text",  "text": "..."}                 input texto opcional
    {"type": "interrupt"}                            user interrompeu
    {"type": "close"}                                fim

  Server → Client:
    {"type": "ready", "sessionId": ..., "model": ...}
    {"type": "audio", "data": "<base64 PCM 24kHz>"}  chunk áudio Sofia
    {"type": "transcript", "role": "user|assistant", "text": "..."}
    {"type": "tool_call", "name": "...", "ok": true|false}
    {"type": "turn_complete"}
    {"type": "interrupted"}
    {"type": "error", "detail": "..."}

Auth: query param ?token=<JWT> assinado pelo api (5min TTL). Payload do
JWT contém a persona já resolvida — voice_app não consulta o DB pra
validar persona, confia no token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.voice_session import VoiceSession


# JWT inline (HS256) compatível com api/src/services/jwt_utils.py — voice
# precisa do mesmo segredo (JWT_SECRET) que o api usa pra emitir tokens.
def _b64url_decode(data: str) -> bytes:
    padding = "=" * ((4 - (len(data) % 4)) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _verify_voice_token(token: str) -> dict | None:
    """Valida JWT HS256 emitido pelo api. Retorna payload se OK, None senão."""
    secret = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or ""
    if not secret or not token or token.count(".") != 2:
        return None
    header_b64, payload_b64, sig_b64 = token.split(".", 2)
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_b64):
        return None
    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("scope") != "sofia_voice":
        return None
    return payload

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sofia-voice")

app = FastAPI(title="Sofia Care — Voice Live")

# Voice é interno (chamado só pelo proxy api). Sem CORS amplo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

INTERNAL_KEY = os.getenv("SOFIA_INTERNAL_KEY", "")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sofia-voice", "version": "0.1.0"}


@app.websocket("/voice/ws")
async def voice_ws(ws: WebSocket):
    # Auth: ?token=<JWT> emitido pelo api (scope=sofia_voice, 5min TTL).
    # JWT carrega a persona já resolvida — confiamos no api.
    token = ws.query_params.get("token", "")
    payload = _verify_voice_token(token)
    if not payload:
        await ws.close(code=1008)
        return

    persona_ctx_from_token = payload.get("persona") or {}
    if not persona_ctx_from_token.get("persona"):
        await ws.close(code=1008)
        return

    await ws.accept()
    logger.info(
        "voice_ws_connected",
        extra={
            "persona": persona_ctx_from_token.get("persona"),
            "user_id": persona_ctx_from_token.get("user_id"),
        },
    )

    voice: VoiceSession | None = None

    async def send_to_browser(payload: dict) -> None:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception as exc:
            logger.warning("voice_ws_send_failed", extra={"error": str(exc)})

    try:
        while True:
            msg_text = await ws.receive_text()
            try:
                msg = json.loads(msg_text)
            except json.JSONDecodeError:
                await send_to_browser({"type": "error", "detail": "bad_json"})
                continue

            mtype = msg.get("type")

            if mtype == "start":
                if voice is not None:
                    await send_to_browser({"type": "error", "detail": "already_started"})
                    continue
                # Persona vem do JWT (server-trusted), não do client message.
                voice = VoiceSession(persona_ctx_from_token, send_to_browser)
                try:
                    await voice.start()
                except Exception as exc:
                    logger.exception("voice_start_failed")
                    await send_to_browser({"type": "error", "detail": f"start_failed: {exc}"})
                    voice = None
                continue

            if voice is None:
                await send_to_browser({"type": "error", "detail": "not_started"})
                continue

            if mtype == "audio":
                data_b64 = msg.get("data") or ""
                if data_b64:
                    try:
                        pcm = base64.b64decode(data_b64)
                        await voice.feed_audio(pcm)
                    except Exception as exc:
                        logger.warning("voice_decode_failed", extra={"error": str(exc)})
            elif mtype == "text":
                text = (msg.get("text") or "").strip()
                if text:
                    await voice.feed_text(text)
            elif mtype == "interrupt":
                await voice.interrupt()
            elif mtype == "close":
                break
            else:
                await send_to_browser({"type": "error", "detail": f"unknown_type:{mtype}"})

    except WebSocketDisconnect:
        logger.info("voice_ws_disconnected")
    except Exception:
        logger.exception("voice_ws_error")
    finally:
        if voice:
            try:
                await voice.close()
            except Exception:
                logger.exception("voice_close_failed")
        logger.info("voice_ws_closed")
