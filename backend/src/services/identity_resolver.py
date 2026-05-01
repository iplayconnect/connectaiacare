"""IdentityResolver — phone E.164 → identidade(s) na plataforma.

Princípio: o phone é a chave universal. A partir dele resolvemos
quem é, em qual tenant, qual profile, e qual contexto carregar.

Ordem de match (do mais forte pro mais fraco):
    1. aia_health_users.phone               (auth identity, mais forte)
    2. aia_health_caregivers.phone          (cuidador profissional)
    3. aia_health_patients.proactive_call_phone (paciente B2C direto)
    4. aia_health_patients.responsible[*].phone (familiar)
    5. aia_health_user_phone_history.phone (active=TRUE)  (phone antigo)

Multi-tenant: mesmo phone aparecendo em 2 tenants → retorna ambos
matches. Super Sofia decide via heurística (último ativo) ou
pergunta ao usuário.

Anonymous: nenhum match → is_anonymous=True. Caller (super_sofia
router) deve mandar pro fluxo comercial/suporte (tenant
connectaiacare_central).

Cache: Redis hash `identity:{phone}` TTL 60s. Invalidação ainda
não implementada via Postgres trigger (Phase futura) — por
enquanto TTL curto basta.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from src.services.postgres import get_postgres
from src.services.redis_client import get_redis
from src.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 60
CACHE_KEY_PREFIX = "identity"


@dataclass
class IdentityMatch:
    """Um match individual. Phone pode ter N (mesmo phone em
    múltiplos tenants/perfis)."""
    tenant_id: str
    profile: str           # 'medico'|'cuidador_pro'|'familia'|'paciente_b2c'|...
    source: str            # 'users.phone'|'caregivers.phone'|'patients.proactive_call_phone'|'patients.responsible'|'phone_history'
    confidence: float      # 0.0–1.0 (quanto mais alto = mais forte)
    user_id: Optional[str] = None
    caregiver_id: Optional[str] = None
    patient_id: Optional[str] = None
    full_name: Optional[str] = None
    last_active_at: Optional[str] = None  # ISO 8601
    extra: dict = field(default_factory=dict)


@dataclass
class Identity:
    """Resultado completo da resolução de um phone."""
    phone: str
    matches: list[IdentityMatch]
    primary: Optional[IdentityMatch]
    is_anonymous: bool

    def to_dict(self) -> dict:
        return {
            "phone": self.phone,
            "matches": [asdict(m) for m in self.matches],
            "primary": asdict(self.primary) if self.primary else None,
            "is_anonymous": self.is_anonymous,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Identity":
        matches = [IdentityMatch(**m) for m in d.get("matches", [])]
        primary_d = d.get("primary")
        primary = IdentityMatch(**primary_d) if primary_d else None
        return cls(
            phone=d["phone"],
            matches=matches,
            primary=primary,
            is_anonymous=d["is_anonymous"],
        )


# ──────────────────────────────────────────────────────────────────
# Phone normalization
# ──────────────────────────────────────────────────────────────────


def normalize_phone_e164_br(raw: str | None) -> str | None:
    """Normaliza phone BR pra E.164 sem +.

    Aceita formatos: '51 99948-2737', '+55 51 99948-2737',
    '5551999482737', '(51) 9 9948-2737', '51999482737',
    '5599948482737' (sem 9 do DDD móvel).

    - Remove tudo não-dígito
    - Se 10 (fixo c/ DDD) ou 11 (móvel c/ DDD) → prepende 55
    - Se 12 (fixo c/ DDI) ou 13 (móvel c/ DDI) → mantém
    - Outros → None
    - Não inventa DDI: assume BR (55) só pra 10/11 dígitos
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) in (10, 11):
        digits = "55" + digits
    if len(digits) not in (12, 13):
        return None
    return digits


def phone_variants_for_match(phone_e164: str) -> list[str]:
    """Variantes possíveis pra match em DBs históricos.

    A base atual tem inconsistência: alguns rows têm 13 dígitos
    (5551999482737), outros 12 (555199482737 — sem 9 do móvel),
    Evolution as vezes manda 555196161700 (sem o 9).

    Retorna conjunto de strings pra ILIKE / IN. Sempre inclui o
    formato canônico.
    """
    variants = {phone_e164}
    if len(phone_e164) == 13 and phone_e164.startswith("55"):
        # 13 dígitos: 55 + DDD(2) + 9 + 8 dígitos. Variante: tira o 9.
        ddd = phone_e164[2:4]
        rest = phone_e164[5:]  # pula o 9
        if len(rest) == 8:
            variants.add(f"55{ddd}{rest}")
    if len(phone_e164) == 12 and phone_e164.startswith("55"):
        # 12 dígitos: pode ser fixo ou móvel sem 9. Adiciona variante com 9.
        ddd = phone_e164[2:4]
        rest = phone_e164[4:]
        if len(rest) == 8:
            variants.add(f"55{ddd}9{rest}")
    return list(variants)


# ──────────────────────────────────────────────────────────────────
# Resolver
# ──────────────────────────────────────────────────────────────────


class IdentityResolver:
    """Resolve phone → Identity. Singleton via get_identity_resolver()."""

    def __init__(self) -> None:
        self.db = get_postgres()
        self._redis = None  # lazy

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    # ── Public API ──

    def resolve(
        self,
        phone: str,
        *,
        tenant_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> Identity:
        """Resolve phone. tenant_id opcional: filtra matches só desse
        tenant (útil quando webhook já sabe tenant pela instance)."""
        normalized = normalize_phone_e164_br(phone)
        if not normalized:
            logger.warning("identity_phone_invalid", phone=phone)
            return Identity(phone=phone or "", matches=[], primary=None, is_anonymous=True)

        # Cache lookup (key inclui tenant_id se especificado)
        cache_key = self._cache_key(normalized, tenant_id)
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached:
                return cached

        matches = self._lookup_all_sources(normalized, tenant_id)
        primary = self._select_primary(matches)
        identity = Identity(
            phone=normalized,
            matches=matches,
            primary=primary,
            is_anonymous=primary is None,
        )

        self._cache_set(cache_key, identity)
        return identity

    def invalidate(self, phone: str) -> None:
        """Invalida cache. Chamar quando user muda de phone, etc."""
        normalized = normalize_phone_e164_br(phone)
        if not normalized:
            return
        try:
            keys = self.redis.keys(f"{CACHE_KEY_PREFIX}:{normalized}*")
            if keys:
                self.redis.delete(*keys)
        except Exception as exc:
            logger.warning("identity_cache_invalidate_failed", error=str(exc))

    # ── Internals ──

    def _cache_key(self, phone: str, tenant_id: Optional[str]) -> str:
        if tenant_id:
            return f"{CACHE_KEY_PREFIX}:{phone}:t:{tenant_id}"
        return f"{CACHE_KEY_PREFIX}:{phone}"

    def _cache_get(self, key: str) -> Optional[Identity]:
        try:
            raw = self.redis.get(key)
            if not raw:
                return None
            return Identity.from_dict(json.loads(raw))
        except Exception as exc:
            logger.debug("identity_cache_get_failed", error=str(exc))
            return None

    def _cache_set(self, key: str, identity: Identity) -> None:
        try:
            self.redis.setex(key, CACHE_TTL_SECONDS, json.dumps(identity.to_dict()))
        except Exception as exc:
            logger.debug("identity_cache_set_failed", error=str(exc))

    def _lookup_all_sources(
        self, phone: str, tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        """Roda todos os 5 lookups e agrega matches."""
        matches: list[IdentityMatch] = []
        variants = phone_variants_for_match(phone)

        matches.extend(self._lookup_users(variants, tenant_id))
        matches.extend(self._lookup_caregivers(variants, tenant_id))
        matches.extend(self._lookup_patients_proactive(variants, tenant_id))
        matches.extend(self._lookup_patients_responsible(variants, tenant_id))
        # phone history só consulta se nada match — evita ruído
        if not matches:
            matches.extend(self._lookup_phone_history(variants, tenant_id))

        return matches

    def _lookup_users(
        self, variants: list[str], tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        sql = (
            "SELECT id, tenant_id, role, full_name, last_login_at, active "
            "FROM aia_health_users "
            "WHERE phone = ANY(%s) AND active = TRUE"
        )
        params: list = [variants]
        if tenant_id:
            sql += " AND tenant_id = %s"
            params.append(tenant_id)
        try:
            rows = self.db.fetch_all(sql, tuple(params))
        except Exception as exc:
            logger.warning("identity_lookup_users_failed", error=str(exc))
            return []
        out: list[IdentityMatch] = []
        for r in rows:
            out.append(IdentityMatch(
                tenant_id=r["tenant_id"],
                profile=r["role"],
                source="users.phone",
                confidence=1.00,
                user_id=str(r["id"]),
                full_name=r.get("full_name"),
                last_active_at=(
                    r["last_login_at"].isoformat() if r.get("last_login_at") else None
                ),
            ))
        return out

    def _lookup_caregivers(
        self, variants: list[str], tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        sql = (
            "SELECT id, tenant_id, full_name, role, active, updated_at "
            "FROM aia_health_caregivers "
            "WHERE phone = ANY(%s) AND active = TRUE"
        )
        params: list = [variants]
        if tenant_id:
            sql += " AND tenant_id = %s"
            params.append(tenant_id)
        try:
            rows = self.db.fetch_all(sql, tuple(params))
        except Exception as exc:
            logger.warning("identity_lookup_caregivers_failed", error=str(exc))
            return []
        out: list[IdentityMatch] = []
        for r in rows:
            # Caregiver role pode ser cuidador_pro|enfermeiro|medico
            # dependendo do schema atual; default cuidador_pro.
            profile = (r.get("role") or "cuidador_pro").lower()
            out.append(IdentityMatch(
                tenant_id=r["tenant_id"],
                profile=profile,
                source="caregivers.phone",
                confidence=0.90,
                caregiver_id=str(r["id"]),
                full_name=r.get("full_name"),
                last_active_at=(
                    r["updated_at"].isoformat() if r.get("updated_at") else None
                ),
            ))
        return out

    def _lookup_patients_proactive(
        self, variants: list[str], tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        sql = (
            "SELECT id, tenant_id, full_name, active, updated_at "
            "FROM aia_health_patients "
            "WHERE proactive_call_phone = ANY(%s) AND active = TRUE"
        )
        params: list = [variants]
        if tenant_id:
            sql += " AND tenant_id = %s"
            params.append(tenant_id)
        try:
            rows = self.db.fetch_all(sql, tuple(params))
        except Exception as exc:
            logger.warning("identity_lookup_patients_proactive_failed", error=str(exc))
            return []
        out: list[IdentityMatch] = []
        for r in rows:
            out.append(IdentityMatch(
                tenant_id=r["tenant_id"],
                profile="paciente_b2c",
                source="patients.proactive_call_phone",
                confidence=0.85,
                patient_id=str(r["id"]),
                full_name=r.get("full_name"),
                last_active_at=(
                    r["updated_at"].isoformat() if r.get("updated_at") else None
                ),
            ))
        return out

    def _lookup_patients_responsible(
        self, variants: list[str], tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        """Familiar via campo JSONB responsible.

        Schema: {nurse_override?:{name,phone},
                 family:[{name,relationship,phone,level}]}
                 + legado top-level {name,phone,relationship}.
        """
        sql = (
            "SELECT id, tenant_id, full_name, responsible, active, updated_at "
            "FROM aia_health_patients "
            "WHERE active = TRUE AND responsible IS NOT NULL "
            "  AND ("
            "      (responsible->>'phone') = ANY(%s)"
            "      OR EXISTS ("
            "          SELECT 1 FROM jsonb_array_elements(COALESCE(responsible->'family','[]'::jsonb)) AS f"
            "          WHERE (f->>'phone') = ANY(%s)"
            "      )"
            "      OR (responsible->'nurse_override'->>'phone') = ANY(%s)"
            "  )"
        )
        params: list = [variants, variants, variants]
        if tenant_id:
            sql += " AND tenant_id = %s"
            params.append(tenant_id)
        try:
            rows = self.db.fetch_all(sql, tuple(params))
        except Exception as exc:
            logger.warning("identity_lookup_patients_responsible_failed", error=str(exc))
            return []
        out: list[IdentityMatch] = []
        for r in rows:
            resp = r.get("responsible") or {}
            family = resp.get("family") if isinstance(resp, dict) else None
            # Tenta achar nome do familiar específico
            family_name = None
            family_relationship = None
            if isinstance(family, list):
                for f in family:
                    if not isinstance(f, dict):
                        continue
                    fphone_normalized = normalize_phone_e164_br(f.get("phone"))
                    if fphone_normalized in variants or fphone_normalized == variants[0]:
                        family_name = f.get("name")
                        family_relationship = f.get("relationship")
                        break
            out.append(IdentityMatch(
                tenant_id=r["tenant_id"],
                profile="familia",
                source="patients.responsible",
                confidence=0.75,
                patient_id=str(r["id"]),
                full_name=family_name,  # nome do familiar, não do paciente
                last_active_at=(
                    r["updated_at"].isoformat() if r.get("updated_at") else None
                ),
                extra={
                    "patient_full_name": r.get("full_name"),
                    "relationship": family_relationship,
                },
            ))
        return out

    def _lookup_phone_history(
        self, variants: list[str], tenant_id: Optional[str],
    ) -> list[IdentityMatch]:
        """Phone que foi de algum user/caregiver/patient mas hoje
        está marcado active=TRUE no histórico (recente, ainda válido)."""
        sql = (
            "SELECT user_id, caregiver_id, patient_id, "
            "       phone, added_at, metadata "
            "FROM aia_health_user_phone_history "
            "WHERE phone = ANY(%s) AND active = TRUE"
        )
        try:
            rows = self.db.fetch_all(sql, (variants,))
        except Exception as exc:
            logger.warning("identity_lookup_phone_history_failed", error=str(exc))
            return []
        out: list[IdentityMatch] = []
        for r in rows:
            # Pra cada hit, busca tenant + profile do owner
            owner = self._resolve_phone_history_owner(r)
            if not owner:
                continue
            if tenant_id and owner.get("tenant_id") != tenant_id:
                continue
            out.append(IdentityMatch(
                tenant_id=owner["tenant_id"],
                profile=owner["profile"],
                source="phone_history",
                confidence=0.50,  # menor confiança (phone antigo)
                user_id=owner.get("user_id"),
                caregiver_id=owner.get("caregiver_id"),
                patient_id=owner.get("patient_id"),
                full_name=owner.get("full_name"),
                last_active_at=(
                    r["added_at"].isoformat() if r.get("added_at") else None
                ),
                extra={"history_metadata": r.get("metadata") or {}},
            ))
        return out

    def _resolve_phone_history_owner(self, history_row: dict) -> Optional[dict]:
        """Busca tenant+profile do dono original do phone histórico."""
        if history_row.get("user_id"):
            row = self.db.fetch_one(
                "SELECT tenant_id, role, full_name FROM aia_health_users "
                "WHERE id = %s AND active = TRUE",
                (history_row["user_id"],),
            )
            if row:
                return {
                    "tenant_id": row["tenant_id"],
                    "profile": row["role"],
                    "user_id": str(history_row["user_id"]),
                    "full_name": row.get("full_name"),
                }
        if history_row.get("caregiver_id"):
            row = self.db.fetch_one(
                "SELECT tenant_id, role, full_name FROM aia_health_caregivers "
                "WHERE id = %s AND active = TRUE",
                (history_row["caregiver_id"],),
            )
            if row:
                return {
                    "tenant_id": row["tenant_id"],
                    "profile": (row.get("role") or "cuidador_pro").lower(),
                    "caregiver_id": str(history_row["caregiver_id"]),
                    "full_name": row.get("full_name"),
                }
        if history_row.get("patient_id"):
            row = self.db.fetch_one(
                "SELECT tenant_id, full_name FROM aia_health_patients "
                "WHERE id = %s AND active = TRUE",
                (history_row["patient_id"],),
            )
            if row:
                return {
                    "tenant_id": row["tenant_id"],
                    "profile": "paciente_b2c",
                    "patient_id": str(history_row["patient_id"]),
                    "full_name": row.get("full_name"),
                }
        return None

    def _select_primary(
        self, matches: list[IdentityMatch],
    ) -> Optional[IdentityMatch]:
        """Heurística:
            1. Maior confidence
            2. Empate → mais recente last_active_at
            3. Empate → primeiro da lista
        """
        if not matches:
            return None
        sorted_matches = sorted(
            matches,
            key=lambda m: (
                -m.confidence,
                -(self._epoch(m.last_active_at) if m.last_active_at else 0),
            ),
        )
        return sorted_matches[0]

    @staticmethod
    def _epoch(iso_string: Optional[str]) -> float:
        if not iso_string:
            return 0
        try:
            from datetime import datetime
            return datetime.fromisoformat(iso_string.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_resolver_instance: Optional[IdentityResolver] = None


def get_identity_resolver() -> IdentityResolver:
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = IdentityResolver()
    return _resolver_instance
