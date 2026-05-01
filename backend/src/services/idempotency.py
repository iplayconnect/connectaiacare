"""Idempotency helper — Redis SETNX pra dedupe de eventos.

Webhook recebe message_id do Evolution. Se já vimos esse id, skip.
Default TTL 24h (Evolution não retry depois disso).

Tools de ação também usam (Phase C): mesmo idempotency key não
cria registro duplicado.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from src.services.redis_client import get_redis


DEFAULT_TTL_SECONDS = 86400  # 24h


def is_first_occurrence(
    namespace: str,
    key: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    """Returns True se é a primeira vez que vemos (namespace, key).
    False se já vimos (duplicado).

    Usa Redis SETNX. Threadsafe e atomic.
    """
    if not key:
        return True  # se sem key, deixa passar (não bloqueia)
    redis_key = f"idemp:{namespace}:{key}"
    return bool(get_redis().set(redis_key, "1", nx=True, ex=ttl_seconds))


def hash_payload(payload: dict) -> str:
    """Gera hash determinístico de payload pra usar como
    idempotency key quando não há id explícito."""
    import json as _json
    canonical = _json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]
