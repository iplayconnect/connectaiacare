"""Sofia Memory Service — memória persistente cross-session por usuário.

Lifecycle:
  1. Sessão inicia → load_user_memory(user_id) → injetar summary + key_facts
     no system_prompt da Sofia.
  2. A cada N mensagens (RESUMMARY_THRESHOLD) OU no close() da sessão →
     update_user_memory(user_id) → roda LLM (Gemini Flash) sobre as
     mensagens NOVAS desde o último resumo + summary anterior → produz
     summary atualizado + key_facts.
  3. Persistido em aia_health_sofia_user_memory.

Opt-in: respeita aia_health_users.sofia_memory_enabled. Se FALSE, todas
as funções viram no-op.

Modelo: GEMINI_MEMORY_MODEL (default gemini-3-flash-preview). Barato e
rápido — ~200 tokens in / 300 out por extração ≈ $0.0005/extração.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from src import persistence
from src.llm_client import generate

logger = logging.getLogger(__name__)

# Default = mesmo modelo do chat (gemini-3-flash-preview). Override via
# SOFIA_MEMORY_MODEL pra usar nano/Lite quando GA. Fallback 2.5 se 3 falhar.
MEMORY_MODEL = (
    os.getenv("SOFIA_MEMORY_MODEL")
    or os.getenv("SOFIA_LLM_MODEL")
    or "gemini-3-flash-preview"
)

# A cada N mensagens novas (user+assistant), re-summariza.
RESUMMARY_THRESHOLD = int(os.getenv("SOFIA_MEMORY_THRESHOLD") or "20")

# Tamanho máximo do summary (chars) injetado no prompt — mantém prompt enxuto
SUMMARY_MAX_CHARS = 800

EXTRACT_PROMPT = """Você é um sumarizador de conversas. Recebe o resumo \
ANTERIOR (se houver) e as mensagens NOVAS, e produz um resumo atualizado \
+ fatos estruturados sobre o usuário.

Regras:
- Resumo: 3-5 frases, foco em CONTEXTO ÚTIL pra próxima conversa (não \
narre tudo, sintetize). Português do Brasil.
- key_facts: extraia SÓ fatos persistentes (preferências, contexto \
profissional, casos/pacientes recorrentes, condições mencionadas, \
preocupações). NÃO repita o que já está em key_facts anteriores se não \
mudou. Sintetize listas longas.
- Nunca invente. Se não aparece nas mensagens, não inclua.

Devolva APENAS JSON válido no formato:
{
  "summary": "...",
  "key_facts": {
    "role_context": "...",
    "preferences": ["..."],
    "ongoing_topics": ["..."],
    "concerns": ["..."],
    "key_patients": ["..."],
    "other": {"...": "..."}
  }
}

Omita qualquer chave de key_facts que não tiver dado."""


def _is_enabled(user_id: str) -> bool:
    """Verifica flag opt-in. Default seguro: desabilita se row não existe."""
    if not user_id:
        return False
    row = persistence.fetch_one(
        "SELECT sofia_memory_enabled FROM aia_health_users WHERE id = %s",
        (user_id,),
    )
    return bool(row and row.get("sofia_memory_enabled"))


def load_user_memory(user_id: str) -> dict | None:
    """Retorna {summary, key_facts, total_messages, last_summarized_at} ou None
    se memória desabilitada/inexistente."""
    if not user_id or not _is_enabled(user_id):
        return None
    row = persistence.fetch_one(
        """SELECT summary, key_facts, total_messages, last_summarized_at,
                  messages_at_last_summary
           FROM aia_health_sofia_user_memory
           WHERE user_id = %s""",
        (user_id,),
    )
    if not row:
        return None
    summary = row.get("summary")
    key_facts = row.get("key_facts") or {}
    if not summary and not key_facts:
        return None
    return {
        "summary": (summary or "")[:SUMMARY_MAX_CHARS],
        "key_facts": key_facts,
        "total_messages": row.get("total_messages") or 0,
        "messages_at_last_summary": row.get("messages_at_last_summary") or 0,
        "last_summarized_at": row.get("last_summarized_at"),
    }


def format_for_prompt(memory: dict | None) -> str:
    """Renderiza memory dict pra ser injetado no system_prompt. Retorna
    string vazia se memory é None."""
    if not memory:
        return ""
    parts = ["\n# MEMÓRIA SOBRE O USUÁRIO (de conversas anteriores)"]
    if memory.get("summary"):
        parts.append(memory["summary"])
    facts = memory.get("key_facts") or {}
    if facts:
        parts.append("\n## Fatos importantes:")
        role_ctx = facts.get("role_context")
        if role_ctx:
            parts.append(f"- Contexto: {role_ctx}")
        for k_label, k_field in [
            ("Preferências", "preferences"),
            ("Tópicos em curso", "ongoing_topics"),
            ("Preocupações", "concerns"),
        ]:
            items = facts.get(k_field) or []
            if items:
                parts.append(f"- {k_label}: " + "; ".join(str(x) for x in items[:5]))
        kp = facts.get("key_patients") or []
        if kp:
            parts.append(f"- Pacientes recorrentes: {len(kp)} referenciados")
        other = facts.get("other") or {}
        if other:
            for k, v in list(other.items())[:3]:
                parts.append(f"- {k}: {v}")
    parts.append(
        "\nUse essa memória implicitamente — não recite os fatos, "
        "apenas demonstre que conhece o contexto."
    )
    return "\n".join(parts)


def _count_new_messages_since(user_id: str, last_count: int) -> int:
    """Quantas mensagens (user+assistant) o user gerou em TODAS as sessões dele,
    pra comparar com last_count."""
    row = persistence.fetch_one(
        """SELECT COUNT(*) AS n
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE s.user_id = %s
             AND m.role IN ('user', 'assistant')""",
        (user_id,),
    )
    total = int(row.get("n") if row else 0)
    return total - last_count, total


def should_resummarize(user_id: str) -> tuple[bool, int, int]:
    """Decide se vale rodar nova extração. Retorna (yes, new_count, total)."""
    if not user_id or not _is_enabled(user_id):
        return False, 0, 0
    row = persistence.fetch_one(
        "SELECT messages_at_last_summary, total_messages "
        "FROM aia_health_sofia_user_memory WHERE user_id = %s",
        (user_id,),
    )
    last_count = int((row or {}).get("messages_at_last_summary") or 0)
    new_count, total = _count_new_messages_since(user_id, last_count)
    return new_count >= RESUMMARY_THRESHOLD, new_count, total


def _fetch_recent_messages_across_sessions(user_id: str, limit: int = 60) -> list[dict]:
    """Últimas N mensagens do user em qualquer sessão dele, mais antigas primeiro."""
    rows = persistence.fetch_all(
        """SELECT m.role, m.content, m.tool_name, m.created_at
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE s.user_id = %s
             AND m.role IN ('user', 'assistant', 'tool')
             AND m.content IS NOT NULL
           ORDER BY m.created_at DESC
           LIMIT %s""",
        (user_id, limit),
    )
    return list(reversed(rows))


def update_user_memory(user_id: str, force: bool = False) -> dict | None:
    """Roda extração via LLM e persiste. Retorna nova memory ou None se
    desabilitado/sem mensagens."""
    if not user_id or not _is_enabled(user_id):
        return None

    yes, new_count, total = should_resummarize(user_id)
    if not (yes or force):
        return None
    if total == 0:
        return None

    # Carrega memória anterior pra prover contexto pro LLM
    prior = load_user_memory(user_id) or {}
    prior_summary = prior.get("summary") or "(sem resumo anterior)"
    prior_facts = prior.get("key_facts") or {}

    # Mensagens recentes — limitamos pra não estourar contexto
    msgs = _fetch_recent_messages_across_sessions(user_id, limit=60)
    if not msgs:
        return None
    msg_lines = []
    for m in msgs:
        role = m.get("role") or "?"
        content = (m.get("content") or "")[:400]
        msg_lines.append(f"[{role}] {content}")
    history_block = "\n".join(msg_lines)

    user_prompt = (
        "RESUMO ANTERIOR:\n"
        f"{prior_summary}\n\n"
        "FATOS ANTERIORES:\n"
        f"{json.dumps(prior_facts, ensure_ascii=False)}\n\n"
        "MENSAGENS NOVAS (cronológicas):\n"
        f"{history_block}\n\n"
        "Devolva o JSON conforme o formato pedido."
    )

    try:
        result = generate(
            system_prompt=EXTRACT_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            model=MEMORY_MODEL,
            max_output_tokens=1500,
            thinking_level="low",
        )
    except Exception as exc:
        logger.warning("memory_extract_llm_failed user_id=%s: %s", user_id, exc)
        return None

    raw = (result.text or "").strip()
    # Aceita resposta com possível ```json ... ``` wrapping
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "memory_extract_parse_failed user_id=%s err=%s raw=%r",
            user_id, exc, raw[:200],
        )
        return None

    new_summary = (parsed.get("summary") or "").strip()[:SUMMARY_MAX_CHARS * 2]
    new_facts = parsed.get("key_facts") or {}
    if not isinstance(new_facts, dict):
        new_facts = {}

    # Upsert
    persistence.execute(
        """INSERT INTO aia_health_sofia_user_memory
            (user_id, tenant_id, summary, key_facts,
             messages_at_last_summary, total_messages, summary_model,
             last_summarized_at)
        VALUES (%s,
                COALESCE((SELECT tenant_id FROM aia_health_users WHERE id = %s),
                         'connectaiacare_demo'),
                %s, %s::jsonb, %s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            summary = EXCLUDED.summary,
            key_facts = EXCLUDED.key_facts,
            messages_at_last_summary = EXCLUDED.messages_at_last_summary,
            total_messages = EXCLUDED.total_messages,
            summary_model = EXCLUDED.summary_model,
            last_summarized_at = NOW()""",
        (
            user_id, user_id,
            new_summary,
            json.dumps(new_facts, ensure_ascii=False),
            total, total, MEMORY_MODEL,
        ),
    )
    logger.info(
        "memory_updated user_id=%s total_messages=%d summary_chars=%d facts_keys=%s",
        user_id, total, len(new_summary), list(new_facts.keys()),
    )
    return {
        "summary": new_summary,
        "key_facts": new_facts,
        "total_messages": total,
    }


def maybe_update_async(user_id: str) -> None:
    """Wrapper que tenta atualizar mas nunca propaga erro/atrasa quem chamou.
    Roda síncronamente (a chamada já está no fim de uma turn → ok bloquear
    ~1s). Pra throughput maior, mover pra ThreadPoolExecutor."""
    if not user_id:
        return
    try:
        update_user_memory(user_id)
    except Exception as exc:
        logger.warning("memory_maybe_update_failed user_id=%s: %s", user_id, exc)
