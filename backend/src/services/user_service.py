"""User service — CRUD de usuários autenticáveis + sessões de refresh.

Tabela: aia_health_users (UUID), aia_health_user_sessions (BIGSERIAL).
Hash de senha: bcrypt via passlib (já em requirements.txt).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from passlib.hash import bcrypt

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    """bcrypt com cost 12 (padrão passlib)."""
    return bcrypt.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ─── Users ────────────────────────────────────────────────

_USER_COLUMNS = """
    id, tenant_id, email, password_hash, full_name, role,
    permissions, profile_id, avatar_url, phone,
    crm_register, coren_register, caregiver_id, patient_id,
    allowed_patient_ids, partner_org, active,
    password_change_required, mfa_enabled,
    last_login_at, metadata, created_at, updated_at
"""

_USER_COLUMNS_PUBLIC = """
    id, tenant_id, email, full_name, role,
    permissions, profile_id, avatar_url, phone,
    crm_register, coren_register, caregiver_id, patient_id,
    allowed_patient_ids, partner_org, active,
    password_change_required, mfa_enabled,
    last_login_at, metadata, created_at, updated_at
"""


def get_user_by_email(tenant_id: str, email: str) -> dict | None:
    return get_postgres().fetch_one(
        f"SELECT {_USER_COLUMNS} FROM aia_health_users "
        "WHERE tenant_id = %s AND lower(email) = lower(%s)",
        (tenant_id, email),
    )


def get_user_by_id(user_id: str, *, with_password: bool = False) -> dict | None:
    cols = _USER_COLUMNS if with_password else _USER_COLUMNS_PUBLIC
    return get_postgres().fetch_one(
        f"SELECT {cols} FROM aia_health_users WHERE id = %s",
        (user_id,),
    )


def find_user_any_tenant(email: str) -> dict | None:
    """Procura usuário por email em qualquer tenant (super_admin tem precedência)."""
    return get_postgres().fetch_one(
        f"""
        SELECT {_USER_COLUMNS} FROM aia_health_users
        WHERE lower(email) = lower(%s) AND active = TRUE
        ORDER BY CASE role WHEN 'super_admin' THEN 0 WHEN 'admin_tenant' THEN 1 ELSE 2 END
        LIMIT 1
        """,
        (email,),
    )


def list_users(tenant_id: str, *, include_inactive: bool = False) -> list[dict]:
    where = "WHERE tenant_id = %s"
    params: list = [tenant_id]
    if not include_inactive:
        where += " AND active = TRUE"
    return get_postgres().fetch_all(
        f"SELECT {_USER_COLUMNS_PUBLIC} FROM aia_health_users {where} "
        "ORDER BY full_name",
        tuple(params),
    )


def update_user(user_id: str, fields: dict) -> dict | None:
    """Atualiza campos editáveis. Ignora password_hash e metadata-only fields."""
    allowed = {
        "full_name", "role", "phone", "avatar_url",
        "crm_register", "coren_register",
        "caregiver_id", "patient_id",
        "allowed_patient_ids", "partner_org",
        "active", "permissions", "profile_id",
    }
    sets: list[str] = []
    values: list = []
    pg = get_postgres()
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"permissions", "allowed_patient_ids"}:
            sets.append(f"{key} = %s")
            values.append(pg.json_adapt(value or []))
        else:
            sets.append(f"{key} = %s")
            values.append(value)
    if not sets:
        return get_user_by_id(user_id)
    values.append(user_id)
    return pg.insert_returning(
        f"UPDATE aia_health_users SET {', '.join(sets)} "
        f"WHERE id = %s RETURNING {_USER_COLUMNS_PUBLIC}",
        tuple(values),
    )


def soft_delete_user(user_id: str) -> None:
    get_postgres().execute(
        "UPDATE aia_health_users SET active = FALSE WHERE id = %s",
        (user_id,),
    )


# ─── Profiles (Bloco C) ────────────────────────────────────

def get_profile_by_id(profile_id: str) -> dict | None:
    return get_postgres().fetch_one(
        "SELECT id, tenant_id, slug, display_name, description, "
        "permissions, config, active "
        "FROM aia_health_profiles WHERE id = %s",
        (profile_id,),
    )


def list_profiles(tenant_id: str) -> list[dict]:
    return get_postgres().fetch_all(
        "SELECT id, tenant_id, slug, display_name, description, "
        "permissions, config, active, created_at, updated_at "
        "FROM aia_health_profiles WHERE tenant_id = %s AND active = TRUE "
        "ORDER BY display_name",
        (tenant_id,),
    )


def create_user(
    tenant_id: str,
    email: str,
    full_name: str,
    password: str,
    role: str,
    *,
    permissions: list[str] | None = None,
    profile_id: str | None = None,
    avatar_url: str | None = None,
    phone: str | None = None,
    crm_register: str | None = None,
    coren_register: str | None = None,
    caregiver_id: str | None = None,
    patient_id: str | None = None,
    allowed_patient_ids: list[str] | None = None,
    partner_org: str | None = None,
    password_change_required: bool = False,
    metadata: dict | None = None,
) -> dict | None:
    pg = get_postgres()
    return pg.insert_returning(
        """
        INSERT INTO aia_health_users
            (tenant_id, email, password_hash, full_name, role,
             permissions, profile_id, avatar_url, phone,
             crm_register, coren_register, caregiver_id, patient_id,
             allowed_patient_ids, partner_org, password_change_required, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, tenant_id, email, full_name, role, permissions, profile_id,
                  avatar_url, phone, active, password_change_required, created_at
        """,
        (
            tenant_id,
            email.lower(),
            hash_password(password),
            full_name,
            role,
            pg.json_adapt(permissions or []),
            profile_id,
            avatar_url,
            phone,
            crm_register,
            coren_register,
            caregiver_id,
            patient_id,
            pg.json_adapt(allowed_patient_ids or []),
            partner_org,
            password_change_required,
            pg.json_adapt(metadata or {}),
        ),
    )


def record_login(user_id: str) -> None:
    get_postgres().execute(
        "UPDATE aia_health_users SET last_login_at = NOW() WHERE id = %s",
        (user_id,),
    )


def set_password(user_id: str, new_password: str) -> None:
    get_postgres().execute(
        """
        UPDATE aia_health_users
        SET password_hash = %s, password_change_required = FALSE
        WHERE id = %s
        """,
        (hash_password(new_password), user_id),
    )


# ─── Refresh sessions ─────────────────────────────────────

def create_refresh_session(
    tenant_id: str,
    user_id: str,
    refresh_days: int,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, datetime]:
    refresh_token = secrets.token_urlsafe(48)
    refresh_hash = _hash_refresh_token(refresh_token)
    expires_at = _now_utc() + timedelta(days=refresh_days)
    get_postgres().execute(
        """
        INSERT INTO aia_health_user_sessions
            (tenant_id, user_id, refresh_token_hash, expires_at, user_agent, ip)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (tenant_id, user_id, refresh_hash, expires_at, user_agent, ip),
    )
    return refresh_token, expires_at


def get_session_by_token(refresh_token: str) -> dict | None:
    return get_postgres().fetch_one(
        """
        SELECT id, tenant_id, user_id, expires_at, revoked_at
        FROM aia_health_user_sessions
        WHERE refresh_token_hash = %s
        """,
        (_hash_refresh_token(refresh_token),),
    )


def revoke_session(session_id: int) -> None:
    get_postgres().execute(
        "UPDATE aia_health_user_sessions SET revoked_at = NOW() WHERE id = %s",
        (session_id,),
    )


def revoke_all_sessions(user_id: str) -> None:
    get_postgres().execute(
        """
        UPDATE aia_health_user_sessions SET revoked_at = NOW()
        WHERE user_id = %s AND revoked_at IS NULL
        """,
        (user_id,),
    )


# ─── Seed inicial via env vars ────────────────────────────

def ensure_seed_users() -> None:
    """Cria usuários iniciais (super_admin + parceiro) se env vars setadas e não existirem.

    Variáveis suportadas:
      HEALTH_ADMIN_EMAIL / HEALTH_ADMIN_PASSWORD / HEALTH_ADMIN_NAME (opcional)
      HEALTH_PARTNER_EMAIL / HEALTH_PARTNER_PASSWORD / HEALTH_PARTNER_NAME / HEALTH_PARTNER_ORG

    Idempotente: skip silencioso se usuário já existe.
    """
    import os

    tenant_id = os.getenv("TENANT_ID", "connectaiacare_demo")

    admin_email = (os.getenv("HEALTH_ADMIN_EMAIL") or "").strip().lower()
    admin_password = os.getenv("HEALTH_ADMIN_PASSWORD") or ""
    admin_name = os.getenv("HEALTH_ADMIN_NAME") or "Admin"

    if admin_email and admin_password:
        if not get_user_by_email(tenant_id, admin_email):
            try:
                create_user(
                    tenant_id=tenant_id,
                    email=admin_email,
                    full_name=admin_name,
                    password=admin_password,
                    role="super_admin",
                    password_change_required=True,
                )
                logger.info("seed_super_admin_created", email=admin_email)
            except Exception as exc:  # noqa: BLE001
                logger.error("seed_super_admin_failed", error=str(exc))

    partner_email = (os.getenv("HEALTH_PARTNER_EMAIL") or "").strip().lower()
    partner_password = os.getenv("HEALTH_PARTNER_PASSWORD") or ""
    partner_name = os.getenv("HEALTH_PARTNER_NAME") or "Parceiro"
    partner_org = os.getenv("HEALTH_PARTNER_ORG") or ""

    if partner_email and partner_password:
        if not get_user_by_email(tenant_id, partner_email):
            try:
                create_user(
                    tenant_id=tenant_id,
                    email=partner_email,
                    full_name=partner_name,
                    password=partner_password,
                    role="parceiro",
                    partner_org=partner_org or None,
                    password_change_required=True,
                )
                logger.info("seed_partner_created", email=partner_email, org=partner_org)
            except Exception as exc:  # noqa: BLE001
                logger.error("seed_partner_failed", error=str(exc))
