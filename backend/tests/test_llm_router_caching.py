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


class _FakeAnthropicTextBlock:
    """Mimica anthropic SDK TextBlock pra parser identificar."""
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeAnthropicToolUseBlock:
    """Mimica anthropic SDK ToolUseBlock pra parser identificar."""
    def __init__(self, name: str, input_data: dict, block_id: str = "tu_test"):
        self.type = "tool_use"
        self.id = block_id
        self.name = name
        self.input = input_data


class _FakeAnthropicResponse:
    def __init__(self, text: str = "", usage=None, tool_uses: list | None = None):
        self.content: list = []
        if text:
            self.content.append(_FakeAnthropicTextBlock(text))
        for tu in (tool_uses or []):
            self.content.append(_FakeAnthropicToolUseBlock(
                name=tu["name"],
                input_data=tu.get("input", {}),
                block_id=tu.get("id", "tu_test"),
            ))
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


class TestAnthropicToolUseNative:
    """Phase D 2026-05-02: tool-use nativo via param `tools=[...]`."""

    def test_tools_param_propagated_to_anthropic_api(
        self, router_with_anthropic, fake_anthropic,
    ):
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text="",
            tool_uses=[{
                "name": "escalate_to_human_whatsapp",
                "input": {"phone": "5511", "reason": "user pediu humano",
                          "summary": "lead disse PRECISO HUMANO AGORA",
                          "urgency": "P1"},
                "id": "tu_abc123",
            }],
            usage=_FakeAnthropicUsage(input_tokens=200, output_tokens=50,
                                     cache_creation_input_tokens=0,
                                     cache_read_input_tokens=0),
        )

        tools_schema = [{
            "name": "escalate_to_human_whatsapp",
            "description": "test",
            "input_schema": {"type": "object", "properties": {}},
        }]

        result = router_with_anthropic.complete_json(
            task="any_task",
            system="dyn",
            user="quero falar com humano",
            tools=tools_schema,
            tool_choice="auto",
        )

        # Confirma que messages.create recebeu tools= + tool_choice
        call_kwargs = fake_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["tools"] == tools_schema
        assert call_kwargs["tool_choice"] == {"type": "auto"}

        # Result tem o formato estruturado de tool call
        assert result["action"] == "tool"
        assert result["tool_name"] == "escalate_to_human_whatsapp"
        assert result["args"]["urgency"] == "P1"
        assert result["args"]["phone"] == "5511"
        assert result["tool_use_id"] == "tu_abc123"
        assert result["text_after"] == ""

    def test_tool_choice_force_specific_tool(
        self, router_with_anthropic, fake_anthropic,
    ):
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text="",
            tool_uses=[{
                "name": "capture_lead",
                "input": {"phone": "5511", "intent": "interesse_servico_b2c",
                          "full_name": "Douglas"},
                "id": "tu_capture",
            }],
        )

        router_with_anthropic.complete_json(
            task="any_task",
            system="x",
            user="sou douglas",
            tools=[{"name": "capture_lead", "description": "x",
                   "input_schema": {"type": "object"}}],
            tool_choice="capture_lead",  # força específica
        )

        call_kwargs = fake_anthropic.messages.create.call_args.kwargs
        assert call_kwargs["tool_choice"] == {"type": "tool",
                                              "name": "capture_lead"}

    def test_text_with_tool_use_combines(
        self, router_with_anthropic, fake_anthropic,
    ):
        """Modelo pode retornar texto ANTES da tool call."""
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text="Vou conectar você com nossa equipe agora mesmo.",
            tool_uses=[{
                "name": "escalate_to_human_whatsapp",
                "input": {"phone": "5511", "reason": "lead pediu humano",
                         "summary": "...", "urgency": "P2"},
                "id": "tu_1",
            }],
        )

        result = router_with_anthropic.complete_json(
            task="any_task", system="x", user="humano",
            tools=[{"name": "escalate_to_human_whatsapp",
                   "description": "x",
                   "input_schema": {"type": "object"}}],
        )

        assert result["action"] == "tool"
        assert result["tool_name"] == "escalate_to_human_whatsapp"
        assert "conectar" in result["text_after"]

    def test_no_tools_passed_falls_back_to_json_string(
        self, router_with_anthropic, fake_anthropic,
    ):
        """Sem tools=, comportamento legado (JSON-em-string parsed)."""
        fake_anthropic.messages.create.return_value = _FakeAnthropicResponse(
            text='{"action":"text","text":"oi"}',
        )

        result = router_with_anthropic.complete_json(
            task="any_task", system="x", user="hi",
            # NO tools=
        )

        # API call NÃO recebeu tools=
        call_kwargs = fake_anthropic.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

        # Resposta parseada via JSON-em-string
        assert result["action"] == "text"
        assert result["text"] == "oi"


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
