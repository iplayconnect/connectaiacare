"""Cliente para Sofia Voz (Grok Voice) via API do sofia-service.

Consome como microsserviço — fronteira limpa, sem acoplamento de código.
"""
from __future__ import annotations

from typing import Any

import httpx

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SofiaVoiceClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.sofia_voice_url).rstrip("/")
        self.api_key = api_key or settings.sofia_voice_key
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        self._client = httpx.Client(timeout=30.0)

    def place_call(
        self,
        phone: str,
        script: str,
        patient_context: dict[str, Any] | None = None,
        voice_profile: str = "geriatric_caring",
    ) -> dict[str, Any]:
        """Dispara uma ligação IA via Sofia Voice.

        Args:
            phone: número E.164 para ligar (+5511999999999).
            script: prompt/script que a Sofia deve seguir na ligação.
            patient_context: contexto do paciente para a IA referenciar.
            voice_profile: perfil de voz (tom, velocidade).
        """
        payload = {
            "phone": phone,
            "script": script,
            "patient_context": patient_context or {},
            "voice_profile": voice_profile,
            "source": "connectaiacare",
        }
        if not self.base_url:
            logger.warning("sofia_voice_not_configured", phone=phone)
            return {"status": "skipped", "reason": "sofia_voice_not_configured"}
        try:
            resp = self._client.post(
                f"{self.base_url}/api/voice/call", json=payload, headers=self.headers
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info("sofia_call_placed", phone=phone, call_id=result.get("call_id"))
            return result
        except Exception as exc:
            logger.error("sofia_call_failed", phone=phone, error=str(exc))
            return {"status": "error", "error": str(exc)}


_sofia_instance: SofiaVoiceClient | None = None


def get_sofia_voice() -> SofiaVoiceClient:
    global _sofia_instance
    if _sofia_instance is None:
        _sofia_instance = SofiaVoiceClient()
    return _sofia_instance
