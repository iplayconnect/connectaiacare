"""Persistence helpers — sessões, mensagens, audit, quota.

Reutiliza o mesmo Postgres do connectaiacare-api (DATABASE_URL apontando
pro mesmo container). Mantém escrita simples — sem SQLAlchemy aqui pra
reduzir overhead de boot do container Sofia.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

DSN = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/connectaiacare")
_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 8, DSN)
        psycopg2.extras.register_uuid()
    return _pool


@contextmanager
def cursor(commit: bool = True):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def fetch_one(sql: str, params=()) -> dict | None:
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_all(sql: str, params=()) -> list[dict]:
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def execute(sql: str, params=()) -> None:
    with cursor() as cur:
        cur.execute(sql, params)


def insert_returning(sql: str, params=()) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


# ─── Sessions ─────────────────────────────────────────────

SESSION_INACTIVE_HOURS = 1


def get_or_create_session(
    *,
    tenant_id: str,
    persona: str,
    user_id: str | None = None,
    phone: str | None = None,
    caregiver_id: str | None = None,
    patient_id: str | None = None,
    channel: str = "web",
) -> dict:
    """Retorna sessão ativa < SESSION_INACTIVE_HOURS ou cria nova."""
    where = "tenant_id = %s AND closed_at IS NULL "
    params: list = [tenant_id]
    if user_id:
        where += "AND user_id = %s "
        params.append(user_id)
    elif phone:
        where += "AND phone = %s AND user_id IS NULL "
        params.append(phone)
    else:
        return _create_session(
            tenant_id=tenant_id, persona=persona,
            user_id=user_id, phone=phone,
            caregiver_id=caregiver_id, patient_id=patient_id,
            channel=channel,
        )

    where += "AND last_active_at > NOW() - (%s || ' hours')::interval"
    params.append(str(SESSION_INACTIVE_HOURS))

    row = fetch_one(
        f"""
        SELECT id, persona, channel, user_id, phone, caregiver_id, patient_id, last_active_at
        FROM aia_health_sofia_sessions
        WHERE {where}
        ORDER BY last_active_at DESC
        LIMIT 1
        """,
        tuple(params),
    )
    if row:
        execute(
            "UPDATE aia_health_sofia_sessions SET last_active_at = NOW() WHERE id = %s",
            (row["id"],),
        )
        return row

    return _create_session(
        tenant_id=tenant_id, persona=persona,
        user_id=user_id, phone=phone,
        caregiver_id=caregiver_id, patient_id=patient_id,
        channel=channel,
    )


def _create_session(**kwargs) -> dict:
    return insert_returning(
        """
        INSERT INTO aia_health_sofia_sessions
            (tenant_id, persona, user_id, phone, caregiver_id, patient_id, channel)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, persona, channel, user_id, phone, caregiver_id, patient_id, last_active_at
        """,
        (
            kwargs["tenant_id"], kwargs["persona"], kwargs.get("user_id"),
            kwargs.get("phone"), kwargs.get("caregiver_id"),
            kwargs.get("patient_id"), kwargs.get("channel", "web"),
        ),
    )


def list_recent_messages(session_id: str, limit: int = 30) -> list[dict]:
    """Mensagens em ordem cronológica (mais antigas primeiro)."""
    rows = fetch_all(
        """
        SELECT role, content, tool_name, tool_input, tool_output,
               model, tokens_in, tokens_out, audio_url, audio_duration_ms,
               created_at
        FROM aia_health_sofia_messages
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (session_id, limit),
    )
    return list(reversed(rows))


def append_message(
    *,
    session_id: str,
    tenant_id: str,
    role: str,
    content: str | None = None,
    tool_name: str | None = None,
    tool_input: dict | None = None,
    tool_output: dict | None = None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    audio_url: str | None = None,
    audio_duration_ms: int | None = None,
    metadata: dict | None = None,
) -> int:
    row = insert_returning(
        """
        INSERT INTO aia_health_sofia_messages
            (session_id, tenant_id, role, content,
             tool_name, tool_input, tool_output,
             model, tokens_in, tokens_out,
             audio_url, audio_duration_ms, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            session_id, tenant_id, role, content,
            tool_name,
            psycopg2.extras.Json(tool_input) if tool_input is not None else None,
            psycopg2.extras.Json(tool_output) if tool_output is not None else None,
            model, tokens_in, tokens_out,
            audio_url, audio_duration_ms,
            psycopg2.extras.Json(metadata or {}),
        ),
    )
    return int(row["id"]) if row else 0


# ─── Audit ─────────────────────────────────────────────────

def audit(
    *,
    tenant_id: str,
    session_id: str | None,
    user_id: str | None,
    persona: str | None,
    event_type: str,
    decision: str | None = None,
    details: dict | None = None,
) -> None:
    try:
        execute(
            """
            INSERT INTO aia_health_sofia_audit
                (tenant_id, session_id, user_id, persona, event_type, decision, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id, session_id, user_id, persona,
                event_type, decision,
                psycopg2.extras.Json(details or {}),
            ),
        )
    except Exception as exc:
        logger.warning("audit_insert_failed", extra={"error": str(exc)})


# ─── Quota ─────────────────────────────────────────────────

def record_usage(
    *,
    tenant_id: str,
    user_id: str | None,
    phone: str | None,
    plan_sku: str | None,
    tokens_in: int,
    tokens_out: int,
    audio_seconds: float = 0.0,
    tool_calls: int = 0,
    messages: int = 1,
) -> None:
    if not user_id and not phone:
        return
    now = datetime.now(timezone.utc)
    audio_min = round(audio_seconds / 60.0, 2) if audio_seconds else 0.0
    try:
        if user_id:
            execute(
                """
                INSERT INTO aia_health_sofia_token_usage
                    (tenant_id, user_id, phone, period_year, period_month, plan_sku,
                     messages_count, tokens_in_total, tokens_out_total,
                     audio_minutes_total, tool_calls_count, last_used_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, user_id, period_year, period_month)
                WHERE user_id IS NOT NULL
                DO UPDATE SET
                    messages_count = aia_health_sofia_token_usage.messages_count + EXCLUDED.messages_count,
                    tokens_in_total = aia_health_sofia_token_usage.tokens_in_total + EXCLUDED.tokens_in_total,
                    tokens_out_total = aia_health_sofia_token_usage.tokens_out_total + EXCLUDED.tokens_out_total,
                    audio_minutes_total = aia_health_sofia_token_usage.audio_minutes_total + EXCLUDED.audio_minutes_total,
                    tool_calls_count = aia_health_sofia_token_usage.tool_calls_count + EXCLUDED.tool_calls_count,
                    last_used_at = NOW(),
                    plan_sku = COALESCE(EXCLUDED.plan_sku, aia_health_sofia_token_usage.plan_sku)
                """,
                (
                    tenant_id, user_id, phone, now.year, now.month, plan_sku,
                    messages, tokens_in, tokens_out, audio_min, tool_calls,
                ),
            )
        else:
            execute(
                """
                INSERT INTO aia_health_sofia_token_usage
                    (tenant_id, user_id, phone, period_year, period_month, plan_sku,
                     messages_count, tokens_in_total, tokens_out_total,
                     audio_minutes_total, tool_calls_count, last_used_at)
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, phone, period_year, period_month)
                WHERE user_id IS NULL AND phone IS NOT NULL
                DO UPDATE SET
                    messages_count = aia_health_sofia_token_usage.messages_count + EXCLUDED.messages_count,
                    tokens_in_total = aia_health_sofia_token_usage.tokens_in_total + EXCLUDED.tokens_in_total,
                    tokens_out_total = aia_health_sofia_token_usage.tokens_out_total + EXCLUDED.tokens_out_total,
                    audio_minutes_total = aia_health_sofia_token_usage.audio_minutes_total + EXCLUDED.audio_minutes_total,
                    tool_calls_count = aia_health_sofia_token_usage.tool_calls_count + EXCLUDED.tool_calls_count,
                    last_used_at = NOW(),
                    plan_sku = COALESCE(EXCLUDED.plan_sku, aia_health_sofia_token_usage.plan_sku)
                """,
                (
                    tenant_id, phone, now.year, now.month, plan_sku,
                    messages, tokens_in, tokens_out, audio_min, tool_calls,
                ),
            )
    except Exception as exc:
        logger.warning("usage_record_failed", extra={"error": str(exc)})


def usage_for_user(tenant_id: str, user_id: str | None, phone: str | None) -> dict:
    now = datetime.now(timezone.utc)
    if user_id:
        row = fetch_one(
            """
            SELECT messages_count, tokens_in_total, tokens_out_total,
                   audio_minutes_total, tool_calls_count, plan_sku
            FROM aia_health_sofia_token_usage
            WHERE tenant_id = %s AND user_id = %s
              AND period_year = %s AND period_month = %s
            """,
            (tenant_id, user_id, now.year, now.month),
        )
    elif phone:
        row = fetch_one(
            """
            SELECT messages_count, tokens_in_total, tokens_out_total,
                   audio_minutes_total, tool_calls_count, plan_sku
            FROM aia_health_sofia_token_usage
            WHERE tenant_id = %s AND phone = %s AND user_id IS NULL
              AND period_year = %s AND period_month = %s
            """,
            (tenant_id, phone, now.year, now.month),
        )
    else:
        row = None
    return {
        "year": now.year,
        "month": now.month,
        "messages": int(row["messages_count"]) if row else 0,
        "tokensIn": int(row["tokens_in_total"]) if row else 0,
        "tokensOut": int(row["tokens_out_total"]) if row else 0,
        "audioMinutes": float(row["audio_minutes_total"]) if row else 0.0,
        "toolCalls": int(row["tool_calls_count"]) if row else 0,
        "planSku": row.get("plan_sku") if row else None,
    }
