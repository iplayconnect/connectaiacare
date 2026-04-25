"""Grok Voice session — proxy bidirecional Browser ↔ xAI Realtime API.

Substitui o VoiceSession (Gemini Live) que estava instável. A xAI expõe
uma API Realtime compatível com OpenAI:

    wss://api.x.ai/v1/realtime?model=grok-voice-think-fast-1.0

Protocolo wire (events JSON sobre WS), cliente envia:
    session.update                  → config inicial (instructions/voice/tools)
    input_audio_buffer.append       → chunks de áudio do mic (base64 pcm16)
    input_audio_buffer.commit       → fim da turn (modo VAD desligado)
    response.create                 → pede resposta agora
    response.cancel                 → interrupt
    conversation.item.create        → input texto OU tool response

Servidor envia:
    session.created/updated
    response.audio.delta            → chunk de áudio Sofia (base64)
    response.audio.done
    response.audio_transcript.delta/done
    conversation.item.input_audio_transcription.completed
    response.function_call_arguments.done
    response.done
    error
    input_audio_buffer.speech_started/stopped (server VAD)

Mantém o MESMO contrato externo do VoiceSession (Gemini): start, feed_audio,
feed_text, interrupt, close. Eventos enviados pro browser também idênticos
({type:ready/audio/transcript/tool_call/turn_complete/interrupted/error}) —
voice_app.py não precisa mudar.

Áudio:
    Browser → Server (mic): PCM 16-bit 16kHz mono LE.
    Server → Grok: PCM 16-bit 24kHz (upsample com audioop).
    Grok → Server: PCM 16-bit 24kHz.
    Server → Browser: PCM 16-bit 24kHz (browser já reproduz nessa taxa).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

import websockets

from src import persistence, tools as tools_module
from src.orchestrator import get_agent_for_persona

logger = logging.getLogger(__name__)

DEFAULT_GROK_MODEL = (
    os.getenv("SOFIA_GROK_VOICE_MODEL") or "grok-voice-think-fast-1.0"
)
# Vozes disponíveis no Grok Voice (verificar docs xAI quando GA — começamos
# com 'ara' que tem rendering pt-BR razoável segundo testes do user).
DEFAULT_GROK_VOICE = os.getenv("SOFIA_GROK_VOICE") or "ara"
GROK_REALTIME_URL = (
    os.getenv("XAI_REALTIME_URL") or "wss://api.x.ai/v1/realtime"
)
# Sample rates: browser captura/reproduz a 16k e 24k respectivamente; o
# OpenAI Realtime / Grok pcm16 default é 24k em ambas as direções.
INPUT_RATE_BROWSER = 16000
GROK_AUDIO_RATE = 24000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _upsample_16k_to_24k(pcm16_bytes: bytes) -> bytes:
    """Resample PCM 16-bit mono 16kHz → 24kHz usando audioop (stdlib 3.12)."""
    if not pcm16_bytes:
        return pcm16_bytes
    try:
        import audioop
        # ratecv: (src, sampwidth, channels, inrate, outrate, state)
        out, _ = audioop.ratecv(
            pcm16_bytes, 2, 1, INPUT_RATE_BROWSER, GROK_AUDIO_RATE, None,
        )
        return out
    except Exception:
        # Em Python 3.13+ audioop foi removido. Fallback simplório: nearest
        # neighbor 1.5× (não temos numpy garantido aqui).
        # 16k → 24k = ratio 1.5. Cada 2 amostras viram 3.
        sample_count = len(pcm16_bytes) // 2
        if sample_count == 0:
            return pcm16_bytes
        # tenta numpy se disponível (mais limpo)
        try:
            import numpy as np
            src = np.frombuffer(pcm16_bytes, dtype="<i2")
            n_out = int(round(len(src) * GROK_AUDIO_RATE / INPUT_RATE_BROWSER))
            x_old = np.arange(len(src))
            x_new = np.linspace(0, len(src) - 1, n_out)
            interp = np.interp(x_new, x_old, src).astype("<i2")
            return interp.tobytes()
        except Exception:
            return pcm16_bytes  # último recurso: deixa Grok lidar


class GrokVoiceSession:
    """Sessão WebSocket bidirecional com Grok Voice. Mesma interface do
    VoiceSession (Gemini)."""

    def __init__(self, persona_ctx: dict, send_to_browser):
        self.persona_ctx = persona_ctx
        self.persona = persona_ctx.get("persona") or "anonymous"
        self.tenant_id = persona_ctx.get("tenant_id") or "connectaiacare_demo"
        self.send_to_browser = send_to_browser
        self.session_id: str | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._receive_task: asyncio.Task | None = None
        self._closed = False
        self._tool_calls = 0
        # Acumuladores de transcript pra persistência (delta → completo)
        self._user_transcript_buffer = ""
        self._assistant_transcript_buffer = ""
        # Args parciais por call_id (Grok envia em deltas)
        self._fc_args_buf: dict[str, str] = {}
        self._fc_name_by_call: dict[str, str] = {}
        self._fc_response_id_by_call: dict[str, str] = {}

    # ─────────────── tools (Gemini → OpenAI/Grok schema) ───────────────

    def _build_tools(self) -> list[dict]:
        """Converte tools_for_persona() pro formato OpenAI Realtime."""
        specs = tools_module.tools_for_persona(self.persona)
        out = []
        for s in specs:
            params = s.get("parameters") or {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "name": s["name"],
                "description": s["description"],
                "parameters": params,
            })
        return out

    # ─────────────── lifecycle ───────────────

    async def start(self) -> None:
        api_key = os.getenv("XAI_API_KEY")
        if not api_key:
            raise RuntimeError("XAI_API_KEY required for Grok voice")

        # DB session (mesma row de chat texto se já existir)
        session_row = persistence.get_or_create_session(
            tenant_id=self.tenant_id,
            persona=self.persona,
            user_id=self.persona_ctx.get("user_id"),
            phone=self.persona_ctx.get("phone"),
            caregiver_id=self.persona_ctx.get("caregiver_id"),
            patient_id=self.persona_ctx.get("patient_id"),
            channel="voice",
        )
        self.session_id = str(session_row["id"])

        url = f"{GROK_REALTIME_URL}?model={DEFAULT_GROK_MODEL}"
        # websockets 12+ usa "additional_headers" via hook, mas a API direta
        # suporta lista de tuplas via extra_headers.
        self._ws = await websockets.connect(
            url,
            additional_headers=[("Authorization", f"Bearer {api_key}")],
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        )

        # Configura sessão: persona prompt + voice + tools + audio formats.
        AgentClass = get_agent_for_persona(self.persona)
        instructions = AgentClass.system_prompt(self.persona_ctx)

        first_name = (
            self.persona_ctx.get("full_name") or "amigo(a)"
        ).split(" ")[0]
        instructions += (
            f"\n\n# CONTEXTO IMEDIATO\nVocê está em uma chamada de voz ao vivo "
            f"com {first_name}. Responda em português do Brasil, em frases "
            "curtas e tom conversacional. Não fale 'olá' duas vezes."
        )

        config = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": instructions,
                "voice": DEFAULT_GROK_VOICE,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                # Server-side VAD: Grok decide quando o user terminou de
                # falar e dispara response.create automaticamente.
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600,
                },
                "input_audio_transcription": {"model": "whisper-1"},
                "tools": self._build_tools(),
                "tool_choice": "auto",
                "temperature": 0.7,
            },
        }
        await self._ws.send(json.dumps(config))

        self._receive_task = asyncio.create_task(self._receive_loop())

        logger.info(
            "grok_voice_session_started session_id=%s persona=%s model=%s",
            self.session_id, self.persona, DEFAULT_GROK_MODEL,
        )
        await self.send_to_browser({
            "type": "ready",
            "sessionId": self.session_id,
            "model": DEFAULT_GROK_MODEL,
        })

        # Kickoff: Sofia inicia falando. Cria item de sistema e dispara response.
        kickoff_text = (
            f"[INÍCIO DA CHAMADA] Cumprimente {first_name} pelo primeiro "
            "nome de forma calorosa e curta (1 frase) e pergunte como pode "
            "ajudar agora. Não diga 'olá' duas vezes nem se apresente como Sofia."
        )
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": kickoff_text}],
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def feed_audio(self, pcm_bytes: bytes) -> None:
        """Browser enviou um chunk PCM 16kHz mono. Resample → 24k → Grok."""
        if self._closed or not self._ws:
            return
        upsampled = _upsample_16k_to_24k(pcm_bytes)
        if not upsampled:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": _b64(upsampled),
            }))
        except Exception as exc:
            logger.warning("grok_feed_failed: %s", exc)

    async def feed_text(self, text: str) -> None:
        if self._closed or not self._ws:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }))
            await self._ws.send(json.dumps({"type": "response.create"}))
        except Exception as exc:
            logger.warning("grok_feed_text_failed: %s", exc)

    async def interrupt(self) -> None:
        """User interrompeu Sofia. Cancela a resposta em curso."""
        if self._closed or not self._ws:
            return
        try:
            await self._ws.send(json.dumps({"type": "response.cancel"}))
        except Exception as exc:
            logger.warning("grok_interrupt_failed: %s", exc)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

        persistence.record_usage(
            tenant_id=self.tenant_id,
            user_id=self.persona_ctx.get("user_id"),
            phone=self.persona_ctx.get("phone"),
            plan_sku=self.persona_ctx.get("plan_sku"),
            tokens_in=0,  # Grok Realtime não retorna usage tokens em tempo real
            tokens_out=0,
            tool_calls=self._tool_calls,
            messages=1,
            audio_seconds=0,
        )
        persistence.audit(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            user_id=self.persona_ctx.get("user_id"),
            persona=self.persona,
            event_type="voice_session_closed",
            decision="ok",
            details={
                "tool_calls": self._tool_calls,
                "provider": "grok",
                "model": DEFAULT_GROK_MODEL,
            },
        )

    # ─────────────── receive loop ───────────────

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                await self._handle_grok_event(msg)
        except asyncio.CancelledError:
            return
        except websockets.ConnectionClosed as exc:
            logger.info("grok_ws_closed code=%s reason=%s", exc.code, exc.reason)
            await self.send_to_browser({
                "type": "error",
                "detail": f"upstream_closed:{exc.code}",
            })
        except Exception as exc:
            logger.exception("grok_receive_error session_id=%s", self.session_id)
            await self.send_to_browser({"type": "error", "detail": str(exc)})

    async def _handle_grok_event(self, msg: dict) -> None:
        etype = msg.get("type") or ""

        # ── Áudio output (chunks PCM 24kHz base64) ──
        # xAI usa "response.output_audio.delta"; OpenAI Realtime usa
        # "response.audio.delta". Aceitamos ambos pra robustez.
        if etype in ("response.output_audio.delta", "response.audio.delta"):
            delta = msg.get("delta")
            if delta:
                await self.send_to_browser({"type": "audio", "data": delta})
            return

        if etype in ("response.output_audio.done", "response.audio.done"):
            return

        # ── Transcript Sofia (output) ──
        if etype in (
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
        ):
            chunk = msg.get("delta") or ""
            if chunk:
                self._assistant_transcript_buffer += chunk
                await self.send_to_browser({
                    "type": "transcript",
                    "role": "assistant",
                    "text": chunk,
                })
            return

        if etype in (
            "response.output_audio_transcript.done",
            "response.audio_transcript.done",
        ):
            full = msg.get("transcript") or self._assistant_transcript_buffer
            self._assistant_transcript_buffer = ""
            if full:
                persistence.append_message(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="assistant",
                    content=full,
                    model=DEFAULT_GROK_MODEL,
                    metadata={"channel": "voice", "provider": "grok"},
                )
            return

        # ── Transcript user (input STT pelo Grok/Whisper) ──
        if etype == "conversation.item.input_audio_transcription.completed":
            full = msg.get("transcript") or ""
            if full:
                await self.send_to_browser({
                    "type": "transcript",
                    "role": "user",
                    "text": full,
                })
                persistence.append_message(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="user",
                    content=full,
                    metadata={"channel": "voice", "provider": "grok"},
                )
            return

        # ── VAD events ──
        if etype == "input_audio_buffer.speech_started":
            # User começou a falar — interrompe Sofia se ela estiver falando
            await self.send_to_browser({"type": "interrupted"})
            return

        # ── Turn complete ──
        if etype == "response.done":
            await self.send_to_browser({"type": "turn_complete"})
            return

        # ── Tool calls (function_call_arguments.delta + .done) ──
        if etype == "response.function_call_arguments.delta":
            call_id = msg.get("call_id") or msg.get("response_id") or ""
            self._fc_args_buf[call_id] = (
                self._fc_args_buf.get(call_id, "") + (msg.get("delta") or "")
            )
            return

        if etype == "response.function_call_arguments.done":
            call_id = msg.get("call_id") or ""
            name = msg.get("name") or self._fc_name_by_call.get(call_id) or ""
            args_str = (
                msg.get("arguments")
                or self._fc_args_buf.pop(call_id, "")
                or "{}"
            )
            try:
                args = json.loads(args_str) if args_str else {}
            except Exception:
                args = {}
            if name:
                await self._execute_tool_call(call_id, name, args)
            return

        # Alguns servidores enviam o item completo via response.output_item.added
        if etype == "response.output_item.added":
            item = msg.get("item") or {}
            if item.get("type") == "function_call":
                call_id = item.get("call_id") or item.get("id") or ""
                name = item.get("name") or ""
                if call_id and name:
                    self._fc_name_by_call[call_id] = name
            return

        # ── Erros do upstream ──
        if etype == "error":
            err = msg.get("error") or {}
            detail = err.get("message") or err.get("type") or "grok_error"
            logger.warning("grok_upstream_error: %s", detail)
            await self.send_to_browser({
                "type": "error",
                "detail": f"grok:{detail}",
            })
            return

        # ── session.created/updated, response.created etc — silenciosos ──
        # (logamos só em DEBUG)
        logger.debug("grok_event_ignored: %s", etype)

    async def _execute_tool_call(self, call_id: str, name: str, args: dict) -> None:
        self._tool_calls += 1
        logger.info(
            "grok_voice_tool_call name=%s session_id=%s",
            name, self.session_id,
        )

        output = tools_module.execute_tool(name, args, self.persona_ctx)
        persistence.append_message(
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            role="tool",
            content=name,
            tool_name=name,
            tool_input=args,
            tool_output=output,
            model=DEFAULT_GROK_MODEL,
        )
        persistence.audit(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            user_id=self.persona_ctx.get("user_id"),
            persona=self.persona,
            event_type="tool_call",
            decision="allow" if output.get("ok") else "tool_error",
            details={
                "tool": name, "args": args,
                "ok": output.get("ok"), "channel": "voice",
                "provider": "grok",
            },
        )
        await self.send_to_browser({
            "type": "tool_call",
            "name": name,
            "ok": bool(output.get("ok")),
        })

        # Devolve o output via conversation.item.create com type=function_call_output
        try:
            await self._ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output),
                },
            }))
            # Pede pra Sofia continuar a resposta agora que tem o resultado
            await self._ws.send(json.dumps({"type": "response.create"}))
        except Exception as exc:
            logger.warning("grok_tool_response_failed: %s", exc)
