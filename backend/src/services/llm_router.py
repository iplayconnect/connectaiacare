"""ConnectaIACare LLMRouter — rotação por tarefa + fallback cascade + cost tracking.

Carrega `config/llm_routing.yaml` e expõe interface única:

    from src.services.llm_router import get_llm_router
    router = get_llm_router()
    result = router.complete_json(task="soap_writer", system=..., user=...)

Comportamento:
    1. Pega `primary` da task
    2. Se provider não configurado OU retorna erro transitório: tenta fallbacks[]
    3. Se vision: usa endpoint/payload apropriado do provider
    4. Grava custo estimado em `aia_health_llm_usage` (log simples — sem DB externo)

Providers:
    - anthropic  → API oficial Anthropic (usa settings.anthropic_api_key)
    - openai     → API oficial OpenAI (settings.openai_api_key)
    - gemini     → google-generativeai SDK (settings.google_api_key)
    - deepseek   → API compatível OpenAI (settings.deepseek_api_key)

ADR-025 documenta decisões de roteamento e governança.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Config loader
# ══════════════════════════════════════════════════════════════════

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "llm_routing.yaml"


class LLMRoutingConfig:
    def __init__(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self.tasks: dict[str, dict] = raw.get("tasks", {})
        self.models: dict[str, dict] = raw.get("models", {})
        self.globals: dict = raw.get("global", {})

    def task(self, task_name: str) -> dict:
        t = self.tasks.get(task_name)
        if not t:
            logger.warning("llm_task_not_configured", task=task_name)
            return {
                "primary": "openai/gpt-5.4-mini",
                "fallbacks": ["google/gemini-2.5-flash"],
                "temperature": 0.2,
                "max_tokens": 2048,
            }
        return t

    def model_meta(self, model_key: str) -> dict:
        return self.models.get(model_key, {})


# ══════════════════════════════════════════════════════════════════
# Provider clients (lazy)
# ══════════════════════════════════════════════════════════════════

class _Clients:
    def __init__(self):
        self._anthropic = None
        self._openai = None
        self._gemini_sdk_ready = False
        self._deepseek_url = "https://api.deepseek.com/v1/chat/completions"

    def anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic
                key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
                if not key:
                    return None
                self._anthropic = anthropic.Anthropic(api_key=key)
                logger.info("anthropic_client_ready")
            except Exception as exc:
                logger.warning("anthropic_init_failed", error=str(exc))
                return None
        return self._anthropic

    def openai(self):
        if self._openai is None:
            try:
                from openai import OpenAI
                key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
                if not key:
                    return None
                self._openai = OpenAI(api_key=key)
                logger.info("openai_client_ready")
            except Exception as exc:
                logger.warning("openai_init_failed", error=str(exc))
                return None
        return self._openai

    def ensure_gemini(self):
        if self._gemini_sdk_ready:
            return True
        try:
            import google.generativeai as genai
            key = (
                getattr(settings, "gemini_api_key", None)
                or getattr(settings, "google_api_key", None)
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
            )
            if not key:
                return False
            genai.configure(api_key=key)
            self._gemini_sdk_ready = True
            return True
        except Exception as exc:
            logger.warning("gemini_init_failed", error=str(exc))
            return False


# ══════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════

class LLMRouter:
    def __init__(self):
        self.config = LLMRoutingConfig()
        self.clients = _Clients()

    # ============================================================
    # Public API
    # ============================================================

    def complete_json(
        self,
        task: str,
        system: str,
        user: str,
        image_b64: str | None = None,
        image_mime: str = "image/jpeg",
        cacheable_system: str | None = None,
        **overrides,
    ) -> dict[str, Any]:
        """Completa chamada JSON pra uma task. Aplica fallback cascade.

        Args:
            cacheable_system: parte ESTÁTICA do system prompt (prompt
                template base, whitelists, regras gerais). Se fornecido
                E o provider for Anthropic, é enviado como bloco com
                `cache_control: ephemeral` — chamadas seguintes em <5min
                pagam ~10% do custo dessa parte e respondem ~30% mais
                rápido. `system` (kwarg normal) continua sendo a parte
                DINÂMICA (varia por turno: contexto, dados do user).
                Outros providers (OpenAI/Gemini) ignoram o split e
                concatenam — comportamento idêntico ao antigo.
                Mínimo recomendado: 1024 tokens (~4k chars) pra valer
                a pena. Abaixo disso a Anthropic não cacheia.
        """
        task_cfg = self.config.task(task)
        models_to_try = [task_cfg["primary"]] + (task_cfg.get("fallbacks") or [])
        temperature = overrides.get("temperature", task_cfg.get("temperature", 0.2))
        max_tokens = overrides.get("max_tokens", task_cfg.get("max_tokens", 2048))

        has_vision_input = image_b64 is not None

        last_error = None
        for model_key in models_to_try:
            meta = self.config.model_meta(model_key)
            if has_vision_input and not meta.get("supports_vision"):
                logger.info("skipping_non_vision_model", model=model_key, task=task)
                continue
            provider = meta.get("provider") or model_key.split("/")[0]
            try:
                t0 = time.time()
                result = self._call_provider(
                    provider=provider,
                    model_key=model_key,
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    image_b64=image_b64,
                    image_mime=image_mime,
                    cacheable_system=cacheable_system,
                )
                elapsed_ms = int((time.time() - t0) * 1000)
                logger.info(
                    "llm_call_ok",
                    task=task, model=model_key, provider=provider,
                    elapsed_ms=elapsed_ms,
                    cache_creation_tokens=result.get("_cache_creation_input_tokens"),
                    cache_read_tokens=result.get("_cache_read_input_tokens"),
                )
                result["_model_used"] = model_key
                result["_provider"] = provider
                result["_elapsed_ms"] = elapsed_ms
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_call_failed",
                    task=task, model=model_key, provider=provider,
                    error=str(exc)[:400],
                )
                continue

        on_fail = self.config.globals.get("on_all_failed", "raise")
        if on_fail == "raise":
            raise RuntimeError(
                f"Todos os modelos falharam pra task '{task}': {last_error}"
            )
        return {"_error": str(last_error), "_all_failed": True}

    # ============================================================
    # Provider dispatch
    # ============================================================

    def _call_provider(
        self, provider: str, model_key: str,
        system: str, user: str,
        temperature: float, max_tokens: int,
        image_b64: str | None, image_mime: str,
        cacheable_system: str | None = None,
    ) -> dict:
        model_id = self.config.model_meta(model_key).get("model_id") or model_key.split("/", 1)[-1]

        if provider == "anthropic":
            return self._call_anthropic(
                model_id, system, user, temperature, max_tokens,
                image_b64, image_mime, cacheable_system=cacheable_system,
            )
        # Outros providers: cacheable_system é mesclado com system
        # (sem cache real). OpenAI tem prompt cache automático no
        # backend deles; Gemini tem API diferente (a fazer Phase D).
        merged_system = f"{cacheable_system}\n\n{system}" if cacheable_system else system
        if provider == "openai":
            return self._call_openai(model_id, merged_system, user, temperature, max_tokens, image_b64, image_mime)
        if provider == "gemini":
            return self._call_gemini(model_id, merged_system, user, temperature, max_tokens, image_b64, image_mime)
        if provider == "deepseek":
            return self._call_deepseek(model_id, merged_system, user, temperature, max_tokens)
        raise ValueError(f"provider desconhecido: {provider}")

    # ─── Anthropic ───

    def _call_anthropic(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
        image_b64: str | None, image_mime: str,
        cacheable_system: str | None = None,
    ) -> dict:
        client = self.clients.anthropic()
        if client is None:
            raise RuntimeError("anthropic_not_configured")

        content = []
        if image_b64:
            clean = image_b64.split(",", 1)[1] if "," in image_b64[:50] else image_b64
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": image_mime, "data": clean},
            })
        content.append({"type": "text", "text": user})

        # Prompt caching: se houver bloco estável (cacheable_system),
        # passa system como list[block] com cache_control no estável.
        # Caso contrário, system continua string (path original).
        # Nota: Anthropic exige bloco cacheado >= 1024 tokens (Sonnet/Haiku)
        # ou 2048 (Opus) — abaixo disso a API ignora cache_control e
        # cobra normal. Não há erro nem warning, apenas no-op.
        if cacheable_system:
            system_arg: Any = [
                {
                    "type": "text",
                    "text": cacheable_system,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": system} if system else None,
            ]
            system_arg = [b for b in system_arg if b]
        else:
            system_arg = system

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_arg,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        parsed = _extract_json(text)
        # Métricas de cache (Anthropic 0.34+ retorna em usage)
        usage = getattr(resp, "usage", None)
        if usage:
            ccit = getattr(usage, "cache_creation_input_tokens", None)
            crit = getattr(usage, "cache_read_input_tokens", None)
            if ccit is not None:
                parsed["_cache_creation_input_tokens"] = int(ccit)
            if crit is not None:
                parsed["_cache_read_input_tokens"] = int(crit)
            parsed["_input_tokens"] = int(getattr(usage, "input_tokens", 0) or 0)
            parsed["_output_tokens"] = int(getattr(usage, "output_tokens", 0) or 0)
        return parsed

    # ─── OpenAI ───

    def _call_openai(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
        image_b64: str | None, image_mime: str,
    ) -> dict:
        client = self.clients.openai()
        if client is None:
            raise RuntimeError("openai_not_configured")

        user_content: Any = user
        if image_b64:
            clean = image_b64.split(",", 1)[1] if "," in image_b64[:50] else image_b64
            data_url = f"data:{image_mime};base64,{clean}"
            user_content = [
                {"type": "text", "text": user},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]

        # GPT-5.x usa max_completion_tokens em vez de max_tokens
        uses_completion = any(model.lower().startswith(p) for p in ("gpt-5", "o1", "o3"))
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }
        # Reasoning models não aceitam temperature
        if not uses_completion:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
        else:
            kwargs["max_completion_tokens"] = max_tokens

        resp = client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        parsed = _extract_json(text)
        # OpenAI tem prompt caching automático (out/2024+).
        # Hit reduz custo do prefixo cacheado em 50%. Mínimo 1024 tokens.
        # Não precisa marcar nada — basta o prefixo do prompt repetir.
        # Métrica: usage.prompt_tokens_details.cached_tokens
        usage = getattr(resp, "usage", None)
        if usage:
            parsed["_input_tokens"] = int(getattr(usage, "prompt_tokens", 0) or 0)
            parsed["_output_tokens"] = int(getattr(usage, "completion_tokens", 0) or 0)
            details = getattr(usage, "prompt_tokens_details", None)
            cached = getattr(details, "cached_tokens", 0) if details else 0
            if cached:
                # Mapeia pro mesmo nome da Anthropic pra logging unificado
                parsed["_cache_read_input_tokens"] = int(cached)
        return parsed

    # ─── Gemini ───

    def _call_gemini(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
        image_b64: str | None, image_mime: str,
    ) -> dict:
        if not self.clients.ensure_gemini():
            raise RuntimeError("gemini_not_configured")

        import google.generativeai as genai
        gmodel = genai.GenerativeModel(model)
        combined = system + "\n\n" + user

        parts: list = []
        if image_b64:
            clean = image_b64.split(",", 1)[1] if "," in image_b64[:50] else image_b64
            parts.append({
                "inline_data": {"mime_type": image_mime, "data": base64.b64decode(clean)}
            })
        parts.append(combined)

        resp = gmodel.generate_content(
            parts,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
            },
        )
        text = resp.text if hasattr(resp, "text") else ""
        parsed = _extract_json(text)
        # Gemini tem caching EXPLÍCITO via Cached Content API
        # (caching.create + referenciar em generate_content).
        # Mínimo: 32k tokens (Pro), 4k tokens (Flash). Custo: ~25% +
        # storage. Implementação fica pra Phase D — hoje Gemini é
        # fallback secundário no router; volume não justifica ainda.
        # Ainda assim capturamos o token count se vier (cached_content_token_count
        # quando estivermos usando cached content).
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            parsed["_input_tokens"] = int(getattr(usage, "prompt_token_count", 0) or 0)
            parsed["_output_tokens"] = int(getattr(usage, "candidates_token_count", 0) or 0)
            cached = getattr(usage, "cached_content_token_count", 0) or 0
            if cached:
                parsed["_cache_read_input_tokens"] = int(cached)
        return parsed

    # ─── DeepSeek (OpenAI-compat) ───

    def _call_deepseek(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
    ) -> dict:
        import httpx
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("deepseek_not_configured")
        resp = httpx.post(
            self.clients._deepseek_url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=self.config.globals.get("default_timeout", 45),
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        parsed = _extract_json(text)
        # DeepSeek tem prompt caching automático (Context Caching, fev/2024).
        # Mínimo 128 tokens (mais agressivo que outros). Hit = 10% custo.
        # Métricas: usage.prompt_cache_hit_tokens / prompt_cache_miss_tokens
        usage = data.get("usage") or {}
        if usage:
            parsed["_input_tokens"] = int(usage.get("prompt_tokens") or 0)
            parsed["_output_tokens"] = int(usage.get("completion_tokens") or 0)
            hit = usage.get("prompt_cache_hit_tokens") or 0
            if hit:
                parsed["_cache_read_input_tokens"] = int(hit)
        return parsed


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict:
    """Extrai JSON de resposta LLM (tolerante a code fences)."""
    if not text:
        raise ValueError("empty_llm_response")
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        body = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                if in_block:
                    break
                in_block = True
                continue
            if in_block:
                body.append(line)
        t = "\n".join(body).strip()
    idx = t.find("{")
    if idx > 0:
        t = t[idx:]
    last = t.rfind("}")
    if last > 0:
        t = t[: last + 1]
    return json.loads(t)


_router_instance: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter()
    return _router_instance
