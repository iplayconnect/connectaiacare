"""Testes do correction_handler.

Componente: src/services/correction_handler.py
Escopo: matching regex em pt-BR para RETRY_LAST / GO_BACK / CANCEL / HUMAN.
Sem DB, sem I/O — tudo puro.
"""
from __future__ import annotations

import pytest

from src.services.correction_handler import (
    CorrectionIntent,
    detect,
    friendly_response,
)


class TestCorrectionRetryLast:
    """Intenção de corrigir o dado recém-informado."""

    @pytest.mark.parametrize("text", [
        "espera, não é isso",
        "pera, não é bem assim",
        "errei",
        "me enganei no CPF",
        "deixa eu corrigir",
        "deixa eu refazer",
        "quero corrigir o nome",
        "tô errado",
        "na verdade é Maria",
        "esse não é",
        "digitei errado",
        "mandei errado",
        "troca o nome",
    ])
    def test_detects_retry_intent(self, text):
        assert detect(text) == CorrectionIntent.RETRY_LAST


class TestCorrectionCancel:
    """Intenção de abortar onboarding."""

    @pytest.mark.parametrize("text", [
        "cancelar",
        "desistir",
        "esquece",
        "parar",
        "deixa pra lá",
        "não quero mais",
        "desisto",
    ])
    def test_detects_cancel_intent(self, text):
        assert detect(text) == CorrectionIntent.CANCEL


class TestCorrectionHuman:
    """Escalação pra atendente humano — prioridade máxima."""

    @pytest.mark.parametrize("text", [
        "humano",
        "quero um atendente",
        "falar com alguém",
        "falar com pessoa",
        "falar com gerente",
        "quero uma pessoa",
        "preciso de um consultor",
    ])
    def test_detects_human_intent(self, text):
        assert detect(text) == CorrectionIntent.HUMAN


class TestCorrectionGoBack:
    """Navegação pra estado anterior."""

    @pytest.mark.parametrize("text", [
        "voltar",
        "volta",
        "passo anterior",
        "etapa anterior",
        "anterior",
    ])
    def test_detects_go_back_intent(self, text):
        assert detect(text) == CorrectionIntent.GO_BACK


class TestCorrectionFalsePositives:
    """Frases normais NÃO devem disparar correction."""

    @pytest.mark.parametrize("text", [
        "minha mãe tem 82 anos",
        "não aceito esses termos",      # 'não' isolado não cancel
        "gostei do plano",
        "Maria Silva",
        "51999998888",
        "pressão alta e diabetes",
    ])
    def test_non_correction_text_returns_none(self, text):
        assert detect(text) is None


class TestCorrectionPriority:
    """Ordem de prioridade: HUMAN > CANCEL > RETRY_LAST > GO_BACK."""

    def test_human_beats_cancel(self):
        # Texto ambíguo — "cancelar e falar com humano"
        assert detect("cancelar e falar com humano") == CorrectionIntent.HUMAN

    def test_cancel_beats_retry(self):
        # "esquece, errei" — cancel tem prioridade
        assert detect("esquece isso, errei tudo") == CorrectionIntent.CANCEL

    def test_retry_beats_go_back(self):
        # "deixa eu corrigir, vou voltar" — retry tem prioridade
        result = detect("deixa eu corrigir, volto depois")
        assert result == CorrectionIntent.RETRY_LAST


class TestCorrectionEdgeCases:

    def test_empty_text_returns_none(self):
        assert detect("") is None
        assert detect("   ") is None

    def test_none_input_returns_none(self):
        # defensivo: tipo do Python pode aceitar None em runtime
        assert detect(None) is None  # type: ignore[arg-type]

    def test_very_long_text_returns_none(self):
        """Textos longos (>120 chars) provavelmente contêm info real, não só correção."""
        long_text = "voltar " + "x" * 150
        assert detect(long_text) is None

    def test_case_insensitive(self):
        assert detect("VOLTAR") == CorrectionIntent.GO_BACK
        assert detect("ErRei") == CorrectionIntent.RETRY_LAST
        assert detect("HUMANO") == CorrectionIntent.HUMAN


class TestFriendlyResponse:
    """Mensagens padrão pra cada intent."""

    def test_all_intents_have_response(self):
        for intent in CorrectionIntent:
            msg = friendly_response(intent)
            assert msg, f"Intent {intent} has empty response"
            assert len(msg) > 10, f"Intent {intent} response too short"

    def test_human_mentions_team(self):
        msg = friendly_response(CorrectionIntent.HUMAN)
        assert "time" in msg.lower() or "atend" in msg.lower() or "pessoa" in msg.lower()

    def test_cancel_is_warm(self):
        msg = friendly_response(CorrectionIntent.CANCEL)
        assert "tudo bem" in msg.lower() or "💙" in msg
