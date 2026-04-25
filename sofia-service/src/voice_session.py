"""Voice session — proxy bidirecional Browser ↔ Gemini Live API.

Cada conexão WebSocket do browser abre 1 VoiceSession que:
  1. Conecta no Gemini Live (`client.aio.live.connect`).
  2. Pipe áudio: browser PCM 16kHz → live.send_realtime_input(audio=...).
  3. Pipe áudio: live.receive() → browser (PCM 24kHz → WAV stream).
  4. Tool calls: live emite tool_call → executa via tools.execute_tool →
     send_tool_response.
  5. Persiste cada utterance e resultado de tool em sofia_messages.

Modelo padrão: gemini-3.1-flash-live-preview (real-time, família 3).
Fallback: gemini-2.5-flash-preview-native-audio-dialog (estável).

Áudio:
  Input:  PCM 16-bit 16kHz mono LE
  Output: PCM 16-bit 24kHz mono LE (browser converte pra WAV/Web Audio).

Tools: filtradas por persona via tools.tools_for_persona() — mesma RBAC
do agent_runner texto.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from src import persistence, tools as tools_module
from src.agents.base_agent import PROMPTS_DIR
from src.orchestrator import PERSONA_AGENT, get_agent_for_persona

logger = logging.getLogger(__name__)

DEFAULT_VOICE_MODEL = (
    os.getenv("SOFIA_VOICE_MODEL") or "gemini-3.1-flash-live-preview"
)
DEFAULT_VOICE_NAME = os.getenv("SOFIA_TTS_VOICE") or "Kore"


def _build_system_instruction(persona_ctx: dict) -> str:
    """Reusa o prompt do agent texto da persona pra manter coerência."""
    AgentClass = get_agent_for_persona(persona_ctx.get("persona") or "anonymous")
    return AgentClass.system_prompt(persona_ctx)


def _build_tools(persona: str) -> list[types.Tool]:
    """Filtra tools pela persona (RBAC) e converte pro formato Live."""
    specs = tools_module.tools_for_persona(persona)
    if not specs:
        return []
    decls = [
        types.FunctionDeclaration(
            name=s["name"],
            description=s["description"],
            parameters=_clean_schema(s["parameters"]) if s.get("parameters") else None,
        )
        for s in specs
    ]
    return [types.Tool(function_declarations=decls)]


_GEMINI_SCHEMA_ALLOWED_KEYS = {
    "type", "properties", "required", "description",
    "enum", "items", "format", "nullable",
}


def _clean_schema(node):
    if isinstance(node, list):
        return [_clean_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    cleaned = {}
    for k, v in node.items():
        if k not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {pk: _clean_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            cleaned[k] = _clean_schema(v)
        else:
            cleaned[k] = v
    return cleaned


class VoiceSession:
    """Uma sessão = uma chamada do FAB de voz aberto pelo user.

    Uso (do voice_app.py WebSocket handler):
        async with VoiceSession(persona_ctx, browser_send_fn) as vs:
            await vs.start()
            # browser feed:
            await vs.feed_audio(pcm_chunk_16khz)
            # browser fim:
            await vs.close()
    """

    def __init__(self, persona_ctx: dict, send_to_browser):
        self.persona_ctx = persona_ctx
        self.persona = persona_ctx.get("persona") or "anonymous"
        self.tenant_id = persona_ctx.get("tenant_id") or "connectaiacare_demo"
        self.send_to_browser = send_to_browser  # async fn(dict)
        self.session_id: str | None = None
        self._live_session = None
        self._live_cm = None
        self._receive_task: asyncio.Task | None = None
        self._closed = False
        self._tokens_in = 0
        self._tokens_out = 0
        self._tool_calls = 0

    async def start(self) -> None:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY required for voice")

        client = genai.Client(api_key=api_key)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=DEFAULT_VOICE_NAME,
                    )
                ),
                # language_code não é aceito em SpeechConfig do google-genai.
                # Idioma é detectado automaticamente; reforçamos via prompt.
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=_build_system_instruction(self.persona_ctx))]
            ),
            tools=_build_tools(self.persona),
            # input_audio_transcription / output_audio_transcription só
            # disponíveis em google-genai >= 1.x. Versão atual entrega só
            # audio raw — UI mostra "ouvindo" sem texto até atualizarmos
            # o SDK na próxima onda.
        )

        # Sessão de DB (continua a mesma do chat texto se existir)
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

        self._live_cm = client.aio.live.connect(model=DEFAULT_VOICE_MODEL, config=config)
        self._live_session = await self._live_cm.__aenter__()

        # Inicia loop de recebimento das mensagens do Live
        self._receive_task = asyncio.create_task(self._receive_loop())

        logger.info("voice_session_started", extra={
            "session_id": self.session_id,
            "persona": self.persona,
            "model": DEFAULT_VOICE_MODEL,
        })
        await self.send_to_browser({
            "type": "ready",
            "sessionId": self.session_id,
            "model": DEFAULT_VOICE_MODEL,
        })

    async def feed_audio(self, pcm_bytes: bytes) -> None:
        """Browser enviou um chunk PCM 16kHz."""
        if self._closed or not self._live_session:
            return
        try:
            await self._live_session.send_realtime_input(
                audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000"),
            )
        except Exception as exc:
            logger.warning("voice_feed_failed", extra={"error": str(exc)})

    async def feed_text(self, text: str) -> None:
        """Permite digitar texto durante a chamada (modo híbrido)."""
        if self._closed or not self._live_session:
            return
        await self._live_session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=text)]),
            turn_complete=True,
        )

    async def interrupt(self) -> None:
        """User interrompeu a fala da Sofia. Sinaliza pra Live cortar."""
        # Live API trata interrupt automaticamente quando recebe novo input.
        # Aqui só logamos.
        logger.info("voice_session_interrupt", extra={"session_id": self.session_id})

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._receive_task:
            self._receive_task.cancel()
        if self._live_cm:
            try:
                await self._live_cm.__aexit__(None, None, None)
            except Exception:
                pass

        # Persiste consumo agregado da chamada
        persistence.record_usage(
            tenant_id=self.tenant_id,
            user_id=self.persona_ctx.get("user_id"),
            phone=self.persona_ctx.get("phone"),
            plan_sku=self.persona_ctx.get("plan_sku"),
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            tool_calls=self._tool_calls,
            messages=1,
            audio_seconds=0,  # estimado pelo browser via duração total da call
        )
        persistence.audit(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            user_id=self.persona_ctx.get("user_id"),
            persona=self.persona,
            event_type="voice_session_closed",
            decision="ok",
            details={
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
                "tool_calls": self._tool_calls,
            },
        )

    async def _receive_loop(self) -> None:
        """Lê mensagens do Gemini Live e encaminha pro browser."""
        try:
            async for message in self._live_session.receive():
                await self._handle_live_message(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("voice_receive_error session_id=%s", self.session_id)
            await self.send_to_browser({"type": "error", "detail": str(exc)})

    async def _handle_live_message(self, message: Any) -> None:
        # 1. Áudio output (PCM 24kHz)
        data = getattr(message, "data", None)
        if data:
            await self.send_to_browser({"type": "audio", "data": _b64(data)})

        # 2. Texto (transcript out)
        text = getattr(message, "text", None)
        if text:
            await self.send_to_browser({"type": "text", "role": "assistant", "text": text})

        # 3. Server content — transcrições + estado da turn
        sc = getattr(message, "server_content", None)
        if sc is not None:
            input_tx = getattr(sc, "input_transcription", None)
            if input_tx and getattr(input_tx, "text", None):
                await self.send_to_browser({
                    "type": "transcript",
                    "role": "user",
                    "text": input_tx.text,
                })
                persistence.append_message(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="user",
                    content=input_tx.text,
                    metadata={"channel": "voice"},
                )
            output_tx = getattr(sc, "output_transcription", None)
            if output_tx and getattr(output_tx, "text", None):
                await self.send_to_browser({
                    "type": "transcript",
                    "role": "assistant",
                    "text": output_tx.text,
                })
                persistence.append_message(
                    session_id=self.session_id,
                    tenant_id=self.tenant_id,
                    role="assistant",
                    content=output_tx.text,
                    model=DEFAULT_VOICE_MODEL,
                    metadata={"channel": "voice"},
                )
            if getattr(sc, "turn_complete", False):
                await self.send_to_browser({"type": "turn_complete"})
            if getattr(sc, "interrupted", False):
                await self.send_to_browser({"type": "interrupted"})

        # 4. Tool calls
        tc = getattr(message, "tool_call", None)
        if tc and getattr(tc, "function_calls", None):
            for fc in tc.function_calls:
                await self._execute_tool_call(fc)

        # 5. Usage metadata (atualiza contadores)
        usage = getattr(message, "usage_metadata", None)
        if usage:
            self._tokens_in = max(self._tokens_in, int(getattr(usage, "prompt_token_count", 0) or 0))
            self._tokens_out = max(self._tokens_out, int(getattr(usage, "candidates_token_count", 0) or 0))

    async def _execute_tool_call(self, fc) -> None:
        name = fc.name
        args = dict(getattr(fc, "args", {}) or {})
        self._tool_calls += 1
        logger.info("voice_tool_call name=%s session_id=%s", name, self.session_id)

        output = tools_module.execute_tool(name, args, self.persona_ctx)
        persistence.append_message(
            session_id=self.session_id,
            tenant_id=self.tenant_id,
            role="tool",
            content=name,
            tool_name=name,
            tool_input=args,
            tool_output=output,
            model=DEFAULT_VOICE_MODEL,
        )
        persistence.audit(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            user_id=self.persona_ctx.get("user_id"),
            persona=self.persona,
            event_type="tool_call",
            decision="allow" if output.get("ok") else "tool_error",
            details={"tool": name, "args": args, "ok": output.get("ok"), "channel": "voice"},
        )
        await self.send_to_browser({"type": "tool_call", "name": name, "ok": bool(output.get("ok"))})

        # Devolve pro Live
        try:
            await self._live_session.send_tool_response(
                function_responses=[
                    types.FunctionResponse(
                        id=getattr(fc, "id", None),
                        name=name,
                        response=output,
                    )
                ]
            )
        except Exception as exc:
            logger.warning("voice_tool_response_failed", extra={"error": str(exc)})


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")
