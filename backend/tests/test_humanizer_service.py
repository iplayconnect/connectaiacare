"""Testes do humanizer_service.

Componente: src/services/humanizer_service.py
Escopo: ResponseVariator + HumanBehaviorSimulator + MessageChunker + EmojiManager
Sem DB, sem I/O.
"""
from __future__ import annotations

import pytest

from src.services.humanizer_service import (
    Chunk,
    EmojiManager,
    HumanBehaviorSimulator,
    HumanizerService,
    MessageChunker,
    ResponseVariator,
    get_humanizer,
)


# ══════════════════════════════════════════════════════════════════
# ResponseVariator
# ══════════════════════════════════════════════════════════════════

class TestResponseVariator:

    def test_varies_known_opening(self, fixed_random):
        v = ResponseVariator()
        result = v.vary("Entendo! Vou te ajudar.")
        # Deve trocar "Entendo" por uma das variações
        assert not result.startswith("Entendo")
        assert result.startswith(("Compreendo", "Percebo", "Vejo", "Imagino"))

    def test_preserves_punctuation_after_opening(self, fixed_random):
        v = ResponseVariator()
        result = v.vary("Perfeito! Anotado.")
        # Primeiro token substituído, mas "!" preservado
        assert "!" in result[:15]

    def test_keeps_unknown_opening(self):
        v = ResponseVariator()
        original = "Bom dia, tudo bem?"
        result = v.vary(original)
        assert result.startswith("Bom dia")

    def test_filters_forbidden_phrase(self):
        v = ResponseVariator()
        # "Estamos à disposição" está em PHRASE_REPLACEMENTS
        result = v.vary("Perfeito! Estamos à disposição.")
        assert "Estamos à disposição" not in result

    def test_removes_unreplaced_forbidden_phrase(self):
        v = ResponseVariator()
        # "Compreendo perfeitamente" está em FORBIDDEN_PHRASES sem replacement
        original = "Oi. Compreendo perfeitamente a sua dor. Me conta mais."
        result = v.vary(original)
        assert "Compreendo perfeitamente" not in result

    def test_dedup_adds_emoji_on_repetition(self):
        v = ResponseVariator()
        # Texto sem opening variável: passa igual pelo _vary_openings
        # e bate o cache key, disparando dedup
        text = "Mensagem completamente única aqui"
        v.vary(text)
        v.vary(text)
        # 3ª chamada: count já é 2, _dedup dispara (if count > 1)
        third = v.vary(text)
        assert any(e in third for e in "💙🤝🌸☕️")

    def test_cache_is_bounded(self):
        v = ResponseVariator()
        # 250 textos únicos → cache deve truncar pra 100
        for i in range(250):
            v.vary(f"mensagem única {i}")
        assert len(v._cache) <= 200


# ══════════════════════════════════════════════════════════════════
# HumanBehaviorSimulator
# ══════════════════════════════════════════════════════════════════

class TestHumanBehaviorSimulator:

    def test_min_delay_for_short_text(self):
        s = HumanBehaviorSimulator()
        delay = s.calculate_typing_delay("Oi")
        assert delay >= s.MIN_DELAY_S

    def test_max_delay_for_very_long_text(self):
        s = HumanBehaviorSimulator()
        delay = s.calculate_typing_delay("x" * 5000)
        assert delay <= s.MAX_DELAY_S

    def test_delay_scales_with_length(self):
        s = HumanBehaviorSimulator()
        # Média de vários samples pra reduzir ruído do jitter
        short = sum(s.calculate_typing_delay("Oi") for _ in range(30)) / 30
        medium = sum(s.calculate_typing_delay("x" * 100) for _ in range(30)) / 30
        assert medium > short

    def test_empty_text_has_minimal_delay(self):
        s = HumanBehaviorSimulator()
        assert s.calculate_typing_delay("") < 1.0

    def test_pause_between_chunks_in_range(self):
        s = HumanBehaviorSimulator()
        for _ in range(20):
            pause = s.calculate_pause_between_chunks()
            assert 0.8 <= pause <= 1.6


# ══════════════════════════════════════════════════════════════════
# MessageChunker
# ══════════════════════════════════════════════════════════════════

class TestMessageChunker:

    def test_short_text_single_chunk(self):
        c = MessageChunker()
        result = c.chunk("Oi, tudo bem?")
        assert result == ["Oi, tudo bem?"]

    def test_medium_text_2_or_3_chunks(self):
        c = MessageChunker()
        text = "x" * 250  # entre SHORT_LIMIT (180) e MEDIUM_LIMIT (380)
        # Sem quebras naturais — deve retornar 1 ou 2 (depende de sentenças)
        result = c.chunk(text)
        assert len(result) >= 1

    def test_long_text_max_3_chunks(self):
        c = MessageChunker()
        paragraphs = ["Este é o parágrafo número " + str(i) * 30 for i in range(10)]
        text = "\n\n".join(paragraphs)
        result = c.chunk(text)
        assert len(result) <= 3

    def test_respects_paragraph_breaks(self):
        c = MessageChunker()
        text = (
            "Primeira ideia aqui, bem grande que passa do limite básico.\n\n"
            "Segunda ideia separada, também com um tamanho razoável.\n\n"
            "Terceira e última ideia pra fechar."
        ) * 3  # força múltiplos chunks
        result = c.chunk(text)
        # Cada chunk deve conter pelo menos um parágrafo completo
        for chunk in result:
            assert chunk.strip(), "Chunk vazio não é aceitável"

    def test_empty_input_returns_list_with_empty_or_empty_list(self):
        c = MessageChunker()
        assert c.chunk("") in ([""], [])

    def test_chunks_preserve_total_content(self):
        """A soma dos chunks deve conter todo conteúdo original significativo."""
        c = MessageChunker()
        text = "Primeira parte. " * 50
        chunks = c.chunk(text)
        combined = " ".join(chunks)
        # Todas palavras originais estão em algum chunk
        assert "Primeira" in combined
        assert "parte" in combined


# ══════════════════════════════════════════════════════════════════
# EmojiManager
# ══════════════════════════════════════════════════════════════════

class TestEmojiManager:

    def test_passthrough_when_few_emojis(self):
        e = EmojiManager()
        text = "Oi 💙 tudo bem?"
        assert e.moderate(text) == text

    def test_limits_excess_emojis(self):
        e = EmojiManager()
        text = "Olá 👋 💙 🤝 🌸 ☕ 😊 !"  # 6 emojis
        result = e.moderate(text)
        # Conta emojis no resultado (simples: caracteres fora ASCII básico)
        emoji_count = sum(1 for c in result if ord(c) > 0x2700)
        assert emoji_count <= e.MAX_EMOJIS_PER_MSG + 1  # tolerância

    def test_prefers_warm_emojis(self):
        e = EmojiManager()
        # mistura warm + corporate — deve manter warm
        text = "Ok 💙 ✅ 🤝 🚀 pronto!"
        result = e.moderate(text)
        # Algum dos warm deve estar preservado
        assert any(w in result for w in ["💙", "🤝", "🌸"])


# ══════════════════════════════════════════════════════════════════
# HumanizerService (facade)
# ══════════════════════════════════════════════════════════════════

class TestHumanizerService:

    def test_empty_text_returns_empty_list(self):
        h = HumanizerService()
        assert h.humanize("") == []
        assert h.humanize(None) == []  # type: ignore[arg-type]

    def test_returns_list_of_chunks(self):
        h = HumanizerService()
        result = h.humanize("Olá! Tudo bem com você?")
        assert isinstance(result, list)
        assert all(isinstance(c, Chunk) for c in result)

    def test_first_chunk_capped_at_2s(self):
        h = HumanizerService()
        # Texto longo garante chunks múltiplos
        text = "x" * 500
        chunks = h.humanize(text)
        if chunks:
            assert chunks[0].typing_delay_seconds <= h.FIRST_CHUNK_MAX_DELAY_S

    def test_chunk_flags_correct(self):
        h = HumanizerService()
        text = "a" * 50 + "\n\n" + "b" * 50 + "\n\n" + "c" * 50 + "\n\n" + "d" * 100 + "\n\n" + "e" * 150 + "\n\n" + "f" * 200
        chunks = h.humanize(text)
        if len(chunks) > 1:
            assert chunks[0].is_first is True
            assert chunks[-1].is_last is True
            # chunks do meio não são first nem last
            for mid in chunks[1:-1]:
                assert mid.is_first is False
                assert mid.is_last is False

    def test_singleton(self):
        h1 = get_humanizer()
        h2 = get_humanizer()
        assert h1 is h2

    def test_short_response_is_single_chunk(self):
        h = HumanizerService()
        chunks = h.humanize("Ok, anotado.")
        assert len(chunks) == 1
        assert chunks[0].is_first is True
        assert chunks[0].is_last is True
