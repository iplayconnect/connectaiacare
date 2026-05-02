"""active_context — memória cross-channel cross-turn da Sofia.

Tabela: `aia_health_sofia_active_context` (UNLOGGED, TTL 45min via
expires_at). Mesma usada pelo voice-call-service/services/persistence.

Phase C bug fix 2026-05-02: orquestrador chat NÃO estava persistindo
turnos. Cada msg virava "primeira conversa" → Sofia esquecia nome.

Ordem de chave (mais forte → mais fraca):
    user_id    (auth identity)
    patient_id (paciente associado)
    phone      (anônimo / fallback)

Reusa o que existe — não cria tabela nova.
"""
from __future__ import annotations

from typing import Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_context_key(
    *,
    user_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[str]:
    if user_id:
        return f"user:{user_id}"
    if patient_id:
        return f"patient:{patient_id}"
    if phone:
        return f"phone:{phone}"
    return None


def append_turn(
    *,
    tenant_id: str,
    role: str,                # 'user' | 'assistant' | 'tool'
    content: Optional[str],
    channel: str = "whatsapp",  # 'whatsapp' | 'voice_call' | 'web'
    user_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    phone: Optional[str] = None,
    tool_name: Optional[str] = None,
    ttl_minutes: int = 45,
) -> bool:
    """Persiste 1 turn na tabela active_context. Returns True se ok.

    Best-effort: log warning em falha mas NÃO levanta (não quer
    derrubar request por causa de memory).
    """
    key = _resolve_context_key(user_id=user_id, patient_id=patient_id, phone=phone)
    if not key:
        return False
    if not content and not tool_name:
        return False
    try:
        get_postgres().execute(
            """INSERT INTO aia_health_sofia_active_context
                (tenant_id, user_id, patient_id, context_key, channel,
                 role, content, tool_name, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    NOW() + (%s || ' minutes')::interval)""",
            (
                tenant_id, user_id, patient_id, key, channel, role,
                (content or "")[:500], tool_name, str(ttl_minutes),
            ),
        )
        return True
    except Exception as exc:
        logger.warning(
            "active_context_append_failed",
            error=str(exc)[:200], key=key, role=role,
        )
        return False


def load_recent(
    *,
    user_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    phone: Optional[str] = None,
    limit: int = 12,
) -> list[dict]:
    """Carrega últimos N turnos cross-channel pra contexto. Ordena
    cronologicamente (mais antigo primeiro)."""
    key = _resolve_context_key(user_id=user_id, patient_id=patient_id, phone=phone)
    if not key:
        return []
    try:
        rows = get_postgres().fetch_all(
            """SELECT role, content, channel, tool_name, created_at
               FROM aia_health_sofia_active_context
               WHERE context_key = %s AND expires_at > NOW()
               ORDER BY created_at DESC LIMIT %s""",
            (key, limit),
        )
    except Exception as exc:
        logger.warning("active_context_load_failed", error=str(exc)[:200])
        return []
    out = []
    for r in reversed(rows):
        out.append({
            "role": r.get("role"),
            "content": r.get("content"),
            "channel": r.get("channel"),
            "tool_name": r.get("tool_name"),
        })
    return out
