"""Auth routes — login, refresh, me, logout, change-password.

Bearer token via Authorization header (sem cookies, supports_credentials=False
em CORS — ver app.py L46).

Endpoints:
    POST /api/auth/login
    POST /api/auth/refresh
    POST /api/auth/logout       (auth required)
    GET  /api/auth/me           (auth required)
    POST /api/auth/change-password  (auth required)
"""
from __future__ import annotations

import os
from functools import wraps
from typing import Callable

from flask import Blueprint, g, jsonify, request

from src.services import user_service
from src.services.audit_service import AuditAction, audit_log
from src.services.jwt_utils import JWTError, extract_bearer_token, jwt_decode, jwt_encode
from src.services.permissions import has_permission, has_role, resolve_permissions
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("auth", __name__)


# Caminhos públicos (sem JWT). Verificados em wildcards no middleware.
PUBLIC_PATHS = (
    "/",
    "/health",
    "/api/auth/login",
    "/api/auth/refresh",
)

# Prefixos públicos: rotas que servem fluxos não-autenticados (webhook,
# portal do paciente com PIN, onboarding B2C).
PUBLIC_PREFIXES = (
    "/webhook/",
    "/api/onboarding/",
    "/api/patient/portal/",  # PIN-gated
    "/static/",
)


def _jwt_secret() -> str:
    """JWT_SECRET com fallback para SECRET_KEY em dev (sem fail-closed aqui;
    settings.py já valida em produção)."""
    return os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY") or ""


def _jwt_exp_seconds() -> int:
    return int(os.getenv("JWT_EXP_SECONDS") or "86400")


def _refresh_days() -> int:
    return int(os.getenv("JWT_REFRESH_DAYS") or "7")


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def authenticate_request() -> tuple[dict | None, tuple | None]:
    """Verifica JWT do header Authorization. Retorna (payload, error_response).

    error_response é (json, status) se falhou, None se OK.
    """
    token = extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        return None, (jsonify({"status": "error", "reason": "missing_token"}), 401)
    try:
        payload = jwt_decode(token, _jwt_secret())
    except JWTError as exc:
        return None, (jsonify({"status": "error", "reason": "invalid_token", "detail": str(exc)}), 401)
    return payload, None


def _resolve_user_permissions(user: dict) -> list[str]:
    """Calcula permissions efetivas considerando profile_id se houver."""
    profile_perms: list[str] | None = None
    profile_id = user.get("profile_id")
    if profile_id:
        prof = user_service.get_profile_by_id(profile_id)
        if prof and prof.get("active"):
            profile_perms = list(prof.get("permissions") or [])
    return resolve_permissions(user, profile_perms)


def _user_payload(user: dict, tenant_id: str, permissions: list[str]) -> dict:
    """Payload do JWT (subset do user que cabe no token)."""
    return {
        "sub": str(user["id"]),
        "tenant_id": tenant_id,
        "email": user["email"],
        "role": user["role"],
        "name": user.get("full_name"),
        "permissions": permissions,
        "profile_id": str(user["profile_id"]) if user.get("profile_id") else None,
        "caregiver_id": str(user["caregiver_id"]) if user.get("caregiver_id") else None,
        "patient_id": str(user["patient_id"]) if user.get("patient_id") else None,
        "partner_org": user.get("partner_org"),
        "allowed_patient_ids": user.get("allowed_patient_ids") or [],
    }


def _user_response(user: dict, tenant_id: str, permissions: list[str]) -> dict:
    """Subset do user retornado para o frontend (sem hash, sem metadata interna)."""
    return {
        "id": str(user["id"]),
        "tenantId": tenant_id,
        "email": user["email"],
        "fullName": user.get("full_name"),
        "role": user["role"],
        "permissions": permissions,
        "profileId": str(user["profile_id"]) if user.get("profile_id") else None,
        "avatarUrl": user.get("avatar_url"),
        "phone": user.get("phone"),
        "crmRegister": user.get("crm_register"),
        "corenRegister": user.get("coren_register"),
        "caregiverId": str(user["caregiver_id"]) if user.get("caregiver_id") else None,
        "patientId": str(user["patient_id"]) if user.get("patient_id") else None,
        "partnerOrg": user.get("partner_org"),
        "allowedPatientIds": user.get("allowed_patient_ids") or [],
        "mfaEnabled": bool(user.get("mfa_enabled")),
        "passwordChangeRequired": bool(user.get("password_change_required")),
    }


# ─── Decorators reutilizáveis para outros blueprints ──────────

def require_role(*roles: str) -> Callable:
    """Decorator: exige que g.user.role esteja em roles. Falha 403 se não."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_role(getattr(g, "user", {}) or {}, *roles):
                return jsonify({"status": "error", "reason": "forbidden_role"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


def require_permission(permission: str) -> Callable:
    """Decorator: exige permission resolvida no JWT (g.user.permissions)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, "user", {}) or {}
            perms = user.get("permissions") or []
            if not has_permission(perms, permission):
                return jsonify({"status": "error", "reason": "forbidden_permission"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


# ══════════════════════════════════════════════════════════════════
# POST /api/auth/login
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/auth/login")
def login():
    if not _jwt_secret():
        return jsonify({"status": "error", "reason": "jwt_secret_not_configured"}), 500

    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        return jsonify({"status": "error", "reason": "missing_credentials"}), 400

    tenant_id = (body.get("tenantId") or body.get("tenant_id") or "").strip()
    user = None
    if tenant_id:
        user = user_service.get_user_by_email(tenant_id, email)
    # Fallback: procura em qualquer tenant (login sem seleção explícita)
    if not user:
        user = user_service.find_user_any_tenant(email)
        if user:
            tenant_id = user["tenant_id"]

    if not user or not user.get("active"):
        logger.info("login_failed_user_not_found_or_inactive", email=email)
        audit_log(
            action=AuditAction.LOGIN_FAILED,
            resource_type="user",
            payload={"email": email, "reason": "user_not_found_or_inactive"},
            tenant_id=tenant_id or "connectaiacare_demo",
            actor=email,
        )
        return jsonify({"status": "error", "reason": "invalid_credentials"}), 401

    if not user_service.verify_password(password, user.get("password_hash") or ""):
        logger.info("login_failed_wrong_password", email=email, tenant_id=tenant_id)
        audit_log(
            action=AuditAction.LOGIN_FAILED,
            resource_type="user",
            resource_id=str(user["id"]),
            payload={"email": email, "reason": "wrong_password"},
            tenant_id=tenant_id,
            actor=str(user["id"]),
        )
        return jsonify({"status": "error", "reason": "invalid_credentials"}), 401

    user_service.record_login(user["id"])
    permissions = _resolve_user_permissions(user)

    token = jwt_encode(
        _user_payload(user, tenant_id, permissions),
        _jwt_secret(),
        exp_seconds=_jwt_exp_seconds(),
    )
    refresh_token, refresh_expires = user_service.create_refresh_session(
        tenant_id=tenant_id,
        user_id=user["id"],
        refresh_days=_refresh_days(),
        user_agent=request.headers.get("User-Agent"),
        ip=request.headers.get("X-Forwarded-For") or request.remote_addr,
    )

    logger.info("login_success", user_id=str(user["id"]), email=email, role=user["role"])
    audit_log(
        action=AuditAction.LOGIN,
        resource_type="user",
        resource_id=str(user["id"]),
        payload={"email": email, "role": user["role"]},
        tenant_id=tenant_id,
        actor=str(user["id"]),
    )
    return jsonify(
        {
            "status": "ok",
            "token": token,
            "refreshToken": refresh_token,
            "refreshExpiresAt": refresh_expires.isoformat(),
            "user": _user_response(user, tenant_id, permissions),
        }
    )


# ══════════════════════════════════════════════════════════════════
# POST /api/auth/refresh
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/auth/refresh")
def refresh():
    if not _jwt_secret():
        return jsonify({"status": "error", "reason": "jwt_secret_not_configured"}), 500

    body = request.get_json(silent=True) or {}
    refresh_token = (body.get("refreshToken") or body.get("refresh_token") or "").strip()
    if not refresh_token:
        return jsonify({"status": "error", "reason": "missing_refresh_token"}), 400

    session = user_service.get_session_by_token(refresh_token)
    if not session or session.get("revoked_at"):
        return jsonify({"status": "error", "reason": "invalid_refresh_token"}), 401

    from datetime import datetime, timezone
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return jsonify({"status": "error", "reason": "expired_refresh_token"}), 401

    user = user_service.get_user_by_id(session["user_id"])
    if not user or not user.get("active"):
        return jsonify({"status": "error", "reason": "invalid_user"}), 401

    # Rotaciona: revoga a sessão atual e emite uma nova
    user_service.revoke_session(session["id"])

    tenant_id = session["tenant_id"]
    permissions = _resolve_user_permissions(user)
    token = jwt_encode(
        _user_payload(user, tenant_id, permissions),
        _jwt_secret(),
        exp_seconds=_jwt_exp_seconds(),
    )
    new_refresh, refresh_expires = user_service.create_refresh_session(
        tenant_id=tenant_id,
        user_id=user["id"],
        refresh_days=_refresh_days(),
        user_agent=request.headers.get("User-Agent"),
        ip=request.headers.get("X-Forwarded-For") or request.remote_addr,
    )

    return jsonify(
        {
            "status": "ok",
            "token": token,
            "refreshToken": new_refresh,
            "refreshExpiresAt": refresh_expires.isoformat(),
        }
    )


# ══════════════════════════════════════════════════════════════════
# POST /api/auth/logout
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/auth/logout")
def logout():
    payload, err = authenticate_request()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    refresh_token = (body.get("refreshToken") or body.get("refresh_token") or "").strip()
    all_sessions = bool(body.get("allSessions") or body.get("all_sessions"))

    user_id = payload["sub"]
    if all_sessions:
        user_service.revoke_all_sessions(user_id)
    elif refresh_token:
        session = user_service.get_session_by_token(refresh_token)
        if session and str(session["user_id"]) == user_id:
            user_service.revoke_session(session["id"])

    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════════════
# GET /api/auth/me
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/auth/me")
def me():
    payload, err = authenticate_request()
    if err:
        return err

    user = user_service.get_user_by_id(payload["sub"])
    if not user or not user.get("active"):
        return jsonify({"status": "error", "reason": "user_not_found"}), 404

    permissions = _resolve_user_permissions(user)
    return jsonify(
        {
            "status": "ok",
            "user": _user_response(user, payload.get("tenant_id"), permissions),
        }
    )


# ══════════════════════════════════════════════════════════════════
# POST /api/auth/change-password
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/auth/change-password")
def change_password():
    payload, err = authenticate_request()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    current_password = body.get("currentPassword") or body.get("current_password") or ""
    new_password = body.get("newPassword") or body.get("new_password") or ""
    if not current_password or not new_password:
        return jsonify({"status": "error", "reason": "missing_passwords"}), 400
    if len(new_password) < 8:
        return jsonify({"status": "error", "reason": "password_too_short"}), 400

    tenant_id = payload.get("tenant_id")
    user = user_service.get_user_by_email(tenant_id, payload["email"])
    if not user:
        return jsonify({"status": "error", "reason": "user_not_found"}), 404

    if not user_service.verify_password(current_password, user.get("password_hash") or ""):
        return jsonify({"status": "error", "reason": "invalid_current_password"}), 401

    user_service.set_password(user["id"], new_password)
    # Por segurança, derruba todas as sessões de refresh ativas
    user_service.revoke_all_sessions(user["id"])

    logger.info("password_changed", user_id=str(user["id"]))
    audit_log(
        action=AuditAction.PASSWORD_CHANGED,
        resource_type="user",
        resource_id=str(user["id"]),
        actor=str(user["id"]),
    )
    return jsonify({"status": "ok"})
