"""TTS client — síntese de voz via Gemini.

google-generativeai (0.8.x) NÃO suporta `response_modalities=["AUDIO"]`.
Precisamos do novo SDK `google-genai` (>=0.5) que tem suporte oficial.

Modelo padrão: gemini-2.5-flash-preview-tts
Voz padrão: "Kore" (feminina pt-BR neutra calorosa)

Retorna WAV (PCM 24kHz mono → wav container) base64 + metadata.
ADR-028 documenta o roadmap de migração ElevenLabs → Gemini TTS.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import wave

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = os.getenv("SOFIA_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
DEFAULT_VOICE = os.getenv("SOFIA_TTS_VOICE") or "Kore"
SAMPLE_RATE_HZ = 24000

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY required for TTS")
        _client = genai.Client(api_key=api_key)
    return _client


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = SAMPLE_RATE_HZ) -> bytes:
    """Wrap PCM 16-bit mono em container WAV pra browser tocar."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def synthesize(text: str, voice: str | None = None) -> dict:
    """Gera áudio. Retorna {audio_base64, mime_type, duration_seconds, model, voice}."""
    client = _get_client()
    voice_name = voice or DEFAULT_VOICE

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )

    try:
        resp = client.models.generate_content(
            model=DEFAULT_TTS_MODEL,
            contents=text,
            config=config,
        )
    except Exception as exc:
        logger.warning("tts_generate_failed", extra={"error": str(exc), "model": DEFAULT_TTS_MODEL})
        raise

    pcm_chunks: list[bytes] = []
    for cand in (resp.candidates or []):
        content = cand.content
        if not content:
            continue
        for part in (content.parts or []):
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                pcm_chunks.append(inline.data)

    if not pcm_chunks:
        raise RuntimeError("tts_no_audio_returned")

    pcm = b"".join(pcm_chunks)
    wav = _pcm_to_wav(pcm)
    duration_seconds = len(pcm) / (SAMPLE_RATE_HZ * 2)  # 16-bit = 2 bytes/sample

    return {
        "audio_base64": base64.b64encode(wav).decode("utf-8"),
        "mime_type": "audio/wav",
        "duration_seconds": round(duration_seconds, 2),
        "model": DEFAULT_TTS_MODEL,
        "voice": voice_name,
    }
