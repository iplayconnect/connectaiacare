"""Testes do low_confidence_handler.

Componente: src/services/low_confidence_handler.py
Escopo: protocolo 3 degraus + categorias "nunca inventar" (diagnosis/dosage/etc).
"""
from __future__ import annotations

import pytest

from src.services.low_confidence_handler import (
    CONFIDENCE_THRESHOLD_DEGREE_1,
    CONFIDENCE_THRESHOLD_DEGREE_2,
    MAX_ATTEMPTS_BEFORE_HANDOFF,
    LowConfidenceHandler,
    get_low_confidence_handler,
)


class TestNeverInventCategories:
    """Categorias onde Sofia NUNCA responde, sempre escala humano."""

    @pytest.mark.parametrize("text,expected_category", [
        # diagnosis
        ("ela tem câncer?", "diagnosis"),
        ("tenho diabetes grave?", "diagnosis"),
        ("o que ela tem?", "diagnosis"),
        ("qual o diagnóstico?", "diagnosis"),
        # dosage
        ("posso aumentar a dose de losartana?", "dosage"),
        ("quantos mg de dipirona posso tomar?", "dosage"),
        ("dá pra dobrar a dose?", "dosage"),
        ("posso tomar 2 comprimidos?", "dosage"),
        ("posso reduzir a dose?", "dosage"),
        # differential
        ("o que pode ser essa dor no peito?", "differential"),
        ("o que pode estar causando essa tosse?", "differential"),
        # drug_interaction
        ("posso misturar dipirona com paracetamol?", "drug_interaction"),
        ("posso tomar losartana com metformina?", "drug_interaction"),
        # legal_specific
        ("posso processar o médico?", "legal_specific"),
        ("tenho direito a aposentadoria?", "legal_specific"),
    ])
    def test_detects_never_invent_category(self, text, expected_category):
        cat = LowConfidenceHandler._detect_never_invent(text)
        assert cat == expected_category, f"Expected {expected_category} for '{text}', got {cat}"

    @pytest.mark.parametrize("text", [
        "meu nome é Alexandre",
        "minha mãe tem 82 anos",
        "pressão alta e artrose",
        "Maria Silva",
        "51999998888",
        "aceito os termos",
    ])
    def test_normal_text_does_not_trigger(self, text):
        assert LowConfidenceHandler._detect_never_invent(text) is None


class TestEvaluateFlow:
    """Fluxo end-to-end de evaluate() — 3 degraus."""

    def test_degree_3_for_never_invent_category(self, mock_db):
        lc = LowConfidenceHandler()
        decision = lc.evaluate(
            text="posso aumentar a dose de losartana?",
            phone="5511999998888",
        )
        assert decision.should_handle is True
        assert decision.degree == 3
        assert decision.escalate_to_human is True
        assert decision.category == "dosage"
        assert decision.response is not None

    def test_degree_3_after_max_attempts(self, mock_db):
        lc = LowConfidenceHandler()
        decision = lc.evaluate(
            text="texto qualquer",
            phone="5511",
            prior_attempts=MAX_ATTEMPTS_BEFORE_HANDOFF - 1,
        )
        assert decision.degree == 3
        assert decision.escalate_to_human is True

    def test_degree_2_on_very_low_confidence(self, mock_db):
        lc = LowConfidenceHandler()
        decision = lc.evaluate(
            text="algo confuso aqui",
            phone="5511",
            llm_confidence=CONFIDENCE_THRESHOLD_DEGREE_2 - 0.01,
        )
        assert decision.degree == 2
        assert decision.escalate_to_human is False

    def test_degree_1_on_medium_confidence(self, mock_db):
        lc = LowConfidenceHandler()
        decision = lc.evaluate(
            text="pergunta ambígua",
            phone="5511",
            llm_confidence=0.45,
            paraphrase="Você quer saber sobre plano Família",
        )
        assert decision.degree == 1
        assert decision.response is not None
        assert "confirmar" in decision.response.lower() or "entendi" in decision.response.lower()

    def test_no_handling_when_confident(self, mock_db):
        lc = LowConfidenceHandler()
        decision = lc.evaluate(
            text="quero o plano Família",
            phone="5511",
            llm_confidence=0.95,
        )
        assert decision.should_handle is False
        assert decision.degree == 0


class TestHandoffResponses:
    """Mensagens específicas por categoria."""

    @pytest.mark.parametrize("category,must_contain", [
        ("diagnosis", "médico"),
        ("dosage", "dose"),
        ("prescription", "médic"),   # "médica" ou "médico"
        ("differential", "médic"),
        ("drug_interaction", "médico"),
        ("legal_specific", "jurídic"),
        ("generic", "equipe"),
    ])
    def test_response_mentions_category_context(self, category, must_contain):
        msg = LowConfidenceHandler._build_handoff_response(category)
        assert must_contain.lower() in msg.lower(), f"'{must_contain}' missing in {category}"

    def test_unknown_category_falls_back_to_generic(self):
        msg = LowConfidenceHandler._build_handoff_response("inexistente")
        # Fallback é o generic
        assert "equipe" in msg.lower()


class TestTrackingPersistence:
    """Registro em aia_health_safety_events."""

    def test_track_handoff_writes_to_safety_events(self, mock_db):
        lc = LowConfidenceHandler()
        lc._track_handoff(
            phone="5511",
            session_id="abc",
            category="dosage",
            attempts=1,
            reason="never_invent_category",
        )
        inserts = mock_db.queries_matching("aia_health_safety_events")
        assert len(inserts) >= 1, "deveria inserir em safety_events"

    def test_tracking_failure_does_not_raise(self, mock_db, monkeypatch):
        """Se DB falhar, handler não pode quebrar o pipeline."""
        def broken(*a, **kw):
            raise RuntimeError("simulated DB failure")
        monkeypatch.setattr(mock_db, "execute", broken)
        lc = LowConfidenceHandler()
        # Não deve levantar exceção
        lc._track_handoff(
            phone="5511", session_id=None, category="generic",
            attempts=1, reason="test",
        )


class TestSingleton:
    def test_singleton(self):
        assert get_low_confidence_handler() is get_low_confidence_handler()
