"""Wrapper para Evolution API v2 (WhatsApp)."""
from __future__ import annotations

import base64
from typing import Any

import httpx

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EvolutionClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        instance: str | None = None,
    ):
        self.base_url = (base_url or settings.evolution_api_url).rstrip("/")
        self.api_key = api_key or settings.evolution_api_key
        self.instance = instance or settings.evolution_instance
        self.headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        self._client = httpx.Client(timeout=30.0)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    # ---------- Envio de mensagens ----------
    def send_text(self, phone: str, text: str, quoted_message_id: str | None = None) -> dict:
        payload: dict[str, Any] = {"number": phone, "text": text}
        if quoted_message_id:
            payload["quoted"] = {"key": {"id": quoted_message_id}}
        resp = self._client.post(
            self._url(f"/message/sendText/{self.instance}"), json=payload, headers=self.headers
        )
        resp.raise_for_status()
        logger.info("evolution_send_text", phone=phone, status=resp.status_code)
        return resp.json()

    def send_media(
        self, phone: str, media_url: str, caption: str = "", media_type: str = "image"
    ) -> dict:
        payload = {
            "number": phone,
            "mediatype": media_type,
            "media": media_url,
            "caption": caption,
        }
        resp = self._client.post(
            self._url(f"/message/sendMedia/{self.instance}"), json=payload, headers=self.headers
        )
        resp.raise_for_status()
        logger.info("evolution_send_media", phone=phone, type=media_type, status=resp.status_code)
        return resp.json()

    def send_media_base64(
        self, phone: str, media_b64: str, filename: str, caption: str = "", mimetype: str = "image/jpeg"
    ) -> dict:
        payload = {
            "number": phone,
            "mediatype": "image" if mimetype.startswith("image/") else "document",
            "mimetype": mimetype,
            "media": media_b64,
            "fileName": filename,
            "caption": caption,
        }
        resp = self._client.post(
            self._url(f"/message/sendMedia/{self.instance}"), json=payload, headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()

    def send_audio(self, phone: str, audio_url: str) -> dict:
        payload = {"number": phone, "audio": audio_url}
        resp = self._client.post(
            self._url(f"/message/sendWhatsAppAudio/{self.instance}"),
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    # ---------- Download de mídia ----------
    def download_media_base64(self, message: dict) -> bytes:
        payload = {"message": {"key": message.get("key"), "message": message.get("message")}}
        resp = self._client.post(
            self._url(f"/chat/getBase64FromMediaMessage/{self.instance}"),
            json=payload,
            headers=self.headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        b64 = data.get("base64") or data.get("data") or ""
        return base64.b64decode(b64)

    # ---------- Perfil ----------
    def get_profile_picture(self, phone: str) -> str | None:
        resp = self._client.post(
            self._url(f"/chat/fetchProfilePictureUrl/{self.instance}"),
            json={"number": phone},
            headers=self.headers,
        )
        if resp.status_code == 200:
            return resp.json().get("profilePictureUrl")
        return None

    # ---------- Presença ----------
    def set_presence(self, phone: str, presence: str = "composing") -> None:
        """presence in: composing | recording | paused | available"""
        try:
            self._client.post(
                self._url(f"/chat/sendPresence/{self.instance}"),
                json={"number": phone, "presence": presence, "delay": 1200},
                headers=self.headers,
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("presence_failed", error=str(exc))


_evolution_instance: EvolutionClient | None = None


def get_evolution() -> EvolutionClient:
    global _evolution_instance
    if _evolution_instance is None:
        _evolution_instance = EvolutionClient()
    return _evolution_instance
