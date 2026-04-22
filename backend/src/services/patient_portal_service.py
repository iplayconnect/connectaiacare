"""Patient Portal Service — PIN de acesso + resumo + preços (ADR futuro).

Gera PIN de 6 dígitos na assinatura da teleconsulta, armazena bcrypt hash,
envia via WhatsApp, valida acessos com rate-limit (5 tentativas → lock).

Integração:
    - WhatsApp (Evolution API) — envio da mensagem
    - patient_summary_service — resumo em linguagem simples (Claude)
    - price_search_service — busca real de preços via scraper-service

Segurança:
    - PIN nunca em claro no banco (bcrypt hash)
    - 24h TTL forçado
    - Rate limit 5 tentativas
    - Audit log completo (LGPD Art. 37)
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Config
PIN_LENGTH = 6
TTL_HOURS = 24
MAX_FAILED_ATTEMPTS = 5
PRICE_CACHE_TTL_HOURS = 6
SUMMARY_CACHE_TTL_HOURS = 24  # mesmo TTL do PIN


class PatientPortalService:
    def __init__(self):
        self.db = get_postgres()

    # ══════════════════════════════════════════════════════════════════
    # Geração de PIN (chamado no sign_teleconsulta)
    # ══════════════════════════════════════════════════════════════════

    def create_access(
        self,
        teleconsultation_id: str,
        tenant_id: str,
        recipient_phone: str,
    ) -> tuple[str, dict]:
        """Gera PIN, armazena hash, retorna PIN em claro (só pra envio WhatsApp).

        Idempotente: se já existe acesso ativo não-revogado, revoga o antigo
        e cria novo. Evita que médico precise reassinar pra regerar PIN.
        """
        # Revoga acessos ativos anteriores (idempotência)
        self.db.execute(
            """
            UPDATE aia_health_patient_portal_access
            SET revoked_at = NOW(), revoked_reason = 'superseded_by_new_pin'
            WHERE teleconsultation_id = %s
              AND revoked_at IS NULL
              AND expires_at > NOW()
            """,
            (teleconsultation_id,),
        )

        # Gera PIN de 6 dígitos usando secrets (criptográfico)
        pin_plain = "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))
        pin_hash = bcrypt.hashpw(pin_plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        expires_at = datetime.now(timezone.utc) + timedelta(hours=TTL_HOURS)

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_patient_portal_access (
                teleconsultation_id, tenant_id, pin_hash,
                recipient_phone, expires_at
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING id, teleconsultation_id, expires_at, created_at
            """,
            (
                teleconsultation_id, tenant_id, pin_hash,
                recipient_phone, expires_at,
            ),
        )

        self._log(
            row["id"], teleconsultation_id, tenant_id,
            action="pin_sent",
            detail={"recipient_phone": recipient_phone, "expires_at": expires_at.isoformat()},
        )

        logger.info(
            "patient_portal_pin_created",
            tc_id=teleconsultation_id,
            expires_at=expires_at.isoformat(),
            pin_length=PIN_LENGTH,
        )
        return pin_plain, row

    # ══════════════════════════════════════════════════════════════════
    # Validação de PIN (chamado pela rota pública)
    # ══════════════════════════════════════════════════════════════════

    def validate_pin(
        self,
        teleconsultation_id: str,
        pin_plain: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Valida PIN. Retorna status + access record se ok.

        Estados possíveis:
            - valid: acesso liberado
            - invalid_pin: PIN errado (incrementa failed_attempts)
            - expired: TTL expirou
            - locked: excedeu MAX_FAILED_ATTEMPTS
            - revoked: médico revogou
            - not_found: não existe acesso pra essa teleconsulta
        """
        record = self.db.fetch_one(
            """
            SELECT id, teleconsultation_id, tenant_id, pin_hash,
                   expires_at, failed_attempts, locked_at, revoked_at,
                   access_count, first_accessed_at
            FROM aia_health_patient_portal_access
            WHERE teleconsultation_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (teleconsultation_id,),
        )
        if not record:
            return {"status": "not_found"}

        now = datetime.now(timezone.utc)

        if record.get("revoked_at"):
            self._log(record["id"], teleconsultation_id, record["tenant_id"],
                      action="access_denied",
                      detail={"reason": "revoked", "ip": ip_address},
                      ip=ip_address, ua=user_agent)
            return {"status": "revoked"}

        if record.get("locked_at"):
            return {"status": "locked"}

        # Normaliza expires_at pra timezone-aware
        exp = record["expires_at"]
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < now:
            self._log(record["id"], teleconsultation_id, record["tenant_id"],
                      action="access_denied",
                      detail={"reason": "expired", "ip": ip_address},
                      ip=ip_address, ua=user_agent)
            return {"status": "expired"}

        # Valida PIN
        ok = bcrypt.checkpw(
            pin_plain.encode("utf-8"),
            record["pin_hash"].encode("utf-8"),
        )
        if not ok:
            new_failed = (record["failed_attempts"] or 0) + 1
            if new_failed >= MAX_FAILED_ATTEMPTS:
                self.db.execute(
                    """
                    UPDATE aia_health_patient_portal_access
                    SET failed_attempts = %s, locked_at = NOW()
                    WHERE id = %s
                    """,
                    (new_failed, record["id"]),
                )
                self._log(record["id"], teleconsultation_id, record["tenant_id"],
                          action="locked",
                          detail={"attempts": new_failed, "ip": ip_address},
                          ip=ip_address, ua=user_agent)
                return {"status": "locked"}

            self.db.execute(
                "UPDATE aia_health_patient_portal_access SET failed_attempts = %s WHERE id = %s",
                (new_failed, record["id"]),
            )
            self._log(record["id"], teleconsultation_id, record["tenant_id"],
                      action="access_denied",
                      detail={"reason": "invalid_pin", "attempt": new_failed, "ip": ip_address},
                      ip=ip_address, ua=user_agent)
            return {"status": "invalid_pin", "attempts_remaining": MAX_FAILED_ATTEMPTS - new_failed}

        # Sucesso: atualiza access_count + first_accessed_at
        self.db.execute(
            """
            UPDATE aia_health_patient_portal_access
            SET access_count = access_count + 1,
                first_accessed_at = COALESCE(first_accessed_at, NOW()),
                last_accessed_at = NOW(),
                failed_attempts = 0
            WHERE id = %s
            """,
            (record["id"],),
        )
        self._log(record["id"], teleconsultation_id, record["tenant_id"],
                  action="access_granted",
                  detail={"ip": ip_address, "access_count": (record["access_count"] or 0) + 1},
                  ip=ip_address, ua=user_agent)

        return {"status": "valid", "access_id": record["id"]}

    # ══════════════════════════════════════════════════════════════════
    # Cache helpers (evita rescrape + re-llm a cada render)
    # ══════════════════════════════════════════════════════════════════

    def get_cached_summary(self, tc_id: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT patient_summary, patient_summary_at
            FROM aia_health_patient_portal_access
            WHERE teleconsultation_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tc_id,),
        )
        if not row or not row.get("patient_summary") or not row.get("patient_summary_at"):
            return None
        age = datetime.now(timezone.utc) - self._as_utc(row["patient_summary_at"])
        if age.total_seconds() > SUMMARY_CACHE_TTL_HOURS * 3600:
            return None
        return row["patient_summary"]

    def save_summary(self, tc_id: str, summary: dict) -> None:
        self.db.execute(
            """
            UPDATE aia_health_patient_portal_access
            SET patient_summary = %s, patient_summary_at = NOW()
            WHERE teleconsultation_id = %s
              AND id = (
                  SELECT id FROM aia_health_patient_portal_access
                  WHERE teleconsultation_id = %s
                  ORDER BY created_at DESC
                  LIMIT 1
              )
            """,
            (self.db.json_adapt(summary), tc_id, tc_id),
        )

    def get_cached_prices(self, tc_id: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT price_cache, price_cache_at
            FROM aia_health_patient_portal_access
            WHERE teleconsultation_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tc_id,),
        )
        if not row or not row.get("price_cache") or not row.get("price_cache_at"):
            return None
        age = datetime.now(timezone.utc) - self._as_utc(row["price_cache_at"])
        if age.total_seconds() > PRICE_CACHE_TTL_HOURS * 3600:
            return None
        return row["price_cache"]

    def save_prices(self, tc_id: str, prices: dict) -> None:
        self.db.execute(
            """
            UPDATE aia_health_patient_portal_access
            SET price_cache = %s, price_cache_at = NOW()
            WHERE teleconsultation_id = %s
              AND id = (
                  SELECT id FROM aia_health_patient_portal_access
                  WHERE teleconsultation_id = %s
                  ORDER BY created_at DESC
                  LIMIT 1
              )
            """,
            (self.db.json_adapt(prices), tc_id, tc_id),
        )

    # ══════════════════════════════════════════════════════════════════
    # Internals
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _log(
        self,
        portal_access_id: str | None,
        tc_id: str,
        tenant_id: str,
        action: str,
        detail: dict | None = None,
        ip: str | None = None,
        ua: str | None = None,
    ) -> None:
        try:
            self.db.execute(
                """
                INSERT INTO aia_health_patient_portal_access_log
                    (portal_access_id, teleconsultation_id, tenant_id,
                     ip_address, user_agent, action, detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    portal_access_id, tc_id, tenant_id,
                    ip, ua, action, self.db.json_adapt(detail or {}),
                ),
            )
        except Exception as exc:
            logger.warning("portal_access_log_failed", error=str(exc), action=action)


_instance: PatientPortalService | None = None


def get_patient_portal_service() -> PatientPortalService:
    global _instance
    if _instance is None:
        _instance = PatientPortalService()
    return _instance
