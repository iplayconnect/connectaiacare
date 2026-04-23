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
        **overrides,
    ) -> dict[str, Any]:
        """Completa chamada JSON pra uma task. Aplica fallback cascade."""
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
                )
                elapsed_ms = int((time.time() - t0) * 1000)
                logger.info(
                    "llm_call_ok",
                    task=task, model=model_key, provider=provider,
                    elapsed_ms=elapsed_ms,
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
    ) -> dict:
        model_id = self.config.model_meta(model_key).get("model_id") or model_key.split("/", 1)[-1]

        if provider == "anthropic":
            return self._call_anthropic(model_id, system, user, temperature, max_tokens, image_b64, image_mime)
        if provider == "openai":
            return self._call_openai(model_id, system, user, temperature, max_tokens, image_b64, image_mime)
        if provider == "gemini":
            return self._call_gemini(model_id, system, user, temperature, max_tokens, image_b64, image_mime)
        if provider == "deepseek":
            return self._call_deepseek(model_id, system, user, temperature, max_tokens)
        raise ValueError(f"provider desconhecido: {provider}")

    # ─── Anthropic ───

    def _call_anthropic(
        self, model: str, system: str, user: str,
        temperature: float, max_tokens: int,
        image_b64: str | None, image_mime: str,
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

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        parsed = _extract_json(text)
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
        return _extract_json(text)

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
        return _extract_json(text)

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
        return _extract_json(text)


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
