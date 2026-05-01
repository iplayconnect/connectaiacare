"""Admin handoff queue — fila de pedidos pra atendimento humano.

Endpoints:
    GET  /api/admin/handoff                    — lista + filtros
    GET  /api/admin/handoff/<id>               — detalhe
    POST /api/admin/handoff/<id>/claim         — humano reivindica
    POST /api/admin/handoff/<id>/resolve       — humano marca resolvido
    GET  /api/admin/handoff/stats              — agregação SLA

Acesso: super_admin, admin_tenant.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_handoff", __name__)

VALID_STATUSES = ("pending", "claimed", "resolved", "expired")
VALID_PRIORITIES = ("P1", "P2", "P3")


def _serialize_handoff(row: dict) -> dict:
    if not row:
        return None
    out = dict(row)
    for k in ("created_at", "claimed_at", "resolved_at",
              "notified_central_at", "sla_breached_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    out["id"] = str(out["id"])
    if out.get("trace_id"):
        out["trace_id"] = str(out["trace_id"])
    if out.get("assigned_to_user_id"):
        out["assigned_to_user_id"] = str(out["assigned_to_user_id"])
    if out.get("claimed_by_user_id"):
        out["claimed_by_user_id"] = str(out["claimed_by_user_id"])
    if out.get("resolved_by_user_id"):
        out["resolved_by_user_id"] = str(out["resolved_by_user_id"])
    return out


@bp.get("/api/admin/handoff")
@require_role("super_admin", "admin_tenant")
def list_handoff():
    qs = request.args
    where = ["1=1"]
    params: list = []

    if qs.get("status"):
        statuses = [s.strip() for s in qs["status"].split(",") if s.strip()]
        valid = [s for s in statuses if s in VALID_STATUSES]
        if valid:
            where.append("status = ANY(%s)")
            params.append(valid)

    if qs.get("priority"):
        prio = [p.strip() for p in qs["priority"].split(",") if p.strip()]
        valid = [p for p in prio if p in VALID_PRIORITIES]
        if valid:
            where.append("priority = ANY(%s)")
            params.append(valid)

    days = int(qs.get("days") or 7)
    days = max(1, min(days, 90))
    where.append("created_at >= NOW() - (%s || ' days')::interval")
    params.append(str(days))

    limit = max(1, min(int(qs.get("limit") or 50), 200))
    offset = max(0, int(qs.get("offset") or 0))

    rows = get_postgres().fetch_all(
        f"""SELECT id, trace_id, phone, tenant_id, channel, reason,
                   priority, status,
                   assigned_to_user_id, claimed_by_user_id,
                   resolved_by_user_id, resolution_summary,
                   notified_central_at, claimed_at, resolved_at,
                   sla_target_seconds, sla_breached_at,
                   LEFT(context_summary, 280) AS context_preview,
                   jsonb_array_length(COALESCE(conversation_log, '[]'::jsonb)) AS msgs_count,
                   created_at
            FROM aia_health_human_handoff_queue
            WHERE {' AND '.join(where)}
            ORDER BY
              CASE priority WHEN 'P1' THEN 0 WHEN 'P2' THEN 1 ELSE 2 END,
              created_at DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "items": [_serialize_handoff(r) for r in rows],
    })


@bp.get("/api/admin/handoff/<handoff_id>")
@require_role("super_admin", "admin_tenant")
def get_handoff(handoff_id: str):
    row = get_postgres().fetch_one(
        "SELECT * FROM aia_health_human_handoff_queue WHERE id = %s",
        (handoff_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    return jsonify({"status": "ok", "handoff": _serialize_handoff(row)})


@bp.post("/api/admin/handoff/<handoff_id>/claim")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def claim_handoff(handoff_id: str):
    user_id = (getattr(g, "user", {}) or {}).get("sub")
    if not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    db = get_postgres()
    row = db.fetch_one(
        "SELECT id, status FROM aia_health_human_handoff_queue WHERE id = %s",
        (handoff_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    if row["status"] != "pending":
        return jsonify({
            "status": "error", "reason": "not_claimable",
            "current_status": row["status"],
        }), 409

    db.execute(
        """UPDATE aia_health_human_handoff_queue
              SET status = 'claimed',
                  claimed_at = NOW(),
                  claimed_by_user_id = %s,
                  assigned_to_user_id = COALESCE(assigned_to_user_id, %s)
            WHERE id = %s""",
        (user_id, user_id, handoff_id),
    )
    write_audit(
        action="handoff_claimed",
        actor=str(user_id), resource_type="handoff", resource_id=handoff_id,
    )
    updated = db.fetch_one(
        "SELECT * FROM aia_health_human_handoff_queue WHERE id = %s",
        (handoff_id,),
    )
    return jsonify({"status": "ok", "handoff": _serialize_handoff(updated)})


@bp.post("/api/admin/handoff/<handoff_id>/resolve")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def resolve_handoff(handoff_id: str):
    body = request.get_json(silent=True) or {}
    summary = (body.get("resolution_summary") or "").strip()
    if not summary:
        return jsonify({
            "status": "error", "reason": "resolution_summary_required",
        }), 400

    user_id = (getattr(g, "user", {}) or {}).get("sub")
    db = get_postgres()
    row = db.fetch_one(
        "SELECT id, status FROM aia_health_human_handoff_queue WHERE id = %s",
        (handoff_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    if row["status"] not in ("pending", "claimed"):
        return jsonify({
            "status": "error", "reason": "not_resolvable",
            "current_status": row["status"],
        }), 409

    db.execute(
        """UPDATE aia_health_human_handoff_queue
              SET status = 'resolved',
                  resolved_at = NOW(),
                  resolved_by_user_id = %s,
                  resolution_summary = %s
            WHERE id = %s""",
        (user_id, summary, handoff_id),
    )
    write_audit(
        action="handoff_resolved",
        actor=str(user_id), resource_type="handoff", resource_id=handoff_id,
        payload={"summary_chars": len(summary)},
    )
    updated = db.fetch_one(
        "SELECT * FROM aia_health_human_handoff_queue WHERE id = %s",
        (handoff_id,),
    )
    return jsonify({"status": "ok", "handoff": _serialize_handoff(updated)})


@bp.get("/api/admin/handoff/stats")
@require_role("super_admin", "admin_tenant")
def handoff_stats():
    days = int(request.args.get("days") or 7)
    days = max(1, min(days, 90))
    db = get_postgres()
    totals = db.fetch_one(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                  COUNT(*) FILTER (WHERE status = 'claimed') AS claimed,
                  COUNT(*) FILTER (WHERE status = 'resolved') AS resolved,
                  COUNT(*) FILTER (WHERE sla_breached_at IS NOT NULL) AS sla_breached,
                  AVG(EXTRACT(EPOCH FROM (claimed_at - created_at))) AS avg_claim_seconds
           FROM aia_health_human_handoff_queue
           WHERE created_at >= NOW() - (%s || ' days')::interval""",
        (str(days),),
    ) or {}
    for k in ("total", "pending", "claimed", "resolved", "sla_breached"):
        totals[k] = int(totals.get(k) or 0)
    if totals.get("avg_claim_seconds") is not None:
        try:
            totals["avg_claim_seconds"] = float(totals["avg_claim_seconds"])
        except Exception:
            totals["avg_claim_seconds"] = None

    by_priority = db.fetch_all(
        """SELECT priority, status, COUNT(*) AS n
           FROM aia_health_human_handoff_queue
           WHERE created_at >= NOW() - (%s || ' days')::interval
           GROUP BY 1, 2 ORDER BY 1, 2""",
        (str(days),),
    )
    for r in by_priority:
        r["n"] = int(r.get("n") or 0)

    return jsonify({
        "status": "ok",
        "days": days,
        "totals": totals,
        "by_priority": by_priority,
    })
