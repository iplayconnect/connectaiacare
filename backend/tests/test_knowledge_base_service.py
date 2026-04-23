"""Testes do knowledge_base_service.

Componente: src/services/knowledge_base_service.py
Escopo: upsert + search + format_for_prompt + telemetria.

Nota: embedding é mockado (retorna vetor fixo) pra testes determinísticos.
"""
from __future__ import annotations

import pytest

from src.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeResult,
    get_knowledge_base,
)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

class FakeEmbeddings:
    """Mock embedding service: retorna vetor fixo."""
    def __init__(self, dim: int = 768, return_empty: bool = False):
        self.dim = dim
        self.return_empty = return_empty
        self.calls = []

    def embed(self, text: str):
        self.calls.append(("embed", text))
        if self.return_empty:
            return []
        # Vetor determinístico baseado em hash pra tests
        return [hash(text) % 100 / 100.0] * self.dim

    def embed_for_query(self, text: str):
        self.calls.append(("embed_for_query", text))
        if self.return_empty:
            return []
        return [hash(text) % 100 / 100.0] * self.dim


@pytest.fixture
def fake_embeddings():
    return FakeEmbeddings()


@pytest.fixture
def svc(mock_db, fake_embeddings):
    s = KnowledgeBaseService()
    s.embeddings = fake_embeddings
    return s


# ══════════════════════════════════════════════════════════════════
# Upsert
# ══════════════════════════════════════════════════════════════════

class TestUpsertChunk:

    def test_inserts_new_chunk(self, svc, mock_db):
        mock_db.fetch_one_response = None  # não existe ainda
        mock_db.insert_returning_response = {"id": "chunk-1"}
        chunk_id = svc.upsert_chunk(
            domain="plans",
            title="Plano Essencial",
            content="Conteúdo do plano essencial",
            subdomain="plano_essencial",
            keywords=["essencial", "49.90"],
            priority=80,
        )
        assert chunk_id == "chunk-1"
        inserts = mock_db.queries_matching("INSERT INTO aia_health_knowledge_chunks")
        assert len(inserts) == 1

    def test_updates_existing_chunk(self, svc, mock_db):
        mock_db.fetch_one_response = {"id": "existing-1"}
        chunk_id = svc.upsert_chunk(
            domain="plans",
            title="Plano Essencial",
            content="novo conteúdo",
        )
        assert chunk_id == "existing-1"
        updates = mock_db.queries_matching("UPDATE aia_health_knowledge_chunks")
        assert len(updates) == 1

    def test_embedding_failure_stores_null(self, svc, mock_db, fake_embeddings):
        fake_embeddings.return_empty = True
        mock_db.fetch_one_response = None
        mock_db.insert_returning_response = {"id": "x"}
        # Não deve levantar
        svc.upsert_chunk(domain="plans", title="Teste", content="conteúdo")

    def test_vector_format(self, svc):
        # _format_vector → '[0.1,0.2,...]'
        result = svc._format_vector([0.1, 0.2, 0.3])
        assert result.startswith("[")
        assert result.endswith("]")
        assert "," in result


# ══════════════════════════════════════════════════════════════════
# Search
# ══════════════════════════════════════════════════════════════════

class TestSearch:

    def test_empty_query_returns_empty(self, svc):
        assert svc.search("") == []
        assert svc.search("   ") == []

    def test_no_embedding_returns_empty(self, svc, fake_embeddings):
        fake_embeddings.return_empty = True
        assert svc.search("query") == []

    def test_returns_list_of_results(self, svc, mock_db):
        mock_db.fetch_all_response = [
            {
                "id": "c1", "domain": "plans", "subdomain": "essencial",
                "title": "Plano Essencial", "content": "conteúdo",
                "summary": "resumo", "keywords": ["essencial"],
                "priority": 80, "confidence": "high",
                "source_type": "internal_curated",
                "similarity": 0.85,
            },
        ]
        results = svc.search("quanto custa o plano")
        assert len(results) == 1
        assert isinstance(results[0], KnowledgeResult)
        assert results[0].id == "c1"
        assert results[0].similarity == 0.85

    def test_filters_below_min_similarity(self, svc, mock_db):
        mock_db.fetch_all_response = [
            {"id": "c1", "domain": "plans", "subdomain": None,
             "title": "t1", "content": "c1", "summary": None,
             "keywords": [], "priority": 50, "confidence": "high",
             "source_type": None, "similarity": 0.35},  # abaixo do min (0.55)
            {"id": "c2", "domain": "plans", "subdomain": None,
             "title": "t2", "content": "c2", "summary": None,
             "keywords": [], "priority": 50, "confidence": "high",
             "source_type": None, "similarity": 0.65},
        ]
        results = svc.search("qualquer", min_similarity=0.55)
        assert len(results) == 1
        assert results[0].id == "c2"

    def test_respects_top_k(self, svc, mock_db):
        mock_db.fetch_all_response = [
            {"id": f"c{i}", "domain": "plans", "subdomain": None,
             "title": f"t{i}", "content": f"c{i}", "summary": None,
             "keywords": [], "priority": 50, "confidence": "high",
             "source_type": None, "similarity": 0.90 - i * 0.01}
            for i in range(10)
        ]
        results = svc.search("query", top_k=3)
        assert len(results) == 3

    def test_domain_filter_in_query(self, svc, mock_db):
        svc.search("query", domain="compliance")
        queries = mock_db.queries_matching("aia_health_knowledge_chunks")
        assert any("domain = %s" in q[0] for q in queries)

    def test_logs_retrieval(self, svc, mock_db):
        svc.search("query", phone="5511", session_id="s1")
        log_inserts = mock_db.queries_matching("aia_health_kb_retrieval_log")
        assert len(log_inserts) >= 1


# ══════════════════════════════════════════════════════════════════
# Format pra prompt
# ══════════════════════════════════════════════════════════════════

class TestFormatForPrompt:

    def test_empty_returns_empty_string(self):
        assert KnowledgeBaseService.format_for_prompt([]) == ""

    def test_formats_multiple_chunks(self):
        results = [
            KnowledgeResult(
                id="c1", domain="plans", subdomain="essencial",
                title="Plano Essencial", content="Conteúdo A",
                summary=None, similarity=0.9, priority=80,
            ),
            KnowledgeResult(
                id="c2", domain="plans", subdomain="familia",
                title="Plano Família", content="Conteúdo B",
                summary=None, similarity=0.8, priority=85,
            ),
        ]
        formatted = KnowledgeBaseService.format_for_prompt(results)
        assert "CONTEXTO DA BASE DE CONHECIMENTO" in formatted
        assert "[1]" in formatted and "[2]" in formatted
        assert "Plano Essencial" in formatted
        assert "Plano Família" in formatted

    def test_truncates_long_content(self):
        long_content = "x" * 2000
        results = [KnowledgeResult(
            id="c1", domain="plans", subdomain=None,
            title="Teste", content=long_content,
            summary=None, similarity=0.9, priority=50,
        )]
        formatted = KnowledgeBaseService.format_for_prompt(results)
        # Não deve passar muito de 800+header overhead
        assert len(formatted) < 1100


# ══════════════════════════════════════════════════════════════════
# Utilitárias
# ══════════════════════════════════════════════════════════════════

class TestCountByDomain:

    def test_returns_dict_mapping(self, svc, mock_db):
        mock_db.fetch_all_response = [
            {"domain": "plans", "n": 5},
            {"domain": "compliance", "n": 7},
            {"domain": "geriatrics", "n": 9},
        ]
        counts = svc.count_by_domain()
        assert counts == {"plans": 5, "compliance": 7, "geriatrics": 9}


class TestSingleton:
    def test_singleton(self):
        assert get_knowledge_base() is get_knowledge_base()
