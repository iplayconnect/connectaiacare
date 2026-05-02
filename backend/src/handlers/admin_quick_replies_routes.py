"""Admin quick replies — respostas pré-aprovadas pra operador no chat handoff.

Endpoints:
    GET    /api/admin/quick-replies                — lista active do tenant
    POST   /api/admin/quick-replies                — cria (admin only)
    PUT    /api/admin/quick-replies/<id>           — edita (admin only)
    DELETE /api/admin/quick-replies/<id>           — soft delete (admin only)
    POST   /api/admin/quick-replies/<id>/use       — track uso (qq operador)

Acesso:
    GET / use     → super_admin, admin_tenant, medico, enfermeiro
    POST/PUT/DEL  → super_admin, admin_tenant

Tenant isolation: TODA query filtra por g.user["tenant_id"]. Body NUNCA
sobrescreve tenant_id (anti-tenant-hopping).
"""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_quick_replies", __name__)

VALID_CATEGORIES = ("emergencia", "medicacao", "rotina", "fechamento", "geral")
SHORTCUT_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def _serialize(row: dict) -> dict:
    out = dict(row)
    out["id"] = str(out["id"])
    if out.get("created_by_user_id"):
        out["created_by_user_id"] = str(out["created_by_user_id"])
    for k in ("created_at", "updated_at", "last_used_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def _tenant_id() -> str | None:
    return (getattr(g, "user", {}) or {}).get("tenant_id")


def _user_id() -> str | None:
    return (getattr(g, "user", {}) or {}).get("sub")


def _validate_payload(body: dict, *, partial: bool = False) -> tuple[dict, str | None]:
    """Normaliza e valida payload de create/update.

    Retorna (clean_dict, error_reason). Se error não é None, abortar.
    Em modo partial=True (PUT), só valida campos presentes.
    """
    clean: dict = {}

    cat = (body.get("category") or "").strip().lower()
    if cat or not partial:
        if cat not in VALID_CATEGORIES:
            return clean, "invalid_category"
        clean["category"] = cat

    sc = (body.get("shortcut") or "").strip().lower().replace(" ", "_")
    sc = sc.lstrip("/")
    if sc or not partial:
        if not SHORTCUT_RE.match(sc):
            return clean, "invalid_shortcut"
        clean["shortcut"] = sc

    label = (body.get("label") or "").strip()
    if label or not partial:
        if not label or len(label) > 80:
            return clean, "invalid_label"
        clean["label"] = label

    content = (body.get("content") or "").strip()
    if content or not partial:
        if not content or len(content) > 2000:
            return clean, "invalid_content"
        clean["content"] = content

    hotkey = body.get("hotkey")
    if hotkey is not None:
        hk = (hotkey or "").strip()
        if hk and len(hk) > 20:
            return clean, "invalid_hotkey"
        clean["hotkey"] = hk or None

    return clean, None


@bp.get("/api/admin/quick-replies")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_quick_replies():
    tenant_id = _tenant_id()
    if not tenant_id:
        return jsonify({"status": "error", "reason": "no_tenant"}), 401

    qs = request.args
    category = (qs.get("category") or "").strip().lower() or None
    if category and category not in VALID_CATEGORIES:
        return jsonify({"status": "error", "reason": "invalid_category"}), 400

    where = ["tenant_id = %s", "active = TRUE"]
    params: list = [tenant_id]
    if category:
        where.append("category = %s")
        params.append(category)

    rows = get_postgres().fetch_all(
        f"""SELECT id, tenant_id, category, shortcut, label, content,
                   hotkey, created_by_user_id, active, usage_count,
                   last_used_at, created_at, updated_at
            FROM aia_health_quick_replies
            WHERE {' AND '.join(where)}
            ORDER BY usage_count DESC, label ASC""",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.post("/api/admin/quick-replies")
@require_role("super_admin", "admin_tenant")
def create_quick_reply():
    tenant_id = _tenant_id()
    user_id = _user_id()
    if not tenant_id or not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    body = request.get_json(silent=True) or {}
    clean, err = _validate_payload(body, partial=False)
    if err:
        return jsonify({"status": "error", "reason": err}), 400

    db = get_postgres()
    # Conflito de shortcut só importa entre rows ativas (UNIQUE INDEX
    # com WHERE active = TRUE). Pré-check pra retornar 409 amigável.
    existing = db.fetch_one(
        """SELECT id FROM aia_health_quick_replies
           WHERE tenant_id = %s AND shortcut = %s AND active = TRUE""",
        (tenant_id, clean["shortcut"]),
    )
    if existing:
        return jsonify({
            "status": "error", "reason": "shortcut_already_exists",
        }), 409

    row = db.fetch_one(
        """INSERT INTO aia_health_quick_replies
               (tenant_id, category, shortcut, label, content, hotkey,
                created_by_user_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id, tenant_id, category, shortcut, label, content,
                     hotkey, created_by_user_id, active, usage_count,
                     last_used_at, created_at, updated_at""",
        (
            tenant_id, clean["category"], clean["shortcut"],
            clean["label"], clean["content"], clean.get("hotkey"),
            user_id,
        ),
    )
    write_audit(
        action="quick_reply_created",
        actor=str(user_id),
        tenant_id=tenant_id,
        resource_type="quick_reply",
        resource_id=str(row["id"]),
        payload={"shortcut": clean["shortcut"], "category": clean["category"]},
    )
    return jsonify({"status": "ok", "item": _serialize(row)}), 201


@bp.put("/api/admin/quick-replies/<reply_id>")
@require_role("super_admin", "admin_tenant")
def update_quick_reply(reply_id: str):
    tenant_id = _tenant_id()
    user_id = _user_id()
    if not tenant_id or not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    body = request.get_json(silent=True) or {}
    clean, err = _validate_payload(body, partial=True)
    if err:
        return jsonify({"status": "error", "reason": err}), 400
    if not clean:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    db = get_postgres()
    existing = db.fetch_one(
        """SELECT id FROM aia_health_quick_replies
           WHERE id = %s AND tenant_id = %s AND active = TRUE""",
        (reply_id, tenant_id),
    )
    if not existing:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    if "shortcut" in clean:
        conflict = db.fetch_one(
            """SELECT id FROM aia_health_quick_replies
               WHERE tenant_id = %s AND shortcut = %s
                 AND active = TRUE AND id != %s""",
            (tenant_id, clean["shortcut"], reply_id),
        )
        if conflict:
            return jsonify({
                "status": "error", "reason": "shortcut_already_exists",
            }), 409

    set_clauses = [f"{k} = %s" for k in clean.keys()]
    params = list(clean.values()) + [reply_id, tenant_id]
    row = db.fetch_one(
        f"""UPDATE aia_health_quick_replies
            SET {', '.join(set_clauses)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, category, shortcut, label, content,
                      hotkey, created_by_user_id, active, usage_count,
                      last_used_at, created_at, updated_at""",
        tuple(params),
    )
    write_audit(
        action="quick_reply_updated",
        actor=str(user_id),
        tenant_id=tenant_id,
        resource_type="quick_reply",
        resource_id=reply_id,
        payload={"fields": list(clean.keys())},
    )
    return jsonify({"status": "ok", "item": _serialize(row)})


@bp.delete("/api/admin/quick-replies/<reply_id>")
@require_role("super_admin", "admin_tenant")
def delete_quick_reply(reply_id: str):
    tenant_id = _tenant_id()
    user_id = _user_id()
    if not tenant_id or not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    db = get_postgres()
    row = db.fetch_one(
        """UPDATE aia_health_quick_replies
              SET active = FALSE
            WHERE id = %s AND tenant_id = %s AND active = TRUE
            RETURNING id, shortcut""",
        (reply_id, tenant_id),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    write_audit(
        action="quick_reply_deleted",
        actor=str(user_id),
        tenant_id=tenant_id,
        resource_type="quick_reply",
        resource_id=reply_id,
        payload={"shortcut": row["shortcut"]},
    )
    return jsonify({"status": "ok"})


@bp.post("/api/admin/quick-replies/<reply_id>/use")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def track_quick_reply_use(reply_id: str):
    """Incrementa usage_count + atualiza last_used_at.

    Best-effort: silencia erros pra não atrapalhar fluxo do operador.
    Não loga audit (ruído alto, baixo valor).
    """
    tenant_id = _tenant_id()
    if not tenant_id:
        return jsonify({"status": "error", "reason": "no_tenant"}), 401

    try:
        get_postgres().execute(
            """UPDATE aia_health_quick_replies
                  SET usage_count = usage_count + 1,
                      last_used_at = NOW()
                WHERE id = %s AND tenant_id = %s AND active = TRUE""",
            (reply_id, tenant_id),
        )
    except Exception as exc:
        logger.warning(
            "quick_reply_use_track_failed",
            reply_id=reply_id, error=str(exc)[:200],
        )
    return jsonify({"status": "ok"})
