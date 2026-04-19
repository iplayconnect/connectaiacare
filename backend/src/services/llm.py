"""Wrapper de LLM (Anthropic Claude) — roteador simples para ConnectaIACare."""
from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_DEFAULT = "claude-sonnet-4-6"
MODEL_DEEP = "claude-opus-4-7"


class LLMService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        self._client = Anthropic(api_key=self.api_key)

    def complete(
        self,
        system: str,
        user: str,
        model: str = MODEL_DEFAULT,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        logger.info(
            "llm_complete",
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
        return text

    def complete_json(
        self,
        system: str,
        user: str,
        model: str = MODEL_DEFAULT,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        system_with_json = (
            system
            + "\n\nIMPORTANTE: Sua resposta DEVE ser JSON válido, sem texto adicional antes ou depois. "
            "Não use blocos markdown ``` . Apenas o JSON puro."
        )
        text = self.complete(system_with_json, user, model=model, max_tokens=max_tokens, temperature=temperature)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("llm_json_parse_failed", error=str(exc), text=text[:500])
            raise


_llm_instance: LLMService | None = None


def get_llm() -> LLMService:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance
