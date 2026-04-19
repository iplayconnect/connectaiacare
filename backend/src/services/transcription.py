"""Transcrição de áudio via Deepgram (pt-BR)."""
from __future__ import annotations

from typing import Any

from deepgram import DeepgramClient, PrerecordedOptions, FileSource

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TranscriptionService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.deepgram_api_key
        self._client = DeepgramClient(self.api_key)

    def transcribe_bytes(self, audio_bytes: bytes, mimetype: str = "audio/ogg") -> dict[str, Any]:
        payload: FileSource = {"buffer": audio_bytes}
        options = PrerecordedOptions(
            model="nova-2",
            language="pt-BR",
            smart_format=True,
            punctuate=True,
            diarize=False,
            utterances=False,
            detect_language=False,
        )
        response = self._client.listen.rest.v("1").transcribe_file(payload, options)
        result = response.to_dict() if hasattr(response, "to_dict") else response

        try:
            channels = result.get("results", {}).get("channels", [])
            alt = channels[0].get("alternatives", [{}])[0] if channels else {}
            transcript = alt.get("transcript", "")
            confidence = alt.get("confidence", 0.0)
        except Exception as exc:
            logger.error("transcription_parse_error", error=str(exc))
            transcript = ""
            confidence = 0.0

        logger.info(
            "transcription_complete",
            chars=len(transcript),
            confidence=round(confidence, 3),
        )
        return {"transcript": transcript, "confidence": confidence, "raw": result}


_transcription_instance: TranscriptionService | None = None


def get_transcription() -> TranscriptionService:
    global _transcription_instance
    if _transcription_instance is None:
        _transcription_instance = TranscriptionService()
    return _transcription_instance
