"""Active Context — buffer cross-channel pra Sofia 'continuar a conversa'
mesmo trocando de canal (chat texto, voz browser, ligação).

Idoso fala com Sofia no telefone às 8h30. Filha abre app às 10h e
pergunta "como minha mãe está?". Sofia injeta últimos N turnos da
ligação no system prompt do chat → continua de onde parou.

TTL 45min (configurável). Cleanup automático via scheduler.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from src import persistence

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = int(os.getenv("ACTIVE_CONTEXT_TTL_MIN", "45"))
MAX_TURNS_INJECT = int(os.getenv("ACTIVE_CONTEXT_MAX_TURNS", "8"))


def _resolve_context_key(persona_ctx: dict, patient_id: str | None) -> str | None:
    """Determina chave única pra agrupar conversa cross-channel.
    Prioridade: user_id > phone > patient_id."""
    user_id = persona_ctx.get("user_id")
    if user_id:
        return f"user:{user_id}"
    phone = persona_ctx.get("phone")
    if phone:
        return f"phone:{phone}"
    if patient_id:
        return f"patient:{patient_id}"
    return None


def append_turn(
    *,
    persona_ctx: dict,
    role: str,
    content: str | None,
    channel: str,
    patient_id: str | None = None,
    tool_name: str | None = None,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> None:
    """Empurra um turno pro active context. Não bloqueia se falhar."""
    key = _resolve_context_key(persona_ctx, patient_id)
    if not key:
        return
    if not content and not tool_name:
        return
    try:
        persistence.execute(
            """INSERT INTO aia_health_sofia_active_context
                (tenant_id, user_id, patient_id, context_key, channel,
                 role, content, tool_name, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW() + (%s || ' minutes')::interval)""",
            (
                persona_ctx.get("tenant_id") or "connectaiacare_demo",
                persona_ctx.get("user_id"),
                patient_id or persona_ctx.get("patient_id"),
                key, channel, role,
                (content or "")[:500],
                tool_name,
                str(ttl_minutes),
            ),
        )
    except Exception as exc:
        logger.warning("active_context_append_failed: %s", exc)


def get_recent_turns(
    *, persona_ctx: dict, patient_id: str | None = None,
    max_turns: int = MAX_TURNS_INJECT,
) -> list[dict]:
    """Últimos N turnos cross-channel pra essa key. Mais antigos primeiro."""
    key = _resolve_context_key(persona_ctx, patient_id)
    if not key:
        return []
    rows = persistence.fetch_all(
        """SELECT role, content, channel, tool_name, created_at
           FROM aia_health_sofia_active_context
           WHERE context_key = %s AND expires_at > NOW()
           ORDER BY created_at DESC LIMIT %s""",
        (key, max_turns),
    )
    return list(reversed(rows))


def format_for_prompt(turns: list[dict]) -> str:
    """Renderiza lista de turnos em bloco markdown pra injetar no system prompt."""
    if not turns:
        return ""
    parts = ["\n# CONTEXTO ATIVO (de outros canais nos últimos 45min)"]
    parts.append(
        "Estes turnos vieram de outros canais (chat/voz/ligação). Use pra "
        "manter continuidade — não recite-os, apenas demonstre que conhece "
        "o contexto. Se o usuário trocar de canal, é a MESMA conversa."
    )
    parts.append("")
    for t in turns:
        ch = t.get("channel") or "?"
        role = t.get("role") or "?"
        content = (t.get("content") or "")[:300]
        prefix = f"[{ch}/{role}]"
        if t.get("tool_name"):
            prefix += f" [{t['tool_name']}]"
        parts.append(f"{prefix} {content}")
    return "\n".join(parts)
