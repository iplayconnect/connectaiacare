"""Safety Queue Executor — worker que processa timeouts do guardrail queue.

Roda a cada 30s. Verifica items com `auto_execute_after < NOW`:
  - severity=critical AND auto_execute_on_timeout_critical=true → auto_executed
  - outras severidades → expired

Concorrência: pg_try_advisory_lock próprio (não conflita com outros schedulers).
"""
from __future__ import annotations

import os
import socket
import threading

from src.services import safety_guardrail
from src.utils.logger import get_logger

logger = get_logger(__name__)

SAFETY_QUEUE_LOCK_KEY = 5527391081
TICK_INTERVAL_SEC = int(os.getenv("SAFETY_QUEUE_TICK_SEC", "30"))


class SafetyQueueExecutor:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="safety-queue-executor", daemon=True,
        )
        self._thread.start()
        logger.info(
            "safety_queue_executor_started worker_id=%s tick=%ds",
            self._worker_id, TICK_INTERVAL_SEC,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _try_acquire_lock(self) -> bool:
        from src.services.postgres import get_postgres
        row = get_postgres().fetch_one(
            "SELECT pg_try_advisory_lock(%s) AS got", (SAFETY_QUEUE_LOCK_KEY,),
        )
        return bool(row and row.get("got"))

    def _release_lock(self) -> None:
        from src.services.postgres import get_postgres
        try:
            get_postgres().execute(
                "SELECT pg_advisory_unlock(%s)", (SAFETY_QUEUE_LOCK_KEY,),
            )
        except Exception:
            pass

    def _loop(self) -> None:
        # Pequeno delay no boot
        self._stop_event.wait(15)
        while not self._stop_event.is_set():
            try:
                if self._try_acquire_lock():
                    try:
                        n = safety_guardrail.execute_pending_timeouts()
                        if n:
                            logger.info("safety_queue_auto_executed count=%d", n)
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("safety_queue_tick_error: %s", exc)
            self._stop_event.wait(TICK_INTERVAL_SEC)


_singleton: SafetyQueueExecutor | None = None


def get_executor() -> SafetyQueueExecutor:
    global _singleton
    if _singleton is None:
        _singleton = SafetyQueueExecutor()
    return _singleton
