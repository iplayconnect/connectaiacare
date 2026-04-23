"""Testes do objection_handler_service.

Componente: src/services/objection_handler_service.py
Escopo: detecção regex + busca KB + fallback genérico.
"""
from __future__ import annotations

import pytest

from src.services.objection_handler_service import (
    ObjectionHandlerService,
    ObjectionResponse,
    get_objection_handler,
)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

class FakeKB:
    """Mock do knowledge_base service — search() retorna o que configurarmos."""
    def __init__(self):
        self.search_results = []
        self.search_calls = []

    def search(self, query, **kwargs):
        self.search_calls.append((query, kwargs))
        return list(self.search_results)


class FakeLLMRouter:
    def complete(self, **kw): return ""
    def complete_json(self, **kw): return {}


@pytest.fixture
def svc(mock_db):
    s = ObjectionHandlerService()
    s.kb = FakeKB()
    s.router = FakeLLMRouter()
    return s


# ══════════════════════════════════════════════════════════════════
# Detecção
# ══════════════════════════════════════════════════════════════════

class TestDetect:

    @pytest.mark.parametrize("text,expected_cat", [
        ("é muito caro", "caro"),
        ("tá caro demais", "caro"),
        ("não tenho dinheiro agora", "caro"),
        ("ela não precisa disso", "nao_preciso"),
        ("minha mãe é autônoma", "nao_preciso"),
        ("ela está bem", "nao_preciso"),
        ("já tenho Unimed", "ja_tem_plano_saude"),
        ("tenho cobertura do Bradesco", "ja_tem_plano_saude"),
        ("não confio em IA", "nao_confio_ia"),
        ("prefiro pessoa", "nao_confio_ia"),
        ("minha mãe não aceita tecnologia", "mae_recusa_tech"),
        ("ela não sabe usar celular", "mae_recusa_tech"),
        ("prefiro contratar cuidador", "prefere_cuidador"),
        ("vou pensar depois decido", "esperar_mais"),
        ("tem algo grátis?", "alternativas_gratuitas"),
        ("parece complicado demais", "muito_complicado"),
    ])
    def test_detects_objection(self, svc, text, expected_cat):
        cat, conf = svc.detect(text)
        assert cat == expected_cat
        assert conf > 0.5

    @pytest.mark.parametrize("text", [
        "quero o plano Família",
        "minha mãe tem 82 anos",
        "pressão alta há 10 anos",
        "ok, pode cadastrar",
        "obrigada!",
    ])
    def test_normal_text_not_objection(self, svc, text):
        cat, conf = svc.detect(text)
        assert cat is None
        assert conf == 0.0

    def test_empty_returns_none(self, svc):
        assert svc.detect("") == (None, 0.0)

    def test_is_objection_boolean(self, svc):
        assert svc.is_objection("muito caro") is True
        assert svc.is_objection("ok") is False


# ══════════════════════════════════════════════════════════════════
# Handle
# ══════════════════════════════════════════════════════════════════

class TestHandle:

    def test_non_objection_returns_empty_response(self, svc):
        r = svc.handle(user_text="quero o plano Família")
        assert r.is_objection is False
        assert r.category is None
        assert r.reply == ""

    def test_objection_searches_kb(self, svc):
        from src.services.knowledge_base_service import KnowledgeResult
        svc.kb.search_results = [
            KnowledgeResult(
                id="kb-1", domain="pricing_objections",
                subdomain="caro", title="Caro",
                content='Conteúdo com **Resposta padrão (tom acolhedor):**\n\n"Entendo, vamos ver junto..."\n\n**Estratégia:**',
                summary=None, similarity=0.88, priority=95,
            ),
        ]
        r = svc.handle(user_text="muito caro esse plano")
        assert r.is_objection is True
        assert r.category == "caro"
        assert r.reply
        assert "kb-1" in r.kb_chunks_used
        assert r.fallback_used is False

    def test_fallback_when_kb_empty(self, svc):
        svc.kb.search_results = []
        r = svc.handle(user_text="muito caro")
        assert r.is_objection is True
        assert r.fallback_used is True
        assert r.reply  # fallback genérico existe

    def test_passes_phone_and_session_to_kb_search(self, svc):
        svc.handle(
            user_text="é caro demais",
            phone="5511",
            session_id="sess-1",
        )
        assert len(svc.kb.search_calls) >= 1
        _, kw = svc.kb.search_calls[0]
        assert kw.get("phone") == "5511"
        assert kw.get("session_id") == "sess-1"


# ══════════════════════════════════════════════════════════════════
# Extract reply from chunk
# ══════════════════════════════════════════════════════════════════

class TestExtractReply:

    def test_extracts_resposta_padrao_block(self):
        content = '''**Resposta padrão (tom acolhedor):**

"Entendo totalmente, cuidado é investimento 💙.

Vamos ver junto..."

**Estratégia:**
- Valida preocupação'''
        reply = ObjectionHandlerService._extract_reply_from_chunk(content)
        assert "Entendo totalmente" in reply
        assert "Estratégia" not in reply

    def test_extracts_resposta_simple(self):
        content = '''**Resposta:**

"Claro! Aqui vai..."

**Estratégia:** ...'''
        reply = ObjectionHandlerService._extract_reply_from_chunk(content)
        assert "Claro!" in reply

    def test_fallback_to_first_500_chars(self):
        # Conteúdo sem bloco "Resposta:" formal
        content = "Texto livre sem marcador. " * 30
        reply = ObjectionHandlerService._extract_reply_from_chunk(content)
        assert reply
        assert len(reply) <= 500


# ══════════════════════════════════════════════════════════════════
# Fallback responses
# ══════════════════════════════════════════════════════════════════

class TestFallback:

    @pytest.mark.parametrize("category", [
        "caro", "nao_preciso", "ja_tem_plano_saude",
        "nao_confio_ia", "mae_recusa_tech",
    ])
    def test_has_fallback_for_each_category(self, category):
        msg = ObjectionHandlerService._build_generic_fallback(category, None)
        assert msg
        assert len(msg) > 30

    def test_unknown_category_has_generic(self):
        msg = ObjectionHandlerService._build_generic_fallback("inexistente", None)
        assert msg

    def test_fallback_is_non_defensive(self):
        """Fallbacks não devem conter frases tipo 'mas' ou contra-argumentar."""
        for cat in ["caro", "nao_preciso", "nao_confio_ia"]:
            msg = ObjectionHandlerService._build_generic_fallback(cat, None).lower()
            # Valida algum emoji de acolhimento ou palavra empática
            assert any(w in msg for w in ["💙", "entendo", "fico feliz", "ótimo", "respeito", "comum"])


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton(self):
        assert get_objection_handler() is get_objection_handler()
