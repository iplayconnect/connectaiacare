"""TTS client — síntese de voz via Gemini.

Modelo padrão: gemini-2.5-flash-preview-tts (capacidade nativa de TTS).
Cai pra fallback se o tenant não tiver acesso ao preview.

Retorna áudio raw (PCM 24kHz mono) base64 + metadata.
ADR-028 documenta o roadmap de migração ElevenLabs → Gemini TTS.
"""
from __future__ import annotations

import base64
import logging
import os
import wave
import io

import google.generativeai as genai

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = os.getenv("SOFIA_TTS_MODEL") or "gemini-2.5-flash-preview-tts"
# Voz: lista oficial Gemini TTS (2026). "Kore" = feminina pt-BR neutra calorosa.
DEFAULT_VOICE = os.getenv("SOFIA_TTS_VOICE") or "Kore"
SAMPLE_RATE_HZ = 24000


_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY required for TTS")
    genai.configure(api_key=key)
    _configured = True


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
    """Gera áudio. Retorna {audio_base64, mime_type, duration_seconds, model}."""
    _ensure_configured()
    voice = voice or DEFAULT_VOICE

    model = genai.GenerativeModel(model_name=DEFAULT_TTS_MODEL)
    try:
        resp = model.generate_content(
            text,
            generation_config={
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {"voice_name": voice}
                    }
                },
            },
        )
    except Exception as exc:
        logger.warning("tts_generate_failed", extra={"error": str(exc), "model": DEFAULT_TTS_MODEL})
        raise

    # Extrai PCM dos parts
    pcm_chunks: list[bytes] = []
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in (getattr(content, "parts", None) or []):
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
        "voice": voice,
    }
