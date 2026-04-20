"""LLM dispatcher multi-provider — Anthropic + Google Gemini.

Abstração que permite trocar o fornecedor de LLM via env var `LLM_PROVIDER`
sem alterar qualquer outro código consumidor (analysis_service, routes, etc.).

Interface pública estável:
    - complete(system, user, model, max_tokens, temperature) -> str
    - complete_json(system, user, model, max_tokens, temperature) -> dict

Model aliases são resolvidos para o modelo específico do provider ativo:
    MODEL_FAST    -> Haiku (Anthropic) / Flash (Gemini)
    MODEL_DEFAULT -> Sonnet / Flash
    MODEL_DEEP    -> Opus / Pro (ou Flash como fallback)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Model aliases — abstração estável para o resto do código
# ──────────────────────────────────────────────────────────────────────

MODEL_FAST = "fast"      # extração de entidades, tarefas curtas
MODEL_DEFAULT = "default"  # análises médias
MODEL_DEEP = "deep"      # análise clínica profunda, raciocínio complexo


# Mapeamento alias → modelo real por provider
_MODEL_MAP = {
    "anthropic": {
        "fast": "claude-haiku-4-5-20251001",
        "default": "claude-sonnet-4-6",
        "deep": "claude-opus-4-7",
    },
    "gemini": {
        # Gemini 2.5 Flash é o mais rápido e barato (tem tier gratuito).
        # NOTA: Usamos Flash em deep também para evitar thinking tokens
        # invisíveis do Pro consumirem budget e truncar a resposta JSON.
        # Quando for upgrade estratégico, trocar deep para gemini-2.5-pro
        # COM max_tokens >= 8192 e thinking_budget ajustado.
        "fast": "gemini-2.5-flash",
        "default": "gemini-2.5-flash",
        "deep": "gemini-2.5-flash",
    },
}


def _resolve_model(alias: str, provider: str) -> str:
    """Resolve alias (MODEL_FAST etc.) para modelo específico do provider."""
    provider_models = _MODEL_MAP.get(provider, _MODEL_MAP["anthropic"])
    return provider_models.get(alias, provider_models["default"])


# ──────────────────────────────────────────────────────────────────────
# Service unificado
# ──────────────────────────────────────────────────────────────────────


class LLMService:
    """Dispatcher para LLM multi-provider.

    Provider é escolhido por env (`LLM_PROVIDER`):
        - "anthropic" (default): usa Claude
        - "gemini": usa Google Gemini
    """

    def __init__(self, provider: str | None = None):
        self.provider = (provider or settings.llm_provider or "anthropic").lower()
        logger.info("llm_service_init", provider=self.provider)

        if self.provider == "anthropic":
            self._init_anthropic()
        elif self.provider == "gemini":
            self._init_gemini()
        else:
            raise ValueError(f"Provider '{self.provider}' não suportado. Use 'anthropic' ou 'gemini'.")

    def _init_anthropic(self) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não configurada, mas LLM_PROVIDER=anthropic. "
                "Configure a key ou mude LLM_PROVIDER=gemini."
            )
        from anthropic import Anthropic
        self._anthropic = Anthropic(api_key=settings.anthropic_api_key)

    def _init_gemini(self) -> None:
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY não configurada, mas LLM_PROVIDER=gemini. "
                "Obter grátis em https://aistudio.google.com/apikey"
            )
        # SDK google-genai é o unified novo. Fallback para google-generativeai se não instalado.
        try:
            from google import genai  # google-genai (novo SDK unificado)
            self._gemini = genai.Client(api_key=settings.google_api_key)
            self._gemini_api_style = "new"
        except ImportError:
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=settings.google_api_key)
            self._gemini_legacy = genai_legacy
            self._gemini_api_style = "legacy"

    # ──────────────────────────────────────────────────────────────────
    # Interface pública — unchanged API para o resto do código
    # ──────────────────────────────────────────────────────────────────

    def complete(
        self,
        system: str,
        user: str,
        model: str = MODEL_DEFAULT,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """Completion de texto sem estrutura obrigatória."""
        real_model = _resolve_model(model, self.provider)
        if self.provider == "anthropic":
            return self._anthropic_complete(system, user, real_model, max_tokens, temperature)
        return self._gemini_complete(system, user, real_model, max_tokens, temperature)

    def complete_json(
        self,
        system: str,
        user: str,
        model: str = MODEL_DEFAULT,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Completion com saída JSON estruturado."""
        real_model = _resolve_model(model, self.provider)
        if self.provider == "anthropic":
            return self._anthropic_complete_json(system, user, real_model, max_tokens, temperature)
        return self._gemini_complete_json(system, user, real_model, max_tokens, temperature)

    # ──────────────────────────────────────────────────────────────────
    # Anthropic implementation
    # ──────────────────────────────────────────────────────────────────

    def _anthropic_complete(self, system, user, model, max_tokens, temperature) -> str:
        resp = self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        logger.info(
            "llm_complete",
            provider="anthropic",
            model=model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
        return text

    def _anthropic_complete_json(self, system, user, model, max_tokens, temperature) -> dict:
        system_with_json = (
            system
            + "\n\nIMPORTANTE: Sua resposta DEVE ser JSON válido, sem texto adicional antes ou depois. "
            "Não use blocos markdown ``` . Apenas o JSON puro."
        )
        text = self._anthropic_complete(system_with_json, user, model, max_tokens, temperature)
        return _strip_and_parse_json(text)

    # ──────────────────────────────────────────────────────────────────
    # Gemini implementation
    # ──────────────────────────────────────────────────────────────────

    def _gemini_complete(self, system, user, model, max_tokens, temperature) -> str:
        if self._gemini_api_style == "new":
            # SDK google-genai (novo unificado)
            resp = self._gemini.models.generate_content(
                model=model,
                contents=user,
                config={
                    "system_instruction": system,
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            text = resp.text or ""
            usage = getattr(resp, "usage_metadata", None)
            logger.info(
                "llm_complete",
                provider="gemini",
                model=model,
                input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            )
            return text

        # Legacy SDK google-generativeai
        model_obj = self._gemini_legacy.GenerativeModel(
            model_name=model,
            system_instruction=system,
        )
        resp = model_obj.generate_content(
            user,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        logger.info("llm_complete", provider="gemini_legacy", model=model)
        return resp.text or ""

    def _gemini_complete_json(self, system, user, model, max_tokens, temperature) -> dict:
        """Gemini tem JSON mode nativo via response_mime_type."""
        if self._gemini_api_style == "new":
            resp = self._gemini.models.generate_content(
                model=model,
                contents=user,
                config={
                    "system_instruction": system,
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                },
            )
            text = resp.text or "{}"
            logger.info(
                "llm_complete_json",
                provider="gemini",
                model=model,
                chars=len(text),
            )
            return _strip_and_parse_json(text)

        # Legacy fallback — força instrução JSON no prompt
        system_with_json = (
            system
            + "\n\nIMPORTANTE: Sua resposta DEVE ser JSON válido, sem texto adicional. "
            "Não use ```. Apenas o JSON puro."
        )
        text = self._gemini_complete(system_with_json, user, model, max_tokens, temperature)
        return _strip_and_parse_json(text)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _strip_and_parse_json(text: str) -> dict[str, Any]:
    """Remove wrapping markdown ``` se houver, e parseia JSON."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("llm_json_parse_failed", error=str(exc), text_sample=text[:500])
        raise


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────

_llm_instance: LLMService | None = None


def get_llm() -> LLMService:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance
