"""Profiles routes (Bloco C) — perfis customizáveis com permissions.

Permite que admin_tenant crie perfis ("supervisor noturno", "auxiliar de
cuidador", etc) com listas de permissions específicas. Quando vinculado a
user (user.profile_id), tem precedência sobre o ROLE_PERMISSIONS hardcoded.

Endpoints (via middleware before_request):
    GET    /api/profiles              — lista do tenant
    POST   /api/profiles              — cria
    GET    /api/profiles/<id>         — detalhe
    PATCH  /api/profiles/<id>         — atualiza
    DELETE /api/profiles/<id>         — soft delete
    GET    /api/profiles/permissions  — catálogo de permissions disponíveis (UI)
"""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services import user_service
from src.services.audit_service import AuditAction, audit_log
from src.services.permissions import ROLE_PERMISSIONS
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("profiles", __name__)

SLUG_RE = re.compile(r"^[a-z0-9_-]{2,40}$")


def _serialize(p: dict) -> dict:
    return {
        "id": str(p["id"]),
        "tenantId": p.get("tenant_id"),
        "slug": p.get("slug"),
        "displayName": p.get("display_name"),
        "description": p.get("description"),
        "permissions": p.get("permissions") or [],
        "config": p.get("config") or {},
        "active": bool(p.get("active", True)),
        "createdAt": p["created_at"].isoformat() if p.get("created_at") else None,
        "updatedAt": p["updated_at"].isoformat() if p.get("updated_at") else None,
    }


def _tenant_from_g() -> str:
    return (getattr(g, "user", {}) or {}).get("tenant_id") or "connectaiacare_demo"


@bp.get("/api/profiles")
def list_profiles():
    profiles = user_service.list_profiles(_tenant_from_g())
    return jsonify({"status": "ok", "profiles": [_serialize(p) for p in profiles]})


@bp.get("/api/profiles/permissions")
def list_available_permissions():
    """Catálogo unificado: une todas as permissions usadas em ROLE_PERMISSIONS,
    agrupadas por recurso. UI usa pra montar checkboxes."""
    all_perms: set[str] = set()
    for perms in ROLE_PERMISSIONS.values():
        all_perms.update(perms)
    grouped: dict[str, list[str]] = {}
    for perm in sorted(all_perms):
        if perm == "*":
            grouped.setdefault("_wildcard", []).append(perm)
            continue
        resource = perm.split(":", 1)[0]
        grouped.setdefault(resource, []).append(perm)
    return jsonify({"status": "ok", "groups": grouped, "all": sorted(all_perms)})


@bp.post("/api/profiles")
@require_role("super_admin", "admin_tenant")
def create_profile():
    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip().lower()
    display_name = (body.get("displayName") or body.get("display_name") or "").strip()
    description = body.get("description") or ""
    permissions = body.get("permissions") or []
    config = body.get("config") or {}

    if not slug or not display_name:
        return jsonify({"status": "error", "reason": "missing_fields"}), 400
    if not SLUG_RE.match(slug):
        return jsonify({"status": "error", "reason": "invalid_slug"}), 400
    if not isinstance(permissions, list):
        return jsonify({"status": "error", "reason": "permissions_must_be_list"}), 400

    pg = get_postgres()
    tenant_id = _tenant_from_g()
    try:
        created = pg.insert_returning(
            """
            INSERT INTO aia_health_profiles
                (tenant_id, slug, display_name, description, permissions, config)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, slug, display_name, description,
                      permissions, config, active, created_at, updated_at
            """,
            (
                tenant_id,
                slug,
                display_name,
                description,
                pg.json_adapt(permissions),
                pg.json_adapt(config),
            ),
        )
    except Exception as exc:  # provavelmente unique violation
        logger.warning("create_profile_failed", error=str(exc))
        return jsonify({"status": "error", "reason": "slug_already_exists"}), 409

    audit_log(
        action=AuditAction.PROFILE_CREATE,
        resource_type="profile",
        resource_id=str(created["id"]),
        payload={"slug": slug, "permissions_count": len(permissions)},
    )
    return jsonify({"status": "ok", "profile": _serialize(created)}), 201


@bp.get("/api/profiles/<profile_id>")
def get_profile(profile_id: str):
    profile = user_service.get_profile_by_id(profile_id)
    if not profile:
        return jsonify({"status": "error", "reason": "profile_not_found"}), 404
    requester = getattr(g, "user", {}) or {}
    if (
        requester.get("role") != "super_admin"
        and profile.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403
    return jsonify({"status": "ok", "profile": _serialize(profile)})


@bp.patch("/api/profiles/<profile_id>")
@require_role("super_admin", "admin_tenant")
def update_profile(profile_id: str):
    profile = user_service.get_profile_by_id(profile_id)
    if not profile:
        return jsonify({"status": "error", "reason": "profile_not_found"}), 404
    requester = getattr(g, "user", {}) or {}
    if (
        requester.get("role") != "super_admin"
        and profile.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403

    body = request.get_json(silent=True) or {}
    pg = get_postgres()
    sets: list[str] = []
    values: list = []
    for key in ("display_name", "displayName"):
        if key in body:
            sets.append("display_name = %s")
            values.append(body[key])
            break
    if "description" in body:
        sets.append("description = %s")
        values.append(body["description"])
    if "permissions" in body:
        if not isinstance(body["permissions"], list):
            return jsonify({"status": "error", "reason": "permissions_must_be_list"}), 400
        sets.append("permissions = %s")
        values.append(pg.json_adapt(body["permissions"]))
    if "config" in body:
        sets.append("config = %s")
        values.append(pg.json_adapt(body["config"] or {}))
    if "active" in body:
        sets.append("active = %s")
        values.append(bool(body["active"]))

    if not sets:
        return jsonify({"status": "ok", "profile": _serialize(profile)})

    values.append(profile_id)
    updated = pg.insert_returning(
        f"""
        UPDATE aia_health_profiles SET {', '.join(sets)}
        WHERE id = %s
        RETURNING id, tenant_id, slug, display_name, description,
                  permissions, config, active, created_at, updated_at
        """,
        tuple(values),
    )
    audit_log(
        action=AuditAction.PROFILE_UPDATE,
        resource_type="profile",
        resource_id=profile_id,
        payload={"changed": list(body.keys())},
    )
    return jsonify({"status": "ok", "profile": _serialize(updated)})


@bp.delete("/api/profiles/<profile_id>")
@require_role("super_admin", "admin_tenant")
def delete_profile(profile_id: str):
    profile = user_service.get_profile_by_id(profile_id)
    if not profile:
        return jsonify({"status": "error", "reason": "profile_not_found"}), 404
    requester = getattr(g, "user", {}) or {}
    if (
        requester.get("role") != "super_admin"
        and profile.get("tenant_id") != requester.get("tenant_id")
    ):
        return jsonify({"status": "error", "reason": "forbidden_cross_tenant"}), 403

    get_postgres().execute(
        "UPDATE aia_health_profiles SET active = FALSE WHERE id = %s",
        (profile_id,),
    )
    audit_log(
        action=AuditAction.PROFILE_DELETE,
        resource_type="profile",
        resource_id=profile_id,
    )
    return jsonify({"status": "ok"})
