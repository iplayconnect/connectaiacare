"""LlmCostTracker — registra custo de cada chamada LLM.

Persiste em aia_health_llm_cost_log (migration 061). Dashboard
cross-tenant em /admin/system/health/cost lê e agrega.

Princípio: toda chamada LLM relevante (intent_classifier,
clinical_judge, summarization, etc.) DEVE registrar custo.
Sem isso ficamos cegos quando o burn explode.

Usage:
    tracker = get_llm_cost_tracker()
    tracker.record(
        provider="deepseek",
        model="deepseek-chat",
        task="intent_classifier",
        prompt_tokens=234,
        completion_tokens=56,
        duration_ms=1250,
        tenant_id="connectaiacare_central",
        trace_id=trace_id,
    )

Pricing table embarcada — atualizar manualmente quando tabela
de preços mudar (anual ou semestral).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Pricing table (USD per 1M tokens) — atualizar quando vendor mudar
# ──────────────────────────────────────────────────────────────────
# Última atualização: 2026-05-01

PRICING_USD_PER_M_TOKENS: dict[tuple[str, str], dict] = {
    # Anthropic
    ("anthropic", "claude-haiku-3.5"):  {"input": 0.80,  "output": 4.00},
    ("anthropic", "claude-sonnet-4"):   {"input": 3.00,  "output": 15.00},
    ("anthropic", "claude-sonnet-4.5"): {"input": 3.00,  "output": 15.00},
    ("anthropic", "claude-sonnet-4.6"): {"input": 3.00,  "output": 15.00},
    ("anthropic", "claude-opus-4"):     {"input": 15.00, "output": 75.00},
    ("anthropic", "claude-opus-4.5"):   {"input": 15.00, "output": 75.00},
    ("anthropic", "claude-opus-4.6"):   {"input": 15.00, "output": 75.00},
    ("anthropic", "claude-opus-4.7"):   {"input": 15.00, "output": 75.00},

    # DeepSeek (V4)
    ("deepseek", "deepseek-chat"):       {"input": 0.27, "output": 1.10},  # V4-Pro
    ("deepseek", "deepseek-v4-pro"):     {"input": 0.27, "output": 1.10},
    ("deepseek", "deepseek-v4-flash"):   {"input": 0.07, "output": 0.30},

    # Google Gemini
    ("gemini", "gemini-2.0-flash"):      {"input": 0.10, "output": 0.40},
    ("gemini", "gemini-2.5-pro"):        {"input": 1.25, "output": 10.00},

    # xAI Grok
    ("xai", "grok-voice-think-fast-1.0"): {"input": 0.50, "output": 5.00},
    # Voice realtime: cobra por minuto de áudio também — não cobre aqui;
    # voz é tracked separado em métricas Prometheus voice_call.

    # OpenAI (caso uso pontual)
    ("openai", "gpt-4o-mini"):           {"input": 0.15, "output": 0.60},
    ("openai", "gpt-4o"):                {"input": 2.50, "output": 10.00},
}


def estimate_cost_usd(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Calcula custo em USD baseado na tabela. Retorna 0 se modelo
    desconhecido (loga warning pra atualização da tabela)."""
    pricing = PRICING_USD_PER_M_TOKENS.get((provider, model))
    if not pricing:
        # Tenta normalizar (sem versão minor)
        for (p, m), v in PRICING_USD_PER_M_TOKENS.items():
            if p == provider and model.startswith(m.split("-")[0] + "-"):
                pricing = v
                break
    if not pricing:
        logger.warning(
            "llm_pricing_unknown",
            provider=provider, model=model,
            note="adicionar em PRICING_USD_PER_M_TOKENS"
        )
        return Decimal("0")
    cost_input = Decimal(str(pricing["input"])) * Decimal(prompt_tokens) / Decimal(1_000_000)
    cost_output = Decimal(str(pricing["output"])) * Decimal(completion_tokens) / Decimal(1_000_000)
    return cost_input + cost_output


class LlmCostTracker:
    def __init__(self) -> None:
        self.db = get_postgres()

    def record(
        self,
        *,
        provider: str,
        model: str,
        task: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: Optional[int] = None,
        tenant_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        profile: Optional[str] = None,
        fallback_used: bool = False,
        fallback_from_provider: Optional[str] = None,
        error_class: Optional[str] = None,
    ) -> dict:
        """Persiste 1 linha em aia_health_llm_cost_log. Returns dict
        com cost_usd estimado pra logging."""
        cost = estimate_cost_usd(provider, model, prompt_tokens, completion_tokens)
        try:
            self.db.execute(
                """INSERT INTO aia_health_llm_cost_log (
                    tenant_id, trace_id, session_id, provider, model, task,
                    profile, prompt_tokens, completion_tokens,
                    estimated_cost_usd, duration_ms, fallback_used,
                    fallback_from_provider, error_class
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id, trace_id, session_id, provider, model, task,
                    profile, prompt_tokens, completion_tokens,
                    str(cost), duration_ms, fallback_used,
                    fallback_from_provider, error_class,
                ),
            )
        except Exception as exc:
            # Não derruba a request por causa de cost log
            logger.warning("llm_cost_log_failed", error=str(exc))
        return {
            "provider": provider,
            "model": model,
            "task": task,
            "tokens": prompt_tokens + completion_tokens,
            "cost_usd": float(cost),
        }

    # ── Aggregations (pra dashboard) ──

    def cost_by_tenant_last_n_days(self, n_days: int = 30) -> list[dict]:
        """Total acumulado por tenant. Pra /admin/system/health/cost."""
        rows = self.db.fetch_all(
            """SELECT
                tenant_id,
                COUNT(*) AS calls,
                SUM(prompt_tokens)::bigint AS input_tokens,
                SUM(completion_tokens)::bigint AS output_tokens,
                SUM(estimated_cost_usd) AS cost_usd
              FROM aia_health_llm_cost_log
              WHERE created_at >= NOW() - (%s || ' days')::interval
              GROUP BY tenant_id
              ORDER BY cost_usd DESC NULLS LAST""",
            (str(n_days),),
        )
        for r in rows:
            r["calls"] = int(r.get("calls") or 0)
            r["input_tokens"] = int(r.get("input_tokens") or 0)
            r["output_tokens"] = int(r.get("output_tokens") or 0)
            r["cost_usd"] = float(r.get("cost_usd") or 0)
        return rows

    def cost_by_task_last_n_days(self, n_days: int = 30) -> list[dict]:
        rows = self.db.fetch_all(
            """SELECT task, provider, model,
                      COUNT(*) AS calls,
                      SUM(estimated_cost_usd) AS cost_usd,
                      AVG(duration_ms)::int AS avg_duration_ms
              FROM aia_health_llm_cost_log
              WHERE created_at >= NOW() - (%s || ' days')::interval
              GROUP BY task, provider, model
              ORDER BY cost_usd DESC NULLS LAST""",
            (str(n_days),),
        )
        for r in rows:
            r["calls"] = int(r.get("calls") or 0)
            r["cost_usd"] = float(r.get("cost_usd") or 0)
        return rows

    def daily_burn_last_n_days(self, n_days: int = 30) -> list[dict]:
        rows = self.db.fetch_all(
            """SELECT DATE_TRUNC('day', created_at)::date AS day,
                      COUNT(*) AS calls,
                      SUM(estimated_cost_usd) AS cost_usd
              FROM aia_health_llm_cost_log
              WHERE created_at >= NOW() - (%s || ' days')::interval
              GROUP BY 1
              ORDER BY 1 ASC""",
            (str(n_days),),
        )
        for r in rows:
            v = r.get("day")
            if v and hasattr(v, "isoformat"):
                r["day"] = v.isoformat()
            r["calls"] = int(r.get("calls") or 0)
            r["cost_usd"] = float(r.get("cost_usd") or 0)
        return rows


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_instance: Optional[LlmCostTracker] = None


def get_llm_cost_tracker() -> LlmCostTracker:
    global _instance
    if _instance is None:
        _instance = LlmCostTracker()
    return _instance
