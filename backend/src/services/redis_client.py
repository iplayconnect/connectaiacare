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
    """Singleton Redis. Pool default tamanho 10, decode_responses=True."""
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
            socket_connect_timeout=2,
            socket_timeout=5,
            retry_on_timeout=True,
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
