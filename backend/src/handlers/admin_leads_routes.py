"""Admin leads — funil B2B/B2C capturado pela Super Sofia.

Endpoints:
    GET  /api/admin/leads                  — lista + filtros
    GET  /api/admin/leads/<id>             — detalhe + transcript
    PATCH /api/admin/leads/<id>            — qualifica / descarta
    POST /api/admin/leads/<id>/convert     — converter pra tenant
    GET  /api/admin/leads/stats            — agregação pra dashboard

Acesso: super_admin, admin_tenant.

Phase D scope: read-mostly + ações leves de qualificação. Conversão
pra tenant cria entry vazia em aia_health_tenants (Phase D.4 futura
adiciona wizard pre-fill).
"""
from __future__ import annotations

import json
from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_leads", __name__)

VALID_STATUSES = (
    "new", "qualified", "demo_scheduled",
    "in_demo", "proposal_sent", "converted", "lost",
)


def _serialize_lead(row: dict) -> dict:
    if not row:
        return None
    out = dict(row)
    for k in ("created_at", "updated_at", "qualified_at",
              "demo_scheduled_at", "converted_at", "last_contact_at"):
        v = out.get(k)
        if v and hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    out["id"] = str(out["id"])
    if out.get("qualified_by_user_id"):
        out["qualified_by_user_id"] = str(out["qualified_by_user_id"])
    if out.get("confidence") is not None:
        try:
            out["confidence"] = float(out["confidence"])
        except Exception:
            pass
    return out


# ──────────────────────────────────────────────────────────────────
# GET /api/admin/leads
# ──────────────────────────────────────────────────────────────────


@bp.get("/api/admin/leads")
@require_role("super_admin", "admin_tenant")
def list_leads():
    """Lista paginada com filtros.

    Query params:
        status (str | csv)      — new|qualified|demo_scheduled|in_demo|...
        intent (str)            — interesse_servico_b2c|b2b|agendar_demo|...
        days (int, default 30)  — janela de criação
        search (str)            — substring em phone/full_name/organization
        limit (int, default 50, max 200)
        offset (int, default 0)
    """
    qs = request.args
    where = ["1=1"]
    params: list = []

    statuses = qs.get("status")
    if statuses:
        status_list = [s.strip() for s in statuses.split(",") if s.strip()]
        valid = [s for s in status_list if s in VALID_STATUSES]
        if valid:
            where.append("status = ANY(%s)")
            params.append(valid)

    if qs.get("intent"):
        where.append("intent = %s")
        params.append(qs["intent"])

    days = int(qs.get("days") or 30)
    days = max(1, min(days, 365))
    where.append("created_at >= NOW() - (%s || ' days')::interval")
    params.append(str(days))

    if qs.get("search"):
        s = f"%{qs['search'].strip()}%"
        where.append(
            "(phone ILIKE %s OR full_name ILIKE %s OR organization ILIKE %s)"
        )
        params.extend([s, s, s])

    limit = max(1, min(int(qs.get("limit") or 50), 200))
    offset = max(0, int(qs.get("offset") or 0))

    rows = get_postgres().fetch_all(
        f"""SELECT id, phone, full_name, email, organization,
                   role_self_declared, intent, confidence,
                   source_channel, status, qualification_score,
                   demo_link, demo_scheduled_at, qualified_at,
                   converted_at, converted_to_tenant_id,
                   lost_reason, last_contact_at,
                   created_at, updated_at,
                   jsonb_array_length(COALESCE(notes, '[]'::jsonb)) AS notes_count
            FROM aia_health_leads
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    total_row = get_postgres().fetch_one(
        f"SELECT COUNT(*) AS n FROM aia_health_leads WHERE {' AND '.join(where)}",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "total": int((total_row or {}).get("n") or 0),
        "limit": limit,
        "offset": offset,
        "leads": [_serialize_lead(r) for r in rows],
    })


# ──────────────────────────────────────────────────────────────────
# GET /api/admin/leads/<id>
# ──────────────────────────────────────────────────────────────────


@bp.get("/api/admin/leads/<lead_id>")
@require_role("super_admin", "admin_tenant")
def get_lead(lead_id: str):
    db = get_postgres()
    row = db.fetch_one(
        "SELECT * FROM aia_health_leads WHERE id = %s", (lead_id,),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    # Busca audit relacionado a esse phone (turns Sofia)
    turns = db.fetch_all(
        """SELECT action, payload, created_at
           FROM aia_health_audit_log
           WHERE created_at > NOW() - INTERVAL '7 days'
             AND action IN (
                'webhook_received','identity_resolved','intent_classified',
                'sofia_agent_turn','lead_created','lead_updated',
                'demo_scheduled','handoff_initiated','outbound_sent'
             )
             AND (
                payload->>'phone_redacted' = %s
                OR payload->>'phone' = %s
                OR resource_id = %s
             )
           ORDER BY created_at ASC LIMIT 200""",
        (
            # phone_redacted format: 55519****7222
            f"55519****{row['phone'][-4:]}" if len(row['phone']) >= 4 else "***",
            row['phone'],
            lead_id,
        ),
    )
    timeline = []
    for t in turns:
        timeline.append({
            "action": t["action"],
            "payload": t.get("payload") or {},
            "at": t["created_at"].isoformat() if t.get("created_at") else None,
        })

    return jsonify({
        "status": "ok",
        "lead": _serialize_lead(row),
        "timeline": timeline,
    })


# ──────────────────────────────────────────────────────────────────
# PATCH /api/admin/leads/<id>
# ──────────────────────────────────────────────────────────────────


@bp.patch("/api/admin/leads/<lead_id>")
@require_role("super_admin", "admin_tenant", "comercial")
def update_lead(lead_id: str):
    """Atualiza status/qualification/notes/lost_reason.

    Body opcionais:
        status        → new|qualified|demo_scheduled|...|converted|lost
        qualification_score  → int 0-100
        lost_reason   → str (quando status=lost)
        note          → str (append em notes JSONB)
        demo_scheduled_at, demo_link, full_name, email, organization,
        role_self_declared, intent, last_contact_at  → free-form

    Quando o status muda, registra entry em
    aia_health_lead_activities (timeline da página de detalhe do lead)
    além do audit log clássico. Falha do log de activity não derruba
    o update.
    """
    body = request.get_json(silent=True) or {}
    db = get_postgres()
    existing = db.fetch_one(
        "SELECT id, status FROM aia_health_leads WHERE id = %s", (lead_id,),
    )
    if not existing:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    updates: list = []
    params: list = []
    user_ctx = getattr(g, "user", {}) or {}
    user_id = user_ctx.get("sub")

    status_changed_to: str | None = None

    if "status" in body:
        status_new = body["status"]
        if status_new not in VALID_STATUSES:
            return jsonify({"status": "error", "reason": "invalid_status"}), 400
        updates.append("status = %s")
        params.append(status_new)
        # Marcadores automáticos
        if status_new == "qualified":
            updates.append("qualified_at = COALESCE(qualified_at, NOW())")
            updates.append("qualified_by_user_id = COALESCE(qualified_by_user_id, %s)")
            params.append(user_id)
        if status_new == "converted":
            updates.append("converted_at = COALESCE(converted_at, NOW())")
        if existing.get("status") != status_new:
            status_changed_to = status_new

    if "qualification_score" in body:
        try:
            score = int(body["qualification_score"])
            score = max(0, min(score, 100))
            updates.append("qualification_score = %s")
            params.append(score)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "reason": "invalid_score"}), 400

    if "lost_reason" in body:
        updates.append("lost_reason = %s")
        params.append(body["lost_reason"])

    # Campos free-form do funil comercial
    for k in ("demo_scheduled_at", "demo_link", "full_name", "email",
              "organization", "role_self_declared", "intent",
              "last_contact_at"):
        if k in body:
            updates.append(f"{k} = %s")
            params.append(body[k])

    if "note" in body and body["note"]:
        updates.append(
            "notes = COALESCE(notes, '[]'::jsonb) || jsonb_build_array("
            "jsonb_build_object('at', NOW()::text, 'by', %s::text, 'text', %s::text))"
        )
        params.append(str(user_id) if user_id else "admin")
        params.append(str(body["note"]))

    if not updates:
        return jsonify({"status": "error", "reason": "no_changes"}), 400

    params.append(lead_id)
    db.execute(
        f"UPDATE aia_health_leads SET {', '.join(updates)} WHERE id = %s",
        tuple(params),
    )

    # Activity log (timeline do funil comercial). Independente do
    # audit_log clássico — esse aqui aparece pro time comercial na UI.
    if status_changed_to:
        try:
            db.execute(
                """INSERT INTO aia_health_lead_activities
                   (lead_id, activity_type, actor_type, actor_user_id,
                    actor_name, summary, importance)
                   VALUES (%s, 'status_changed', 'human', %s, %s, %s, 'normal')""",
                (
                    lead_id,
                    user_id,
                    user_ctx.get("name") or user_ctx.get("email") or "humano",
                    f"status alterado para {status_changed_to}",
                ),
            )
        except Exception:
            # Não falhar o update por causa do activity log
            logger.warning(
                "activity_log_failed_for_status_change",
                extra={"lead_id": lead_id},
                exc_info=True,
            )

    write_audit(
        action="lead_admin_updated",
        actor=str(user_id) if user_id else "admin",
        resource_type="lead",
        resource_id=lead_id,
        payload={
            "fields": list(body.keys()),
            "new_status": body.get("status"),
        },
    )

    row = db.fetch_one(
        "SELECT * FROM aia_health_leads WHERE id = %s", (lead_id,),
    )
    return jsonify({"status": "ok", "lead": _serialize_lead(row)})


# ──────────────────────────────────────────────────────────────────
# GET /api/admin/leads/stats
# ──────────────────────────────────────────────────────────────────


@bp.get("/api/admin/leads/stats")
@require_role("super_admin", "admin_tenant")
def leads_stats():
    """Agregações por status, intent, dia. Pra dashboard."""
    db = get_postgres()
    days = int(request.args.get("days") or 30)
    days = max(1, min(days, 365))

    by_status = db.fetch_all(
        """SELECT status, COUNT(*) AS n
           FROM aia_health_leads
           WHERE created_at >= NOW() - (%s || ' days')::interval
           GROUP BY status ORDER BY n DESC""",
        (str(days),),
    )
    for r in by_status:
        r["n"] = int(r.get("n") or 0)

    by_intent = db.fetch_all(
        """SELECT intent, COUNT(*) AS n
           FROM aia_health_leads
           WHERE created_at >= NOW() - (%s || ' days')::interval
           GROUP BY intent ORDER BY n DESC""",
        (str(days),),
    )
    for r in by_intent:
        r["n"] = int(r.get("n") or 0)

    daily = db.fetch_all(
        """SELECT DATE_TRUNC('day', created_at)::date AS day,
                  COUNT(*) AS n,
                  COUNT(*) FILTER (WHERE status = 'qualified') AS qualified,
                  COUNT(*) FILTER (WHERE status = 'converted') AS converted
           FROM aia_health_leads
           WHERE created_at >= NOW() - (%s || ' days')::interval
           GROUP BY 1 ORDER BY 1 ASC""",
        (str(days),),
    )
    for r in daily:
        v = r.get("day")
        if v and hasattr(v, "isoformat"):
            r["day"] = v.isoformat()
        for k in ("n", "qualified", "converted"):
            r[k] = int(r.get(k) or 0)

    totals = db.fetch_one(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'qualified') AS qualified,
                  COUNT(*) FILTER (WHERE status = 'demo_scheduled') AS demo_scheduled,
                  COUNT(*) FILTER (WHERE status = 'converted') AS converted,
                  COUNT(*) FILTER (WHERE status = 'lost') AS lost
           FROM aia_health_leads
           WHERE created_at >= NOW() - (%s || ' days')::interval""",
        (str(days),),
    ) or {}
    for k in ("total", "qualified", "demo_scheduled", "converted", "lost"):
        totals[k] = int(totals.get(k) or 0)

    return jsonify({
        "status": "ok",
        "days": days,
        "totals": totals,
        "by_status": by_status,
        "by_intent": by_intent,
        "daily": daily,
    })
