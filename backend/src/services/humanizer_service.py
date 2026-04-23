"""Humanizer Service — torna a Sofia humana de verdade.

Baseado no humanizer.py da ConnectaIA + adaptado ao contexto de cuidado
geriátrico (tom mais acolhedor, mais pausas, mais empatia, menos emoji).

Componentes:
    1. ResponseVariator — 3-5 variações de cada "template" de resposta
    2. HumanBehaviorSimulator — calcula typing delay realista
    3. MessageChunker — divide mensagens longas em 2-3 chunks
    4. EmojiManager — controla uso contextual
    5. PhraseFilter — remove frases proibidas robóticas

Uso:
    from src.services.humanizer_service import get_humanizer
    humanizer = get_humanizer()
    chunks = humanizer.humanize_response(
        text=raw_response,
        context={"first_name": "Maria", "tone": "warm"},
    )
    for chunk in chunks:
        evolution.set_presence(phone, "composing")
        time.sleep(chunk.typing_delay_seconds)
        evolution.send_text(phone, chunk.text)
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any


# ══════════════════════════════════════════════════════════════════
# Dataclasses
# ══════════════════════════════════════════════════════════════════

@dataclass
class Chunk:
    text: str
    typing_delay_seconds: float
    is_first: bool = False
    is_last: bool = False


# ══════════════════════════════════════════════════════════════════
# Phrases proibidas (pt-BR contexto healthcare/B2C)
# ══════════════════════════════════════════════════════════════════

FORBIDDEN_PHRASES = [
    # Robotic openings
    "Como posso te ajudar hoje",
    "Como posso te ajudar",
    "Como posso ajudá-lo",
    "Como posso ajudá-la",
    "Em que posso ser útil",
    "Em que posso ajudar",
    "Posso te ajudar",
    "Gostaria de saber mais",
    "Posso esclarecer",
    "Posso te auxiliar",
    "O que você gostaria de saber",

    # Frases passivas
    "Estamos à disposição",
    "Fico à disposição",
    "Qualquer dúvida estamos aqui",
    "É normal ter dúvidas",
    "Você pode ficar tranquilo(a)",

    # Clichês vagos
    "Entendo sua situação",  # substituir por algo concreto
    "Compreendo perfeitamente",
    "Faz sentido",  # no início de frase
]

PHRASE_REPLACEMENTS = {
    # ATENÇÃO: evitar que o replacement tenha palavras que possam estar ANTES
    # do match no texto original (gera duplicação tipo "Me conta Me conta").
    "Como posso te ajudar?": "O que precisa?",
    "Como posso ajudar?": "Como eu posso apoiar?",
    "Em que posso ajudar?": "Como posso apoiar?",
    "Posso te ajudar?": "Tô aqui, me conta",
    "Estamos à disposição": "Tô aqui com você",
    "Fico à disposição": "Qualquer coisa, me chama",
    "É normal ter dúvidas": "Faz todo sentido perguntar",
    "Você pode ficar tranquilo": "Pode ficar tranquilo(a) — eu cuido disso",
}


# ══════════════════════════════════════════════════════════════════
# Response variator
# ══════════════════════════════════════════════════════════════════

OPENING_VARIATIONS = {
    "entendo": ["Compreendo", "Percebo", "Vejo", "Imagino"],
    "perfeito": ["Ótimo", "Excelente", "Show"],
    "anotado": ["Anotei", "Registrei", "Já tá aqui comigo"],
    "ok": ["Combinado", "Beleza", "Tá certo"],
    "claro": ["Com certeza", "Pode deixar", "Sem dúvida"],
    "prazer": ["Que bom conversar", "Legal te conhecer", "É um prazer"],
}

AFFECTIONATE_ADDITIONS = [
    "💙",
    "",
    "",  # dobra a chance de não ter emoji
    "🤝",
    "",
]


class ResponseVariator:
    """Gera variações naturais pra evitar repetição."""

    def __init__(self):
        self._cache: dict[str, int] = {}

    def vary(self, text: str) -> str:
        """Aplica variações contextuais."""
        if not text:
            return text

        # 1. Remove frases proibidas / substitui
        text = self._filter_phrases(text)

        # 2. Varia palavras de abertura
        text = self._vary_openings(text)

        # 3. Evita repetição exata dentro da sessão
        text = self._dedup(text)

        return text

    def _filter_phrases(self, text: str) -> str:
        # Substitui se possível
        for phrase, replacement in PHRASE_REPLACEMENTS.items():
            pattern = re.escape(phrase)
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Remove frases sem substituição (heurística: remove a sentença inteira)
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in text.lower() and phrase.lower() not in [
                k.lower() for k in PHRASE_REPLACEMENTS
            ]:
                # Remove sentence containing the forbidden phrase
                sentences = re.split(r"(?<=[.!?])\s+", text)
                sentences = [
                    s for s in sentences if phrase.lower() not in s.lower()
                ]
                text = " ".join(sentences)
        return text.strip()

    def _vary_openings(self, text: str) -> str:
        if not text:
            return text
        first_token = text.split()[0]
        first_word = first_token.lower().rstrip(",.!?")
        if first_word in OPENING_VARIATIONS:
            variations = OPENING_VARIATIONS[first_word]
            replacement = random.choice(variations)
            # Preserva pontuação original (!, ?, ., ,) e o resto da frase.
            trailing_punct = first_token[len(first_word):]
            rest = text[len(first_token):]
            text = replacement + trailing_punct + rest
        return text

    def _dedup(self, text: str) -> str:
        """Se exato texto foi enviado recentemente, varia levemente."""
        key = hashlib.md5(text.lower().encode()).hexdigest()[:16]
        count = self._cache.get(key, 0)
        self._cache[key] = count + 1
        if count > 1:
            # Adiciona emoji sutil pra quebrar repetição
            if not any(e in text for e in "💙🤝🌸☕️"):
                text = text.rstrip(".!?") + " 💙"
        if len(self._cache) > 200:
            # limpa cache
            self._cache = dict(list(self._cache.items())[-100:])
        return text


# ══════════════════════════════════════════════════════════════════
# Human behavior (typing delay)
# ══════════════════════════════════════════════════════════════════

class HumanBehaviorSimulator:
    """Calcula typing delay realista baseado em comprimento + variação humana."""

    # Velocidade humana média de leitura/escrita (chars/segundo)
    CHARS_PER_SEC_MIN = 18
    CHARS_PER_SEC_MAX = 28

    # Bounds absolutos (segundos)
    MIN_DELAY_S = 1.2
    MAX_DELAY_S = 6.0

    def calculate_typing_delay(self, text: str) -> float:
        """Calcula delay em segundos pra simular digitação da Sofia."""
        if not text:
            return 0.5

        chars = len(text)
        speed = random.uniform(self.CHARS_PER_SEC_MIN, self.CHARS_PER_SEC_MAX)
        base = chars / speed

        # Variação humana ±15%
        jitter = random.uniform(0.85, 1.15)
        delay = base * jitter

        # Clamp
        delay = max(self.MIN_DELAY_S, min(delay, self.MAX_DELAY_S))
        return delay

    def calculate_pause_between_chunks(self) -> float:
        """Pausa natural entre 2 chunks (ela 'pensou' o que dizer a seguir)."""
        return random.uniform(0.8, 1.6)


# ══════════════════════════════════════════════════════════════════
# Message chunker
# ══════════════════════════════════════════════════════════════════

class MessageChunker:
    """Divide mensagens longas em 2-3 chunks naturais."""

    # Limiar de chars pra começar a chunkar
    SHORT_LIMIT = 180   # até aqui, envia inteiro
    MEDIUM_LIMIT = 380  # divide em 2
    # Acima disso, divide em 3

    def chunk(self, text: str) -> list[str]:
        if not text or len(text) <= self.SHORT_LIMIT:
            return [text]

        # Busca quebras naturais (\n\n, depois . ? !)
        parts = self._split_by_paragraph(text)
        if len(parts) >= 2 and all(len(p) > 30 for p in parts):
            # Se tem parágrafos claros, usa eles
            return self._consolidate(parts, max_chunks=3)

        # Fallback: sentenças
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return self._consolidate(sentences, max_chunks=3)

    def _split_by_paragraph(self, text: str) -> list[str]:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        return parts

    def _consolidate(self, parts: list[str], max_chunks: int) -> list[str]:
        """Agrupa sentenças/parágrafos pra formar N chunks balanceados."""
        if len(parts) <= 1:
            return parts

        total_len = sum(len(p) for p in parts)
        target_chunks = min(max_chunks, max(2, total_len // self.SHORT_LIMIT))
        target_size = total_len / target_chunks

        chunks: list[str] = []
        current = ""
        for p in parts:
            if not current:
                current = p
            elif len(current) + len(p) + 1 < target_size * 1.2:
                current += "\n\n" + p
            else:
                chunks.append(current)
                current = p
        if current:
            chunks.append(current)

        # Se gerou mais que max_chunks, consolida os últimos
        while len(chunks) > max_chunks:
            chunks[-2] = chunks[-2] + "\n\n" + chunks[-1]
            chunks.pop()
        return chunks


# ══════════════════════════════════════════════════════════════════
# Emoji manager
# ══════════════════════════════════════════════════════════════════

class EmojiManager:
    """Modera uso de emojis — contexto healthcare geriátrico prefere menos + humanos."""

    # Emojis "amigáveis/carinhosos" vs "corporativos/técnicos"
    WARM_EMOJIS = ["💙", "🤝", "🌸", "☕", "👋", "🫖", "😊"]
    AVOID_CORPORATE = ["✅", "❌", "⚡", "🚀", "💼"]
    MAX_EMOJIS_PER_MSG = 2

    def moderate(self, text: str) -> str:
        """Limita excesso de emojis e troca por mais humanos."""
        # Conta emojis
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001F9FF]",
            flags=re.UNICODE,
        )
        emojis = emoji_pattern.findall(text)
        if len(emojis) <= self.MAX_EMOJIS_PER_MSG:
            return text

        # Remove excesso mantendo os warm
        kept = 0
        def replace(match):
            nonlocal kept
            emo = match.group()
            if emo in self.WARM_EMOJIS and kept < self.MAX_EMOJIS_PER_MSG:
                kept += 1
                return emo
            if emo not in self.WARM_EMOJIS and emo not in self.AVOID_CORPORATE and kept < self.MAX_EMOJIS_PER_MSG:
                kept += 1
                return emo
            return ""
        return emoji_pattern.sub(replace, text)


# ══════════════════════════════════════════════════════════════════
# Facade
# ══════════════════════════════════════════════════════════════════

class HumanizerService:
    def __init__(self):
        self.variator = ResponseVariator()
        self.behavior = HumanBehaviorSimulator()
        self.chunker = MessageChunker()
        self.emoji = EmojiManager()

    # Primeira mensagem sempre rápida — feedback visual imediato ao user
    FIRST_CHUNK_MAX_DELAY_S = 2.0

    def humanize(self, text: str) -> list[Chunk]:
        """Aplica toda pipeline e retorna chunks prontos pra envio."""
        if not text:
            return []

        # 1. Modera emojis
        text = self.emoji.moderate(text)
        # 2. Aplica variações
        text = self.variator.vary(text)
        # 3. Chunk
        parts = self.chunker.chunk(text)
        # 4. Calcula delays
        chunks: list[Chunk] = []
        for i, p in enumerate(parts):
            delay = self.behavior.calculate_typing_delay(p)
            if i == 0:
                # Primeiro chunk: delay capped pra o user ter feedback rápido
                # (se Sofia fica 5s "digitando" sem mandar nada, parece travada)
                delay = min(delay, self.FIRST_CHUNK_MAX_DELAY_S)
            else:
                # pausa entre chunks (inclui no delay do próximo)
                delay += self.behavior.calculate_pause_between_chunks()
            chunks.append(Chunk(
                text=p,
                typing_delay_seconds=delay,
                is_first=(i == 0),
                is_last=(i == len(parts) - 1),
            ))
        return chunks


_instance: HumanizerService | None = None


def get_humanizer() -> HumanizerService:
    global _instance
    if _instance is None:
        _instance = HumanizerService()
    return _instance
