"""Tests pra UserMemoryWriter (Phase C v2.7)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.services.csm.user_memory import (
    SUMMARIZE_EVERY_N,
    UserMemorySnapshot,
    UserMemoryWriter,
)


@pytest.fixture
def fake_llm():
    llm = MagicMock()
    llm.complete_json.return_value = {
        "summary": "Médica geriatra, atende 30 pacientes/semana. Caso aberto: paciente Maria, dose levodopa.",
        "key_facts": {
            "role_context": "médica geriatria",
            "ongoing_topics": ["caso Maria - levodopa"],
            "preferences": ["respostas curtas"],
        },
    }
    return llm


@pytest.fixture
def writer(fake_llm):
    return UserMemoryWriter(llm=fake_llm)


class TestSnapshot:
    def test_from_row_with_str_facts(self):
        # JSONB às vezes vem como str dependendo do driver
        snap = UserMemorySnapshot.from_row({
            "user_id": "u1", "tenant_id": "t1",
            "summary": "X",
            "key_facts": '{"foo": "bar"}',
            "messages_at_last_summary": 10,
            "total_messages": 15,
        })
        assert snap.key_facts == {"foo": "bar"}

    def test_from_row_with_dict_facts(self):
        snap = UserMemorySnapshot.from_row({
            "user_id": "u1", "tenant_id": "t1",
            "summary": "X",
            "key_facts": {"foo": "bar"},
            "messages_at_last_summary": 0,
            "total_messages": 0,
        })
        assert snap.key_facts == {"foo": "bar"}

    def test_for_prompt_empty(self):
        snap = UserMemorySnapshot(
            user_id="u1", tenant_id="t1", key_facts={},
        )
        assert snap.for_prompt() == ""

    def test_for_prompt_with_data(self):
        snap = UserMemorySnapshot(
            user_id="u1", tenant_id="t1",
            summary="Médica geriatra",
            key_facts={"role": "medico", "topics": ["X", "Y"]},
        )
        out = snap.for_prompt()
        assert "MEMÓRIA_PERSISTENTE" in out
        assert "Médica geriatra" in out
        assert "FATOS_CHAVE" in out


class TestLoad:
    def test_returns_none_when_not_exists(self, writer, mock_db):
        mock_db.fetch_one_response = None
        snap = writer.load("u1")
        assert snap is None

    def test_returns_snapshot(self, writer, mock_db):
        mock_db.fetch_one_response = {
            "user_id": "u1", "tenant_id": "t1",
            "summary": "memo",
            "key_facts": {"foo": "bar"},
            "messages_at_last_summary": 5,
            "total_messages": 10,
            "last_summarized_at": None,
        }
        snap = writer.load("u1")
        assert snap.user_id == "u1"
        assert snap.summary == "memo"
        assert snap.key_facts == {"foo": "bar"}


class TestShouldSummarize:
    def test_first_time_under_threshold(self, writer, mock_db):
        # No memory exists, count = 5 < 10 → False
        def _fetch(query, params):
            if "user_memory" in query:
                return None
            if "COUNT" in query:
                return {"c": 5}
            return None
        mock_db.fetch_one_fn = _fetch
        assert writer.should_summarize("u1") is False

    def test_first_time_at_threshold(self, writer, mock_db):
        def _fetch(query, params):
            if "user_memory" in query:
                return None
            if "COUNT" in query:
                return {"c": SUMMARIZE_EVERY_N}
            return None
        mock_db.fetch_one_fn = _fetch
        assert writer.should_summarize("u1") is True

    def test_subsequent_threshold(self, writer, mock_db):
        # Memory existing with 5 msgs, total now 15 → diff=10 → True
        def _fetch(query, params):
            if "user_memory" in query:
                return {
                    "user_id": "u1", "tenant_id": "t1",
                    "summary": "old", "key_facts": {},
                    "messages_at_last_summary": 5,
                    "total_messages": 5,
                    "last_summarized_at": None,
                }
            if "COUNT" in query:
                return {"c": 15}
            return None
        mock_db.fetch_one_fn = _fetch
        assert writer.should_summarize("u1") is True


class TestSummarize:
    def test_skips_when_not_threshold(self, writer, mock_db, fake_llm):
        # 3 msgs, no prior memory → skip
        def _fetch(query, params):
            if "user_memory" in query:
                return None
            if "COUNT" in query:
                return {"c": 3}
            return None
        mock_db.fetch_one_fn = _fetch
        result = writer.summarize("u1", "t1")
        assert result is None
        fake_llm.complete_json.assert_not_called()

    def test_summarize_force_calls_llm(self, writer, mock_db, fake_llm):
        # force=True bypasses threshold check
        msgs_response_state = {"loaded": False}

        def _fetch_one(query, params):
            if "user_memory" in query:
                if msgs_response_state["loaded"]:
                    # Após upsert, retorna nova snapshot
                    return {
                        "user_id": "u1", "tenant_id": "t1",
                        "summary": "Médica geriatra, atende 30 pacientes/semana. Caso aberto: paciente Maria, dose levodopa.",
                        "key_facts": {"role_context": "médica geriatria"},
                        "messages_at_last_summary": 0,
                        "total_messages": 0,
                        "last_summarized_at": None,
                    }
                return None
            if "COUNT" in query:
                return {"c": 0}
            return None

        def _fetch_all(query, params):
            return [
                {"role": "user", "content": "olá",
                 "created_at": MagicMock()},
                {"role": "assistant", "content": "oi, tudo bem?",
                 "created_at": MagicMock()},
            ]
        mock_db.fetch_one_fn = _fetch_one
        mock_db.fetch_all_fn = _fetch_all

        # Após o execute (upsert), próximo load retorna nova
        original_execute = mock_db.execute

        def _exec(q, p=None):
            original_execute(q, p)
            msgs_response_state["loaded"] = True
        mock_db.execute = _exec

        result = writer.summarize("u1", "t1", force=True)
        assert result is not None
        assert "Médica geriatra" in result.summary
        fake_llm.complete_json.assert_called_once()

    def test_handles_llm_failure(self, writer, mock_db, fake_llm):
        def _fetch_one(query, params):
            if "user_memory" in query:
                return None
            if "COUNT" in query:
                return {"c": 100}
            return None
        mock_db.fetch_one_fn = _fetch_one
        mock_db.fetch_all_response = [
            {"role": "user", "content": "X", "created_at": MagicMock()},
        ]
        fake_llm.complete_json.side_effect = RuntimeError("LLM down")
        result = writer.summarize("u1", "t1", force=True)
        assert result is None

    def test_truncates_long_summary(self, writer, mock_db, fake_llm):
        long_text = "x" * 2000
        fake_llm.complete_json.return_value = {
            "summary": long_text,
            "key_facts": {},
        }

        def _fetch_one(query, params):
            if "user_memory" in query:
                return None
            if "COUNT" in query:
                return {"c": 100}
            return None
        mock_db.fetch_one_fn = _fetch_one
        mock_db.fetch_all_response = [
            {"role": "user", "content": "X", "created_at": MagicMock()},
        ]

        # Captura args do upsert
        executed = []
        original = mock_db.execute

        def _exec(q, p=None):
            executed.append((q, p))
            return original(q, p)
        mock_db.execute = _exec

        writer.summarize("u1", "t1", force=True)
        # Verifica que o summary persistido foi truncado em 800 chars
        upserts = [e for e in executed if "user_memory" in e[0] and "INSERT" in e[0]]
        assert len(upserts) == 1
        params = upserts[0][1]
        # params[2] = summary
        assert len(params[2]) <= 800


class TestMaybeSummarizeAsync:
    def test_no_user_id_skips(self, writer, mock_db, fake_llm):
        writer.maybe_summarize_async(None, "t1")
        fake_llm.complete_json.assert_not_called()

    def test_swallows_exception(self, writer, mock_db, fake_llm):
        def _raise(query, params):
            raise RuntimeError("boom")
        mock_db.fetch_one_fn = _raise
        # Não deve levantar
        writer.maybe_summarize_async("u1", "t1")
