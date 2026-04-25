"""Sofia quota service — track de consumo de tokens.

Nesta fase NÃO há enforcement (limit hard). Pacotes serão definidos
após coletar dados reais. A função registra consumo agregado por
mês/user em aia_health_sofia_token_usage via UPSERT.

Caller típico: orchestrator depois de cada round (LLM call concluído).

    quota_service.record_usage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        phone=ctx.phone,
        plan_sku=ctx.plan_sku,
        tokens_in=120,
        tokens_out=380,
        audio_seconds=14.2,
        tool_calls=2,
    )
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _period_keys(now: datetime | None = None) -> tuple[int, int]:
    """(year, month) UTC do consumo. Reset mensal acompanha calendário UTC."""
    now = now or datetime.now(timezone.utc)
    return now.year, now.month


def record_usage(
    *,
    tenant_id: str,
    user_id: str | None = None,
    phone: str | None = None,
    plan_sku: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    audio_seconds: float = 0.0,
    tool_calls: int = 0,
    messages: int = 1,
) -> None:
    """UPSERT idempotente. Se row do mês já existe, incrementa contadores."""
    if not user_id and not phone:
        # Sem identidade não tem como atribuir consumo. Loga e segue.
        logger.warning("quota_record_skip_no_identity", tenant_id=tenant_id)
        return

    year, month = _period_keys()
    audio_minutes = round(audio_seconds / 60.0, 2) if audio_seconds else 0.0

    pg = get_postgres()
    try:
        # Identidade: user_id tem precedência sobre phone (espelha os dois
        # partial indexes únicos da migration 017).
        if user_id:
            pg.execute(
                """
                INSERT INTO aia_health_sofia_token_usage
                    (tenant_id, user_id, phone, period_year, period_month, plan_sku,
                     messages_count, tokens_in_total, tokens_out_total,
                     audio_minutes_total, tool_calls_count, last_used_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, user_id, period_year, period_month)
                WHERE user_id IS NOT NULL
                DO UPDATE SET
                    messages_count    = aia_health_sofia_token_usage.messages_count + EXCLUDED.messages_count,
                    tokens_in_total   = aia_health_sofia_token_usage.tokens_in_total + EXCLUDED.tokens_in_total,
                    tokens_out_total  = aia_health_sofia_token_usage.tokens_out_total + EXCLUDED.tokens_out_total,
                    audio_minutes_total = aia_health_sofia_token_usage.audio_minutes_total + EXCLUDED.audio_minutes_total,
                    tool_calls_count  = aia_health_sofia_token_usage.tool_calls_count + EXCLUDED.tool_calls_count,
                    last_used_at      = NOW(),
                    plan_sku          = COALESCE(EXCLUDED.plan_sku, aia_health_sofia_token_usage.plan_sku)
                """,
                (
                    tenant_id, user_id, phone, year, month, plan_sku,
                    messages, tokens_in, tokens_out, audio_minutes, tool_calls,
                ),
            )
        else:
            pg.execute(
                """
                INSERT INTO aia_health_sofia_token_usage
                    (tenant_id, user_id, phone, period_year, period_month, plan_sku,
                     messages_count, tokens_in_total, tokens_out_total,
                     audio_minutes_total, tool_calls_count, last_used_at)
                VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (tenant_id, phone, period_year, period_month)
                WHERE user_id IS NULL AND phone IS NOT NULL
                DO UPDATE SET
                    messages_count    = aia_health_sofia_token_usage.messages_count + EXCLUDED.messages_count,
                    tokens_in_total   = aia_health_sofia_token_usage.tokens_in_total + EXCLUDED.tokens_in_total,
                    tokens_out_total  = aia_health_sofia_token_usage.tokens_out_total + EXCLUDED.tokens_out_total,
                    audio_minutes_total = aia_health_sofia_token_usage.audio_minutes_total + EXCLUDED.audio_minutes_total,
                    tool_calls_count  = aia_health_sofia_token_usage.tool_calls_count + EXCLUDED.tool_calls_count,
                    last_used_at      = NOW(),
                    plan_sku          = COALESCE(EXCLUDED.plan_sku, aia_health_sofia_token_usage.plan_sku)
                """,
                (
                    tenant_id, phone, year, month, plan_sku,
                    messages, tokens_in, tokens_out, audio_minutes, tool_calls,
                ),
            )
    except Exception as exc:  # noqa: BLE001 — quota nunca quebra fluxo
        logger.error(
            "quota_record_failed",
            tenant_id=tenant_id,
            user_id=user_id,
            error=str(exc),
        )


def get_current_month_usage(
    *,
    tenant_id: str,
    user_id: str | None = None,
    phone: str | None = None,
) -> dict:
    """Retorna o consumo do mês corrente. Útil pra UI mostrar barrinha."""
    year, month = _period_keys()
    where = "WHERE tenant_id = %s AND period_year = %s AND period_month = %s "
    params: list = [tenant_id, year, month]
    if user_id:
        where += "AND user_id = %s"
        params.append(user_id)
    elif phone:
        where += "AND phone = %s AND user_id IS NULL"
        params.append(phone)
    else:
        return _zero_usage(year, month)

    row = get_postgres().fetch_one(
        f"""
        SELECT messages_count, tokens_in_total, tokens_out_total,
               audio_minutes_total, tool_calls_count, plan_sku, last_used_at
        FROM aia_health_sofia_token_usage
        {where}
        """,
        tuple(params),
    )
    if not row:
        return _zero_usage(year, month)
    return {
        "year": year,
        "month": month,
        "messages": int(row["messages_count"]),
        "tokens_in": int(row["tokens_in_total"]),
        "tokens_out": int(row["tokens_out_total"]),
        "audio_minutes": float(row["audio_minutes_total"]),
        "tool_calls": int(row["tool_calls_count"]),
        "plan_sku": row.get("plan_sku"),
        "last_used_at": row["last_used_at"].isoformat() if row.get("last_used_at") else None,
    }


def _zero_usage(year: int, month: int) -> dict:
    return {
        "year": year, "month": month,
        "messages": 0, "tokens_in": 0, "tokens_out": 0,
        "audio_minutes": 0.0, "tool_calls": 0,
        "plan_sku": None, "last_used_at": None,
    }
