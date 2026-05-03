"""Redis client compartilhado.

Singleton com pool de conexões. Todos os services Phase A
(IdentityResolver cache, rate limit, idempotency, futuro event bus)
consomem daqui.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import redis

_lock = threading.Lock()
_instance: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """Singleton Redis. Pool default tamanho 10, decode_responses=True.

    socket_timeout precisa ser MAIOR que qualquer comando bloqueante
    (XREADGROUP block, BLPOP timeout). Default 60s cobre BLOCK_MS=5000ms
    e BLOCK_MS=30000 com folga.

    Bug observado em prod 2026-05-03: socket_timeout=5s igual ao
    WORKER_BLOCK_MS=5000ms fazia o socket levantar TimeoutError exatamente
    quando o XREADGROUP terminava o block. Workers (sofia-inbound,
    delivery) entravam em loop de timeout e msgs do stream ficavam
    presas. Sofia respondia por sorte (quando msg nova chegava durante
    o pequeno window de socket vivo entre timeouts). Healthchecks dos
    workers viraram UNHEALTHY em loop.

    Fix: socket_timeout=60s default + health_check_interval=30s pra
    detectar conexões mortas sem cortar blocking commands. Override
    via env var REDIS_SOCKET_TIMEOUT pra testes.
    """
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        pool = redis.ConnectionPool.from_url(
            url,
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
            decode_responses=True,
            socket_connect_timeout=int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5")),
            socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "60")),
            socket_keepalive=True,
            retry_on_timeout=True,
            health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")),
        )
        _instance = redis.Redis(connection_pool=pool)
        return _instance


def close_redis() -> None:
    """Pra testes / shutdown limpo."""
    global _instance
    if _instance is not None:
        try:
            _instance.connection_pool.disconnect()
        finally:
            _instance = None
