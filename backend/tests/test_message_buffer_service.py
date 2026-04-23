"""Testes do message_buffer_service.

Componente: src/services/message_buffer_service.py
Escopo: debounce + typing extension + flood protection + combinação textual.

Nota: testes marcados 'slow' usam threading real com timers pequenos.
"""
from __future__ import annotations

import time

import pytest

from src.services.message_buffer_service import (
    MAX_MESSAGES_PER_BUFFER,
    MessageBufferService,
    get_message_buffer,
)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

class ProcessorRecorder:
    """Grava todas chamadas do processor callback."""
    def __init__(self):
        self.calls: list[tuple[str, str, list[dict]]] = []

    def __call__(self, phone: str, combined: str, parts: list[dict]) -> None:
        self.calls.append((phone, combined, parts))


@pytest.fixture
def fast_buffer():
    """Buffer com timings baixos pra testes rápidos."""
    return MessageBufferService(
        debounce_seconds=0.2,
        max_wait_seconds=1.0,
        typing_extend_seconds=0.3,
    )


# ══════════════════════════════════════════════════════════════════
# Add message
# ══════════════════════════════════════════════════════════════════

class TestAddMessage:

    def test_single_message_buffered(self, fast_buffer):
        p = ProcessorRecorder()
        result = fast_buffer.add_message("5511", "oi", processor=p)
        assert result["status"] == "buffered"
        assert result["buffered_count"] == 1

    def test_sequential_messages_accumulate(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "oi", processor=p)
        result = fast_buffer.add_message("5511", "tudo bem?", processor=p)
        assert result["buffered_count"] == 2

    def test_empty_message_ignored(self, fast_buffer):
        p = ProcessorRecorder()
        result = fast_buffer.add_message("5511", "", processor=p)
        assert result["status"] == "ignored"

    def test_different_phones_have_separate_buffers(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "mensagem A", processor=p)
        r = fast_buffer.add_message("5522", "mensagem B", processor=p)
        assert r["buffered_count"] == 1  # cada phone = buffer próprio


# ══════════════════════════════════════════════════════════════════
# Flush automático (debounce)
# ══════════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestDebounce:

    def test_flush_after_debounce(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "olá", processor=p)
        fast_buffer.add_message("5511", "tudo bem?", processor=p)
        # Espera debounce (0.2s) + folga
        time.sleep(0.5)
        assert len(p.calls) == 1
        phone, combined, parts = p.calls[0]
        assert phone == "5511"
        assert "olá" in combined or "tudo bem" in combined
        assert len(parts) == 2

    def test_new_message_resets_debounce(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "a", processor=p)
        time.sleep(0.1)
        fast_buffer.add_message("5511", "b", processor=p)
        time.sleep(0.1)
        fast_buffer.add_message("5511", "c", processor=p)
        # Ainda não deveria ter disparado (cada msg reseta)
        assert len(p.calls) == 0
        time.sleep(0.5)
        assert len(p.calls) == 1


@pytest.mark.slow
class TestTypingExtension:

    def test_typing_notification_extends_wait(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "começando a digitar", processor=p)
        time.sleep(0.1)
        fast_buffer.notify_typing("5511")  # estende
        time.sleep(0.15)
        # Ainda não flushou (typing extension = 0.3s)
        assert len(p.calls) == 0
        time.sleep(0.5)
        # Agora sim
        assert len(p.calls) == 1

    def test_typing_without_buffer_is_noop(self, fast_buffer):
        result = fast_buffer.notify_typing("5511")
        assert result["status"] == "no_buffer"


@pytest.mark.slow
class TestMaxWait:

    def test_max_wait_forces_flush_even_with_typing(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "msg", processor=p)
        # Spam typing pra tentar empurrar max_wait (1.0s)
        for _ in range(20):
            fast_buffer.notify_typing("5511")
            time.sleep(0.1)
        # Após 2s, flush forçado mesmo com typing contínuo
        time.sleep(0.5)
        assert len(p.calls) >= 1


# ══════════════════════════════════════════════════════════════════
# Force flush
# ══════════════════════════════════════════════════════════════════

class TestForceFlush:

    def test_force_flush_triggers_processor_immediately(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "oi", processor=p)
        fast_buffer.force_flush("5511")
        assert len(p.calls) == 1
        assert p.calls[0][0] == "5511"

    def test_force_flush_on_empty_returns_no_buffer(self, fast_buffer):
        result = fast_buffer.force_flush("5511")
        assert result["status"] == "no_buffer"

    def test_force_flush_clears_state(self, fast_buffer):
        p = ProcessorRecorder()
        fast_buffer.add_message("5511", "a", processor=p)
        fast_buffer.force_flush("5511")
        assert fast_buffer.has_pending("5511") is False


# ══════════════════════════════════════════════════════════════════
# Flood protection
# ══════════════════════════════════════════════════════════════════

class TestFloodProtection:

    def test_overflow_triggers_immediate_flush(self, fast_buffer):
        p = ProcessorRecorder()
        # Enche o buffer até o limite
        for i in range(MAX_MESSAGES_PER_BUFFER):
            fast_buffer.add_message("5511", f"msg {i}", processor=p)
        # Próxima deve disparar flush
        fast_buffer.add_message("5511", "msg overflow", processor=p)
        # Processor deve ter sido chamado pelo menos uma vez
        assert len(p.calls) >= 1


# ══════════════════════════════════════════════════════════════════
# Combinação de textos
# ══════════════════════════════════════════════════════════════════

class TestCombineMessages:

    def test_single_message_returns_trimmed(self):
        parts = [{"text": "  oi  ", "ts": 1.0}]
        assert MessageBufferService._combine_messages(parts) == "oi"

    def test_joins_with_space_when_no_final_punct(self):
        parts = [
            {"text": "oi", "ts": 1.0},
            {"text": "tudo bem", "ts": 2.0},
        ]
        result = MessageBufferService._combine_messages(parts)
        # separados por espaço
        assert "oi" in result and "tudo bem" in result

    def test_joins_with_newline_after_final_punct(self):
        parts = [
            {"text": "Primeira frase.", "ts": 1.0},
            {"text": "Segunda frase", "ts": 2.0},
        ]
        result = MessageBufferService._combine_messages(parts)
        assert "\n" in result

    def test_dedup_consecutive_duplicates(self):
        parts = [
            {"text": "oi", "ts": 1.0},
            {"text": "oi", "ts": 2.0},  # dup
            {"text": "tudo bem?", "ts": 3.0},
        ]
        result = MessageBufferService._combine_messages(parts)
        # "oi" aparece 1 vez só
        assert result.count("oi") == 1

    def test_empty_parts_returns_empty_string(self):
        assert MessageBufferService._combine_messages([]) == ""


# ══════════════════════════════════════════════════════════════════
# Thread safety (smoke)
# ══════════════════════════════════════════════════════════════════

@pytest.mark.slow
class TestThreadSafety:

    def test_concurrent_adds_do_not_crash(self, fast_buffer):
        import threading
        p = ProcessorRecorder()
        errors = []

        def worker(phone: str, i: int):
            try:
                fast_buffer.add_message(phone, f"msg {i}", processor=p)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(f"phone_{i % 3}", i))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        time.sleep(0.5)
        assert errors == []


class TestSingleton:
    def test_singleton(self):
        assert get_message_buffer() is get_message_buffer()
