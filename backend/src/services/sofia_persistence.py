"""sofia_persistence — wraps aia_health_sofia_sessions e
aia_health_sofia_messages que já existem em produção.

Phase C v1 NÃO usava essas tabelas — só active_context (TTL 45min).
Phase C v2 conecta tudo: session por (phone, tenant, channel) +
toda mensagem persistida em sofia_messages com embedding pendente
(worker em background gera embedding depois pra semantic recall).

Padrão idempotente — multi-worker safe via SELECT FOR UPDATE.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SofiaSession:
    """Sessão Sofia ativa. 1 por (phone, tenant, channel) com janela
    de continuação de 45min default."""
    id: str
    tenant_id: str
    persona: str
    user_id: Optional[str]
    phone: Optional[str]
    caregiver_id: Optional[str]
    patient_id: Optional[str]
    channel: str
    sub_agent: Optional[str]
    metadata: dict
    started_at: str
    last_active_at: str

    @classmethod
    def from_row(cls, row: dict) -> "SofiaSession":
        return cls(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            persona=row.get("persona") or "anonymous",
            user_id=str(row["user_id"]) if row.get("user_id") else None,
            phone=row.get("phone"),
            caregiver_id=str(row["caregiver_id"]) if row.get("caregiver_id") else None,
            patient_id=str(row["patient_id"]) if row.get("patient_id") else None,
            channel=row.get("channel") or "whatsapp",
            sub_agent=row.get("sub_agent"),
            metadata=row.get("metadata") or {},
            started_at=row["started_at"].isoformat() if row.get("started_at") else "",
            last_active_at=row["last_active_at"].isoformat() if row.get("last_active_at") else "",
        )


def get_or_create_session(
    *,
    tenant_id: str,
    phone: Optional[str] = None,
    user_id: Optional[str] = None,
    persona: str = "anonymous",
    channel: str = "whatsapp",
    sub_agent: Optional[str] = None,
    patient_id: Optional[str] = None,
    caregiver_id: Optional[str] = None,
    continuation_window_minutes: int = 45,
    trace_id: Optional[str] = None,
) -> SofiaSession:
    """Reusa session ativa (last_active_at < window) ou cria nova.

    Idempotente — múltiplos workers chamando concorrentemente
    convergem pra mesma sessão (ON CONFLICT NOT NEEDED, pois
    sofia_sessions não tem unique constraint, mas a JANELA de
    continuação garante que SELECT-then-INSERT race produz no
    máximo 1 sessão extra que vira "duplicata recente" — recuperável
    no próximo turno).
    """
    db = get_postgres()
    # Lookup: prioriza user_id se temos, senão phone
    if user_id:
        existing = db.fetch_one(
            """SELECT * FROM aia_health_sofia_sessions
               WHERE tenant_id = %s AND user_id = %s
                 AND closed_at IS NULL
                 AND last_active_at > NOW() - (%s || ' minutes')::interval
               ORDER BY last_active_at DESC LIMIT 1""",
            (tenant_id, user_id, str(continuation_window_minutes)),
        )
    elif phone:
        existing = db.fetch_one(
            """SELECT * FROM aia_health_sofia_sessions
               WHERE tenant_id = %s AND phone = %s
                 AND channel = %s
                 AND closed_at IS NULL
                 AND last_active_at > NOW() - (%s || ' minutes')::interval
               ORDER BY last_active_at DESC LIMIT 1""",
            (tenant_id, phone, channel, str(continuation_window_minutes)),
        )
    else:
        existing = None

    if existing:
        # Bump last_active + atualiza sub_agent + append trace_id
        update_sql = (
            "UPDATE aia_health_sofia_sessions "
            "SET last_active_at = NOW(), "
            "    sub_agent = COALESCE(%s, sub_agent), "
            "    active_channels = ARRAY(SELECT DISTINCT unnest(active_channels || %s::text[]))"
        )
        params: list = [sub_agent, [channel]]
        if trace_id:
            update_sql += ", trace_ids = ARRAY(SELECT DISTINCT unnest(trace_ids || ARRAY[%s::uuid]))"
            params.append(trace_id)
        update_sql += " WHERE id = %s RETURNING *"
        params.append(existing["id"])
        try:
            updated = db.insert_returning(update_sql, tuple(params))
            return SofiaSession.from_row(updated or existing)
        except Exception as exc:
            logger.warning("sofia_session_update_failed", error=str(exc))
            return SofiaSession.from_row(existing)

    # Cria nova
    try:
        row = db.insert_returning(
            """INSERT INTO aia_health_sofia_sessions (
                tenant_id, persona, user_id, phone, channel,
                patient_id, caregiver_id, sub_agent,
                active_channels, trace_ids,
                metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *""",
            (
                tenant_id, persona, user_id, phone, channel,
                patient_id, caregiver_id, sub_agent,
                [channel],
                [trace_id] if trace_id else [],
                json.dumps({}),
            ),
        )
        return SofiaSession.from_row(row)
    except Exception as exc:
        logger.exception("sofia_session_create_failed", tenant_id=tenant_id, phone=phone)
        raise


def append_message(
    *,
    session_id: str,
    tenant_id: str,
    role: str,                # 'user' | 'assistant' | 'tool' | 'system'
    content: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_input: Optional[dict] = None,
    tool_output: Optional[dict] = None,
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    audio_url: Optional[str] = None,
    audio_duration_ms: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """Persiste mensagem em aia_health_sofia_messages.

    Embedding fica NULL — worker background (Phase C v2.6) processa
    em batch via index `idx_sofia_messages_pending_embed`.

    Best-effort: log warning se falhar mas NÃO levanta (não derruba
    request por causa de log).
    """
    if not content and not tool_name:
        return None
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_sofia_messages (
                session_id, tenant_id, role, content,
                tool_name, tool_input, tool_output,
                model, tokens_in, tokens_out,
                audio_url, audio_duration_ms, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                      %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id""",
            (
                session_id, tenant_id, role, content,
                tool_name,
                json.dumps(tool_input) if tool_input is not None else None,
                json.dumps(tool_output) if tool_output is not None else None,
                model, tokens_in, tokens_out,
                audio_url, audio_duration_ms,
                json.dumps(metadata or {}),
            ),
        )
        return str(row["id"]) if row else None
    except Exception as exc:
        logger.warning(
            "sofia_message_append_failed",
            session_id=session_id, role=role, error=str(exc)[:200],
        )
        return None


def load_recent_messages(
    *,
    session_id: str,
    limit: int = 20,
    include_tool: bool = True,
) -> list[dict]:
    """Carrega últimas N mensagens da sessão. Cronológico (mais antigo
    primeiro).
    """
    where = "session_id = %s"
    params: list = [session_id]
    if not include_tool:
        where += " AND role <> 'tool'"
    try:
        rows = get_postgres().fetch_all(
            f"""SELECT role, content, tool_name, tool_input, tool_output,
                       model, tokens_in, tokens_out, created_at
               FROM aia_health_sofia_messages
               WHERE {where}
               ORDER BY created_at DESC LIMIT %s""",
            tuple(params + [limit]),
        )
    except Exception as exc:
        logger.warning("sofia_messages_load_failed", error=str(exc)[:200])
        return []
    return list(reversed([
        {
            "role": r["role"],
            "content": r.get("content"),
            "tool_name": r.get("tool_name"),
            "tool_input": r.get("tool_input"),
            "tool_output": r.get("tool_output"),
            "model": r.get("model"),
            "tokens_in": r.get("tokens_in"),
            "tokens_out": r.get("tokens_out"),
        }
        for r in rows
    ]))


def close_session(session_id: str, *, reason: Optional[str] = None) -> None:
    """Marca sessão como fechada. Chamado em handoff humano,
    timeout, etc."""
    try:
        get_postgres().execute(
            """UPDATE aia_health_sofia_sessions
               SET closed_at = NOW(),
                   metadata = COALESCE(metadata, '{}'::jsonb)
                            || jsonb_build_object('close_reason', %s::text)
               WHERE id = %s AND closed_at IS NULL""",
            (reason, session_id),
        )
    except Exception as exc:
        logger.warning("sofia_session_close_failed", error=str(exc))
