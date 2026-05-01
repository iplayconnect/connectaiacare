"""Métricas Prometheus do voice-call-service.

Mantemos um conjunto enxuto e imediatamente útil pro piloto:

- ``active_calls``      → chamadas em andamento (gauge, label: direction)
- ``calls_started``     → contador, label: direction (inbound/outbound)
- ``calls_ended``       → contador, labels: direction, state
                          (CONFIRMED, DISCONNECTED, FAILED, etc.)
- ``grok_ws_connected`` → 1/0 — Grok WebSocket aberto agora
- ``tool_executions``   → contador, labels: name, ok (true/false)
- ``tool_latency``      → histograma, label: name
- ``grok_first_resp``   → histograma — segundos entre call CONFIRMED
                          e primeiro áudio out da Sofia
- ``interrupts``        → contador — vezes que o VAD interrompeu Sofia
- ``db_pool_in_use``    → gauge (psycopg2 ThreadedConnectionPool)
- ``db_pool_max``       → gauge

Uso:
    from services.metrics import metrics
    metrics.active_calls.labels(direction="inbound").inc()
    with metrics.tool_latency.labels(name="search_patients").time():
        run_tool()
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("voice_metrics")


class _Metrics:
    def __init__(self) -> None:
        try:
            from prometheus_client import (
                Counter, Gauge, Histogram, CollectorRegistry,
            )
        except ImportError:  # gracefully no-op se prometheus_client ausente
            logger.warning("prometheus_client_missing — metrics disabled")
            self._enabled = False
            return

        self._enabled = True
        self.registry = CollectorRegistry()

        self.active_calls = Gauge(
            "voice_call_active_calls",
            "Chamadas em andamento agora",
            ["direction"],
            registry=self.registry,
        )
        self.calls_started = Counter(
            "voice_call_calls_started_total",
            "Total de chamadas iniciadas",
            ["direction"],
            registry=self.registry,
        )
        self.calls_ended = Counter(
            "voice_call_calls_ended_total",
            "Total de chamadas encerradas",
            ["direction", "state"],
            registry=self.registry,
        )
        self.grok_ws_connected = Gauge(
            "voice_call_grok_ws_connected",
            "Grok Realtime WebSocket connections abertas agora",
            registry=self.registry,
        )
        self.tool_executions = Counter(
            "voice_call_tool_executions_total",
            "Tools executadas pela Sofia",
            ["name", "ok"],
            registry=self.registry,
        )
        self.tool_latency = Histogram(
            "voice_call_tool_latency_seconds",
            "Latência por tool (do start ao retorno)",
            ["name"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16),
            registry=self.registry,
        )
        self.grok_first_resp = Histogram(
            "voice_call_grok_first_response_seconds",
            "Segundos entre call CONFIRMED e primeiro áudio out da Sofia",
            buckets=(0.5, 1, 1.5, 2, 3, 4, 6, 9, 15),
            registry=self.registry,
        )
        self.interrupts = Counter(
            "voice_call_interrupts_total",
            "VAD interrompeu Sofia (usuário falou por cima)",
            registry=self.registry,
        )
        self.db_pool_in_use = Gauge(
            "voice_call_db_pool_in_use",
            "Conexões PG em uso agora",
            registry=self.registry,
        )
        self.db_pool_max = Gauge(
            "voice_call_db_pool_max",
            "Tamanho máximo do pool PG (maxconn)",
            registry=self.registry,
        )
        self.calls_origin_total = Counter(
            "voice_call_dial_phone_total",
            "Tool dial_phone disparada — Sofia originou nova chamada",
            ["scenario_code", "ok"],
            registry=self.registry,
        )

    # ── Helpers no-op se prometheus_client ausente ──
    def __getattr__(self, item: str) -> Any:  # pragma: no cover
        # Se não inicializado (lib ausente), devolve no-op.
        if not getattr(self, "_enabled", False):
            return _NoopMetric()
        raise AttributeError(item)


class _NoopMetric:
    def labels(self, *_a, **_kw):
        return self

    def inc(self, *_a, **_kw):
        return None

    def dec(self, *_a, **_kw):
        return None

    def set(self, *_a, **_kw):
        return None

    def observe(self, *_a, **_kw):
        return None

    def time(self):
        class _CM:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *_a):
                return False

        return _CM()


metrics = _Metrics()


def render_metrics() -> tuple[bytes, str]:
    """Retorna (payload, content_type) pra response Flask."""
    if not getattr(metrics, "_enabled", False):
        return b"# prometheus_client not installed\n", "text/plain"
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return generate_latest(metrics.registry), CONTENT_TYPE_LATEST
