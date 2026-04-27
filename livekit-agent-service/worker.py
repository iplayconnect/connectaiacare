"""LiveKit Agent Worker — Sofia em ligação telefônica via LiveKit Cloud + SIP.

Stack:
  STT  : Deepgram nova-2 (PT-BR)
  LLM  : Grok via OpenAI-compatible API (mesma base que voice-call-service)
  TTS  : ElevenLabs Multilingual v2 (PT-BR) — fallback Cartesia se config
  VAD  : Silero
  Tools: SofiaTools (10 tools com Safety Guardrail)

Recebe metadata da room (criada pelo dispatcher) com:
  patient_id, persona, tenant_id, scenario_*, sofia_session_id, allowed_tools,
  full_name, system_prompt (do scenario), user_id, destination

Decisão de não usar Grok Voice Realtime aqui:
  Grok Voice (speech-to-speech direto) não tem plugin LiveKit oficial. Para
  manter LiveKit Agents framework como camada (estabilidade, interrupção,
  observabilidade nativa), rodamos pipeline STT+LLM+TTS. Trade-off: perde a
  prosódia nativa do Grok Voice; ganha framework maduro.

  Para A/B com Grok Voice futuro, voice-call-service (Grok+PJSIP) continua
  funcional e pode ser ativado via VOICE_BACKEND=voice-call-service no backend.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import structlog
from livekit import agents, rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import deepgram, openai, silero

from tools import SofiaTools

logger = structlog.get_logger()
logging.basicConfig(level=logging.INFO)


# ════════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════════
STT_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "pt-BR")
STT_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-2-general")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.x.ai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "grok-2-1212")
LLM_API_KEY_ENV = os.getenv("LLM_API_KEY_ENV", "XAI_API_KEY")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "elevenlabs")  # elevenlabs | cartesia
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "")            # ElevenLabs voice ID

DEFAULT_SYSTEM_PROMPT = (
    "Você é Sofia, assistente clínica conversacional do ConnectaIACare. "
    "Você fala português brasileiro, com tom acolhedor e claro. "
    "Você NÃO diagnostica e NÃO prescreve. Toda informação clínica vem com o "
    "lembrete de que a decisão é sempre do médico responsável. "
    "Quando algo for grave ou urgente, escale via tool escalate_to_attendant. "
    "Use as tools quando precisar de dado clínico ou registrar evento."
)


# ════════════════════════════════════════════════════════════════
# TTS factory
# ════════════════════════════════════════════════════════════════
def _build_tts():
    if TTS_PROVIDER == "elevenlabs":
        from livekit.plugins import elevenlabs

        kwargs = {
            "model": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        }
        if TTS_VOICE_ID:
            # API moderna: usa Voice() com id
            kwargs["voice"] = elevenlabs.Voice(
                id=TTS_VOICE_ID, name="Sofia",
                category="premade",
            )
        return elevenlabs.TTS(**kwargs)
    elif TTS_PROVIDER == "cartesia":
        from livekit.plugins import cartesia
        return cartesia.TTS(
            model=os.getenv("CARTESIA_MODEL", "sonic-multilingual"),
            voice=TTS_VOICE_ID or None,
            language="pt",
        )
    raise ValueError(f"unknown TTS_PROVIDER={TTS_PROVIDER}")


# ════════════════════════════════════════════════════════════════
# Entrypoint — chamado pelo LiveKit pra cada job (room nova)
# ════════════════════════════════════════════════════════════════
async def entrypoint(ctx: JobContext) -> None:
    """Roda quando uma room recebe um SIP participant + nosso agent é
    despachado. ctx.room.metadata trás contexto da call."""

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    metadata: dict = {}
    try:
        if ctx.room.metadata:
            metadata = json.loads(ctx.room.metadata)
    except Exception as e:
        logger.warning("invalid_room_metadata", error=str(e))

    full_name = metadata.get("full_name") or "amigo(a)"
    system_prompt = metadata.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    extra_context = metadata.get("extra_context") or {}

    # Adiciona contexto do paciente no system prompt
    if extra_context:
        system_prompt += (
            "\n\n--- Contexto do contato ---\n"
            + json.dumps(extra_context, ensure_ascii=False)
        )

    chat_ctx = llm.ChatContext().append(role="system", text=system_prompt)

    # Tools com contexto da call injetado
    fnc_ctx = SofiaTools(call_ctx={
        "patient_id": metadata.get("patient_id"),
        "persona": metadata.get("persona") or "paciente",
        "tenant_id": metadata.get("tenant_id") or "connectaiacare_demo",
        "sofia_session_id": metadata.get("sofia_session_id"),
        "scenario_code": metadata.get("scenario_code"),
        "scenario_id": metadata.get("scenario_id"),
        "allowed_tools": metadata.get("allowed_tools") or [],
        "user_id": metadata.get("user_id"),
        "full_name": full_name,
        "destination": metadata.get("destination"),
    })

    # Aguarda SIP participant entrar na room (= ligação atendida)
    participant = await ctx.wait_for_participant()
    logger.info(
        "participant_joined",
        identity=participant.identity, room=ctx.room.name,
    )

    # Constrói VoicePipelineAgent com STT+LLM+TTS+VAD
    agent = agents.VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=deepgram.STT(language=STT_LANGUAGE, model=STT_MODEL),
        llm=openai.LLM(
            model=LLM_MODEL,
            base_url=LLM_BASE_URL,
            api_key=os.getenv(LLM_API_KEY_ENV),
        ),
        tts=_build_tts(),
        chat_ctx=chat_ctx,
        fnc_ctx=fnc_ctx,
        # Interrupção rápida: usuário fala → Sofia para de falar
        allow_interruptions=True,
        interrupt_speech_duration=0.5,
        interrupt_min_words=0,
        # min_endpointing_delay menor = resposta mais rápida (default 0.5s)
        min_endpointing_delay=0.4,
    )

    agent.start(ctx.room, participant)

    # Sofia abre a conversa proativamente
    opening = f"Alô! Aqui é a Sofia falando. Posso falar com {full_name}?"
    await agent.say(opening, allow_interruptions=True)

    # Mantém alive até a room fechar
    await asyncio.Future()


# ════════════════════════════════════════════════════════════════
# CLI runner
# ════════════════════════════════════════════════════════════════
def _prewarm(proc) -> None:
    """Pré-carrega VAD model — corre 1× por worker, não por call."""
    proc.userdata["vad"] = silero.VAD.load()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=_prewarm,
            # Worker se identifica pra LiveKit — só atende rooms com este
            # tipo dispatched
            agent_name=os.getenv("LIVEKIT_AGENT_NAME", "sofia-voice"),
        )
    )
