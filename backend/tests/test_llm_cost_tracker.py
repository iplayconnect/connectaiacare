"""Tests pra llm_cost_tracker — pricing + estimate logic."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.services.llm_cost_tracker import (
    PRICING_USD_PER_M_TOKENS,
    estimate_cost_usd,
)


def test_pricing_table_known_models():
    """Modelos críticos do roadmap precisam estar na tabela."""
    assert ("anthropic", "claude-haiku-3.5") in PRICING_USD_PER_M_TOKENS
    assert ("anthropic", "claude-sonnet-4.6") in PRICING_USD_PER_M_TOKENS
    assert ("deepseek", "deepseek-v4-pro") in PRICING_USD_PER_M_TOKENS
    assert ("deepseek", "deepseek-v4-flash") in PRICING_USD_PER_M_TOKENS
    assert ("gemini", "gemini-2.0-flash") in PRICING_USD_PER_M_TOKENS


def test_estimate_haiku_simple():
    """Haiku 3.5: $0.80/M input, $4/M output."""
    cost = estimate_cost_usd(
        provider="anthropic", model="claude-haiku-3.5",
        prompt_tokens=1_000_000, completion_tokens=0,
    )
    assert cost == Decimal("0.80")


def test_estimate_haiku_output_heavy():
    cost = estimate_cost_usd(
        provider="anthropic", model="claude-haiku-3.5",
        prompt_tokens=0, completion_tokens=1_000_000,
    )
    assert cost == Decimal("4.00")


def test_estimate_deepseek_flash_low_cost():
    """V4-Flash é o mais barato — caso típico intent_classifier."""
    cost = estimate_cost_usd(
        provider="deepseek", model="deepseek-v4-flash",
        prompt_tokens=500, completion_tokens=100,
    )
    # 500 * 0.07 / 1M + 100 * 0.30 / 1M
    expected = Decimal("0.07") * 500 / 1_000_000 + Decimal("0.30") * 100 / 1_000_000
    assert cost == expected
    # Sanity: deve ser menos de 1 cent
    assert cost < Decimal("0.001")


def test_estimate_unknown_model_returns_zero():
    cost = estimate_cost_usd(
        provider="acme", model="unknown-model-9000",
        prompt_tokens=1000, completion_tokens=1000,
    )
    assert cost == Decimal("0")


def test_estimate_zero_tokens_returns_zero():
    cost = estimate_cost_usd(
        provider="anthropic", model="claude-sonnet-4.6",
        prompt_tokens=0, completion_tokens=0,
    )
    assert cost == Decimal("0")
