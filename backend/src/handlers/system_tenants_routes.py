"""Endpoints super_admin pra gestão de tenants.

Inspirado no padrão da ConnectaIA (system_admin_routes.py). Adaptado
pra contexto saúde — tenants podem ser ILPI, clínica, hospital, B2C
ou parceiro (tipo Tecnosenior). Multi-tenant é pré-requisito pra
Sofia/Emília (cada tenant tem sua persona IA).

Rotas:
    GET    /api/system/tenants              — lista
    POST   /api/system/tenants              — cria
    GET    /api/system/tenants/<id>         — detalhe
    PATCH  /api/system/tenants/<id>         — edita campos
    POST   /api/system/tenants/<id>/suspend — suspende/reativa
    GET    /api/system/tenants/<id>/health  — saúde por tenant

Acesso: super_admin only.
"""
from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("system_tenants", __name__)


def _serialize_tenant(row: dict) -> dict:
    """Converte row pra dict serializável (timestamps, jsonb, etc)."""
    if not row:
        return None
    out = dict(row)
    for k in ("created_at", "updated_at", "suspended_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    if out.get("created_by_user_id"):
        out["created_by_user_id"] = str(out["created_by_user_id"])
    return out


@bp.get("/api/system/tenants")
@require_role("super_admin")
def list_tenants():
    """Lista todos tenants. Filtros opcionais: ?active=true, ?suspended=false."""
    qs = request.args
    where = []
    params: list = []
    if qs.get("active") in ("true", "false"):
        where.append("active = %s")
        params.append(qs["active"] == "true")
    if qs.get("suspended") in ("true", "false"):
        where.append("suspended = %s")
        params.append(qs["suspended"] == "true")
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = get_postgres().fetch_all(
        f"""SELECT t.*,
                   (SELECT COUNT(*) FROM aia_health_patients
                    WHERE tenant_id = t.id AND active = TRUE) AS patients_count,
                   (SELECT COUNT(*) FROM aia_health_users
                    WHERE tenant_id = t.id AND active = TRUE) AS users_count
            FROM aia_health_tenants t
            {where_clause}
            ORDER BY t.created_at DESC""",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "tenants": [_serialize_tenant(r) for r in rows],
    })


@bp.post("/api/system/tenants")
@require_role("super_admin")
def create_tenant():
    """Cria novo tenant.

    Body obrigatórios: id (slug), name
    Body opcionais: ai_name, ai_voice, ai_kickoff_phrase, branding
    fields, channels (whatsapp_phone, voice_did), integrations_enabled.
    """
    body = request.get_json(silent=True) or {}
    tid = (body.get("id") or "").strip().lower()
    name = (body.get("name") or "").strip()
    if not tid or not name:
        return jsonify({"status": "error", "reason": "id_and_name_required"}), 400
    # Slug check: só lowercase + underscore + número
    import re
    if not re.match(r"^[a-z][a-z0-9_]{2,40}$", tid):
        return jsonify({
            "status": "error", "reason": "invalid_slug",
            "detail": "Use lowercase + underscore + numbers (3-40 chars)",
        }), 400

    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")

    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_tenants (
                id, name, ai_name, ai_voice, ai_kickoff_phrase,
                logo_url, primary_color, accent_color,
                whatsapp_phone, whatsapp_evolution_instance,
                voice_did, voice_sip_provider,
                integrations_enabled, active, created_by_user_id, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *""",
            (
                tid, name,
                body.get("ai_name") or "Sofia",
                body.get("ai_voice") or "ara",
                body.get("ai_kickoff_phrase"),
                body.get("logo_url"),
                body.get("primary_color"),
                body.get("accent_color"),
                body.get("whatsapp_phone"),
                body.get("whatsapp_evolution_instance"),
                body.get("voice_did"),
                body.get("voice_sip_provider"),
                json.dumps(body.get("integrations_enabled") or {}),
                bool(body.get("active", True)),
                user_id,
                json.dumps(body.get("metadata") or {}),
            ),
        )
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            return jsonify({"status": "error", "reason": "tenant_id_already_exists"}), 409
        logger.exception("create_tenant_failed")
        return jsonify({"status": "error", "reason": "create_failed", "detail": str(exc)[:200]}), 500

    audit_log(action="system.tenant.create", payload={
        "tenant_id": tid, "name": name, "by_user": user_id,
    })
    return jsonify({"status": "ok", "tenant": _serialize_tenant(row)}), 201


@bp.get("/api/system/tenants/<tenant_id>")
@require_role("super_admin")
def get_tenant(tenant_id: str):
    db = get_postgres()
    row = db.fetch_one(
        """SELECT t.*,
                  (SELECT COUNT(*) FROM aia_health_patients
                   WHERE tenant_id = t.id AND active = TRUE) AS patients_count,
                  (SELECT COUNT(*) FROM aia_health_users
                   WHERE tenant_id = t.id AND active = TRUE) AS users_count,
                  (SELECT COUNT(*) FROM aia_health_caregivers
                   WHERE tenant_id = t.id AND active = TRUE) AS caregivers_count
           FROM aia_health_tenants t
           WHERE id = %s""",
        (tenant_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    cfg = db.fetch_one(
        """SELECT tenant_id, tenant_type, licensing_model, escalation_policy,
                  features, review_strategy, message_quota_monthly
           FROM aia_health_tenant_config WHERE tenant_id = %s""",
        (tenant_id,),
    )
    return jsonify({
        "status": "ok",
        "tenant": _serialize_tenant(row),
        "config": cfg,
    })


@bp.patch("/api/system/tenants/<tenant_id>")
@require_role("super_admin")
def update_tenant(tenant_id: str):
    body = request.get_json(silent=True) or {}
    allowed = {
        "name", "ai_name", "ai_voice", "ai_kickoff_phrase",
        "logo_url", "primary_color", "accent_color",
        "whatsapp_phone", "whatsapp_evolution_instance",
        "voice_did", "voice_sip_provider",
        "integrations_enabled", "active", "metadata",
    }
    fields, params = [], []
    for k, v in body.items():
        if k not in allowed:
            continue
        if k in ("integrations_enabled", "metadata"):
            fields.append(f"{k} = %s::jsonb")
            params.append(json.dumps(v or {}))
        else:
            fields.append(f"{k} = %s")
            params.append(v)
    if not fields:
        return jsonify({"status": "error", "reason": "no_valid_fields"}), 400
    params.append(tenant_id)
    row = get_postgres().insert_returning(
        f"UPDATE aia_health_tenants SET {', '.join(fields)} WHERE id = %s RETURNING *",
        tuple(params),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    user_ctx = getattr(g, "user", None) or {}
    audit_log(action="system.tenant.update", payload={
        "tenant_id": tenant_id, "fields": list(body.keys()),
        "by_user": user_ctx.get("sub"),
    })
    return jsonify({"status": "ok", "tenant": _serialize_tenant(row)})


@bp.post("/api/system/tenants/<tenant_id>/suspend")
@require_role("super_admin")
def suspend_tenant(tenant_id: str):
    body = request.get_json(silent=True) or {}
    suspended = bool(body.get("suspended", True))
    reason = body.get("reason") if suspended else None
    row = get_postgres().insert_returning(
        """UPDATE aia_health_tenants
           SET suspended = %s, suspended_reason = %s,
               suspended_at = CASE WHEN %s THEN NOW() ELSE NULL END
           WHERE id = %s RETURNING *""",
        (suspended, reason, suspended, tenant_id),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    user_ctx = getattr(g, "user", None) or {}
    audit_log(
        action="system.tenant.suspend" if suspended else "system.tenant.unsuspend",
        payload={
            "tenant_id": tenant_id, "reason": reason,
            "by_user": user_ctx.get("sub"),
        },
    )
    return jsonify({"status": "ok", "tenant": _serialize_tenant(row)})


@bp.get("/api/system/tenants/<tenant_id>/health")
@require_role("super_admin")
def tenant_health(tenant_id: str):
    """Saúde resumida por tenant: contagens + últimas atividades."""
    db = get_postgres()
    if not db.fetch_one(
        "SELECT 1 FROM aia_health_tenants WHERE id = %s", (tenant_id,),
    ):
        return jsonify({"status": "error", "reason": "not_found"}), 404
    metrics = db.fetch_one(
        """SELECT
            (SELECT COUNT(*) FROM aia_health_patients
             WHERE tenant_id = %s AND active = TRUE) AS patients,
            (SELECT COUNT(*) FROM aia_health_users
             WHERE tenant_id = %s AND active = TRUE) AS users,
            (SELECT COUNT(*) FROM aia_health_caregivers
             WHERE tenant_id = %s AND active = TRUE) AS caregivers,
            (SELECT COUNT(*) FROM aia_health_care_events
             WHERE tenant_id = %s AND created_at >= NOW() - INTERVAL '24 hours') AS care_events_24h,
            (SELECT COUNT(*) FROM aia_health_care_events
             WHERE tenant_id = %s AND status NOT IN ('resolved','expired')) AS care_events_open,
            (SELECT MAX(created_at) FROM aia_health_care_events
             WHERE tenant_id = %s) AS last_care_event_at,
            (SELECT MAX(created_at) FROM aia_health_users
             WHERE tenant_id = %s) AS last_user_at""",
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id),
    )
    out = dict(metrics or {})
    for k in ("last_care_event_at", "last_user_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return jsonify({"status": "ok", "tenant_id": tenant_id, "metrics": out})
