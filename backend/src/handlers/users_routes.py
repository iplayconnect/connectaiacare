"""Users routes — admin CRUD + avatar upload + admin password reset.

Endpoints (todos exigem auth via middleware before_request, registrado em app.py):
    GET    /api/users                 — lista (admin_tenant, super_admin)
    POST   /api/users                 — cria
    GET    /api/users/<id>            — detalhe
    PATCH  /api/users/<id>            — atualiza campos editáveis
    DELETE /api/users/<id>            — soft delete (active=false)
    POST   /api/users/<id>/avatar     — upload base64
    POST   /api/users/<id>/password   — admin força reset

Self:
    PATCH  /api/users/me              — atualiza próprio perfil (campos limitados)
"""
from __future__ import annotations

import base64

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services import user_service
from src.services.audit_service import AuditAction, audit_log
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("users", __name__)


VALID_ROLES = {
    "super_admin", "admin_tenant", "medico", "enfermeiro",
    "cuidador_pro", "familia", "parceiro",
}


def _serialize(user: dict) -> dict:
    """Resposta consistente com auth_routes._user_response (sem hash)."""
    return {
        "id": str(user["id"]),
        "tenantId": user.get("tenant_id"),
        "email": user.get("email"),
        "fullName": user.get("full_name"),
        "role": user.get("role"),
        "permissions": user.get("permissions") or [],
        "profileId": str(user["profile_id"]) if user.get("profile_id") else None,
        "avatarUrl": user.get("avatar_url"),
        "phone": user.get("phone"),
        "crmRegister": user.get("crm_register"),
        "corenRegister": user.get("coren_register"),
        "caregiverId": str(user["caregiver_id"]) if user.get("caregiver_id") else None,
        "patientId": str(user["patient_id"]) if user.get("patient_id") else None,
        "partnerOrg": user.get("partner_org"),
        "allowedPatientIds": user.get("allowed_patient_ids") or [],
        "active": bool(user.get("active", True)),
        "passwordChangeRequired": bool(user.get("password_change_required")),
        "mfaEnabled": bool(user.get("mfa_enabled")),
        "lastLoginAt": user["last_login_at"].isoformat() if user.get("last_login_at") else None,
        "createdAt": user["created_at"].isoformat() if user.get("created_at") else None,
        "updatedAt": user["updated_at"].isoformat() if user.get("updated_at") else None,
    }


def _tenant_from_g() -> str:
    return (getattr(g, "user", {}) or {}).get("tenant_id") or "connectaiacare_demo"


# ══════════════════════════════════════════════════════════════════
# GET /api/users
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/users")
@require_role("super_admin", "admin_tenant")
def list_users():
    include_inactive = request.args.get("include_inactive", "false").lower() == "true"
    tenant_id = _tenant_from_g()
    users = user_service.list_users(tenant_id, include_inactive=include_inactive)
    return jsonify({"status": "ok", "users": [_serialize(u) for u in users]})


# ══════════════════════════════════════════════════════════════════
# POST /api/users
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/users")
@require_role("super_admin", "admin_tenant")
def create_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    full_name = (body.get("fullName") or body.get("full_name") or "").strip()
    password = body.get("password") or ""
    role = (body.get("role") or "").strip()

    if not email or not full_name or not password or not role:
        return jsonify({"status": "error", "reason": "missing_fields"}), 400
    if role not in VALID_ROLES:
        return jsonify({"status": "error", "reason": "invalid_role"}), 400
    if len(password) < 8:
        return jsonify({"status": "error", "reason": "password_too_short"}), 400

    # super_admin pode criar em qualquer tenant; admin_tenant fica preso ao próprio
    requester = getattr(g, "user", {}) or {}
    requester_role = requester.get("role")
    target_tenant = body.get("tenantId") or body.get("tenant_id") or _tenant_from_g()
    if requester_role != "super_admin" and target_tenant != _tenant_from_g():
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403
    # Apenas super_admin pode criar outros super_admin
    if role == "super_admin" and requester_role != "super_admin":
        return jsonify({"status": "error", "reason": "forbidden_super_admin_creation"}), 403

    if user_service.get_user_by_email(target_tenant, email):
        return jsonify({"status": "error", "reason": "email_already_exists"}), 409

    created = user_service.create_user(
        tenant_id=target_tenant,
        email=email,
        full_name=full_name,
        password=password,
        role=role,
        permissions=body.get("permissions") or [],
        profile_id=body.get("profileId") or body.get("profile_id"),
        phone=body.get("phone"),
        crm_register=body.get("crmRegister") or body.get("crm_register"),
        coren_register=body.get("corenRegister") or body.get("coren_register"),
        caregiver_id=body.get("caregiverId") or body.get("caregiver_id"),
        patient_id=body.get("patientId") or body.get("patient_id"),
        allowed_patient_ids=body.get("allowedPatientIds")
        or body.get("allowed_patient_ids")
        or [],
        partner_org=body.get("partnerOrg") or body.get("partner_org"),
        password_change_required=bool(
            body.get("passwordChangeRequired")
            or body.get("password_change_required")
            or True
        ),
    )
    if not created:
        return jsonify({"status": "error", "reason": "create_failed"}), 500

    audit_log(
        action=AuditAction.USER_CREATE,
        resource_type="user",
        resource_id=str(created["id"]),
        payload={"email": email, "role": role, "tenant": target_tenant},
    )
    # Recarrega com colunas completas pra serializar consistente
    full = user_service.get_user_by_id(str(created["id"])) or created
    return jsonify({"status": "ok", "user": _serialize(full)}), 201


# ══════════════════════════════════════════════════════════════════
# GET /api/users/<id>
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/users/<user_id>")
def get_user(user_id: str):
    requester = getattr(g, "user", {}) or {}
    is_self = requester.get("sub") == user_id
    if not is_self and requester.get("role") not in ("super_admin", "admin_tenant"):
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    user = user_service.get_user_by_id(user_id)
    if not user:
        return jsonify({"status": "error", "reason": "user_not_found"}), 404
    if (
        requester.get("role") != "super_admin"
        and user.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403
    return jsonify({"status": "ok", "user": _serialize(user)})


# ══════════════════════════════════════════════════════════════════
# PATCH /api/users/<id>
# ══════════════════════════════════════════════════════════════════

@bp.patch("/api/users/<user_id>")
def update_user(user_id: str):
    requester = getattr(g, "user", {}) or {}
    is_self = requester.get("sub") == user_id
    is_admin = requester.get("role") in ("super_admin", "admin_tenant")
    if not is_self and not is_admin:
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    user = user_service.get_user_by_id(user_id)
    if not user:
        return jsonify({"status": "error", "reason": "user_not_found"}), 404
    if (
        requester.get("role") != "super_admin"
        and user.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403

    body = request.get_json(silent=True) or {}

    # Self pode atualizar só campos limitados (full_name, phone, avatar_url, mfa via fluxo dedicado).
    self_allowed = {"full_name", "phone", "avatar_url"}
    admin_allowed = self_allowed | {
        "role", "permissions", "profile_id",
        "crm_register", "coren_register",
        "caregiver_id", "patient_id",
        "allowed_patient_ids", "partner_org", "active",
    }

    # Mapeia camelCase pra snake_case
    field_map = {
        "fullName": "full_name", "phone": "phone", "avatarUrl": "avatar_url",
        "role": "role", "permissions": "permissions",
        "profileId": "profile_id",
        "crmRegister": "crm_register", "corenRegister": "coren_register",
        "caregiverId": "caregiver_id", "patientId": "patient_id",
        "allowedPatientIds": "allowed_patient_ids",
        "partnerOrg": "partner_org", "active": "active",
    }
    sanitized: dict = {}
    allowed = admin_allowed if is_admin else self_allowed
    for key, value in body.items():
        snake = field_map.get(key, key)
        if snake in allowed:
            sanitized[snake] = value

    if sanitized.get("role") and sanitized["role"] not in VALID_ROLES:
        return jsonify({"status": "error", "reason": "invalid_role"}), 400
    # Não permite admin_tenant promover alguém a super_admin
    if (
        sanitized.get("role") == "super_admin"
        and requester.get("role") != "super_admin"
    ):
        return jsonify({"status": "error", "reason": "forbidden_super_admin"}), 403

    updated = user_service.update_user(user_id, sanitized)
    audit_log(
        action=AuditAction.USER_UPDATE,
        resource_type="user",
        resource_id=user_id,
        payload={"changed_fields": list(sanitized.keys())},
    )
    return jsonify({"status": "ok", "user": _serialize(updated or user)})


# ══════════════════════════════════════════════════════════════════
# DELETE /api/users/<id> (soft)
# ══════════════════════════════════════════════════════════════════

@bp.delete("/api/users/<user_id>")
@require_role("super_admin", "admin_tenant")
def delete_user(user_id: str):
    requester = getattr(g, "user", {}) or {}
    user = user_service.get_user_by_id(user_id)
    if not user:
        return jsonify({"status": "error", "reason": "user_not_found"}), 404
    if (
        requester.get("role") != "super_admin"
        and user.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403
    if requester.get("sub") == user_id:
        return jsonify({"status": "error", "reason": "cannot_delete_self"}), 400

    user_service.soft_delete_user(user_id)
    user_service.revoke_all_sessions(user_id)
    audit_log(
        action=AuditAction.USER_DELETE,
        resource_type="user",
        resource_id=user_id,
    )
    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════════════
# POST /api/users/<id>/avatar
# Body: { "image": "data:image/png;base64,..." }  OU  multipart com campo file
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/users/<user_id>/avatar")
def upload_avatar(user_id: str):
    requester = getattr(g, "user", {}) or {}
    is_self = requester.get("sub") == user_id
    is_admin = requester.get("role") in ("super_admin", "admin_tenant")
    if not is_self and not is_admin:
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    image_data: str | None = None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        image_data = body.get("image") or body.get("avatar")
    else:
        file = request.files.get("file") or request.files.get("avatar")
        if file:
            mime = file.mimetype or "image/png"
            raw = file.read()
            image_data = f"data:{mime};base64,{base64.b64encode(raw).decode('utf-8')}"

    if not image_data:
        return jsonify({"status": "error", "reason": "missing_image"}), 400
    if len(image_data) > 5 * 1024 * 1024:
        return jsonify({"status": "error", "reason": "image_too_large"}), 413

    user_service.update_user(user_id, {"avatar_url": image_data})
    audit_log(
        action=AuditAction.USER_AVATAR_UPLOAD,
        resource_type="user",
        resource_id=user_id,
    )
    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════════════
# POST /api/users/<id>/password   (admin força reset)
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/users/<user_id>/password")
@require_role("super_admin", "admin_tenant")
def admin_set_password(user_id: str):
    body = request.get_json(silent=True) or {}
    new_password = body.get("newPassword") or body.get("new_password") or ""
    if len(new_password) < 8:
        return jsonify({"status": "error", "reason": "password_too_short"}), 400

    requester = getattr(g, "user", {}) or {}
    user = user_service.get_user_by_id(user_id)
    if not user:
        return jsonify({"status": "error", "reason": "user_not_found"}), 404
    if (
        requester.get("role") != "super_admin"
        and user.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403

    user_service.set_password(user_id, new_password)
    user_service.revoke_all_sessions(user_id)
    # Por padrão, força usuário trocar no primeiro login
    user_service.update_user(user_id, {"active": True})
    audit_log(
        action=AuditAction.PASSWORD_RESET,
        resource_type="user",
        resource_id=user_id,
    )
    return jsonify({"status": "ok"})
