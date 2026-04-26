"""GrokCallSession — variante do GrokVoiceSession (sofia-service) adaptada
pra fonte de áudio SIP (já em PCM linear, taxa nativa Grok 24k).

Reusa o protocolo OpenAI Realtime que já validamos com sofia-service.
Diferenças do irmão browser:
  - Áudio in/out já chega em 24k (audio_bridge converte 8k↔24k antes/depois)
  - Saída vai pra `on_audio_chunk` callback, não pra browser ws
  - System prompt + memória vem do PG (mesmas tabelas que sofia-service usa)
  - Tools chamadas via DB direto (replica execute_tool minimal aqui pra
    evitar acoplamento HTTP — primeira fase só com 3 tools essenciais)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Any, Awaitable, Callable

import websockets

from config import Config

logger = logging.getLogger("grok_call_session")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# Callback type: chamado pelo session quando áudio out chega de Grok.
# A camada SIP recebe e injeta no media port do PJSIP.
AudioOutCallback = Callable[[bytes], Awaitable[None]]


class GrokCallSession:
    """Conecta a uma sessão Grok Realtime, recebe áudio do SIP via
    `feed_audio_24k`, devolve áudio pra SIP via callback `on_audio_chunk_24k`.
    """

    def __init__(
        self,
        *,
        persona_ctx: dict,
        on_audio_chunk_24k: AudioOutCallback,
        on_call_metric: Callable[[dict], None] | None = None,
    ):
        self.persona_ctx = persona_ctx
        self.persona = persona_ctx.get("persona") or "anonymous"
        self.tenant_id = persona_ctx.get("tenant_id") or Config.DEFAULT_TENANT
        self.on_audio_chunk_24k = on_audio_chunk_24k
        self.on_call_metric = on_call_metric or (lambda _: None)

        self.session_id: str | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._receive_task: asyncio.Task | None = None
        self._closed = False
        self._tool_calls = 0

    # ─── Lifecycle ───

    async def start(self) -> None:
        if not Config.XAI_API_KEY:
            raise RuntimeError("XAI_API_KEY required")

        # Cria session row no PG (importa lazy pra evitar cycle no boot)
        from services.persistence import get_or_create_session, build_persona_prompt
        session_row = get_or_create_session(
            tenant_id=self.tenant_id,
            persona=self.persona,
            user_id=self.persona_ctx.get("user_id"),
            phone=self.persona_ctx.get("phone"),
            patient_id=self.persona_ctx.get("patient_id"),
            channel="voice_call",
        )
        self.session_id = str(session_row["id"])
        instructions = build_persona_prompt(self.persona_ctx)

        url = f"{Config.GROK_REALTIME_URL}?model={Config.GROK_VOICE_MODEL}"
        # websockets 12.x: tenta additional_headers (novo) e cai pra
        # extra_headers (legacy) se a versão instalada não aceitar.
        connect_kwargs = dict(
            max_size=None, ping_interval=20, ping_timeout=20,
        )
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=[("Authorization", f"Bearer {Config.XAI_API_KEY}")],
                **connect_kwargs,
            )
        except TypeError:
            self._ws = await websockets.connect(
                url,
                extra_headers=[("Authorization", f"Bearer {Config.XAI_API_KEY}")],
                **connect_kwargs,
            )

        # session.update — mesma config validada com browser
        first_name = (
            self.persona_ctx.get("full_name") or "amigo(a)"
        ).split(" ")[0]
        instructions += (
            f"\n\n# CONTEXTO IMEDIATO\nVocê está em uma LIGAÇÃO TELEFÔNICA "
            f"ao vivo com {first_name}. Áudio é do telefone — mantenha "
            "frases CURTAS, tom natural, paciência pra silêncios. Não fale "
            "'olá' duas vezes."
        )

        await self._ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": instructions,
                "voice": Config.GROK_VOICE_NAME,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700,  # +100ms vs browser pq lag SIP
                },
                "input_audio_transcription": {"model": "whisper-1"},
                "tools": _build_tools_for_call(self.persona),
                "tool_choice": "auto",
                "temperature": 0.7,
            },
        }))

        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info(
            "grok_call_started session_id=%s persona=%s model=%s",
            self.session_id, self.persona, Config.GROK_VOICE_MODEL,
        )

        # Kickoff: Sofia inicia a fala assim que a chamada conecta
        kickoff = (
            f"[INÍCIO DA LIGAÇÃO TELEFÔNICA] Cumprimente {first_name} pelo "
            "primeiro nome com tom caloroso e curto (1 frase). Diga que é a "
            "Sofia da ConnectaIACare. Em seguida pergunte como pode ajudar."
        )
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": kickoff}],
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def feed_audio_24k(self, pcm16_24k: bytes) -> None:
        """Camada SIP empurra cada frame de áudio (já upsampleado pra 24k)."""
        if self._closed or not self._ws or not pcm16_24k:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": _b64(pcm16_24k),
            }))
        except Exception as exc:
            logger.warning("grok_call_feed_failed: %s", exc)

    async def interrupt(self) -> None:
        if self._closed or not self._ws:
            return
        try:
            await self._ws.send(json.dumps({"type": "response.cancel"}))
        except Exception:
            pass

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

        # Memória — força extração no fim da chamada (replica
        # comportamento do GrokVoiceSession.close() do sofia-service)
        try:
            from services.persistence import update_user_memory_force
            update_user_memory_force(self.persona_ctx.get("user_id"))
        except Exception as exc:
            logger.warning("close_memory_update_failed: %s", exc)

    # ─── Receive loop ───

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                await self._handle_event(msg)
        except asyncio.CancelledError:
            return
        except websockets.ConnectionClosed as exc:
            logger.info("grok_ws_closed code=%s", exc.code)

    async def _handle_event(self, msg: dict) -> None:
        from services.persistence import append_message_voice_call
        etype = msg.get("type") or ""

        # Áudio out (chegou da Grok) — manda pro callback (camada SIP injeta)
        if etype in ("response.output_audio.delta", "response.audio.delta"):
            delta_b64 = msg.get("delta")
            if delta_b64:
                try:
                    pcm = base64.b64decode(delta_b64)
                    await self.on_audio_chunk_24k(pcm)
                except Exception as exc:
                    logger.warning("audio_callback_failed: %s", exc)
            return

        # Transcript Sofia (output)
        if etype in (
            "response.output_audio_transcript.done",
            "response.audio_transcript.done",
        ):
            text = msg.get("transcript") or ""
            if text:
                append_message_voice_call(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="assistant",
                    content=text,
                    model=Config.GROK_VOICE_MODEL,
                )
            return

        # Transcript usuário (STT do Grok/Whisper)
        if etype == "conversation.item.input_audio_transcription.completed":
            text = msg.get("transcript") or ""
            if text:
                append_message_voice_call(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="user",
                    content=text,
                )
            return

        # Tool call args completos
        if etype == "response.function_call_arguments.done":
            call_id = msg.get("call_id") or ""
            name = msg.get("name") or ""
            args_str = msg.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            if name:
                await self._execute_tool(call_id, name, args)
            return

        # Erros
        if etype == "error":
            err = (msg.get("error") or {}).get("message") or "grok_error"
            logger.warning("grok_call_error: %s", err)
            return

    async def _execute_tool(self, call_id: str, name: str, args: dict) -> None:
        from services.persistence import execute_voice_tool
        self._tool_calls += 1
        output = execute_voice_tool(name, args, self.persona_ctx)
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(output),
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))


def _build_tools_for_call(persona: str) -> list[dict]:
    """Tools mais essenciais pra ligação. Mantemos enxuto pra reduzir
    latência. Lista cresce conforme casos reais aparecerem."""
    return [
        {
            "type": "function",
            "name": "get_patient_summary",
            "description": "Resumo do paciente (condições, meds, alertas) por id.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string"}},
            },
        },
        {
            "type": "function",
            "name": "create_care_event",
            "description": "Registra um relato/evento clínico mencionado na ligação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "classification": {
                        "type": "string",
                        "enum": ["routine", "attention", "urgent", "critical"],
                    },
                },
                "required": ["patient_id", "summary"],
            },
        },
        {
            "type": "function",
            "name": "schedule_teleconsulta",
            "description": "Agenda solicitação de teleconsulta a partir da ligação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "requested_for": {"type": "string"},
                },
                "required": ["patient_id", "requested_for"],
            },
        },
    ]
