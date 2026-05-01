"""sofia-inbound-worker — consome sofia:inbound e processa eventos.

Phase B (compat layer): roteia evento de volta pro
`pipeline.handle_webhook()` legado. Comportamento de produção
fica idêntico ao webhook síncrono, mas processado num worker
separado → escala horizontal real, webhook responde <100ms.

Phase C: substituir o handle_webhook legado por
`super_sofia_router.process()` (orquestrador novo).

Run:
    cd backend && python -m src.workers.sofia_inbound_worker

Ou em produção via docker-compose service `sofia-inbound-worker`.
Múltiplos workers compartilham consumer group `sofia-inbound-cg` —
load balancing automático.
"""
from __future__ import annotations

import os
import signal
import socket
import sys
import time

from src.handlers.pipeline import get_pipeline
from src.services.audit_log_writer import write_audit
from src.services.event_bus import ConsumerGroups, Streams, get_event_bus
from src.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────

CONSUMER_NAME = os.getenv(
    "WORKER_CONSUMER_NAME",
    f"sofia-in-{socket.gethostname()}-{os.getpid()}",
)
BLOCK_MS = int(os.getenv("WORKER_BLOCK_MS", "5000"))
COUNT_PER_READ = int(os.getenv("WORKER_BATCH", "10"))


# ──────────────────────────────────────────────────────────────────
# Shutdown handling
# ──────────────────────────────────────────────────────────────────

_shutdown = False


def _on_signal(*_args):
    global _shutdown
    logger.info("sofia_inbound_worker_shutdown_requested")
    _shutdown = True


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


# ──────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────


def process_entry(entry_data: dict) -> None:
    """Processa um evento da stream. Levanta exceção em falha
    pra worker fazer nack.

    Phase C v1 fluxo:
        1. Tenta SuperSofiaOrchestrator (decide entre handle ou
           passthrough)
        2. Se passthrough → chama pipeline.handle_webhook legado
           (preserva fluxo clínico atual)
        3. Se handled → orchestrator já publicou resposta em
           sofia:outbound (delivery worker manda)

    Feature flag SUPER_SOFIA_ENABLED (env, default true) liga/desliga
    Phase C. Off → 100% passthrough pra pipeline legado.
    """
    event_type = entry_data.get("event_type")
    trace_id = entry_data.get("trace_id")
    tenant_id = entry_data.get("tenant_id")

    logger.info(
        "sofia_inbound_processing",
        event_type=event_type,
        trace_id=trace_id,
        tenant_id=tenant_id,
    )

    if event_type != "whatsapp_inbound":
        # Eventos desconhecidos → audit + ignore
        logger.warning(
            "sofia_inbound_unknown_event_type",
            event_type=event_type, trace_id=trace_id,
        )
        from src.services.audit_log_writer import write_audit
        write_audit(
            action="event_bus_unknown_event_type",
            actor="sofia-inbound-worker",
            tenant_id=tenant_id,
            trace_id=trace_id,
            payload={"event_type": event_type},
        )
        return

    super_sofia_enabled = os.getenv("SUPER_SOFIA_ENABLED", "true").lower() == "true"

    if super_sofia_enabled:
        try:
            from src.services.super_sofia_orchestrator import get_super_sofia_orchestrator
            result = get_super_sofia_orchestrator().process(entry_data)
        except Exception as exc:
            logger.exception(
                "super_sofia_orchestrator_crashed",
                trace_id=trace_id, error=str(exc)[:200],
            )
            # Failsafe: cai pro pipeline legado
            result = {"status": "passthrough", "agent": "failsafe"}

        if result.get("status") == "handled":
            logger.info(
                "super_sofia_handled",
                trace_id=trace_id,
                agent=result.get("agent"),
                next_action=result.get("next_action"),
                duration_ms=result.get("duration_ms"),
                is_anonymous=result.get("is_anonymous"),
                intent=(
                    result.get("intent", {}).get("intent")
                    if result.get("intent") else None
                ),
            )
            return
        # passthrough → cai no pipeline legado abaixo

    # Compat layer: pipeline.handle_webhook legado
    original_event = entry_data.get("payload") or {}
    result = get_pipeline().handle_webhook(original_event)
    logger.info(
        "sofia_inbound_passthrough_legacy",
        trace_id=trace_id,
        tenant_id=tenant_id,
        result_status=result.get("status") if isinstance(result, dict) else None,
    )
    return

    # (placeholder removido — checagem de event_type desconhecido
    # já feita no início da função)
    return


def main() -> int:
    configure_logging()
    logger.info(
        "sofia_inbound_worker_started",
        consumer_name=CONSUMER_NAME,
        block_ms=BLOCK_MS,
        count=COUNT_PER_READ,
    )

    bus = get_event_bus()
    consumer = bus.consumer(
        stream=Streams.INBOUND,
        group=ConsumerGroups.INBOUND,
        consumer_name=CONSUMER_NAME,
    )

    while not _shutdown:
        try:
            count_processed = 0
            for entry in consumer.read(count=COUNT_PER_READ, block_ms=BLOCK_MS):
                if _shutdown:
                    break
                started = time.perf_counter()
                try:
                    process_entry(entry.data)
                    consumer.ack(entry.id)
                    duration_ms = (time.perf_counter() - started) * 1000
                    logger.debug(
                        "sofia_inbound_ack",
                        entry_id=entry.id,
                        duration_ms=round(duration_ms, 2),
                        delivery_count=entry.delivery_count,
                    )
                    count_processed += 1
                except Exception as exc:
                    logger.exception(
                        "sofia_inbound_processing_failed",
                        entry_id=entry.id,
                        delivery_count=entry.delivery_count,
                        error_class=type(exc).__name__,
                    )
                    # nack — vai pra reclaim, depois DLQ se passar max_delivery
                    consumer.nack(entry.id)
            if count_processed == 0:
                # Block timeout — só sleep curto pra não hot-loop em
                # streams vazias (na prática xreadgroup já blockeia)
                continue
        except Exception as exc:
            # Erro fatal fora do entry processing — log e retry
            logger.exception("sofia_inbound_loop_failed", error=str(exc))
            time.sleep(2)

    logger.info("sofia_inbound_worker_stopped", consumer_name=CONSUMER_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
