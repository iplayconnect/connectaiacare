"""CRUD de contatos de escalação por tenant (migration 080).

Endpoints:
    GET    /api/admin/tenants/<tid>/escalation-contacts          — lista
    POST   /api/admin/tenants/<tid>/escalation-contacts          — cria
    PATCH  /api/admin/tenants/<tid>/escalation-contacts/<id>     — edita
    DELETE /api/admin/tenants/<tid>/escalation-contacts/<id>     — soft delete

Acesso:
    super_admin: tudo
    admin_tenant: só do próprio tenant
"""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("tenant_escalation", __name__)


VALID_PRIORITIES = frozenset({"P1", "P2", "P3"})
VALID_ROLES = frozenset({
    "plantonista_l1", "plantonista_l2",
    "medico_responsavel", "enfermeiro_chefe",
    "gestor_unidade", "admin_tenant",
    "outro",
})


def _current_user() -> dict:
    return getattr(g, "user", None) or {}


def _can_access_tenant(tenant_id: str) -> bool:
    """super_admin → tudo. admin_tenant → só o próprio tenant."""
    u = _current_user()
    if u.get("role") == "super_admin":
        return True
    return (u.get("role") == "admin_tenant"
            and (u.get("tenant_id") or u.get("tenantId")) == tenant_id)


def _normalize_phone(raw: str) -> str | None:
    """E.164 sem '+'. Remove tudo que não é dígito."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return None
    return digits


def _serialize_contact(row: dict) -> dict:
    if not row:
        return None
    out = dict(row)
    for k in ("created_at", "updated_at", "deactivated_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    for k in ("schedule_start", "schedule_end"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    if out.get("id"):
        out["id"] = str(out["id"])
    return out


@bp.get("/api/admin/tenants/<tenant_id>/escalation-contacts")
@require_role("super_admin", "admin_tenant")
def list_contacts(tenant_id: str):
    if not _can_access_tenant(tenant_id):
        return jsonify({"status": "error", "reason": "forbidden"}), 403
    include_inactive = request.args.get("include_inactive") == "true"

    where = "WHERE tenant_id = %s"
    params: list = [tenant_id]
    if not include_inactive:
        where += " AND active = TRUE"

    rows = get_postgres().fetch_all(
        f"""SELECT * FROM aia_health_tenant_escalation_contacts
            {where}
            ORDER BY active DESC, contact_name ASC""",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "tenant_id": tenant_id,
        "count": len(rows),
        "contacts": [_serialize_contact(r) for r in rows],
    })


@bp.post("/api/admin/tenants/<tenant_id>/escalation-contacts")
@require_role("super_admin", "admin_tenant")
def create_contact(tenant_id: str):
    if not _can_access_tenant(tenant_id):
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    body = request.get_json(silent=True) or {}
    phone = _normalize_phone(body.get("phone") or "")
    contact_name = (body.get("contact_name") or "").strip()
    role = (body.get("role") or "").strip()
    priorities = body.get("priorities") or ["P1"]
    notes = (body.get("notes") or "").strip() or None
    schedule_weekdays = body.get("schedule_weekdays")  # int[] ou None
    schedule_start = body.get("schedule_start")  # "HH:MM" ou None
    schedule_end = body.get("schedule_end")

    # Validações
    if not phone:
        return jsonify({"status": "error", "reason": "invalid_phone"}), 400
    if not contact_name or len(contact_name) < 2:
        return jsonify({"status": "error", "reason": "contact_name_required"}), 400
    if role not in VALID_ROLES:
        return jsonify({
            "status": "error", "reason": "invalid_role",
            "allowed": sorted(VALID_ROLES),
        }), 400
    if not isinstance(priorities, list) or not priorities:
        return jsonify({"status": "error", "reason": "priorities_required"}), 400
    if not all(p in VALID_PRIORITIES for p in priorities):
        return jsonify({
            "status": "error", "reason": "invalid_priority",
            "allowed": sorted(VALID_PRIORITIES),
        }), 400

    user = _current_user()
    db = get_postgres()
    try:
        row = db.fetch_one(
            """INSERT INTO aia_health_tenant_escalation_contacts (
                tenant_id, phone, contact_name, role, priorities,
                schedule_weekdays, schedule_start, schedule_end,
                notes, created_by_user_id, updated_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *""",
            (
                tenant_id, phone, contact_name, role,
                priorities,
                schedule_weekdays,
                schedule_start, schedule_end,
                notes,
                user.get("sub"), user.get("sub"),
            ),
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "uniq_active_escalation_contact" in msg or "duplicate" in msg:
            return jsonify({
                "status": "error",
                "reason": "phone_already_active_for_tenant",
                "hint": "Desative o contato existente antes de cadastrar de novo",
            }), 409
        logger.exception("escalation_contact_insert_failed")
        return jsonify({
            "status": "error", "reason": "insert_failed",
            "detail": str(exc)[:200],
        }), 500

    write_audit(
        action="escalation_contact_created",
        actor=user.get("sub"),
        actor_role=user.get("role"),
        tenant_id=tenant_id,
        resource_type="escalation_contact",
        resource_id=str(row["id"]),
        payload={
            "phone_redacted": phone[:4] + "****" + phone[-4:],
            "contact_name": contact_name,
            "role": role,
            "priorities": priorities,
        },
    )

    return jsonify({"status": "ok", "contact": _serialize_contact(row)}), 201


@bp.patch("/api/admin/tenants/<tenant_id>/escalation-contacts/<contact_id>")
@require_role("super_admin", "admin_tenant")
def update_contact(tenant_id: str, contact_id: str):
    if not _can_access_tenant(tenant_id):
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    body = request.get_json(silent=True) or {}
    sets: list[str] = []
    params: list = []

    if "contact_name" in body:
        sets.append("contact_name = %s")
        params.append((body["contact_name"] or "").strip())
    if "role" in body:
        if body["role"] not in VALID_ROLES:
            return jsonify({"status": "error", "reason": "invalid_role"}), 400
        sets.append("role = %s")
        params.append(body["role"])
    if "priorities" in body:
        pr = body["priorities"]
        if not isinstance(pr, list) or not all(p in VALID_PRIORITIES for p in pr):
            return jsonify({"status": "error", "reason": "invalid_priority"}), 400
        sets.append("priorities = %s")
        params.append(pr)
    if "active" in body:
        sets.append("active = %s")
        params.append(bool(body["active"]))
        if not body["active"]:
            sets.append("deactivated_at = NOW()")
            sets.append("deactivated_by_user_id = %s")
            params.append(_current_user().get("sub"))
    if "notes" in body:
        sets.append("notes = %s")
        params.append((body["notes"] or "").strip() or None)
    for sched_key in ("schedule_weekdays", "schedule_start", "schedule_end"):
        if sched_key in body:
            sets.append(f"{sched_key} = %s")
            params.append(body[sched_key])

    if not sets:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    sets.append("updated_at = NOW()")
    sets.append("updated_by_user_id = %s")
    user = _current_user()
    params.append(user.get("sub"))
    params.extend([contact_id, tenant_id])

    row = get_postgres().fetch_one(
        f"""UPDATE aia_health_tenant_escalation_contacts
            SET {', '.join(sets)}
            WHERE id = %s AND tenant_id = %s
            RETURNING *""",
        tuple(params),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    write_audit(
        action="escalation_contact_updated",
        actor=user.get("sub"),
        actor_role=user.get("role"),
        tenant_id=tenant_id,
        resource_type="escalation_contact",
        resource_id=contact_id,
        payload={"fields_changed": list(body.keys())},
    )
    return jsonify({"status": "ok", "contact": _serialize_contact(row)})


@bp.delete("/api/admin/tenants/<tenant_id>/escalation-contacts/<contact_id>")
@require_role("super_admin", "admin_tenant")
def delete_contact(tenant_id: str, contact_id: str):
    """Soft delete (active=false). Mantém histórico pra audit/LGPD."""
    if not _can_access_tenant(tenant_id):
        return jsonify({"status": "error", "reason": "forbidden"}), 403

    user = _current_user()
    row = get_postgres().fetch_one(
        """UPDATE aia_health_tenant_escalation_contacts
              SET active = FALSE,
                  deactivated_at = NOW(),
                  deactivated_by_user_id = %s,
                  updated_at = NOW(),
                  updated_by_user_id = %s
            WHERE id = %s AND tenant_id = %s
            RETURNING id""",
        (user.get("sub"), user.get("sub"), contact_id, tenant_id),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    write_audit(
        action="escalation_contact_deactivated",
        actor=user.get("sub"),
        actor_role=user.get("role"),
        tenant_id=tenant_id,
        resource_type="escalation_contact",
        resource_id=contact_id,
    )
    return jsonify({"status": "ok"})
