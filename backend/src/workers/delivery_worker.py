"""delivery-worker — consome sofia:outbound e envia via Evolution.

Phase B: pra Sofia mandar mensagem WhatsApp pelo orchestrator
novo (Phase C), publica em sofia:outbound. Este worker pega,
manda via Evolution API, persiste audit, e ack.

Falha de Evolution (5xx, network) → nack → reclaim → retry com
backoff. Após max_delivery → DLQ + audit critical.

Vantagens vs send síncrono:
- Webhook nunca bloqueia em send Evolution
- Worker pode ser scaled horizontalmente
- DLQ separa eventos que precisam atenção humana
- Métricas por tenant/instance

Run:
    cd backend && python -m src.workers.delivery_worker
"""
from __future__ import annotations

import os
import signal
import socket
import sys
import time

from src.services.audit_log_writer import redact_phone, write_audit
from src.services.event_bus import ConsumerGroups, Streams, get_event_bus
from src.services.evolution import get_evolution
from src.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


CONSUMER_NAME = os.getenv(
    "WORKER_CONSUMER_NAME",
    f"sofia-out-{socket.gethostname()}-{os.getpid()}",
)
BLOCK_MS = int(os.getenv("WORKER_BLOCK_MS", "5000"))
COUNT_PER_READ = int(os.getenv("WORKER_BATCH", "10"))

_shutdown = False


def _on_signal(*_args):
    global _shutdown
    logger.info("delivery_worker_shutdown_requested")
    _shutdown = True


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


def process_outbound(data: dict) -> dict:
    """Envia mensagem via Evolution. Retorna response da Evolution
    pra audit. Levanta exceção em falha.

    Schema esperado (publicado pelo orchestrator/Phase C ou pelos
    fluxos atuais que migrarem):
        {
            "tenant_id": "...",
            "trace_id": "...",
            "instance": "v6",          # opcional, default da Evolution config
            "phone": "5551984928518",  # E.164
            "message_type": "text",
            "text": "Olá...",
            "metadata": {...}          # opcional
        }
    """
    phone = data.get("phone")
    text = data.get("text")
    if not phone or not text:
        raise ValueError(f"missing required fields phone/text in {data}")

    msg_type = data.get("message_type") or "text"
    if msg_type != "text":
        raise NotImplementedError(
            f"delivery_worker só suporta text na Phase B (got: {msg_type})"
        )

    # Evolution.send_text é síncrono mas é HTTP — ok pro worker
    response = get_evolution().send_text(phone, text)
    return response or {}


def main() -> int:
    configure_logging()
    logger.info(
        "delivery_worker_started",
        consumer_name=CONSUMER_NAME,
        block_ms=BLOCK_MS,
    )

    bus = get_event_bus()
    consumer = bus.consumer(
        stream=Streams.OUTBOUND,
        group=ConsumerGroups.OUTBOUND,
        consumer_name=CONSUMER_NAME,
    )

    while not _shutdown:
        try:
            for entry in consumer.read(count=COUNT_PER_READ, block_ms=BLOCK_MS):
                if _shutdown:
                    break
                started = time.perf_counter()
                tenant_id = entry.data.get("tenant_id")
                trace_id = entry.data.get("trace_id")
                phone_redacted = redact_phone(entry.data.get("phone"))
                try:
                    response = process_outbound(entry.data)
                    duration_ms = (time.perf_counter() - started) * 1000
                    consumer.ack(entry.id)
                    write_audit(
                        action="outbound_sent",
                        actor="sofia",
                        tenant_id=tenant_id,
                        trace_id=trace_id,
                        payload={
                            "phone_redacted": phone_redacted,
                            "evolution_msg_id": (
                                response.get("key", {}).get("id")
                                if isinstance(response, dict) else None
                            ),
                            "evolution_status": (
                                response.get("status")
                                if isinstance(response, dict) else None
                            ),
                            "duration_ms": round(duration_ms, 2),
                        },
                    )
                    logger.info(
                        "delivery_sent",
                        entry_id=entry.id,
                        tenant_id=tenant_id,
                        trace_id=trace_id,
                        phone_redacted=phone_redacted,
                        duration_ms=round(duration_ms, 2),
                    )
                except ValueError as exc:
                    # Schema inválido — força DLQ imediato (não retry)
                    logger.warning(
                        "delivery_invalid_schema",
                        entry_id=entry.id, error=str(exc),
                    )
                    consumer.nack(entry.id, dlq_reason="invalid_schema")
                except Exception as exc:
                    logger.exception(
                        "delivery_failed",
                        entry_id=entry.id,
                        delivery_count=entry.delivery_count,
                        error_class=type(exc).__name__,
                    )
                    # Deixa pra reclaim → eventually DLQ
                    consumer.nack(entry.id)
        except Exception as exc:
            logger.exception("delivery_loop_failed", error=str(exc))
            time.sleep(2)

    logger.info("delivery_worker_stopped", consumer_name=CONSUMER_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
