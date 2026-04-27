"""Safety Guardrail Layer — endpoints HTTP.

Endpoints internos (chamados por sofia-service e voice-call-service):
    POST /api/safety/route-action       — decide destino de uma ação
    POST /api/safety/queue/<id>/decide  — humano resolve item da fila

Endpoints de admin/UI:
    GET  /api/safety/queue              — lista pendentes do tenant
    GET  /api/safety/circuit-breaker    — estado atual
    POST /api/safety/circuit-breaker/reset — admin força fechar (super_admin)
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, g

from src.handlers.auth_routes import require_role
from src.services import safety_guardrail
from src.services.postgres import get_postgres
from src.services.audit_service import audit_log
from src.utils.logger import get_logger

logger = get_logger(__name__)
bp = Blueprint("safety", __name__)


# ──────────── HTTP central — chamado por outros services ────────────

@bp.post("/api/safety/route-action")
def route_action():
    """Endpoint interno (sem JWT obrigatório). Sofia/voice-call chama
    antes de executar ação clínica."""
    body = request.get_json(silent=True) or {}
    required = ("tenant_id", "action_type", "severity", "summary")
    missing = [k for k in required if not body.get(k)]
    if missing:
        return jsonify({
            "status": "error", "reason": "missing_fields", "fields": missing,
        }), 400

    try:
        result = safety_guardrail.route_action(
            tenant_id=body["tenant_id"],
            action_type=body["action_type"],
            severity=body["severity"],
            summary=body["summary"],
            patient_id=body.get("patient_id"),
            sofia_session_id=body.get("sofia_session_id"),
            triggered_by_tool=body.get("triggered_by_tool"),
            triggered_by_persona=body.get("triggered_by_persona"),
            sofia_confidence=body.get("sofia_confidence"),
            details=body.get("details"),
        )
    except Exception as exc:
        logger.exception("safety_route_action_failed")
        return jsonify({"status": "error", "reason": str(exc)}), 500

    return jsonify({"status": "ok", **result})


# ──────────── Queue: humano decide ────────────

@bp.get("/api/safety/queue")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia")
def list_queue():
    """Lista itens pending pra revisão. Filtra por tenant do user."""
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    limit = int(request.args.get("limit", 50))
    items = safety_guardrail.list_pending_queue(tenant_id, limit=limit)
    return jsonify({"status": "ok", "count": len(items), "items": items})


@bp.post("/api/safety/queue/<qid>/decide")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia")
def decide_queue_item(qid: str):
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")

    if decision not in ("approved", "rejected"):
        return jsonify({"status": "error", "reason": "invalid_decision"}), 400

    result = safety_guardrail.decide_queued_action(
        queue_id=qid,
        decision=decision,
        decided_by_user_id=user_id,
        notes=body.get("notes"),
    )
    if not result.get("ok"):
        return jsonify({"status": "error", "reason": result.get("error")}), 400
    return jsonify({"status": "ok", **result})


# ──────────── Circuit breaker ────────────

@bp.get("/api/safety/circuit-breaker")
@require_role("super_admin", "admin_tenant")
def circuit_status():
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = request.args.get("tenant_id") or user_ctx.get("tenant_id") or "connectaiacare_demo"
    row = get_postgres().fetch_one(
        "SELECT * FROM aia_health_safety_circuit_breaker WHERE tenant_id = %s",
        (tenant_id,),
    )
    if not row:
        return jsonify({"status": "ok", "state": "closed", "tenant_id": tenant_id})
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return jsonify({"status": "ok", **out})


@bp.post("/api/safety/circuit-breaker/reset")
@require_role("super_admin")
def circuit_reset():
    """Admin força fechar o circuit (após investigação)."""
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id") or "connectaiacare_demo"
    get_postgres().execute(
        """UPDATE aia_health_safety_circuit_breaker
           SET state = 'closed', open_until = NULL, opened_at = NULL,
               open_reason = NULL
           WHERE tenant_id = %s""",
        (tenant_id,),
    )
    user_ctx = getattr(g, "user", None) or {}
    audit_log(
        action="guardrail.circuit.manual_reset",
        tenant_id=tenant_id,
        actor=user_ctx.get("sub"),
        payload={"reset_reason": body.get("reason")},
    )
    return jsonify({"status": "ok", "tenant_id": tenant_id})


# ──────────── Stats / Health ────────────

@bp.get("/api/safety/stats")
@require_role("super_admin", "admin_tenant")
def stats():
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    row = get_postgres().fetch_one(
        """SELECT
            COUNT(*) FILTER (WHERE status = 'pending') AS pending,
            COUNT(*) FILTER (WHERE status = 'approved') AS approved,
            COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
            COUNT(*) FILTER (WHERE status = 'auto_executed') AS auto_executed,
            COUNT(*) FILTER (WHERE status = 'expired') AS expired,
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') AS last_24h,
            COUNT(*) AS total
           FROM aia_health_action_review_queue
           WHERE tenant_id = %s""",
        (tenant_id,),
    )
    return jsonify({"status": "ok", "tenant_id": tenant_id, "stats": dict(row) if row else {}})
