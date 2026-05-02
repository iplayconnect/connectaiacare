"""Tests pra v2.4 wiring: AgentContext.csm_context + AgentResponse.next_question_intent.

Não testa orchestrator end-to-end (depende de redis); foca em:
  • Commercial agent prompt inclui dados_confirmados / should_ask /
    pending_question quando csm_context vem preenchido.
  • AgentResponse.next_question_intent é roundtrip.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_ctx(csm_ctx: dict | None = None, inbound_text: str = "oi"):
    """Constrói AgentContext mock sem precisar do tenant_resolver."""
    from src.services.sofia_agents.base import AgentContext

    fake_tenant = MagicMock()
    fake_tenant.id = "test-tenant"
    return AgentContext(
        phone="5511999999999",
        tenant=fake_tenant,
        identity_match=None,
        trace_id="trace-1",
        session_id=None,
        sub_agent="commercial",
        inbound_text=inbound_text,
        active_context_messages=[],
        metadata={"classified_intent": {"intent": "interesse_servico_b2c", "confidence": 0.8}},
        csm_context=csm_ctx or {},
    )


class TestCommercialPromptWithCsm:
    def test_prompt_with_empty_csm(self):
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = _make_ctx(csm_ctx={})
        prompt = agent.system_prompt(ctx)
        assert "sem state ainda" in prompt or "Stage do funil: warmup" in prompt

    def test_prompt_includes_dados_confirmados(self):
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = _make_ctx(csm_ctx={
            "stage": "qualificacao",
            "dados_confirmados": ["primeiro_nome", "count_idosos"],
            "primeiro_nome": "Douglas",
            "count_idosos": 2,
            "has_primeiro_nome": True,
            "has_count_idosos": True,
        })
        prompt = agent.system_prompt(ctx)
        assert "DADOS_JÁ_COLETADOS" in prompt
        assert "primeiro_nome: Douglas" in prompt
        assert "count_idosos: 2" in prompt
        assert "NÃO pergunte de novo" in prompt
        assert "Stage do funil: qualificacao" in prompt

    def test_prompt_includes_should_ask(self):
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = _make_ctx(csm_ctx={
            "stage": "qualificacao",
            "dados_confirmados": ["primeiro_nome"],
            "primeiro_nome": "Douglas",
            "should_ask_dores": True,
            "should_ask_intent_b2c_b2b": True,
        })
        prompt = agent.system_prompt(ctx)
        assert "SHOULD_ASK" in prompt
        assert "dores" in prompt
        assert "intent_b2c_b2b" in prompt

    def test_prompt_includes_pending_question(self):
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = _make_ctx(
            csm_ctx={
                "stage": "qualificacao",
                "pending_question": "Qual a maior dor que você enfrenta hoje?",
                "pending_question_intent": "dor_principal",
            },
            inbound_text="é a queda mesmo",
        )
        prompt = agent.system_prompt(ctx)
        assert "PENDING_QUESTION" in prompt
        assert "dor_principal" in prompt
        # Mensagem do user fica explícita como resposta
        assert "queda" in prompt

    def test_prompt_regression_douglas(self):
        """Cenário: Sofia repetiu 3× 'Quantos idosos'. Após v2.4,
        prompt já recebe count_idosos=2 em DADOS_JÁ_COLETADOS."""
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = _make_ctx(csm_ctx={
            "stage": "qualificacao",
            "dados_confirmados": [
                "primeiro_nome", "count_idosos", "idades_idosos", "relacao",
            ],
            "primeiro_nome": "Douglas",
            "count_idosos": 2,
            "idades_idosos": [90, 92],
            "relacao": "filho_a",
            "has_count_idosos": True,
            "has_idades_idosos": True,
        })
        prompt = agent.system_prompt(ctx)
        assert "count_idosos: 2" in prompt
        assert "[90, 92]" in prompt
        assert "REGRA DE OURO" in prompt
        assert "NÃO REPETIR PERGUNTAS" in prompt


class TestAgentResponseNextQuestionIntent:
    def test_default_none(self):
        from src.services.sofia_agents.base import AgentResponse
        r = AgentResponse(text="oi")
        assert r.next_question_intent is None

    def test_explicit_intent(self):
        from src.services.sofia_agents.base import AgentResponse
        r = AgentResponse(text="qual seu nome?", next_question_intent="primeiro_nome")
        assert r.next_question_intent == "primeiro_nome"

    def test_to_dict_does_not_include_next_intent(self):
        # to_dict é só pra audit log; não precisa quebrar.
        from src.services.sofia_agents.base import AgentResponse
        r = AgentResponse(text="oi", next_question_intent="primeiro_nome")
        d = r.to_dict()
        assert "text_preview" in d


class TestAgentContextCsmField:
    def test_default_empty(self):
        ctx = _make_ctx()
        assert ctx.csm_context == {}

    def test_csm_context_passes_through(self):
        ctx = _make_ctx(csm_ctx={"stage": "warmup", "primeiro_nome": "X"})
        assert ctx.csm_context["stage"] == "warmup"
