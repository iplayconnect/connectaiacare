"""Cron worker que dispara collective_memory_service.run_one_cycle() 1×/dia.

Single-writer via pg_try_advisory_lock — múltiplos workers Gunicorn não
duplicam a extração. Roda em thread daemon iniciada pelo sofia_app.

Variáveis:
  ENABLE_COLLECTIVE_MEMORY (default true)
  SOFIA_COLLECTIVE_TICK_SEC (default 21600 = 6h — checa quem é dono do lock,
    e quem ganhar roda o ciclo se já passou ≥ 24h desde a última run)
  SOFIA_COLLECTIVE_INTERVAL_HOURS (default 24 = 1×/dia)
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import datetime, timezone

from src import persistence

logger = logging.getLogger(__name__)

COLLECTIVE_LOCK_KEY = 884219034
TICK_INTERVAL_SEC = int(os.getenv("SOFIA_COLLECTIVE_TICK_SEC") or "21600")  # 6h
INTERVAL_HOURS = int(os.getenv("SOFIA_COLLECTIVE_INTERVAL_HOURS") or "24")


class CollectiveInsightsScheduler:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="collective-insights", daemon=True,
        )
        self._thread.start()
        logger.info(
            "collective_insights_scheduler_started worker_id=%s tick=%ds interval_h=%d",
            self._worker_id, TICK_INTERVAL_SEC, INTERVAL_HOURS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=30)

    def _try_acquire_lock(self) -> bool:
        row = persistence.fetch_one(
            "SELECT pg_try_advisory_lock(%s) AS got", (COLLECTIVE_LOCK_KEY,),
        )
        return bool(row and row.get("got"))

    def _release_lock(self) -> None:
        try:
            persistence.execute(
                "SELECT pg_advisory_unlock(%s)", (COLLECTIVE_LOCK_KEY,),
            )
        except Exception:
            pass

    def _due_for_run(self) -> bool:
        cursor = persistence.fetch_one(
            "SELECT last_run_at FROM aia_health_sofia_collective_cursor WHERE id = 1"
        )
        if not cursor or not cursor.get("last_run_at"):
            return True
        last = cursor["last_run_at"]
        delta_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return delta_h >= INTERVAL_HOURS

    def _loop(self) -> None:
        # Pequeno delay no boot pra evitar race com migrações
        self._stop_event.wait(120)
        from src import collective_memory_service  # late import (cycle-safe)
        while not self._stop_event.is_set():
            try:
                if self._try_acquire_lock():
                    try:
                        if self._due_for_run():
                            stats = collective_memory_service.run_one_cycle()
                            logger.info(
                                "collective_cycle_done stats=%s", stats
                            )
                        else:
                            logger.debug("collective_cycle_skipped not_due")
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("collective_tick_error: %s", exc)
            self._stop_event.wait(TICK_INTERVAL_SEC)


_singleton: CollectiveInsightsScheduler | None = None


def get_scheduler() -> CollectiveInsightsScheduler:
    global _singleton
    if _singleton is None:
        _singleton = CollectiveInsightsScheduler()
    return _singleton
