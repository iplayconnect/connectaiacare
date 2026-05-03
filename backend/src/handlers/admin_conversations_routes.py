"""Admin conversations — replay + busca por phone/trace.

Phase D scope:
    GET /api/admin/conversations/by-phone/<phone>  — turns Sofia
    GET /api/admin/conversations/by-trace/<trace>  — replay 1 evento
    GET /api/admin/conversations/recent            — últimas N

Reconstrói conversa a partir de aia_health_audit_log + outbound
audit. Não persiste turn-by-turn em tabela própria ainda — Phase E
cria aia_health_sofia_messages_v2 dedicada se volume justificar.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.identity_resolver import normalize_phone_e164_br
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_conversations", __name__)


def _serialize_event(row: dict) -> dict:
    out = {
        "action": row.get("action"),
        "payload": row.get("payload") or {},
        "actor": row.get("actor"),
        "tenant_id": row.get("tenant_id"),
        "trace_id": str(row["trace_id"]) if row.get("trace_id") else None,
        "session_id": str(row["session_id"]) if row.get("session_id") else None,
        "resource_type": row.get("resource_type"),
        "resource_id": row.get("resource_id"),
        "at": (
            row["created_at"].isoformat()
            if row.get("created_at") else None
        ),
    }
    return out


def _tenant_scope() -> tuple[str, list]:
    """Mesmo helper de admin_handoff_routes — super_admin vê tudo, outros
    só seu tenant. Bug fix 2026-05-03 (mesma falha de tenant isolation).

    TODO: extrair pra módulo shared backend/src/handlers/_tenant.py num
    PR de cleanup (3 cópias hoje: handoff/conversations/leads-futuro).
    """
    user = getattr(g, "user", {}) or {}
    role = user.get("role") or ""
    if role == "super_admin":
        return "", []
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return " AND FALSE", []
    return " AND tenant_id = %s", [tenant_id]


@bp.get("/api/admin/conversations/by-phone/<phone>")
@require_role("super_admin", "admin_tenant")
def by_phone(phone: str):
    """Eventos audit que envolvem esse phone, ordenados cronológica."""
    normalized = normalize_phone_e164_br(phone) or phone
    redacted_pattern = (
        f"55519****{normalized[-4:]}"
        if len(normalized) >= 4 else "***"
    )
    days = int(request.args.get("days") or 7)
    days = max(1, min(days, 90))

    scope_sql, scope_params = _tenant_scope()
    rows = get_postgres().fetch_all(
        f"""SELECT action, payload, actor, tenant_id, trace_id,
                  session_id, resource_type, resource_id, created_at
           FROM aia_health_audit_log
           WHERE created_at >= NOW() - (%s || ' days')::interval
             AND (
                payload->>'phone' = %s
                OR payload->>'phone_redacted' = %s
                OR payload->>'destination' = %s
             ){scope_sql}
           ORDER BY created_at ASC LIMIT 500""",
        (str(days), normalized, redacted_pattern, normalized, *scope_params),
    )
    return jsonify({
        "status": "ok",
        "phone": normalized,
        "events": [_serialize_event(r) for r in rows],
        "count": len(rows),
    })


@bp.get("/api/admin/conversations/by-trace/<trace_id>")
@require_role("super_admin", "admin_tenant")
def by_trace(trace_id: str):
    scope_sql, scope_params = _tenant_scope()
    rows = get_postgres().fetch_all(
        f"""SELECT action, payload, actor, tenant_id, trace_id,
                  session_id, resource_type, resource_id, created_at
           FROM aia_health_audit_log
           WHERE trace_id = %s{scope_sql}
           ORDER BY created_at ASC""",
        (trace_id, *scope_params),
    )
    return jsonify({
        "status": "ok",
        "trace_id": trace_id,
        "events": [_serialize_event(r) for r in rows],
        "count": len(rows),
    })


@bp.get("/api/admin/conversations/recent")
@require_role("super_admin", "admin_tenant")
def recent():
    """Lista de phones distintos que tiveram atividade Sofia recente."""
    qs = request.args
    days = int(qs.get("days") or 7)
    days = max(1, min(days, 30))
    limit = max(1, min(int(qs.get("limit") or 50), 200))

    scope_sql, scope_params = _tenant_scope()
    rows = get_postgres().fetch_all(
        f"""SELECT
              COALESCE(payload->>'phone', payload->>'phone_redacted', payload->>'destination') AS phone_or_redacted,
              MAX(created_at) AS last_at,
              COUNT(*) AS events,
              MAX(payload->>'sub_agent') AS last_sub_agent,
              MAX(payload->>'intent') AS last_intent,
              tenant_id
          FROM aia_health_audit_log
          WHERE created_at >= NOW() - (%s || ' days')::interval
            AND (payload->>'phone' IS NOT NULL OR payload->>'phone_redacted' IS NOT NULL)
            AND action IN (
                'webhook_received','sofia_agent_turn',
                'lead_created','lead_updated','outbound_sent',
                'handoff_initiated'
            ){scope_sql}
          GROUP BY 1, tenant_id
          ORDER BY last_at DESC LIMIT %s""",
        (str(days), *scope_params, limit),
    )
    items = []
    for r in rows:
        v = r.get("last_at")
        items.append({
            "phone_or_redacted": r.get("phone_or_redacted"),
            "tenant_id": r.get("tenant_id"),
            "last_at": v.isoformat() if v and hasattr(v, "isoformat") else None,
            "events": int(r.get("events") or 0),
            "last_sub_agent": r.get("last_sub_agent"),
            "last_intent": r.get("last_intent"),
        })
    return jsonify({"status": "ok", "items": items, "count": len(items)})
