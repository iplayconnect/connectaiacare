"""Message Buffer Service — agrupa mensagens sequenciais do usuário.

Problema real: usuário manda "oi"... "tudo bem?"... "preciso de ajuda com minha mãe"
em 3 mensagens em 10 segundos. Se processamos cada uma individualmente, Sofia
responde 3 vezes, atropelando o usuário e gerando contexto fragmentado.

Solução (inspirada no message_buffer da ConnectaIA):

    1. Quando chega mensagem, agrega no buffer em memória (ou Redis)
    2. Se Evolution detectar `presence.update = composing` → estende timer
    3. Quando timer expira (debounce) → processa tudo junto como texto único
    4. Sofia responde UMA vez referente ao bloco inteiro

Estratégia para MVP (sem Redis obrigatório):
    - Buffer in-memory por phone (dict threading-safe)
    - Debounce: 2.5s após última mensagem (ajustável)
    - Timeout absoluto: 12s (mesmo que usuário continue digitando, processa)
    - Callback síncrono quando flush dispara

Uso típico:

    buffer = get_message_buffer()
    def my_processor(phone, combined_text, parts):
        # processa texto consolidado
        pipeline.handle_text(phone, combined_text)

    buffer.add_message(phone, text, processor=my_processor)
    # se chegar outra msg em <2.5s, acumula.
    # se chegar 'composing' via webhook, estende timer.

NOTA: Em produção multi-worker, precisa Redis+lock distribuído. Este impl é
single-process friendly (1 worker gunicorn ou 1 thread) pra MVP/demo.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════

# Tempo de silêncio antes de processar (debounce)
DEBOUNCE_SECONDS = 2.5

# Tempo máximo de espera — mesmo que usuário continue digitando
MAX_WAIT_SECONDS = 12.0

# Tempo extra quando detectamos presence=composing (usuário digitando)
TYPING_EXTEND_SECONDS = 3.0

# Tamanho máximo de buffer por phone (proteção contra flood)
MAX_MESSAGES_PER_BUFFER = 10


@dataclass
class BufferEntry:
    """Estado de um buffer ativo."""
    phone: str
    messages: list[dict] = field(default_factory=list)   # [{text, ts, type, media_type}]
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    typing_until: float = 0.0                           # ts até quando esperar typing
    timer: threading.Timer | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    processor: Callable | None = None                    # callback quando flush
    # metadata extra que o caller quer preservar (ex: channel, session_context)
    meta: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class MessageBufferService:
    """Buffer in-memory de mensagens do usuário com debounce + typing detection.

    Thread-safe: lock por phone + lock global pra acesso ao dict.
    """

    def __init__(
        self,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        max_wait_seconds: float = MAX_WAIT_SECONDS,
        typing_extend_seconds: float = TYPING_EXTEND_SECONDS,
    ):
        self._buffers: dict[str, BufferEntry] = {}
        self._global_lock = threading.Lock()
        self.debounce_seconds = debounce_seconds
        self.max_wait_seconds = max_wait_seconds
        self.typing_extend_seconds = typing_extend_seconds

    # ═══════════════════════════════════════════════════════════════
    # API pública
    # ═══════════════════════════════════════════════════════════════

    def add_message(
        self,
        phone: str,
        text: str,
        *,
        message_type: str = "text",
        processor: Callable[[str, str, list[dict]], None],
        meta: dict | None = None,
    ) -> dict[str, Any]:
        """Adiciona mensagem ao buffer. Agenda flush automático.

        Args:
            phone: número do usuário
            text: texto da mensagem (se áudio, é a transcrição)
            message_type: 'text' | 'audio' | 'image' | 'document'
            processor: callback(phone, combined_text, parts) quando flush dispara
            meta: dict arbitrário (channel, session_context, etc.)

        Returns:
            {"status": "buffered", "buffered_count": N, "will_process_in_s": 2.5}
            ou {"status": "flushed", ...} se flush imediato (flood protection)
        """
        if not phone or not text:
            return {"status": "ignored", "reason": "empty"}

        with self._global_lock:
            entry = self._buffers.get(phone)
            if entry is None:
                entry = BufferEntry(phone=phone, processor=processor, meta=meta or {})
                self._buffers[phone] = entry

        with entry.lock:
            # Flood protection — se ultrapassou limite, força flush imediato
            if len(entry.messages) >= MAX_MESSAGES_PER_BUFFER:
                logger.warning("buffer_overflow_flush", phone=phone, count=len(entry.messages))
                self._cancel_timer(entry)
                self._flush_locked(entry)
                # Re-cria buffer pra nova mensagem
                with self._global_lock:
                    entry = BufferEntry(phone=phone, processor=processor, meta=meta or {})
                    self._buffers[phone] = entry

            entry.messages.append({
                "text": text,
                "type": message_type,
                "ts": time.time(),
            })
            entry.last_activity_at = time.time()
            entry.processor = processor or entry.processor
            if meta:
                entry.meta.update(meta)

            # Calcula quando deve disparar
            delay = self._compute_next_delay(entry)
            self._schedule_flush(entry, delay)

            return {
                "status": "buffered",
                "buffered_count": len(entry.messages),
                "will_process_in_s": round(delay, 2),
            }

    def notify_typing(self, phone: str) -> dict[str, Any]:
        """Chamado quando webhook recebe `presence.update = composing`.

        Estende o timer pra dar tempo do usuário terminar de digitar.
        Se não houver buffer ativo, ignora silenciosamente.
        """
        with self._global_lock:
            entry = self._buffers.get(phone)
        if entry is None:
            return {"status": "no_buffer"}

        with entry.lock:
            entry.typing_until = time.time() + self.typing_extend_seconds
            delay = self._compute_next_delay(entry)
            self._schedule_flush(entry, delay)
            logger.debug(
                "buffer_typing_extended",
                phone=phone, delay=delay, buffer_size=len(entry.messages),
            )
            return {"status": "extended", "new_delay_s": round(delay, 2)}

    def force_flush(self, phone: str) -> dict[str, Any]:
        """Força processamento imediato (útil em testes ou cancelamento)."""
        with self._global_lock:
            entry = self._buffers.pop(phone, None)
        if entry is None:
            return {"status": "no_buffer"}

        with entry.lock:
            self._cancel_timer(entry)
            return self._flush_locked(entry, consumed=True)

    def has_pending(self, phone: str) -> bool:
        with self._global_lock:
            entry = self._buffers.get(phone)
        return entry is not None and len(entry.messages) > 0

    # ═══════════════════════════════════════════════════════════════
    # Internos
    # ═══════════════════════════════════════════════════════════════

    def _compute_next_delay(self, entry: BufferEntry) -> float:
        """Calcula quanto tempo ainda esperar até flushar.

        - Base: debounce_seconds a partir de last_activity
        - Se typing ativo: max(debounce, typing_until - agora)
        - Limitado por max_wait_seconds a partir de created_at
        """
        now = time.time()
        # max é o teto absoluto
        max_deadline = entry.created_at + self.max_wait_seconds
        debounce_deadline = entry.last_activity_at + self.debounce_seconds
        typing_deadline = entry.typing_until if entry.typing_until > now else 0

        # queremos o maior entre debounce e typing, mas limitado por max
        target = max(debounce_deadline, typing_deadline)
        target = min(target, max_deadline)
        delay = max(0.05, target - now)
        return delay

    def _schedule_flush(self, entry: BufferEntry, delay: float) -> None:
        """Cancela timer antigo e agenda novo."""
        self._cancel_timer(entry)
        timer = threading.Timer(delay, self._timer_callback, args=[entry.phone])
        timer.daemon = True
        entry.timer = timer
        timer.start()

    def _cancel_timer(self, entry: BufferEntry) -> None:
        if entry.timer is not None:
            try:
                entry.timer.cancel()
            except Exception:
                pass
            entry.timer = None

    def _timer_callback(self, phone: str) -> None:
        """Dispara quando timer expira."""
        with self._global_lock:
            entry = self._buffers.pop(phone, None)
        if entry is None:
            return

        with entry.lock:
            self._flush_locked(entry, consumed=True)

    def _flush_locked(
        self, entry: BufferEntry, consumed: bool = False,
    ) -> dict[str, Any]:
        """Processa e limpa buffer. Chamado com entry.lock adquirido."""
        if not entry.messages:
            return {"status": "empty"}

        parts = list(entry.messages)
        combined = self._combine_messages(parts)

        logger.info(
            "buffer_flush",
            phone=entry.phone, count=len(parts),
            combined_len=len(combined), age_s=round(time.time() - entry.created_at, 1),
        )

        processor = entry.processor
        entry.messages.clear()

        # Se este flush foi pelo timer, o entry já foi removido do dict.
        # Se foi force_flush, também já foi removido.
        # Garante que está fora pra não reprocessar.
        if not consumed:
            with self._global_lock:
                self._buffers.pop(entry.phone, None)

        if processor:
            try:
                processor(entry.phone, combined, parts)
            except Exception as exc:
                logger.error(
                    "buffer_processor_failed",
                    phone=entry.phone, error=str(exc),
                )

        return {
            "status": "flushed",
            "count": len(parts),
            "combined_length": len(combined),
        }

    @staticmethod
    def _combine_messages(parts: list[dict]) -> str:
        """Combina mensagens fragmentadas em um texto único.

        Heurística:
            - Junta com espaço se parte anterior NÃO termina com pontuação final
            - Junta com nova linha se termina com . ! ?
            - Remove duplicatas exatas consecutivas
        """
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0].get("text", "").strip()

        pieces: list[str] = []
        last_text = ""
        for p in parts:
            text = (p.get("text") or "").strip()
            if not text:
                continue
            if text == last_text:
                continue  # dedup consecutivo
            if pieces and pieces[-1] and pieces[-1][-1] in ".!?":
                pieces.append("\n" + text)
            else:
                pieces.append(" " + text if pieces else text)
            last_text = text

        return "".join(pieces).strip()


# Singleton
_instance: MessageBufferService | None = None


def get_message_buffer() -> MessageBufferService:
    global _instance
    if _instance is None:
        _instance = MessageBufferService()
    return _instance
