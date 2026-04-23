"""Testes do rate_limit_service.

Componente: src/services/rate_limit_service.py
Escopo: contagem por plano + bypass de emergência + grace window + telemetria.
"""
from __future__ import annotations

import pytest

from src.services.rate_limit_service import (
    DEFAULT_LIMIT_NO_PLAN,
    GRACE_MSGS_PER_DAY,
    PLAN_LIMITS,
    RateLimitService,
    get_rate_limiter,
)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

class FakeHistory:
    """Mock do conversation_history service."""
    def __init__(self, count: int = 0):
        self.count = count
        self.calls = []

    def count_recent(self, phone: str, **kw) -> int:
        self.calls.append((phone, kw))
        return self.count


@pytest.fixture
def svc_with_plan(mock_db, monkeypatch):
    """RateLimitService com DB mockado pra retornar plano específico."""
    def _build(plan: str | None = "premium", usage_count: int = 0):
        if plan is None:
            mock_db.fetch_one_response = None
        else:
            mock_db.fetch_one_response = {"plan_sku": plan}
        svc = RateLimitService()
        svc.history = FakeHistory(count=usage_count)
        return svc
    return _build


# ══════════════════════════════════════════════════════════════════
# Plano lookup
# ══════════════════════════════════════════════════════════════════

class TestPlanLookup:

    def test_fetches_plan_from_subscriptions(self, mock_db):
        mock_db.fetch_one_response = {"plan_sku": "premium"}
        svc = RateLimitService()
        plan = svc._get_plan("5511", "sofiacuida_b2c")
        assert plan == "premium"

    def test_unknown_plan_when_no_subscription(self, mock_db):
        mock_db.fetch_one_response = None
        svc = RateLimitService()
        plan = svc._get_plan("5511", "sofiacuida_b2c")
        assert plan == "unknown"

    def test_db_error_returns_unknown(self, mock_db, monkeypatch):
        def broken(*a, **kw):
            raise RuntimeError("DB down")
        monkeypatch.setattr(mock_db, "fetch_one", broken)
        svc = RateLimitService()
        assert svc._get_plan("5511", "sofiacuida_b2c") == "unknown"


# ══════════════════════════════════════════════════════════════════
# Grace window
# ══════════════════════════════════════════════════════════════════

class TestGracePeriod:

    def test_first_messages_always_pass(self, svc_with_plan):
        svc = svc_with_plan(plan="essencial", usage_count=0)
        check = svc.check(phone="5511")
        assert check.allowed is True
        assert check.reason == "grace_period"

    def test_grace_applies_even_if_limit_would_be_exceeded(self, svc_with_plan):
        # Plano essencial tem limite 30, mas grace = primeiras 3
        svc = svc_with_plan(plan="essencial", usage_count=GRACE_MSGS_PER_DAY - 1)
        check = svc.check(phone="5511")
        assert check.allowed is True
        assert check.reason == "grace_period"


# ══════════════════════════════════════════════════════════════════
# Bypass de emergência
# ══════════════════════════════════════════════════════════════════

class TestEmergencyBypass:

    def test_safety_trigger_bypasses_limit(self, svc_with_plan):
        svc = svc_with_plan(plan="essencial", usage_count=100)
        check = svc.check(
            phone="5511",
            safety_triggers=["suicidal_ideation"],
        )
        assert check.allowed is True
        assert check.reason == "emergency_bypass"

    def test_elder_abuse_trigger_bypasses(self, svc_with_plan):
        svc = svc_with_plan(plan="essencial", usage_count=100)
        check = svc.check(
            phone="5511",
            safety_triggers=["elder_abuse"],
        )
        assert check.allowed is True

    @pytest.mark.parametrize("emergency_text", [
        "ajuda",
        "socorro por favor",
        "emergência aqui",
        "preciso de ajuda urgente",
    ])
    def test_emergency_keyword_bypasses(self, svc_with_plan, emergency_text):
        svc = svc_with_plan(plan="essencial", usage_count=100)
        check = svc.check(phone="5511", text=emergency_text)
        assert check.allowed is True
        assert check.reason == "emergency_bypass"

    def test_active_care_event_bypasses(self, svc_with_plan):
        svc = svc_with_plan(plan="essencial", usage_count=100)
        check = svc.check(phone="5511", has_active_care_event=True)
        assert check.allowed is True
        assert check.reason == "active_care_event"

    def test_irrelevant_trigger_does_not_bypass(self, svc_with_plan):
        """Trigger tipo jailbreak_attempt NÃO deve bypassar limite."""
        svc = svc_with_plan(plan="essencial", usage_count=100)
        check = svc.check(
            phone="5511",
            safety_triggers=["jailbreak_attempt"],
        )
        assert check.allowed is False


# ══════════════════════════════════════════════════════════════════
# Limites por plano
# ══════════════════════════════════════════════════════════════════

class TestPlanLimits:

    @pytest.mark.parametrize("plan,limit", [
        ("essencial", 30),
        ("familia", 60),
        ("premium", 100),
        ("premium_device", 150),
    ])
    def test_plan_limits_match_config(self, plan, limit):
        assert PLAN_LIMITS[plan] == limit

    def test_atente_effectively_unlimited(self):
        assert PLAN_LIMITS["atente"] >= 10_000

    def test_no_plan_uses_default_limit(self, svc_with_plan):
        svc = svc_with_plan(plan=None, usage_count=DEFAULT_LIMIT_NO_PLAN - 1)
        check = svc.check(phone="5511")
        assert check.allowed is True
        assert check.plan == "unknown"

    def test_over_limit_blocks(self, svc_with_plan):
        svc = svc_with_plan(plan="essencial", usage_count=PLAN_LIMITS["essencial"])
        check = svc.check(phone="5511")
        assert check.allowed is False
        assert check.reason == "over_limit"
        assert check.response is not None
        assert "💙" in check.response, "resposta deve ser acolhedora"

    def test_under_limit_allows(self, svc_with_plan):
        svc = svc_with_plan(plan="premium", usage_count=50)
        check = svc.check(phone="5511")
        assert check.allowed is True
        assert check.reason == "ok"
        assert check.used == 50
        assert check.limit == 100


# ══════════════════════════════════════════════════════════════════
# Mensagem de over-limit
# ══════════════════════════════════════════════════════════════════

class TestOverLimitMessage:

    def test_message_is_warm_not_rejecting(self):
        msg = RateLimitService._build_over_limit_message()
        assert "💙" in msg
        assert "que bom" in msg.lower() or "bom" in msg.lower()
        # Menciona alternativa pra emergência
        assert "ajuda" in msg.lower()

    def test_message_does_not_blame_user(self):
        msg = RateLimitService._build_over_limit_message().lower()
        # Nunca culpar o usuário
        assert "muito" not in msg  # "você mandou muitas msgs" → ruim
        assert "excedeu" not in msg
        assert "limite" not in msg  # Não menciona a palavra "limite"


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton(self):
        assert get_rate_limiter() is get_rate_limiter()
