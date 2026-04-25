"""Wrapper Gemini para Sofia Care.

SDK consolidado: google-genai (substitui google-generativeai legacy).
Mesmo SDK usado pelo tts_client e voice_session — uma fonte só.

Modelos suportados (snapshot 2026-04-25):
  - gemini-3-flash-preview        — preview família 3, generateContent
  - gemini-3.1-flash-lite-preview — preview lite (mais barato $0.25/$1.50)
  - gemini-3.1-pro-preview        — preview pro (raciocínio profundo)
  - gemini-2.5-flash              — GA estável (recomendado prod por enquanto)
  - gemini-flash-latest           — alias seguro como fallback

Família 3 muda paradigma:
  - thinking_config (substitui thinking_budget): minimal|low|medium|high
  - temperatura: doc orienta NÃO ajustar (default 1.0 é otimizado);
    valores baixos podem causar looping. Removemos config explícito.
  - thought_signatures processadas automaticamente pelo SDK.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Família 3 como default — saúde exige qualidade. gemini-3-flash-preview
# tem "inteligência de nível Pro na velocidade e preço do Flash" + thinking
# nativo. Fallback estável é o 2.5-flash GA.
# Trocar via SOFIA_LLM_MODEL pra testar 3.1-pro-preview (clínico premium)
# ou 3.1-flash-lite-preview (alto volume, mais barato).
DEFAULT_MODEL = os.getenv("SOFIA_LLM_MODEL") or "gemini-3-flash-preview"
FALLBACK_MODEL = os.getenv("SOFIA_LLM_FALLBACK") or "gemini-2.5-flash"

# thinking_level só vale pra família 3.
_THINKING_FAMILY_3_PREFIX = ("gemini-3", "gemini-3.")


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: Callable


@dataclass
class GenerationResult:
    text: str
    tool_calls: list[dict]
    tokens_in: int
    tokens_out: int
    model: str
    finish_reason: str | None = None


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY required")
        _client = genai.Client(api_key=api_key)
    return _client


_GEMINI_SCHEMA_ALLOWED_KEYS = {
    "type", "properties", "required", "description",
    "enum", "items", "format", "nullable",
}


def _clean_schema(node):
    """Poda do JSON Schema os campos não suportados por Gemini Function
    Declarations (minimum/maximum/pattern/etc rejeitados pela API)."""
    if isinstance(node, list):
        return [_clean_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    cleaned = {}
    for k, v in node.items():
        if k not in _GEMINI_SCHEMA_ALLOWED_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {pk: _clean_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            cleaned[k] = _clean_schema(v)
        else:
            cleaned[k] = v
    return cleaned


def _build_tools(tools: list[ToolDefinition] | None):
    if not tools:
        return None
    decls = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters=_clean_schema(t.parameters) if t.parameters else None,
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=decls)]


def _convert_history(messages: list[dict]) -> list[types.Content]:
    """[{role, content, ...}] → list[Content] do google-genai."""
    contents: list[types.Content] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            continue
        if role in ("user",):
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
        elif role in ("assistant", "model"):
            contents.append(types.Content(role="model", parts=[types.Part(text=content)]))
        elif role == "tool":
            tool_name = m.get("tool_name") or "tool"
            payload = m.get("tool_output") if m.get("tool_output") is not None else content
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {"text": payload}
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=tool_name, response=payload)],
            ))
    return contents


def _is_family_3(model: str) -> bool:
    return any(model.startswith(p) for p in _THINKING_FAMILY_3_PREFIX)


def _build_config(
    *,
    model: str,
    system_prompt: str | None,
    tools: list[ToolDefinition] | None,
    max_output_tokens: int,
    thinking_level: str | None,
) -> types.GenerateContentConfig:
    cfg_kwargs: dict[str, Any] = {
        "max_output_tokens": max_output_tokens,
    }
    if system_prompt:
        cfg_kwargs["system_instruction"] = system_prompt
    tool_objs = _build_tools(tools)
    if tool_objs:
        cfg_kwargs["tools"] = tool_objs

    # thinking_config só faz sentido na família 3.
    # minimal/low/medium/high. Valores explícitos só na 3.
    if _is_family_3(model) and thinking_level:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=thinking_level,
        )

    # NÃO setamos temperature — doc Gemini 3 orienta usar default (1.0).
    # Valores baixos podem causar looping/degradação.
    return types.GenerateContentConfig(**cfg_kwargs)


def generate(
    *,
    system_prompt: str,
    messages: list[dict],
    tools: list[ToolDefinition] | None = None,
    model: str | None = None,
    max_output_tokens: int = 1024,
    thinking_level: str | None = None,
) -> GenerationResult:
    client = _get_client()
    model_name = model or DEFAULT_MODEL

    def _call(model_id: str) -> GenerationResult:
        config = _build_config(
            model=model_id,
            system_prompt=system_prompt,
            tools=tools,
            max_output_tokens=max_output_tokens,
            thinking_level=thinking_level,
        )
        contents = _convert_history(messages)
        resp = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        finish_reason = None
        for cand in (getattr(resp, "candidates", None) or []):
            finish_reason = getattr(cand, "finish_reason", None)
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                t = getattr(part, "text", None)
                if t:
                    text_parts.append(t)
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", None):
                    args = dict(getattr(fc, "args", {}) or {})
                    tool_calls.append({"name": fc.name, "args": args})

        usage = getattr(resp, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)

        return GenerationResult(
            text="".join(text_parts).strip(),
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model_id,
            finish_reason=str(finish_reason) if finish_reason else None,
        )

    try:
        return _call(model_name)
    except Exception as exc:
        if model_name != FALLBACK_MODEL:
            logger.warning(
                "gemini_model_failed_falling_back",
                extra={"model": model_name, "fallback": FALLBACK_MODEL, "error": str(exc)},
            )
            return _call(FALLBACK_MODEL)
        raise
