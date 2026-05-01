"""EventBus — Redis Streams wrapper pra inbound/outbound assíncrono.

Streams gerenciadas:
    sofia:inbound      — webhook → workers (msg recebida pra processar)
    sofia:outbound     — workers → delivery worker (msg pra enviar Evolution)
    sofia:tools        — workers → tool executor (futuro Phase C)
    sofia:handoff      — workers → handoff notifier (Central 24h)
    sofia:audit        — broadcast (audit log writer)

Cada stream tem consumer group correspondente:
    {stream}-cg

Princípios:
- **At-least-once delivery**: eventos podem ser re-entregues; consumer
  deve ser idempotente (idempotency key no business event).
- **Manual ack**: consumer só XACK depois que processou com sucesso.
  Falha → fica em pending list → reclaim by claim_idle ou DLQ.
- **DLQ**: após N retries (default 5), evento vai pra
  {stream}:dlq pra inspeção humana.
- **Stream trim**: XTRIM scheduled (cron) limita retention.

Uso publisher:
    from src.services.event_bus import get_event_bus
    bus = get_event_bus()
    bus.publish("sofia:inbound", {
        "event_type": "whatsapp_message",
        "tenant_id": "...",
        "trace_id": str(trace_id),
        "payload": event,
    })

Uso consumer (worker):
    bus = get_event_bus()
    consumer = bus.consumer(
        stream="sofia:inbound",
        group="sofia-inbound-cg",
        consumer_name=f"worker-{os.getpid()}",
    )
    for entry in consumer.read(block_ms=5000):
        try:
            process(entry.data)
            consumer.ack(entry.id)
        except Exception:
            consumer.nack(entry.id)  # vai pra retry / DLQ
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from src.services.redis_client import get_redis
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Stream constants
# ──────────────────────────────────────────────────────────────────

class Streams:
    INBOUND = "sofia:inbound"
    OUTBOUND = "sofia:outbound"
    TOOLS = "sofia:tools"
    HANDOFF = "sofia:handoff"
    AUDIT = "sofia:audit"


class ConsumerGroups:
    INBOUND = "sofia-inbound-cg"
    OUTBOUND = "sofia-outbound-cg"
    TOOLS = "sofia-tools-cg"
    HANDOFF = "sofia-handoff-cg"
    AUDIT = "sofia-audit-cg"


# Default config (override via env)
DEFAULT_MAX_DELIVERY = 5
DEFAULT_RECLAIM_IDLE_MS = 60_000  # 1min
DEFAULT_TRIM_MAX_LEN = 100_000     # 100k events per stream


# ──────────────────────────────────────────────────────────────────
# Event entry
# ──────────────────────────────────────────────────────────────────


@dataclass
class StreamEntry:
    """Um evento lido da stream. Contém id (pra ack) e data dict."""
    id: str
    data: dict
    delivery_count: int = 1  # quantas vezes foi entregue


# ──────────────────────────────────────────────────────────────────
# EventBus
# ──────────────────────────────────────────────────────────────────


class EventBus:
    def __init__(self) -> None:
        self.redis = get_redis()

    # ── Publisher ──

    def publish(
        self,
        stream: str,
        data: dict,
        *,
        max_len: int = DEFAULT_TRIM_MAX_LEN,
        approximate: bool = True,
    ) -> str:
        """Publica evento em stream. Retorna o stream entry id.

        Serializa todos os values pra string (Redis Streams exige
        string). Dict vira JSON.
        """
        flat = self._flatten(data)
        # MAXLEN ~ N (approximate, mais rápido)
        kwargs: dict[str, Any] = {}
        if max_len:
            kwargs["maxlen"] = max_len
            if approximate:
                kwargs["approximate"] = True
        return self.redis.xadd(stream, flat, **kwargs)

    # ── Consumer ──

    def ensure_group(self, stream: str, group: str) -> None:
        """Cria consumer group se não existe. MKSTREAM cria a stream
        vazia se ela ainda não tem nada (1ª vez)."""
        try:
            self.redis.xgroup_create(stream, group, id="$", mkstream=True)
            logger.info("event_bus_group_created", stream=stream, group=group)
        except Exception as exc:
            # BUSYGROUP = já existe, ok
            if "BUSYGROUP" not in str(exc):
                logger.warning(
                    "event_bus_group_create_failed",
                    stream=stream, group=group, error=str(exc),
                )

    def consumer(
        self,
        *,
        stream: str,
        group: str,
        consumer_name: str,
        max_delivery: int = DEFAULT_MAX_DELIVERY,
        reclaim_idle_ms: int = DEFAULT_RECLAIM_IDLE_MS,
    ) -> "EventBusConsumer":
        """Constrói consumer pra um stream/group/consumer_name específico."""
        self.ensure_group(stream, group)
        return EventBusConsumer(
            bus=self,
            stream=stream,
            group=group,
            consumer_name=consumer_name,
            max_delivery=max_delivery,
            reclaim_idle_ms=reclaim_idle_ms,
        )

    # ── DLQ ──

    def push_dlq(self, stream: str, entry: StreamEntry, reason: str) -> str:
        """Move evento da stream principal pra DLQ (`{stream}:dlq`).
        Adiciona razão e timestamp original. Retorna id na DLQ."""
        dlq_stream = f"{stream}:dlq"
        dlq_data = {
            "original_id": entry.id,
            "delivery_count": entry.delivery_count,
            "reason": reason,
            "moved_at": str(time.time()),
            **{f"orig_{k}": v for k, v in self._flatten(entry.data).items()},
        }
        return self.redis.xadd(dlq_stream, dlq_data, maxlen=DEFAULT_TRIM_MAX_LEN, approximate=True)

    # ── Internals ──

    @staticmethod
    def _flatten(data: dict) -> dict:
        """Serializa values pra string (Redis Streams requirement).
        Dicts/lists viram JSON. None/bool/int/float viram str."""
        out: dict[str, str] = {}
        for k, v in data.items():
            if v is None:
                out[k] = ""
            elif isinstance(v, (dict, list)):
                out[k] = json.dumps(v, default=str)
            else:
                out[k] = str(v)
        return out

    @staticmethod
    def _unflatten(flat: dict) -> dict:
        """Tenta deserializar values JSON-shaped. Mantém string se
        não conseguir."""
        out: dict[str, Any] = {}
        for k, v in flat.items():
            if v == "":
                out[k] = None
                continue
            if v.startswith(("{", "[")):
                try:
                    out[k] = json.loads(v)
                    continue
                except Exception:
                    pass
            out[k] = v
        return out


# ──────────────────────────────────────────────────────────────────
# Consumer wrapper
# ──────────────────────────────────────────────────────────────────


class EventBusConsumer:
    def __init__(
        self,
        *,
        bus: EventBus,
        stream: str,
        group: str,
        consumer_name: str,
        max_delivery: int,
        reclaim_idle_ms: int,
    ) -> None:
        self.bus = bus
        self.stream = stream
        self.group = group
        self.consumer_name = consumer_name
        self.max_delivery = max_delivery
        self.reclaim_idle_ms = reclaim_idle_ms

    def read(
        self,
        *,
        count: int = 10,
        block_ms: int = 5000,
    ) -> Iterator[StreamEntry]:
        """Bloqueia até `block_ms` lendo até `count` eventos. Yield
        cada evento. Consumer deve chamar ack/nack em cada um."""
        # Step 1: tenta reclaim de idle pendentes (ex: worker antigo morreu)
        for entry in self._reclaim_idle():
            yield entry

        # Step 2: lê novos eventos
        result = self.bus.redis.xreadgroup(
            self.group,
            self.consumer_name,
            {self.stream: ">"},
            count=count,
            block=block_ms,
        )
        if not result:
            return
        for stream_name, entries in result:
            for entry_id, flat_data in entries:
                yield StreamEntry(
                    id=entry_id,
                    data=self.bus._unflatten(flat_data),
                    delivery_count=1,  # primeira entrega
                )

    def _reclaim_idle(self) -> Iterator[StreamEntry]:
        """Reclaim de eventos idle (consumer crashou/timeout). XAUTOCLAIM
        pega da pending list eventos não-ack há > reclaim_idle_ms.
        Se delivery_count > max_delivery → manda pra DLQ."""
        try:
            # XAUTOCLAIM retorna (next_cursor, claimed_entries, deleted)
            next_cursor, claimed, _deleted = self.bus.redis.xautoclaim(
                self.stream, self.group, self.consumer_name,
                min_idle_time=self.reclaim_idle_ms,
                start_id="0-0",
                count=10,
            )
        except Exception as exc:
            logger.warning(
                "event_bus_reclaim_failed",
                stream=self.stream, group=self.group, error=str(exc),
            )
            return

        if not claimed:
            return

        # Pra cada reclaimed, checa pending info pra saber delivery_count
        try:
            pending_summary = self.bus.redis.xpending_range(
                self.stream, self.group,
                min="-", max="+", count=len(claimed),
                consumername=self.consumer_name,
            )
            delivery_counts = {p["message_id"]: p["times_delivered"] for p in pending_summary}
        except Exception:
            delivery_counts = {}

        for entry_id, flat_data in claimed:
            dc = delivery_counts.get(entry_id, 1)
            if dc > self.max_delivery:
                # Estourou retry → DLQ + ack pra remover da pending list
                entry = StreamEntry(
                    id=entry_id,
                    data=self.bus._unflatten(flat_data),
                    delivery_count=dc,
                )
                self.bus.push_dlq(self.stream, entry, reason="max_delivery_exceeded")
                self.ack(entry_id)
                logger.error(
                    "event_bus_dlq",
                    stream=self.stream, entry_id=entry_id, delivery_count=dc,
                )
                continue
            yield StreamEntry(
                id=entry_id,
                data=self.bus._unflatten(flat_data),
                delivery_count=dc,
            )

    def ack(self, entry_id: str) -> None:
        """Confirma processamento. Remove da pending list."""
        try:
            self.bus.redis.xack(self.stream, self.group, entry_id)
        except Exception as exc:
            logger.warning(
                "event_bus_ack_failed",
                stream=self.stream, entry_id=entry_id, error=str(exc),
            )

    def nack(self, entry_id: str, *, dlq_reason: Optional[str] = None) -> None:
        """Não confirma. Evento volta pra pending list e será reclaim'd
        depois (subjeito a max_delivery → DLQ).

        Se dlq_reason explícito, força DLQ imediato (sem esperar retry).
        """
        if dlq_reason:
            # Pega o evento do PEL (pending entries list) pra mover pra DLQ
            try:
                pending = self.bus.redis.xrange(self.stream, min=entry_id, max=entry_id)
                if pending:
                    _, flat_data = pending[0]
                    entry = StreamEntry(
                        id=entry_id,
                        data=self.bus._unflatten(flat_data),
                        delivery_count=999,  # forçado
                    )
                    self.bus.push_dlq(self.stream, entry, reason=dlq_reason)
                    self.ack(entry_id)
                    return
            except Exception as exc:
                logger.warning(
                    "event_bus_force_dlq_failed",
                    stream=self.stream, entry_id=entry_id, error=str(exc),
                )
        # Default: deixa na pending list (XACK NÃO chamado), espera reclaim
        logger.info(
            "event_bus_nack",
            stream=self.stream, entry_id=entry_id,
        )

    def pending_count(self) -> int:
        """Quantos eventos estão pending (não-ack). Pra métricas."""
        try:
            summary = self.bus.redis.xpending(self.stream, self.group)
            # Returns: {pending: count, min: id, max: id, consumers: [...]}
            if isinstance(summary, dict):
                return int(summary.get("pending") or 0)
            # Some versions return list/tuple
            return int(summary[0]) if summary else 0
        except Exception:
            return 0


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _instance
    if _instance is None:
        _instance = EventBus()
    return _instance
