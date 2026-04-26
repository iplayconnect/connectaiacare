"""GrokCallSession — variante do GrokVoiceSession (sofia-service) adaptada
pra fonte de áudio SIP (já em PCM linear, taxa nativa Grok 24k)."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

import websockets

from config import Config

logger = logging.getLogger("grok_call_session")

BR_TZ = ZoneInfo("America/Sao_Paulo")


def _time_period_pt() -> tuple[str, str, str]:
    """Retorna (saudacao, despedida, hora_str_BRT) baseado no horário BRT."""
    now = datetime.now(BR_TZ)
    h = now.hour
    if 5 <= h < 12:
        greet = "Bom dia"
        farewell = "Tenha um excelente dia"
    elif 12 <= h < 18:
        greet = "Boa tarde"
        farewell = "Tenha uma ótima tarde"
    elif 18 <= h < 24:
        greet = "Boa noite"
        farewell = "Tenha uma boa noite"
    else:  # 0 <= h < 5
        greet = "Olá"  # madrugada — não soa natural saudação de período
        farewell = "Tenha uma boa madrugada e descanse"
    return greet, farewell, now.strftime("%H:%M")


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
        # Scenario override (do backend /api/communications/dial). Se houver
        # scenario_system_prompt, usamos ELE como base + injetamos memória
        # cross-session + contexto do paciente.
        scenario_prompt = self.persona_ctx.get("scenario_system_prompt")
        if scenario_prompt:
            from services.persistence import _load_memory_block
            instructions = scenario_prompt
            mem = _load_memory_block(self.persona_ctx.get("user_id"))
            if mem:
                instructions += "\n\n" + mem
            # Injeta contexto do paciente extra (vem do backend já carregado)
            extra = self.persona_ctx.get("extra_context") or {}
            patient = extra.get("patient")
            if patient:
                instructions += (
                    "\n\n# CONTEXTO DO PACIENTE NA LIGAÇÃO\n"
                    f"Nome: {patient.get('full_name')} "
                    f"(apelido: {patient.get('nickname') or '—'})\n"
                    f"Condições: {', '.join(patient.get('conditions') or []) or '—'}\n"
                    f"Alergias: {', '.join(patient.get('allergies') or []) or '—'}\n"
                    f"Unidade: {patient.get('care_unit') or '—'} "
                    f"Quarto: {patient.get('room_number') or '—'}"
                )
        else:
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
        greet, farewell, hora_brt = _time_period_pt()
        instructions += (
            f"\n\n# CONTEXTO IMEDIATO\n"
            f"Você está em uma LIGAÇÃO TELEFÔNICA ao vivo com {first_name}.\n"
            f"Horário atual no Brasil: {hora_brt} (BRT).\n"
            f"Cumprimento adequado: '{greet}'.\n"
            f"Despedida adequada: '{farewell}'.\n\n"
            "REGRAS DA LIGAÇÃO:\n"
            "- Áudio vai por telefone — frases CURTAS, tom natural, "
            "paciência pra silêncios.\n"
            "- Não fale 'olá' duas vezes.\n"
            f"- Use '{greet}' no início e '{farewell}' ao se despedir.\n"
            "- Quando o usuário disser 'tchau', 'até mais', 'pode desligar' "
            "ou similar, despeça-se brevemente e a ligação será encerrada."
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
                "tools": _build_tools_for_call(
                    self.persona,
                    allowed=self.persona_ctx.get("scenario_allowed_tools") or None,
                ),
                "tool_choice": "auto",
                "temperature": 0.7,
            },
        }))

        self._receive_task = asyncio.create_task(self._receive_loop())
        # Kickoff guardado mas NÃO disparado — quem dispara é a camada SIP
        # via .start_kickoff() quando state == CONFIRMED (paciente atendeu).
        self._kickoff_text = (
            f"[INÍCIO DA LIGAÇÃO TELEFÔNICA] Cumprimente {first_name} pelo "
            f"primeiro nome com '{greet}' e tom caloroso (1 frase curta). "
            "Diga que é a Sofia da ConnectaIACare. Em seguida pergunte como "
            "pode ajudar."
        )
        self._kickoff_sent = False
        logger.info(
            "grok_call_started session_id=%s persona=%s model=%s",
            self.session_id, self.persona, Config.GROK_VOICE_MODEL,
        )

    async def start_kickoff(self) -> None:
        """Dispara a 1ª fala da Sofia. Chamado pela camada SIP ao detectar
        CONFIRMED (paciente atendeu). Idempotente."""
        if self._kickoff_sent or self._closed or not self._ws:
            return
        self._kickoff_sent = True
        await self._ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": self._kickoff_text}],
            },
        }))
        await self._ws.send(json.dumps({"type": "response.create"}))
        logger.info("grok_call_kickoff_sent session_id=%s", self.session_id)

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
        # Diag: log todo evento (apenas tipo)
        logger.info("grok_evt %s", etype)
        if etype == "error":
            logger.error("grok_error_full: %s", msg)

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


def _build_tools_for_call(
    persona: str,
    allowed: list[str] | None = None,
) -> list[dict]:
    """Tools acessíveis durante a ligação. Filtra pelo `allowed` quando
    o scenario impõe lista — caso contrário usa default por persona.

    Inclui:
    - leitura: get_patient_summary, list_medication_schedules,
      get_patient_vitals, query_drug_rules, check_drug_interaction
    - escrita: create_care_event, schedule_teleconsulta
    - cruzamento: check_medication_safety (validação determinística antes
      do médico falar a prescrição)

    Filtramos por persona — paciente_b2c/familia não vê tools clínicas
    de cruzamento, só leitura básica.
    """
    base = [
        {
            "type": "function",
            "name": "get_patient_summary",
            "description": "Resumo do paciente (condições, meds, alergias, último relato, vitais recentes). Use ao iniciar a ligação se patient_id estiver no contexto.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string"}},
            },
        },
        {
            "type": "function",
            "name": "list_medication_schedules",
            "description": "Lista medicações ativas do paciente (nome, dose, horários, with_food, warnings). Use quando alguém perguntar 'que remédios ele toma?'.",
            "parameters": {
                "type": "object",
                "properties": {"patient_id": {"type": "string"}},
            },
        },
        {
            "type": "function",
            "name": "get_patient_vitals",
            "description": "Sinais vitais (PA, FC, FR, SatO2, temperatura, glicemia) dos últimos N dias.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "days": {"type": "integer", "description": "Padrão 7"},
                },
            },
        },
        {
            "type": "function",
            "name": "create_care_event",
            "description": "Registra um relato/evento clínico mencionado na ligação. Use quando o cuidador/familiar relatar uma queixa, queda, mudança de comportamento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "summary": {"type": "string", "description": "Resumo factual do que foi reportado"},
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
            "description": "Cria solicitação de teleconsulta. Use quando combinarem agendamento durante a ligação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "requested_for": {"type": "string", "description": "Data/hora ISO 8601 desejada"},
                },
                "required": ["patient_id", "requested_for"],
            },
        },
    ]

    # Tools clínicas avançadas (motor de cruzamentos) — só pra profissionais
    if persona in ("medico", "enfermeiro", "admin_tenant", "super_admin", "comercial"):
        # Comercial NÃO pega motor clínico — só leitura básica de paciente.
        # Os profissionais clínicos pegam tudo abaixo.
        pass
    if persona in ("medico", "enfermeiro", "admin_tenant", "super_admin"):
        base.extend([
            {
                "type": "function",
                "name": "query_drug_rules",
                "description": "Devolve TODAS as regras carregadas para um princípio ativo: dose, interações, contraindicações, ajustes renal/hepático, ACB, fall risk, alergias. Use pra 'me conta tudo sobre X' ou 'quais regras temos pra Y'.",
                "parameters": {
                    "type": "object",
                    "properties": {"medication_name": {"type": "string"}},
                    "required": ["medication_name"],
                },
            },
            {
                "type": "function",
                "name": "check_drug_interaction",
                "description": "Valida par de medicamentos: severity, mecanismo, recomendação, time_separation. Use pra 'posso usar X com Y?'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "med_a": {"type": "string"},
                        "med_b": {"type": "string"},
                    },
                    "required": ["med_a", "med_b"],
                },
            },
            {
                "type": "function",
                "name": "check_medication_safety",
                "description": "Roda o motor de cruzamentos (12 dimensões: dose, Beers, alergias, interações, contraindicações, ACB, fall risk, renal, hepático, vitais) em uma prescrição candidata SEM persistir. Use ANTES de o médico confirmar uma nova prescrição na ligação.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "medication_name": {"type": "string"},
                        "dose": {"type": "string"},
                        "patient_id": {"type": "string"},
                        "times_of_day": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Horários HH:MM, ex: ['08:00','20:00']",
                        },
                        "route": {"type": "string"},
                    },
                    "required": ["medication_name", "dose"],
                },
            },
        ])

    # Filtro final: se scenario passou allowed, intersecciona
    if allowed:
        allowed_set = set(allowed)
        base = [t for t in base if t["name"] in allowed_set]
        # Tools no allowed que não temos definidas aqui são ignoradas
        # silenciosamente (admin pode adicionar depois).
    return base
