"""Tests pra prompt caching no LLMRouter (Phase D escala).

Foca em:
  • Anthropic: cacheable_system vira system list com cache_control
  • OpenAI/DeepSeek: cacheable_system é mesclado com system (no-op cache)
  • Cache stats (cache_creation_input_tokens, cache_read_input_tokens)
    aparecem no result do complete_json
  • Commercial agent emite duas partes consistentes
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _FakeAnthropicUsage:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeAnthropicResponse:
    def __init__(self, text: str, usage=None):
        block = MagicMock()
        block.text = text
        self.content = [block]
        self.usage = usage


@pytest.fixture
def fake_anthropic():
    """Mock do client Anthropic. Captura args do messages.create."""
    client = MagicMock()
    client.messages = MagicMock()
    return client


@pytest.fixture
def router_with_anthropic(fake_anthropic, monkeypatch):
    """LLMRouter com client Anthropic mockado e config in-memory."""
    from src.services import llm_router

    # Reset singleton pra não pegar instance de outro teste
    llm_router._router_instance = None

    # Patcha o método anthropic() do _Clients pra retornar nosso mock
    original_init = llm_router._Clients.anthropic

    def fake_anthropic_method(self):
        return fake_anthropic

    monkeypatch.setattr(llm_router._Clients, "anthropic", fake_anthropic_method)

    # Patch da config pra ter task de teste
    fake_cfg = MagicMock()
    fake_cfg.task = lambda name: {
        "primary": "anthropic/claude-sonnet-4-6",
        "fallbacks": [],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    fake_cfg.model_meta = lambda key: {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
    }
    fake_cfg.globals = {"on_all_failed": "raise"}

    r = llm_router.LLMRouter()
    r.config = fake_cfg
    return r


class TestAnthropicCacheControl:
    def test_cacheable_system_produces_list_with_cache_control(
        self, router_with_anthropic, fake_anthropic,
    ):
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text='{"action":"text","text":"oi"}',
            usage=_FakeAnthropicUsage(
                input_tokens=100,
                output_tokens=20,
                cache_creation_input_tokens=3000,
                cache_read_input_tokens=0,
            ),
        )

        result = router_with_anthropic.complete_json(
            task="any_task",
            cacheable_system="REGRAS ESTÁTICAS DA SOFIA",
            system="contexto deste turno",
            user="oi",
        )

        # Confirma que messages.create recebeu system como list[dict]
        call_kwargs = fake_anthropic.messages.create.call_args.kwargs
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, list)
        assert len(system_arg) == 2

        # Primeiro bloco: cacheable com cache_control
        assert system_arg[0]["text"] == "REGRAS ESTÁTICAS DA SOFIA"
        assert system_arg[0]["cache_control"] == {"type": "ephemeral"}

        # Segundo bloco: dinâmico, SEM cache_control
        assert system_arg[1]["text"] == "contexto deste turno"
        assert "cache_control" not in system_arg[1]

        # Result expõe métricas de cache
        assert result["_cache_creation_input_tokens"] == 3000
        assert result["_cache_read_input_tokens"] == 0

    def test_no_cacheable_falls_back_to_string_system(
        self, router_with_anthropic, fake_anthropic,
    ):
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text='{"x":1}',
        )

        router_with_anthropic.complete_json(
            task="any_task",
            system="prompt simples sem cache",
            user="oi",
        )

        # Sem cacheable_system, system fica como string (path original)
        call_kwargs = fake_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "prompt simples sem cache"

    def test_cache_hit_logs_read_tokens(
        self, router_with_anthropic, fake_anthropic,
    ):
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text='{"x":1}',
            usage=_FakeAnthropicUsage(
                input_tokens=50,
                output_tokens=20,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=2800,  # 2nd call: cache hit
            ),
        )

        result = router_with_anthropic.complete_json(
            task="any_task",
            cacheable_system="REGRAS X" * 200,
            system="dyn",
            user="oi",
        )
        assert result["_cache_read_input_tokens"] == 2800
        assert result["_cache_creation_input_tokens"] == 0


class TestCommercialAgentPromptParts:
    """O agent commercial separa estática/dinâmica corretamente."""

    def _make_ctx(self, csm_ctx=None):
        from src.services.sofia_agents.base import AgentContext
        fake_tenant = MagicMock()
        fake_tenant.id = "t1"
        return AgentContext(
            phone="5511",
            tenant=fake_tenant,
            identity_match=None,
            trace_id="tr1",
            session_id=None,
            sub_agent="commercial",
            inbound_text="oi",
            active_context_messages=[],
            metadata={"classified_intent": {"intent": "interesse_servico_b2c", "confidence": 0.8}},
            csm_context=csm_ctx or {},
        )

    def test_cacheable_system_is_stable_across_turns(self):
        """A parte estática deve ser igual entre 2 turnos do mesmo persona."""
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx1 = self._make_ctx(csm_ctx={"primeiro_nome": "Ana", "stage": "warmup"})
        ctx2 = self._make_ctx(csm_ctx={"primeiro_nome": "Bruno", "count_idosos": 2})

        cache1 = agent._cacheable_system(ctx1)
        cache2 = agent._cacheable_system(ctx2)
        assert cache1 == cache2  # ESTÁVEL → cache hit no Anthropic

    def test_dynamic_system_changes_with_csm(self):
        """A parte dinâmica deve refletir csm_context."""
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx1 = self._make_ctx(csm_ctx={"primeiro_nome": "Ana", "stage": "warmup"})
        ctx2 = self._make_ctx(csm_ctx={"primeiro_nome": "Bruno", "stage": "qualificacao"})

        dyn1 = agent._dynamic_system(ctx1)
        dyn2 = agent._dynamic_system(ctx2)
        assert dyn1 != dyn2
        assert "warmup" in dyn1
        assert "qualificacao" in dyn2

    def test_cacheable_size_above_anthropic_minimum(self, mock_db):
        """Anthropic exige >= 1024 tokens (~3500-4000 chars PT-BR) pra
        cachear. Em produção, com 6 capabilities seedadas, fica >5000 chars.

        Este teste simula prod injetando seeds no mock_db do conftest.
        """
        from src.services.csm.capabilities import _instance as cap_instance
        # Reset cache do singleton
        from src.services.csm import capabilities as cap_mod
        cap_mod._instance = None

        # Seeds equivalentes ao que migration 062 cria em prod
        mock_db.fetch_all_response = [
            {
                "code": f"feature_{i}",
                "label_user": "feature de teste com label médio aqui",
                "description_full": (
                    "Descrição extensa da feature explicando funcionalidade "
                    "em detalhe pra agent não confundir com outras coisas."
                ),
                "category": "monitoramento",
                "public_facing": True,
                "in_production": True,
                "requires_consent": False,
                "target_personas": ["anonymous", "familia"],
                "notes": None,
            }
            for i in range(6)
        ]

        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = self._make_ctx()
        cacheable = agent._cacheable_system(ctx)
        # ~3.5 chars/token PT-BR. >= 4000 chars garante > 1024 tokens
        # com folga.
        assert len(cacheable) >= 4000, (
            f"Cacheable só tem {len(cacheable)} chars — abaixo do mínimo "
            f"prático pro Anthropic cachear (~4000)."
        )

    def test_system_prompt_full_concat(self):
        """system_prompt() retorna estática + dinâmica concatenadas."""
        from src.services.sofia_agents.commercial import CommercialSofiaAgent
        agent = CommercialSofiaAgent()
        ctx = self._make_ctx(csm_ctx={"stage": "warmup"})
        full = agent.system_prompt(ctx)
        cacheable = agent._cacheable_system(ctx)
        dynamic = agent._dynamic_system(ctx)
        assert cacheable in full
        assert dynamic in full
