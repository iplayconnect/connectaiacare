"""Tests pra EmbeddingWorker (Phase C v2.6)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services.csm.embedding_worker import (
    DEFAULT_MODEL_NAME,
    EmbeddingWorker,
    WorkerStats,
)


@pytest.fixture
def fake_embed():
    """Mock do EmbeddingService — retorna 768 floats fake."""
    fake = MagicMock()
    fake.embed.return_value = [0.1] * 768
    return fake


@pytest.fixture
def worker(fake_embed):
    return EmbeddingWorker(batch_size=5, embedding_service=fake_embed)


class TestFetchPending:
    def test_returns_rows_from_db(self, worker, mock_db):
        mock_db.fetch_all_response = [
            {"id": "m1", "content": "olá", "role": "user", "tenant_id": "t1"},
            {"id": "m2", "content": "tudo bem?", "role": "assistant", "tenant_id": "t1"},
        ]
        rows = worker.fetch_pending(limit=5)
        assert len(rows) == 2

    def test_empty_when_db_fails(self, worker, mock_db):
        def _raise(q, p):
            raise RuntimeError("db down")
        mock_db.fetch_all_fn = _raise
        rows = worker.fetch_pending(limit=5)
        assert rows == []


class TestWriteEmbedding:
    def test_writes_with_correct_dim(self, worker, mock_db):
        ok = worker.write_embedding("m1", [0.1] * 768)
        assert ok is True
        # Verifica que UPDATE foi enviado
        updates = mock_db.queries_matching("UPDATE aia_health_sofia_messages")
        assert len(updates) == 1
        # Vector formatado em string [x1,x2,...]
        params = updates[0][1]
        assert params[0].startswith("[") and params[0].endswith("]")
        assert params[1] == DEFAULT_MODEL_NAME
        assert params[2] == "m1"

    def test_rejects_wrong_dim(self, worker, mock_db):
        ok = worker.write_embedding("m1", [0.1] * 100)
        assert ok is False
        # Não deve ter UPDATE
        assert not mock_db.queries_matching("UPDATE aia_health_sofia_messages")

    def test_rejects_empty(self, worker, mock_db):
        ok = worker.write_embedding("m1", [])
        assert ok is False

    def test_db_failure_returns_false(self, worker, mock_db):
        def _raise(q, p):
            raise RuntimeError("conn refused")
        mock_db.fetch_one_fn = _raise

        # Patch execute to raise
        original = mock_db.execute

        def _exec_raise(q, p=None):
            raise RuntimeError("update failed")
        mock_db.execute = _exec_raise

        ok = worker.write_embedding("m1", [0.1] * 768)
        assert ok is False
        mock_db.execute = original


class TestProcessBatch:
    def test_empty_batch(self, worker, mock_db):
        mock_db.fetch_all_response = []
        stats = worker.process_batch()
        assert stats.processed == 0
        assert stats.failed == 0

    def test_processes_all(self, worker, mock_db, fake_embed):
        mock_db.fetch_all_response = [
            {"id": "m1", "content": "olá Sofia", "role": "user"},
            {"id": "m2", "content": "como vai?", "role": "user"},
            {"id": "m3", "content": "tudo bem!", "role": "assistant"},
        ]
        stats = worker.process_batch()
        assert stats.processed == 3
        assert stats.failed == 0
        assert fake_embed.embed.call_count == 3
        # 3 UPDATEs
        updates = mock_db.queries_matching("UPDATE aia_health_sofia_messages")
        assert len(updates) == 3

    def test_skips_empty_content(self, worker, mock_db):
        mock_db.fetch_all_response = [
            {"id": "m1", "content": "  ", "role": "user"},
        ]
        stats = worker.process_batch()
        assert stats.skipped_empty == 1
        assert stats.processed == 0

    def test_failed_embedding_increments_failed(self, worker, mock_db, fake_embed):
        fake_embed.embed.return_value = []  # falha
        mock_db.fetch_all_response = [
            {"id": "m1", "content": "olá", "role": "user"},
        ]
        stats = worker.process_batch()
        assert stats.failed == 1
        assert stats.processed == 0

    def test_truncates_long_content(self, worker, mock_db, fake_embed):
        long_text = "a" * 10000
        mock_db.fetch_all_response = [
            {"id": "m1", "content": long_text, "role": "user"},
        ]
        worker.process_batch()
        # embed chamado com texto truncado em max_text_len (4000 default)
        called_text = fake_embed.embed.call_args[0][0]
        assert len(called_text) == 4000


class TestWorkerStats:
    def test_default(self):
        s = WorkerStats()
        assert s.processed == 0
        assert s.failed == 0
        assert s.skipped_empty == 0
