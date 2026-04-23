"""Testes do conversation_history_service.

Componente: src/services/conversation_history_service.py
Escopo: persistência inbound/outbound + janela deslizante + formato LLM.
"""
from __future__ import annotations

import pytest

from src.services.conversation_history_service import (
    ConversationHistoryService,
    get_conversation_history,
)


@pytest.fixture
def svc(mock_db):
    return ConversationHistoryService()


# ══════════════════════════════════════════════════════════════════
# Record inbound
# ══════════════════════════════════════════════════════════════════

class TestRecordInbound:

    def test_inserts_user_message(self, svc, mock_db):
        mock_db.insert_returning_response = {"id": "msg-123"}
        msg_id = svc.record_inbound(
            phone="5511",
            content="oi, sofia",
            channel="whatsapp",
            session_context="onboarding",
        )
        assert msg_id == "msg-123"
        inserts = mock_db.queries_matching("aia_health_conversation_messages")
        assert len(inserts) == 1
        _, params = inserts[0]
        # Params devem conter: inbound, user, whatsapp, onboarding
        assert "inbound" in params
        assert "user" in params
        assert "whatsapp" in params
        assert "onboarding" in params

    def test_records_with_all_metadata(self, svc, mock_db):
        mock_db.insert_returning_response = {"id": "m1"}
        svc.record_inbound(
            phone="5511", content="texto",
            subject_id="subj-1",
            subject_type="patient",
            session_id="sess-1",
            message_format="audio",
            content_raw_ref="s3://bucket/file.ogg",
            external_id="wa-123",
            metadata={"foo": "bar"},
        )
        # Não deve raise

    def test_insert_failure_returns_empty(self, svc, mock_db, monkeypatch):
        def broken(*a, **kw):
            raise RuntimeError("DB offline")
        monkeypatch.setattr(mock_db, "insert_returning", broken)
        msg_id = svc.record_inbound(phone="5511", content="oi")
        assert msg_id == ""


# ══════════════════════════════════════════════════════════════════
# Record outbound
# ══════════════════════════════════════════════════════════════════

class TestRecordOutbound:

    def test_inserts_assistant_message(self, svc, mock_db):
        mock_db.insert_returning_response = {"id": "out-1"}
        msg_id = svc.record_outbound(
            phone="5511",
            content="Olá, prazer!",
            session_context="onboarding",
            processing_agent="sofia_onboarding",
        )
        assert msg_id == "out-1"
        _, params = mock_db.queries_matching("aia_health_conversation_messages")[0]
        assert "outbound" in params
        assert "assistant" in params


# ══════════════════════════════════════════════════════════════════
# Sliding window
# ══════════════════════════════════════════════════════════════════

class TestGetWindow:

    def test_returns_chronological_order(self, svc, mock_db):
        # DB retorna DESC (mais recente primeiro); service deve inverter
        mock_db.fetch_all_response = [
            {"id": "3", "direction": "inbound", "role": "user",
             "content": "terceira", "received_at": "2026-04-23T10:02",
             "channel": "whatsapp", "session_context": "onboarding",
             "message_format": "text", "metadata": None,
             "safety_moderated": False, "processing_agent": None},
            {"id": "2", "direction": "outbound", "role": "assistant",
             "content": "segunda", "received_at": "2026-04-23T10:01",
             "channel": "whatsapp", "session_context": "onboarding",
             "message_format": "text", "metadata": None,
             "safety_moderated": False, "processing_agent": "sofia"},
            {"id": "1", "direction": "inbound", "role": "user",
             "content": "primeira", "received_at": "2026-04-23T10:00",
             "channel": "whatsapp", "session_context": "onboarding",
             "message_format": "text", "metadata": None,
             "safety_moderated": False, "processing_agent": None},
        ]
        window = svc.get_window(phone="5511", limit=5)
        # Após reverse, mais antiga primeiro
        assert window[0]["content"] == "primeira"
        assert window[-1]["content"] == "terceira"

    def test_empty_history_returns_empty_list(self, svc, mock_db):
        mock_db.fetch_all_response = []
        window = svc.get_window(phone="5511")
        assert window == []

    def test_filters_by_session_context(self, svc, mock_db):
        mock_db.fetch_all_response = []
        svc.get_window(phone="5511", session_context="care_event")
        # Verifica que a query incluiu filtro
        queries = mock_db.queries_matching("session_context")
        assert len(queries) >= 1


# ══════════════════════════════════════════════════════════════════
# Formato LLM
# ══════════════════════════════════════════════════════════════════

class TestAsLlmMessages:

    def test_converts_to_openai_format(self, svc):
        window = [
            {"role": "user", "content": "oi", "direction": "inbound"},
            {"role": "assistant", "content": "olá!", "direction": "outbound"},
        ]
        result = svc.as_llm_messages(window)
        assert result == [
            {"role": "user", "content": "oi"},
            {"role": "assistant", "content": "olá!"},
        ]

    def test_prepends_system_message(self, svc):
        window = [
            {"role": "user", "content": "oi", "direction": "inbound"},
        ]
        result = svc.as_llm_messages(window, include_system="Você é Sofia.")
        assert result[0] == {"role": "system", "content": "Você é Sofia."}
        assert result[1]["role"] == "user"

    def test_skips_empty_content(self, svc):
        window = [
            {"role": "user", "content": "", "direction": "inbound"},
            {"role": "user", "content": "   ", "direction": "inbound"},
            {"role": "user", "content": "oi", "direction": "inbound"},
        ]
        result = svc.as_llm_messages(window)
        assert len(result) == 1
        assert result[0]["content"] == "oi"

    def test_infers_role_from_direction(self, svc):
        window = [
            {"role": "unknown", "content": "x", "direction": "inbound"},
            {"role": "unknown", "content": "y", "direction": "outbound"},
        ]
        result = svc.as_llm_messages(window)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"


# ══════════════════════════════════════════════════════════════════
# Count recent + last outbound
# ══════════════════════════════════════════════════════════════════

class TestCountAndLast:

    def test_count_recent_returns_number(self, svc, mock_db):
        mock_db.fetch_one_response = {"n": 42}
        count = svc.count_recent(phone="5511", minutes=60)
        assert count == 42

    def test_count_recent_no_rows_returns_zero(self, svc, mock_db):
        mock_db.fetch_one_response = None
        assert svc.count_recent(phone="5511") == 0

    def test_get_last_outbound(self, svc, mock_db):
        mock_db.fetch_one_response = {
            "id": "x", "content": "última da sofia",
            "received_at": "2026-04-23", "metadata": None,
            "processing_agent": "sofia",
        }
        last = svc.get_last_outbound(phone="5511")
        assert last is not None
        assert last["content"] == "última da sofia"


# ══════════════════════════════════════════════════════════════════
# Mark safety
# ══════════════════════════════════════════════════════════════════

class TestMarkSafety:

    def test_updates_message_safety_flags(self, svc, mock_db):
        svc.mark_safety("msg-123", safety_event_id="evt-1", safety_score={"triggers": ["csam"]})
        updates = mock_db.queries_matching("UPDATE aia_health_conversation_messages")
        assert len(updates) == 1

    def test_empty_message_id_is_noop(self, svc, mock_db):
        svc.mark_safety("", safety_event_id="evt")
        updates = mock_db.queries_matching("UPDATE aia_health_conversation_messages")
        assert len(updates) == 0


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_singleton(self):
        assert get_conversation_history() is get_conversation_history()
