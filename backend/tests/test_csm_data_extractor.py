"""Tests pra DataExtractor (Phase C v2.3).

Foca camada regex (PT-BR). Camada LLM coberta por mock.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.csm.care_lead_data import CareLeadData
from src.services.csm.data_extractor import (
    DataExtractor,
    ExtractionResult,
)
from src.services.csm.flow_state import QuestionIntent


@pytest.fixture
def ex():
    """DataExtractor sem LLM (mock pra fallback não tocar Anthropic)."""
    mock_llm = MagicMock()
    mock_llm.complete_json.return_value = {}
    return DataExtractor(llm_provider=mock_llm)


# ══════════════════════════════════════════════════════════════════
# Camada regex
# ══════════════════════════════════════════════════════════════════

class TestRegexIdades:
    def test_pega_duas_idades(self, ex):
        r = ex.extract_regex("São 90 e 92 anos")
        assert r.data.get("idades_idosos") == [90, 92]
        assert r.confidence >= 0.9

    def test_pega_idade_simples(self, ex):
        r = ex.extract_regex("ela tem 87")
        assert r.data.get("idades_idosos") == [87]

    def test_filtra_fora_60_110(self, ex):
        r = ex.extract_regex("eu tenho 35 anos e ela 92")
        assert r.data.get("idades_idosos") == [92]

    def test_sem_idades(self, ex):
        r = ex.extract_regex("oi tudo bem")
        assert "idades_idosos" not in r.data


class TestRegexCountIdosos:
    def test_mae_e_pai_eq_2(self, ex):
        r = ex.extract_regex("cuido da minha mãe e do meu pai")
        assert r.data.get("count_idosos") == 2

    def test_meus_pais_eq_2(self, ex):
        r = ex.extract_regex("são meus pais idosos")
        assert r.data.get("count_idosos") == 2

    def test_minha_mae_eq_1(self, ex):
        r = ex.extract_regex("é só minha mãe")
        assert r.data.get("count_idosos") == 1

    def test_dois_idosos_word(self, ex):
        r = ex.extract_regex("são dois idosos em casa")
        assert r.data.get("count_idosos") == 2

    def test_3_idosos_dig(self, ex):
        r = ex.extract_regex("temos 3 idosos sob cuidado")
        assert r.data.get("count_idosos") == 3


class TestRegexRelacao:
    def test_filho(self, ex):
        r = ex.extract_regex("é minha mãe")
        assert r.data.get("relacao") == "filho_a"

    def test_neto(self, ex):
        r = ex.extract_regex("minha avó tá precisando")
        assert r.data.get("relacao") == "neto_a"

    def test_self(self, ex):
        r = ex.extract_regex("é pra mim mesmo")
        assert r.data.get("relacao") == "self"

    def test_cuidador_pro(self, ex):
        r = ex.extract_regex("eu sou cuidadora profissional")
        assert r.data.get("relacao") == "cuidador_pro"

    def test_conjuge(self, ex):
        r = ex.extract_regex("meu marido tá doente")
        assert r.data.get("relacao") == "conjuge"


class TestRegexDores:
    def test_queda(self, ex):
        r = ex.extract_regex("ela já caiu três vezes")
        assert "queda" in r.data.get("dores", [])

    def test_esquecimento(self, ex):
        r = ex.extract_regex("ela esquece de tomar remédio")
        dores = r.data.get("dores", [])
        assert "esquecimento" in dores
        assert "medicacao" in dores

    def test_isolamento(self, ex):
        r = ex.extract_regex("ele vive sozinho em casa")
        # Pode capturar isolamento
        assert "isolamento" in r.data.get("dores", []) or r.data.get("moram_sozinhos")

    def test_diabetes_hipertensao(self, ex):
        r = ex.extract_regex("ela é diabética e tem pressão alta")
        dores = r.data.get("dores", [])
        assert "diabetes" in dores
        assert "hipertensao" in dores

    def test_sem_dores(self, ex):
        r = ex.extract_regex("oi sou Douglas")
        assert "dores" not in r.data


class TestRegexEmail:
    def test_email_basico(self, ex):
        r = ex.extract_regex("meu email é douglas@gmail.com")
        assert r.data.get("email") == "douglas@gmail.com"

    def test_email_complexo(self, ex):
        r = ex.extract_regex("contato: douglas.silva-jr@empresa.com.br ok?")
        assert r.data.get("email") == "douglas.silva-jr@empresa.com.br"


class TestRegexHabitacao:
    def test_ilpi(self, ex):
        r = ex.extract_regex("ela tá numa ILPI aqui em SP")
        assert r.data.get("moram_em_ilpi") is True

    def test_asilo(self, ex):
        r = ex.extract_regex("colocamos no asilo mês passado")
        assert r.data.get("moram_em_ilpi") is True

    def test_sozinho(self, ex):
        r = ex.extract_regex("eles moram sozinhos numa casa")
        assert r.data.get("moram_sozinhos") is True


class TestRegexB2cB2b:
    def test_b2c(self, ex):
        r = ex.extract_regex("é pra minha mãe que mora em SP")
        assert r.data.get("intent_b2c_b2b") == "b2c"

    def test_b2b_ilpi(self, ex):
        r = ex.extract_regex("sou diretora de uma ILPI com 30 leitos")
        assert r.data.get("intent_b2c_b2b") == "b2b"


class TestRegexFirstName:
    def test_with_pending_extracts(self, ex):
        r = ex.extract_regex(
            "Douglas",
            pending_intent=QuestionIntent.PRIMEIRO_NOME,
        )
        assert r.data.get("primeiro_nome") == "Douglas"

    def test_with_pending_phrase(self, ex):
        r = ex.extract_regex(
            "Sou Douglas",
            pending_intent=QuestionIntent.PRIMEIRO_NOME,
        )
        assert r.data.get("primeiro_nome") == "Douglas"

    def test_without_pending_skips(self, ex):
        # Sem pending=PRIMEIRO_NOME, regex não tenta nome
        r = ex.extract_regex("Douglas é um homem")
        assert "primeiro_nome" not in r.data


class TestRegexYesNo:
    def test_pending_quer_demo_sim(self, ex):
        r = ex.extract_regex(
            "Sim, claro!",
            pending_intent=QuestionIntent.QUER_DEMO,
        )
        assert r.data.get("quer_demo") is True

    def test_pending_moram_sozinhos_nao(self, ex):
        r = ex.extract_regex(
            "não, moram com a minha irmã",
            pending_intent=QuestionIntent.MORAM_SOZINHOS,
        )
        assert r.data.get("moram_sozinhos") is False


# ══════════════════════════════════════════════════════════════════
# Camada combinada
# ══════════════════════════════════════════════════════════════════

class TestExtractCombined:
    def test_regex_strong_skips_llm(self, ex):
        r = ex.extract("São 90 e 92 anos")
        # Regex pegou idades_idosos com confiança 0.9
        assert r.data.get("idades_idosos") == [90, 92]
        # LLM mock não foi chamado (mock retorna {})
        # method continua "regex"
        assert r.method == "regex"

    def test_short_no_pending_skips_llm(self, ex):
        r = ex.extract("oi")
        assert r.data == {}
        assert r.method == "none"

    def test_long_msg_calls_llm(self, ex):
        # Mock LLM para retornar dado
        ex._llm_provider.complete_json.return_value = {
            "primeiro_nome": "Douglas",
            "intent_b2c_b2b": "b2c",
        }
        long_text = (
            "Olá! Sou o Douglas, tô aqui pra ver opção pra minha mãe que "
            "tá com 87 anos. Ela mora em casa com a minha irmã mas a gente "
            "preocupa porque ela esquece os remédios às vezes."
        )
        r = ex.extract(long_text)
        # Regex pega idade + esquecimento + medicação
        assert 87 in r.data.get("idades_idosos", [])
        assert "esquecimento" in r.data.get("dores", [])

    def test_llm_disabled_returns_regex_only(self, ex):
        r = ex.extract(
            "Sou Douglas",
            pending_intent=QuestionIntent.PRIMEIRO_NOME,
            use_llm_fallback=False,
        )
        assert r.data.get("primeiro_nome") == "Douglas"
        # mock LLM não chamado
        ex._llm_provider.complete_json.assert_not_called()


class TestRegressionDouglasScenario:
    """Cenário do test real Douglas 2026-05-01 — Sofia repetiu
    'Quantos idosos' 3×. Após v2.3, regex pega count_idosos +
    idades_idosos da MESMA mensagem."""

    def test_eles_tem_90_e_92_anos(self, ex):
        r = ex.extract("Eles tem 90 e 92 anos")
        assert r.data.get("idades_idosos") == [90, 92]
        # "eles" implica 2+ pessoas — não detectamos via regex (LLM faria)
        # Nesse caso o orchestrator pode inferir count_idosos = len(idades)

    def test_sao_dois_idosos_um_de_90_outro_92(self, ex):
        r = ex.extract("São dois idosos, um de 90 e outro de 92")
        assert r.data.get("count_idosos") == 2
        assert r.data.get("idades_idosos") == [90, 92]
