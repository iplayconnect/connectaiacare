"""Commercial Funnel — endpoints REST pra UI /comercial/funil.

Phase D Comercial — opera as 5 tabelas da migration 068:
  - aia_health_plans
  - aia_health_lead_demos
  - aia_health_lead_calls
  - aia_health_lead_proposals
  - aia_health_lead_activities

Complementa admin_leads_routes.py (que já tinha CRUD do lead row em si).
Aqui vivem operações sobre as entidades AO REDOR do lead.

Endpoints:
    GET  /api/admin/plans                     — catálogo
    POST /api/admin/plans                     — cria plano (super_admin)
    PATCH /api/admin/plans/<id>               — edita
    GET  /api/admin/leads/funnel              — kanban (leads agrupados por status)
    POST /api/admin/leads                     — cria lead manual
    GET  /api/admin/leads/<id>/timeline       — atividades + demos + calls + props
    POST /api/admin/leads/<id>/demos          — agenda demo
    PATCH /api/admin/lead-demos/<id>          — atualiza demo (confirma, completa)
    POST /api/admin/leads/<id>/calls          — registra call
    POST /api/admin/leads/<id>/proposals      — cria proposta
    PATCH /api/admin/lead-proposals/<id>      — atualiza proposta (accept/reject)
    GET  /api/admin/leads/upcoming-demos      — agenda comercial
    GET  /api/admin/leads/upcoming-callbacks  — callbacks pendentes
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request, g

from src.handlers.auth_routes import require_role
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)
bp = Blueprint("commercial_funnel", __name__)


def _serialize(row: dict) -> dict | None:
    """Serializa row pra JSON (UUID→str, datetime→ISO)."""
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):  # UUID
            out[k] = str(v)
        else:
            out[k] = v
    return out


# ════════════════════ PLANS ═══════════════════════════════════════

@bp.get("/api/admin/plans")
@require_role("super_admin", "admin_tenant", "comercial")
def list_plans():
    """Lista planos. Query params:
        active (bool, default true)
        public_only (bool, default false — admin vê tudo)
        target_persona (str)
    """
    qs = request.args
    # Default: scope='commercial_sales' (planos comerciais que time vende).
    # Pra ver subscription_b2c também: ?scope=all
    scope = qs.get("scope", "commercial_sales")
    where = []
    params: list = []
    if scope != "all":
        where.append("scope = %s")
        params.append(scope)
    else:
        where.append("1=1")

    if qs.get("active", "true").lower() == "true":
        where.append("active = TRUE")

    if qs.get("public_only", "false").lower() == "true":
        where.append("public = TRUE")

    if qs.get("target_persona"):
        where.append("target_persona = %s")
        params.append(qs["target_persona"])

    rows = get_postgres().fetch_all(
        f"""SELECT id::text AS id, sku, name, target_persona, target_segment,
                   price_monthly_cents, price_setup_cents, currency,
                   billing_period, max_patients, max_caregivers,
                   max_messages_month, max_voice_minutes_month,
                   features, pitch_short, pitch_full, differentials,
                   active, public, created_at, updated_at
            FROM aia_health_plans
            WHERE {' AND '.join(where)}
            ORDER BY price_monthly_cents NULLS LAST, name""",
        tuple(params),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.post("/api/admin/plans")
@require_role("super_admin")
def create_plan():
    body = request.get_json(silent=True) or {}
    required = ("sku", "name", "target_persona")
    missing = [k for k in required if not body.get(k)]
    if missing:
        return jsonify({
            "status": "error", "reason": "missing_fields", "fields": missing,
        }), 400

    # Endpoint comercial — sempre cria scope='commercial_sales'
    # (planos B2C subscription são gerenciados via /api/plans público
    # antigo, não aqui).
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_plans (
                sku, name, scope, target_persona, target_segment,
                price_monthly_cents, price_setup_cents, currency,
                billing_period, max_patients, max_caregivers,
                max_messages_month, max_voice_minutes_month,
                features, pitch_short, pitch_full, differentials,
                active, public,
                price_cents, max_beneficiaries, max_emergency_contacts,
                trial_days, trial_requires_card, pix_allows_trial,
                required_verification, display_order
            ) VALUES (
                %s, %s, 'commercial_sales', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s, %s, %s::jsonb, %s, %s,
                COALESCE(%s, 0), COALESCE(%s, 0), 0,
                0, FALSE, FALSE, 'cpf_whatsapp', 999
            )
            RETURNING id::text AS id""",
            (
                body["sku"], body["name"], body["target_persona"],
                body.get("target_segment"),
                body.get("price_monthly_cents"),
                body.get("price_setup_cents", 0),
                body.get("currency", "BRL"),
                body.get("billing_period", "monthly"),
                body.get("max_patients"), body.get("max_caregivers"),
                body.get("max_messages_month"),
                body.get("max_voice_minutes_month"),
                json.dumps(body.get("features") or {}),
                body.get("pitch_short"), body.get("pitch_full"),
                json.dumps(body.get("differentials") or []),
                body.get("active", True), body.get("public", True),
                # mirror pra colunas legadas (NOT NULL no schema antigo)
                body.get("price_monthly_cents"),
                body.get("max_patients"),
            ),
        )
        return jsonify({
            "status": "ok", "id": row["id"] if row else None,
        }), 201
    except Exception as exc:
        logger.exception("create_plan_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


@bp.patch("/api/admin/plans/<plan_id>")
@require_role("super_admin")
def update_plan(plan_id: str):
    body = request.get_json(silent=True) or {}
    allowed = (
        "name", "target_segment", "price_monthly_cents", "price_setup_cents",
        "currency", "billing_period", "max_patients", "max_caregivers",
        "max_messages_month", "max_voice_minutes_month",
        "features", "pitch_short", "pitch_full", "differentials",
        "active", "public",
    )
    updates = []
    params: list = []
    for k in allowed:
        if k in body:
            v = body[k]
            if k in ("features", "differentials") and isinstance(v, (dict, list)):
                v = json.dumps(v)
                updates.append(f"{k} = %s::jsonb")
            else:
                updates.append(f"{k} = %s")
            params.append(v)

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(plan_id)
    try:
        get_postgres().execute(
            f"UPDATE aia_health_plans SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        logger.exception("update_plan_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


# ════════════════════ FUNNEL (kanban) ═════════════════════════════

@bp.get("/api/admin/leads/funnel")
@require_role("super_admin", "admin_tenant", "comercial")
def funnel_kanban():
    """Retorna leads agrupados por status pra UI kanban.

    Query: days (default 60)
    """
    days = int(request.args.get("days", 60))
    days = max(1, min(days, 365))

    rows = get_postgres().fetch_all(
        """SELECT id::text AS id, phone, full_name, organization,
                  role_self_declared, intent, status, qualification_score,
                  demo_scheduled_at, last_contact_at, created_at,
                  jsonb_array_length(COALESCE(notes, '[]'::jsonb)) AS notes_count
           FROM aia_health_leads
           WHERE created_at >= NOW() - (%s || ' days')::interval
             AND status NOT IN ('converted', 'lost')
           ORDER BY status, qualification_score DESC NULLS LAST, last_contact_at DESC""",
        (str(days),),
    )

    columns: dict[str, list] = {
        "new": [], "qualified": [], "demo_scheduled": [],
        "in_demo": [], "proposal_sent": [],
    }
    for r in rows:
        st = r.get("status")
        if st in columns:
            columns[st].append(_serialize(r))

    return jsonify({
        "status": "ok",
        "columns": columns,
        "totals": {st: len(items) for st, items in columns.items()},
        "total": sum(len(items) for items in columns.values()),
    })


# ════════════════════ TIMELINE ════════════════════════════════════

@bp.get("/api/admin/leads/<lead_id>/timeline")
@require_role("super_admin", "admin_tenant", "comercial")
def lead_timeline(lead_id: str):
    """Timeline cross-table de tudo que rolou com o lead."""
    db = get_postgres()
    activities = db.fetch_all(
        """SELECT id::text AS id, activity_type, actor_type, actor_name,
                  summary, details, related_demo_id::text AS related_demo_id,
                  related_call_id::text AS related_call_id,
                  related_proposal_id::text AS related_proposal_id,
                  importance, occurred_at
           FROM aia_health_lead_activities
           WHERE lead_id = %s
           ORDER BY occurred_at DESC LIMIT 200""",
        (lead_id,),
    )

    demos = db.fetch_all(
        """SELECT id::text AS id, scheduled_at, duration_minutes,
                  meeting_url, meeting_provider, status,
                  completed_outcome, completed_summary,
                  notes, created_at
           FROM aia_health_lead_demos
           WHERE lead_id = %s
           ORDER BY scheduled_at DESC LIMIT 50""",
        (lead_id,),
    )

    calls = db.fetch_all(
        """SELECT id::text AS id, direction, called_by_actor,
                  started_at, ended_at, duration_seconds,
                  call_type, summary, outcome, sentiment,
                  next_action, next_action_at
           FROM aia_health_lead_calls
           WHERE lead_id = %s
           ORDER BY started_at DESC LIMIT 50""",
        (lead_id,),
    )

    proposals = db.fetch_all(
        """SELECT p.id::text AS id, p.plan_id::text AS plan_id,
                  pl.sku AS plan_sku, pl.name AS plan_name,
                  p.custom_price_monthly_cents,
                  p.custom_price_setup_cents,
                  p.discount_percent, p.valid_until,
                  p.proposal_url, p.sent_via, p.status,
                  p.sent_at, p.viewed_at, p.decided_at, p.decision_reason
           FROM aia_health_lead_proposals p
           JOIN aia_health_plans pl ON pl.id = p.plan_id
           WHERE p.lead_id = %s
           ORDER BY p.sent_at DESC""",
        (lead_id,),
    )

    return jsonify({
        "status": "ok",
        "activities": [_serialize(r) for r in activities],
        "demos": [_serialize(r) for r in demos],
        "calls": [_serialize(r) for r in calls],
        "proposals": [_serialize(r) for r in proposals],
    })


# ════════════════════ DEMOS ════════════════════════════════════════

@bp.post("/api/admin/leads/<lead_id>/demos")
@require_role("super_admin", "admin_tenant", "comercial")
def create_demo(lead_id: str):
    body = request.get_json(silent=True) or {}
    if not body.get("scheduled_at"):
        return jsonify({"status": "error", "reason": "scheduled_at_required"}), 400

    user_ctx = getattr(g, "user", None) or {}
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_lead_demos (
                lead_id, scheduled_by_user_id, scheduled_by_actor,
                assigned_to_user_id, scheduled_at, duration_minutes,
                timezone, meeting_url, meeting_provider,
                plan_focus_id, notes, status
            ) VALUES (%s, %s, 'human', %s, %s::timestamptz, %s, %s,
                      %s, %s, %s, %s, 'scheduled')
            RETURNING id::text AS id""",
            (
                lead_id, user_ctx.get("sub"),
                body.get("assigned_to_user_id"),
                body["scheduled_at"],
                int(body.get("duration_minutes", 30)),
                body.get("timezone", "America/Sao_Paulo"),
                body.get("meeting_url"),
                body.get("meeting_provider", "connectalive"),
                body.get("plan_focus_id"),
                body.get("notes"),
            ),
        )
        get_postgres().execute(
            """UPDATE aia_health_leads
                  SET status = 'demo_scheduled',
                      demo_scheduled_at = %s::timestamptz,
                      updated_at = NOW()
                WHERE id = %s""",
            (body["scheduled_at"], lead_id),
        )
        return jsonify({
            "status": "ok", "id": row["id"] if row else None,
        }), 201
    except Exception as exc:
        logger.exception("create_demo_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


@bp.patch("/api/admin/lead-demos/<demo_id>")
@require_role("super_admin", "admin_tenant", "comercial")
def update_demo(demo_id: str):
    body = request.get_json(silent=True) or {}
    allowed = (
        "scheduled_at", "duration_minutes", "meeting_url",
        "meeting_provider", "plan_focus_id", "notes", "status",
        "completed_outcome", "completed_summary", "follow_up_at",
        "assigned_to_user_id",
    )
    updates = []
    params: list = []
    for k in allowed:
        if k in body:
            v = body[k]
            updates.append(f"{k} = %s")
            params.append(v)

    if "status" in body and body["status"] == "completed":
        updates.append("completed_at = NOW()")
    if "status" in body and body["status"] == "confirmed":
        updates.append("confirmed_at = NOW()")

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(demo_id)
    try:
        get_postgres().execute(
            f"UPDATE aia_health_lead_demos SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        logger.exception("update_demo_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


# ════════════════════ CALLS ═══════════════════════════════════════

@bp.post("/api/admin/leads/<lead_id>/calls")
@require_role("super_admin", "admin_tenant", "comercial")
def register_call(lead_id: str):
    body = request.get_json(silent=True) or {}
    user_ctx = getattr(g, "user", None) or {}
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_lead_calls (
                lead_id, direction, called_by_actor, called_by_user_id,
                started_at, ended_at, duration_seconds,
                call_type, transcript, summary, outcome, sentiment,
                next_action, next_action_at,
                recording_url, recording_consent
            ) VALUES (%s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                      %s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s, %s)
            RETURNING id::text AS id""",
            (
                lead_id,
                body.get("direction", "outbound"),
                body.get("called_by_actor", "human"),
                user_ctx.get("sub"),
                body.get("started_at"),
                body.get("ended_at"),
                body.get("duration_seconds"),
                body.get("call_type", "follow_up"),
                body.get("transcript"),
                body.get("summary"),
                body.get("outcome"),
                body.get("sentiment"),
                body.get("next_action"),
                body.get("next_action_at"),
                body.get("recording_url"),
                bool(body.get("recording_consent", False)),
            ),
        )
        return jsonify({
            "status": "ok", "id": row["id"] if row else None,
        }), 201
    except Exception as exc:
        logger.exception("register_call_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


# ════════════════════ PROPOSALS ═══════════════════════════════════

@bp.post("/api/admin/leads/<lead_id>/proposals")
@require_role("super_admin", "admin_tenant", "comercial")
def create_proposal(lead_id: str):
    body = request.get_json(silent=True) or {}
    if not body.get("plan_id") and not body.get("plan_sku"):
        return jsonify({
            "status": "error", "reason": "plan_id_or_plan_sku_required",
        }), 400

    plan_id = body.get("plan_id")
    if not plan_id:
        plan = get_postgres().fetch_one(
            "SELECT id::text AS id FROM aia_health_plans WHERE sku = %s",
            (body["plan_sku"],),
        )
        if not plan:
            return jsonify({"status": "error", "reason": "plan_not_found"}), 404
        plan_id = plan["id"]

    user_ctx = getattr(g, "user", None) or {}
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_lead_proposals (
                lead_id, plan_id, sent_by_user_id, sent_by_actor,
                custom_price_monthly_cents, custom_price_setup_cents,
                custom_features, discount_percent, valid_until,
                proposal_url, proposal_html, sent_via, status
            ) VALUES (%s, %s, %s, 'human',
                      %s, %s, %s::jsonb, %s, %s::date,
                      %s, %s, %s, 'sent')
            RETURNING id::text AS id""",
            (
                lead_id, plan_id, user_ctx.get("sub"),
                body.get("custom_price_monthly_cents"),
                body.get("custom_price_setup_cents"),
                json.dumps(body.get("custom_features") or {}),
                body.get("discount_percent"),
                body.get("valid_until"),
                body.get("proposal_url"),
                body.get("proposal_html"),
                body.get("sent_via", "email"),
            ),
        )
        get_postgres().execute(
            """UPDATE aia_health_leads
                  SET status = 'proposal_sent',
                      last_contact_at = NOW(),
                      updated_at = NOW()
                WHERE id = %s""",
            (lead_id,),
        )
        return jsonify({
            "status": "ok", "id": row["id"] if row else None,
        }), 201
    except Exception as exc:
        logger.exception("create_proposal_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


@bp.patch("/api/admin/lead-proposals/<proposal_id>")
@require_role("super_admin", "admin_tenant", "comercial")
def update_proposal(proposal_id: str):
    body = request.get_json(silent=True) or {}
    allowed = (
        "status", "decision_reason", "viewed_at", "decided_at",
        "converted_to_tenant_id",
    )
    updates = []
    params: list = []
    for k in allowed:
        if k in body:
            updates.append(f"{k} = %s")
            params.append(body[k])

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(proposal_id)
    try:
        get_postgres().execute(
            f"UPDATE aia_health_lead_proposals SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )
        # Se aceita, atualiza lead pra converted
        if body.get("status") == "accepted":
            row = get_postgres().fetch_one(
                "SELECT lead_id::text AS lead_id, converted_to_tenant_id FROM aia_health_lead_proposals WHERE id = %s",
                (proposal_id,),
            )
            if row:
                get_postgres().execute(
                    """UPDATE aia_health_leads SET
                          status = 'converted',
                          converted_at = NOW(),
                          converted_to_tenant_id = %s,
                          updated_at = NOW()
                       WHERE id = %s""",
                    (row.get("converted_to_tenant_id"), row["lead_id"]),
                )
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        logger.exception("update_proposal_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


# ════════════════════ AGENDA / UPCOMING ═══════════════════════════

@bp.get("/api/admin/leads/upcoming-demos")
@require_role("super_admin", "admin_tenant", "comercial")
def upcoming_demos():
    """Demos agendadas próximas (próximos 14 dias por default)."""
    days = int(request.args.get("days", 14))
    days = max(1, min(days, 90))

    rows = get_postgres().fetch_all(
        """SELECT d.id::text AS id, d.lead_id::text AS lead_id,
                  d.scheduled_at, d.duration_minutes, d.status,
                  d.meeting_url, d.meeting_provider,
                  d.assigned_to_user_id::text AS assigned_to_user_id,
                  l.phone, l.full_name, l.organization,
                  l.qualification_score
           FROM aia_health_lead_demos d
           JOIN aia_health_leads l ON l.id = d.lead_id
           WHERE d.status IN ('scheduled', 'confirmed')
             AND d.scheduled_at BETWEEN NOW() AND NOW() + (%s || ' days')::interval
           ORDER BY d.scheduled_at ASC""",
        (str(days),),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.get("/api/admin/leads/upcoming-callbacks")
@require_role("super_admin", "admin_tenant", "comercial")
def upcoming_callbacks():
    """Callbacks pendentes (próximos 7 dias)."""
    days = int(request.args.get("days", 7))
    days = max(1, min(days, 30))

    rows = get_postgres().fetch_all(
        """SELECT c.id::text AS id, c.lead_id::text AS lead_id,
                  c.next_action_at, c.call_type, c.summary,
                  l.phone, l.full_name, l.organization,
                  l.qualification_score
           FROM aia_health_lead_calls c
           JOIN aia_health_leads l ON l.id = c.lead_id
           WHERE c.outcome IS NULL
             AND c.next_action_at BETWEEN NOW() AND NOW() + (%s || ' days')::interval
           ORDER BY c.next_action_at ASC""",
        (str(days),),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


# ════════════════════ CREATE LEAD MANUAL ══════════════════════════

@bp.post("/api/admin/leads")
@require_role("super_admin", "admin_tenant", "comercial")
def create_lead_manual():
    """Cria lead manualmente (humano cadastrando contato vindo de
    feira, indicação, evento). Sofia continua usando capture_lead."""
    body = request.get_json(silent=True) or {}
    if not body.get("phone"):
        return jsonify({"status": "error", "reason": "phone_required"}), 400

    user_ctx = getattr(g, "user", None) or {}
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_leads (
                phone, full_name, email, organization, role_self_declared,
                intent, source_channel, source_metadata, status,
                qualification_score, last_contact_at,
                qualified_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                      %s, NOW(), %s)
            RETURNING id::text AS id""",
            (
                body["phone"], body.get("full_name"), body.get("email"),
                body.get("organization"), body.get("role_self_declared"),
                body.get("intent", "duvida_geral"),
                body.get("source_channel", "manual"),
                json.dumps(body.get("source_metadata") or {
                    "created_via": "admin_ui",
                    "created_by_user_id": user_ctx.get("sub"),
                }),
                body.get("status", "qualified"),  # manual = já triado humano
                int(body.get("qualification_score", 50)),
                user_ctx.get("sub"),
            ),
        )
        return jsonify({
            "status": "ok", "id": row["id"] if row else None,
        }), 201
    except Exception as exc:
        logger.exception("create_lead_manual_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500

# ════════════════════ NOTA: PATCH /api/admin/leads/<id> ═════════════
# Esse endpoint vive em src/handlers/admin_leads_routes.py (legado),
# que já trata status/qualification_score/lost_reason/notes e gera
# audit no aia_health_audit_log + activity em aia_health_lead_activities
# quando o status muda (drag-drop kanban). Mantemos um único endpoint
# pra evitar conflito de blueprints (Flask aceita rotas duplicadas em
# blueprints diferentes mas usa quem registrou primeiro — frágil).
