"""Testes do conversation_state_manager (CSM).

Componente: src/services/conversation_state_manager.py
Escopo: pending Q/A pairing + validação tipada (CPF, phone, name, age, etc.)
"""
from __future__ import annotations

import pytest

from src.services.conversation_state_manager import (
    ConversationStateManager,
    PendingQuestion,
    get_csm,
)


@pytest.fixture
def csm():
    return ConversationStateManager()


# ══════════════════════════════════════════════════════════════════
# Set / Get / Clear pending
# ══════════════════════════════════════════════════════════════════

class TestPendingLifecycle:

    def test_set_and_get(self, csm):
        csm.set_pending(
            phone="5511", session_id="s1",
            question="CPF?", expected_type="cpf",
            target_field="payer.cpf",
        )
        p = csm.get_pending("5511", "s1")
        assert p is not None
        assert p.expected_type == "cpf"
        assert p.target_field == "payer.cpf"

    def test_clear(self, csm):
        csm.set_pending(
            phone="5511", session_id="s1",
            question="q", expected_type="cpf", target_field="x",
        )
        csm.clear_pending("5511", "s1")
        assert csm.get_pending("5511", "s1") is None

    def test_different_sessions_isolated(self, csm):
        csm.set_pending(phone="5511", session_id="s1",
                       question="q1", expected_type="cpf", target_field="x")
        csm.set_pending(phone="5511", session_id="s2",
                       question="q2", expected_type="name", target_field="y")
        assert csm.get_pending("5511", "s1").expected_type == "cpf"
        assert csm.get_pending("5511", "s2").expected_type == "name"

    def test_increment_attempts(self, csm):
        csm.set_pending(phone="5511", session_id="s1",
                       question="q", expected_type="cpf", target_field="x")
        assert csm.increment_attempts("5511", "s1") == 1
        assert csm.increment_attempts("5511", "s1") == 2

    def test_exceeded_attempts(self, csm):
        csm.set_pending(phone="5511", session_id="s1",
                       question="q", expected_type="cpf", target_field="x",
                       max_attempts=2)
        csm.increment_attempts("5511", "s1")
        csm.increment_attempts("5511", "s1")
        assert csm.exceeded_attempts("5511", "s1") is True


# ══════════════════════════════════════════════════════════════════
# Validação — CPF
# ══════════════════════════════════════════════════════════════════

class TestValidateCPF:

    @pytest.mark.parametrize("cpf", [
        "12345678909",       # válido
        "123.456.789-09",    # válido com formatação
    ])
    def test_valid_cpfs(self, csm, cpf):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="cpf",
                           target_field="cpf")
        result = csm.validate_response(p, cpf)
        assert result.valid is True

    @pytest.mark.parametrize("cpf", [
        "11111111111",       # todos iguais
        "123",               # curto
        "12345678900",       # checksum errado
        "abcdefghijk",       # não numérico
    ])
    def test_invalid_cpfs(self, csm, cpf):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="cpf",
                           target_field="cpf")
        result = csm.validate_response(p, cpf)
        assert result.valid is False
        assert result.clarification is not None


# ══════════════════════════════════════════════════════════════════
# Validação — Nome
# ══════════════════════════════════════════════════════════════════

class TestValidateName:

    def test_full_name_ok(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="name",
                           target_field="name")
        result = csm.validate_response(p, "Maria Silva")
        assert result.valid is True
        assert result.parsed_value == "Maria Silva"

    def test_single_word_name_fails(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="name",
                           target_field="name")
        result = csm.validate_response(p, "Maria")
        assert result.valid is False

    def test_name_with_diacritics(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="name",
                           target_field="name")
        result = csm.validate_response(p, "João Sérgio Gonçalves")
        assert result.valid is True

    def test_rejects_sentence_starting_with_filler(self, csm):
        """'minha mãe Maria Silva' não pode virar full_name."""
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="name",
                           target_field="name")
        result = csm.validate_response(p, "minha mãe Maria Silva")
        assert result.valid is False

    def test_rejects_numbers(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="name",
                           target_field="name")
        result = csm.validate_response(p, "51999998888")
        assert result.valid is False


# ══════════════════════════════════════════════════════════════════
# Validação — Idade
# ══════════════════════════════════════════════════════════════════

class TestValidateAge:

    @pytest.mark.parametrize("text,expected", [
        ("82", 82),
        ("tem 75 anos", 75),
        ("80 aninhos", 80),
        ("é 65", 65),
    ])
    def test_extracts_age_number(self, csm, text, expected):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="age",
                           target_field="age")
        result = csm.validate_response(p, text)
        assert result.valid is True
        assert result.parsed_value == expected

    def test_no_number_fails(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="age",
                           target_field="age")
        result = csm.validate_response(p, "não lembro")
        assert result.valid is False

    def test_age_out_of_range_fails(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="age",
                           target_field="age")
        result = csm.validate_response(p, "150")
        assert result.valid is False


# ══════════════════════════════════════════════════════════════════
# Validação — Yes/No
# ══════════════════════════════════════════════════════════════════

class TestValidateYesNo:

    @pytest.mark.parametrize("text,expected", [
        ("sim", True),
        ("ok", True),
        ("aceito", True),
        ("com certeza", True),
        ("não", False),
        ("nao", False),
        ("recuso", False),
    ])
    def test_detects_yes_no(self, csm, text, expected):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="yes_no",
                           target_field="ok")
        result = csm.validate_response(p, text)
        assert result.valid is True
        assert result.parsed_value is expected

    def test_ambiguous_fails(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="yes_no",
                           target_field="ok")
        result = csm.validate_response(p, "talvez depois")
        assert result.valid is False


# ══════════════════════════════════════════════════════════════════
# Validação — Plan choice
# ══════════════════════════════════════════════════════════════════

class TestValidatePlanChoice:

    @pytest.mark.parametrize("text,expected", [
        ("1", "essencial"),
        ("essencial", "essencial"),
        ("quero o básico", "essencial"),
        ("2", "familia"),
        ("família", "familia"),
        ("plano familia", "familia"),
        ("3", "premium"),
        ("premium", "premium"),
        ("o de 149", "premium"),
        ("4", "premium_device"),
        ("com dispositivo", "premium_device"),
        ("a pulseira", "premium_device"),
    ])
    def test_detects_plan(self, csm, text, expected):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="plan_choice",
                           target_field="plan")
        result = csm.validate_response(p, text)
        assert result.valid is True
        assert result.parsed_value == expected


# ══════════════════════════════════════════════════════════════════
# Validação — Role choice
# ══════════════════════════════════════════════════════════════════

class TestValidateRoleChoice:

    @pytest.mark.parametrize("text,expected", [
        ("pra mim mesmo", "self"),
        ("pra minha mãe", "family"),
        ("meu pai", "family"),
        ("sou enfermeira", "caregiver"),
        ("cuidador profissional", "caregiver"),
    ])
    def test_detects_role(self, csm, text, expected):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="role_choice",
                           target_field="role")
        result = csm.validate_response(p, text)
        assert result.valid is True
        assert result.parsed_value == expected


# ══════════════════════════════════════════════════════════════════
# Validação — CEP
# ══════════════════════════════════════════════════════════════════

class TestValidateCEP:

    @pytest.mark.parametrize("text,expected", [
        ("90010-000", "90010000"),
        ("90010000", "90010000"),
        ("cep é 90010-000", "90010000"),
    ])
    def test_extracts_cep(self, csm, text, expected):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="address_cep",
                           target_field="cep")
        result = csm.validate_response(p, text)
        assert result.valid is True
        assert result.parsed_value == expected


# ══════════════════════════════════════════════════════════════════
# Validação — Texto com opção skip
# ══════════════════════════════════════════════════════════════════

class TestValidateTextWithSkip:

    def test_pular_is_valid(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="text_with_skip",
                           target_field="conditions")
        result = csm.validate_response(p, "pular")
        assert result.valid is True
        assert result.parsed_value is None

    def test_valid_text(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="text_with_skip",
                           target_field="conditions")
        result = csm.validate_response(p, "pressão alta e diabetes")
        assert result.valid is True
        assert result.parsed_value == "pressão alta e diabetes"

    def test_empty_fails(self, csm):
        p = PendingQuestion(phone="5511", session_id="s1",
                           question="q", expected_type="text_with_skip",
                           target_field="conditions")
        result = csm.validate_response(p, "")
        assert result.valid is False


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton(self):
        assert get_csm() is get_csm()
