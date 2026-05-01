"""Tests pra orchestrator + factory + intent classifier (lógica pura).

DB/LLM side-effects mocked.
"""
from __future__ import annotations

from src.services.sofia_agents import get_agent_for
from src.services.sofia_agents.commercial import CommercialSofiaAgent
from src.services.sofia_agents.support import SupportSofiaAgent
from src.services.sofia_agents.passthrough import PassthroughSofiaAgent
from src.services.super_sofia_orchestrator import SuperSofiaOrchestrator
from src.services.whatsapp_intent_classifier import (
    INTENT_BUCKETS, IntentResult,
)


# ──────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────


def test_factory_anonymous_b2c_routes_commercial():
    agent = get_agent_for(
        is_anonymous=True, profile=None, intent="interesse_servico_b2c",
    )
    assert isinstance(agent, CommercialSofiaAgent)


def test_factory_anonymous_b2b_routes_commercial():
    agent = get_agent_for(
        is_anonymous=True, profile=None, intent="interesse_servico_b2b",
    )
    assert isinstance(agent, CommercialSofiaAgent)


def test_factory_anonymous_demo_routes_commercial():
    agent = get_agent_for(
        is_anonymous=True, profile=None, intent="agendar_demo",
    )
    assert isinstance(agent, CommercialSofiaAgent)


def test_factory_anonymous_support_routes_support():
    agent = get_agent_for(
        is_anonymous=True, profile=None, intent="suporte_cliente",
    )
    assert isinstance(agent, SupportSofiaAgent)


def test_factory_anonymous_unclear_routes_commercial():
    """Unclear → commercial (faz pergunta clarificadora)."""
    agent = get_agent_for(
        is_anonymous=True, profile=None, intent="unclear",
    )
    assert isinstance(agent, CommercialSofiaAgent)


def test_factory_identified_routes_passthrough():
    """Phase C v1: perfil identificado → pipeline legado."""
    agent = get_agent_for(
        is_anonymous=False, profile="cuidador_pro",
    )
    assert isinstance(agent, PassthroughSofiaAgent)


def test_factory_admin_routes_passthrough():
    agent = get_agent_for(is_anonymous=False, profile="super_admin")
    assert isinstance(agent, PassthroughSofiaAgent)


# ──────────────────────────────────────────────────────────────────
# Intent classifier — IntentResult validation
# ──────────────────────────────────────────────────────────────────


def test_intent_buckets_complete():
    """Garante que os 6 buckets esperados estão presentes."""
    expected = {
        "interesse_servico_b2c", "interesse_servico_b2b",
        "agendar_demo", "suporte_cliente",
        "spam_abuso", "unclear",
    }
    assert INTENT_BUCKETS == expected


def test_intent_result_uncertain_low_confidence():
    r = IntentResult(
        intent="interesse_servico_b2c", confidence=0.3,
        reasoning="weak signal", duration_ms=100, raw={},
    )
    assert r.is_uncertain is True


def test_intent_result_certain_high_confidence():
    r = IntentResult(
        intent="agendar_demo", confidence=0.9,
        reasoning="clear", duration_ms=100, raw={},
    )
    assert r.is_uncertain is False


def test_intent_result_unclear_always_uncertain():
    r = IntentResult(
        intent="unclear", confidence=0.95,
        reasoning="genuinely ambiguous", duration_ms=100, raw={},
    )
    assert r.is_uncertain is True


# ──────────────────────────────────────────────────────────────────
# Orchestrator — phone/text extraction
# ──────────────────────────────────────────────────────────────────


def test_extract_phone_and_text_text_message():
    event = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "id": "abc",
                "remoteJid": "5551984928518@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {"conversation": "Olá, quero saber sobre a plataforma"},
        },
    }
    phone, text = SuperSofiaOrchestrator._extract_phone_and_text(event)
    assert phone == "5551984928518"
    assert text == "Olá, quero saber sobre a plataforma"


def test_extract_phone_and_text_extended_text():
    event = {
        "data": {
            "key": {"remoteJid": "5511999999999@s.whatsapp.net"},
            "message": {
                "extendedTextMessage": {
                    "text": "msg estendida com link http://example.com",
                },
            },
        },
    }
    phone, text = SuperSofiaOrchestrator._extract_phone_and_text(event)
    assert phone == "5511999999999"
    assert "msg estendida" in text


def test_extract_phone_and_text_no_phone():
    event = {"data": {"message": {"conversation": "x"}}}
    phone, text = SuperSofiaOrchestrator._extract_phone_and_text(event)
    assert phone is None


def test_extract_phone_and_text_audio_no_text():
    event = {
        "data": {
            "key": {"remoteJid": "5551984928518@s.whatsapp.net"},
            "message": {"audioMessage": {"seconds": 10}},
        },
    }
    phone, text = SuperSofiaOrchestrator._extract_phone_and_text(event)
    assert phone == "5551984928518"
    assert text is None
