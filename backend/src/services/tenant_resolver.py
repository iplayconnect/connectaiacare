"""TenantResolver — resolve qual tenant deve receber inbound.

Casos de uso:
    1. Webhook WhatsApp: instance_name → tenant
    2. Voice inbound: did → tenant
    3. Lead anônimo: nenhum dos acima → connectaiacare_central

Cache Redis 5min (tenant config muda raramente; super_admin atualiza
e o cache invalida via TTL natural).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

from src.services.postgres import get_postgres
from src.services.redis_client import get_redis
from src.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300  # 5min
CACHE_PREFIX = "tenant"

CENTRAL_TENANT_ID = "connectaiacare_central"


@dataclass
class TenantInfo:
    id: str
    name: str
    ai_name: str
    ai_voice: str
    active: bool
    suspended: bool
    whatsapp_phone: Optional[str]
    whatsapp_evolution_instance: Optional[str]
    voice_did: Optional[str]
    metadata: dict
    integrations_enabled: dict

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "TenantInfo":
        return cls(
            id=row["id"],
            name=row.get("name") or row["id"],
            ai_name=row.get("ai_name") or "Sofia",
            ai_voice=row.get("ai_voice") or "ara",
            active=bool(row.get("active", True)),
            suspended=bool(row.get("suspended", False)),
            whatsapp_phone=row.get("whatsapp_phone"),
            whatsapp_evolution_instance=row.get("whatsapp_evolution_instance"),
            voice_did=row.get("voice_did"),
            metadata=row.get("metadata") or {},
            integrations_enabled=row.get("integrations_enabled") or {},
        )


class TenantResolver:
    def __init__(self) -> None:
        self.db = get_postgres()
        self._redis = None

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    # ── Public API ──

    def from_evolution_instance(
        self, instance_name: str, *, use_cache: bool = True,
    ) -> Optional[TenantInfo]:
        """Resolve tenant pela instância Evolution. None se não encontrado."""
        if not instance_name:
            return None
        cache_key = f"{CACHE_PREFIX}:by_instance:{instance_name}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        row = self.db.fetch_one(
            "SELECT * FROM aia_health_tenants "
            "WHERE whatsapp_evolution_instance = %s "
            "  AND active = TRUE AND suspended = FALSE",
            (instance_name,),
        )
        tenant = TenantInfo.from_row(row) if row else None
        if tenant:
            self._cache_set(cache_key, tenant)
        return tenant

    def from_voice_did(
        self, did: str, *, use_cache: bool = True,
    ) -> Optional[TenantInfo]:
        if not did:
            return None
        cache_key = f"{CACHE_PREFIX}:by_did:{did}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        row = self.db.fetch_one(
            "SELECT * FROM aia_health_tenants "
            "WHERE voice_did = %s AND active = TRUE AND suspended = FALSE",
            (did,),
        )
        tenant = TenantInfo.from_row(row) if row else None
        if tenant:
            self._cache_set(cache_key, tenant)
        return tenant

    def by_id(
        self, tenant_id: str, *, use_cache: bool = True,
    ) -> Optional[TenantInfo]:
        if not tenant_id:
            return None
        cache_key = f"{CACHE_PREFIX}:by_id:{tenant_id}"
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached
        row = self.db.fetch_one(
            "SELECT * FROM aia_health_tenants WHERE id = %s",
            (tenant_id,),
        )
        tenant = TenantInfo.from_row(row) if row else None
        if tenant:
            self._cache_set(cache_key, tenant)
        return tenant

    def central(self) -> TenantInfo:
        """Tenant central pra leads anônimos. Garantido a existir
        via migration 061. Lança RuntimeError se ausente — isso
        seria um bug grave de provisionamento.
        """
        tenant = self.by_id(CENTRAL_TENANT_ID)
        if not tenant:
            raise RuntimeError(
                f"Tenant central '{CENTRAL_TENANT_ID}' não existe — "
                "migration 061_super_sofia_foundation deve ter rodado."
            )
        return tenant

    def invalidate_all(self) -> None:
        """Invalida todo cache de tenant. Use quando admin atualizar
        config (PATCH /api/system/tenants/:id)."""
        try:
            keys = self.redis.keys(f"{CACHE_PREFIX}:*")
            if keys:
                self.redis.delete(*keys)
        except Exception as exc:
            logger.warning("tenant_cache_invalidate_failed", error=str(exc))

    def invalidate(self, tenant_id: str) -> None:
        """Invalida cache de UM tenant específico (todos os índices
        — by_id, by_instance, by_did)."""
        try:
            tenant = self.by_id(tenant_id, use_cache=False)
            keys_to_del = [f"{CACHE_PREFIX}:by_id:{tenant_id}"]
            if tenant:
                if tenant.whatsapp_evolution_instance:
                    keys_to_del.append(
                        f"{CACHE_PREFIX}:by_instance:"
                        f"{tenant.whatsapp_evolution_instance}"
                    )
                if tenant.voice_did:
                    keys_to_del.append(f"{CACHE_PREFIX}:by_did:{tenant.voice_did}")
            self.redis.delete(*keys_to_del)
        except Exception as exc:
            logger.warning("tenant_cache_invalidate_one_failed", error=str(exc))

    # ── Internals ──

    def _cache_get(self, key: str) -> Optional[TenantInfo]:
        try:
            raw = self.redis.get(key)
            if not raw:
                return None
            return TenantInfo(**json.loads(raw))
        except Exception as exc:
            logger.debug("tenant_cache_get_failed", error=str(exc))
            return None

    def _cache_set(self, key: str, tenant: TenantInfo) -> None:
        try:
            self.redis.setex(key, CACHE_TTL_SECONDS, json.dumps(tenant.to_dict()))
        except Exception as exc:
            logger.debug("tenant_cache_set_failed", error=str(exc))


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_instance: Optional[TenantResolver] = None


def get_tenant_resolver() -> TenantResolver:
    global _instance
    if _instance is None:
        _instance = TenantResolver()
    return _instance
