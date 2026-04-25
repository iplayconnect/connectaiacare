"""Gemini wrapper para Sofia Care.

Usa google-generativeai 0.8.x (genai) com modelo gemini-3.1-flash.
Suporta:
  - chat com histórico (multi-turn)
  - tool-use (function-calling) com schema OpenAPI-like
  - TTS quando provider de TTS estiver disponível (separado em tts_client)
  - contagem de tokens via response.usage_metadata

Envs:
  GOOGLE_API_KEY (ou GEMINI_API_KEY)
  SOFIA_LLM_MODEL (default gemini-3.1-flash; fallback gemini-1.5-flash)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Modelos GA suportados (snapshot 2026-04-25):
#   gemini-2.5-flash, gemini-2.5-flash-lite, gemini-flash-latest (alias),
#   gemini-2.0-flash, gemini-3-flash-preview, gemini-3.1-flash-lite-preview,
#   gemini-3.1-flash-live-preview (real-time, p/ Sofia.4 ligações).
# `gemini-3.1-flash` (não-preview) ainda não existe; usamos 2.5 Flash estável.
DEFAULT_MODEL = os.getenv("SOFIA_LLM_MODEL") or "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-flash-latest"


def _api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    key = _api_key()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY required")
    genai.configure(api_key=key)
    _configured = True


@dataclass
class ToolDefinition:
    """Estrutura simples de uma tool registrada no orchestrator/agents."""
    name: str
    description: str
    parameters: dict             # JSON schema
    handler: callable            # função Python que recebe **params e retorna dict


@dataclass
class GenerationResult:
    text: str
    tool_calls: list[dict]       # [{name, args}]
    tokens_in: int
    tokens_out: int
    model: str
    finish_reason: str | None = None


_GEMINI_SCHEMA_ALLOWED_KEYS = {
    "type", "properties", "required", "description",
    "enum", "items", "format", "nullable",
}


def _clean_schema(node):
    """Remove campos do JSON Schema não suportados pelo Gemini.

    Gemini Function Declarations aceita um subset enxuto: type, properties,
    required, description, enum, items, format (limitado), nullable. Coisas
    como minimum, maximum, pattern, minLength, default são rejeitadas com
    'Unknown field for Schema: <campo>'.
    """
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


def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
    """Converte ToolDefinition para o formato do google-generativeai."""
    return [
        {
            "function_declarations": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": _clean_schema(t.parameters),
                }
                for t in tools
            ]
        }
    ]


def _convert_history(messages: list[dict]) -> list[dict]:
    """Converte histórico [{role, content}] pra contents do Gemini.

    Roles: 'user', 'assistant' (vira 'model'), 'tool' (vira function response).
    """
    contents: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            # Gemini usa system_instruction no GenerativeModel; ignora aqui.
            continue
        if role in ("user",):
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role in ("assistant", "model"):
            contents.append({"role": "model", "parts": [{"text": content}]})
        elif role == "tool":
            # function response = result da tool
            tool_name = m.get("tool_name") or "tool"
            try:
                payload = m.get("tool_output") if m.get("tool_output") is not None else content
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {"text": payload}
                contents.append({
                    "role": "user",
                    "parts": [{
                        "function_response": {
                            "name": tool_name,
                            "response": payload,
                        }
                    }],
                })
            except Exception as exc:
                logger.warning("history_tool_convert_failed", extra={"error": str(exc)})
    return contents


def generate(
    *,
    system_prompt: str,
    messages: list[dict],
    tools: list[ToolDefinition] | None = None,
    model: str | None = None,
    temperature: float = 0.4,
    max_output_tokens: int = 1024,
) -> GenerationResult:
    """Chamada one-shot ao modelo. Não chama tools — devolve as solicitadas
    pra o orchestrator decidir o que executar e re-chamar."""
    _ensure_configured()
    model_name = model or DEFAULT_MODEL

    def _call(model_id: str) -> GenerationResult:
        gm = genai.GenerativeModel(
            model_name=model_id,
            system_instruction=system_prompt or None,
            tools=_convert_tools(tools) if tools else None,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            },
        )
        contents = _convert_history(messages)
        resp = gm.generate_content(contents)

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        candidates = getattr(resp, "candidates", None) or []
        finish_reason = None
        if candidates:
            cand = candidates[0]
            finish_reason = getattr(cand, "finish_reason", None)
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                # text
                t = getattr(part, "text", None)
                if t:
                    text_parts.append(t)
                # function_call
                fc = getattr(part, "function_call", None)
                if fc:
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
        # Modelo 3.1-flash pode não estar disponível em todos os tenants/região.
        # Cai pro fallback estável.
        if model_name != FALLBACK_MODEL:
            logger.warning(
                "gemini_model_failed_falling_back",
                extra={"model": model_name, "fallback": FALLBACK_MODEL, "error": str(exc)},
            )
            return _call(FALLBACK_MODEL)
        raise
