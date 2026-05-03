"""Admin handoff queue — fila de pedidos pra atendimento humano.

Endpoints:
    GET    /api/admin/handoff                              — lista + filtros
    GET    /api/admin/handoff/<id>                         — detalhe
    GET    /api/admin/handoff/<id>/context                 — dados agregados pra ContextPanel
    POST   /api/admin/handoff/<id>/claim                   — humano reivindica
    POST   /api/admin/handoff/<id>/resolve                 — humano marca resolvido
    GET    /api/admin/handoff/<id>/messages                — histórico chat
    POST   /api/admin/handoff/<id>/send                    — operador envia msg
    PATCH  /api/admin/handoff/<id>/messages/<msg_id>       — edita msg do operador
    DELETE /api/admin/handoff/<id>/messages/<msg_id>       — soft delete
    GET    /api/admin/handoff/stats                        — agregação SLA

Acesso: super_admin, admin_tenant, medico, enfermeiro, atendente_humano.
"""
from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.event_bus import Streams, get_event_bus
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("admin_handoff", __name__)

VALID_STATUSES = ("pending", "claimed", "resolved", "expired")
VALID_PRIORITIES = ("P1", "P2", "P3")

# Janela em que operador pode editar/deletar a própria msg. Depois disso a msg
# vira imutável pra audit trail (LGPD/CFM exigem rastreabilidade clínica).
# Escolha de 5min é equilíbrio entre "ops corrigi um typo" e "audit confiável".
MESSAGE_MUTATION_WINDOW_SECONDS = 300


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


def _infer_intent_from_reason(reason: str | None) -> str:
    """Heurística simples — palavras-chave em handoff.reason → intent
    operacional. Vai ser substituído por intent classifier formal em
    fase posterior. Por hoje basta pra destacar capabilities relevantes.
    """
    if not reason:
        return "geral"
    r = reason.lower()
    if any(k in r for k in ("emerg", "samu", "queda", "urgent", "crítico", "critico")):
        return "emergencia"
    if any(k in r for k in ("medic", "remedio", "remédio", "dose", "bula", "interaç")):
        return "medicacao"
    if any(k in r for k in ("agend", "demo", "comercial", "preç", "plano", "venda")):
        return "comercial"
    return "geral"


# Mapeia categoria de capability pra intent que destaca.
_INTENT_HIGHLIGHT_CATEGORIES = {
    "emergencia": ("clinical", "ops"),
    "medicacao": ("clinical",),
    "comercial": ("commercial", "billing"),
    "geral": (),
}


@bp.get("/api/admin/handoff/<handoff_id>/context")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def handoff_context(handoff_id: str):
    """Agregação rica pra ContextPanel — lead + CSM + capabilities + timing.

    Tudo em uma única query batch pra evitar N+1 do polling. Capabilities
    vem ranqueado: highlighted=true pras categorias relevantes ao intent
    detectado em handoff.reason.
    """
    db = get_postgres()
    handoff = db.fetch_one(
        """SELECT id, phone, tenant_id, reason, priority, status,
                  created_at, claimed_at, resolved_at,
                  sla_target_seconds, sla_breached_at,
                  context_summary
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not handoff:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    tenant_id = handoff["tenant_id"]
    phone = handoff["phone"]

    # ── 1. CSM (best-effort — pode não existir pra leads antigos) ──
    csm_block = None
    try:
        from src.services.csm.conversation_state import ConversationState

        state = ConversationState.load(tenant_id, phone)
        if state:
            lead_dict = state.lead_data.to_dict()
            csm_block = {
                "current_stage": getattr(state.flow_state, "current_stage", None),
                "current_agent": getattr(state.flow_state, "current_agent", None),
                "warmup_complete": bool(
                    getattr(state.flow_state, "warmup_complete", False),
                ),
                "qualification_complete": bool(
                    getattr(state.flow_state, "qualification_complete", False),
                ),
                "pending_question": getattr(
                    state.flow_state, "pending_question", None,
                ),
                "lead_data": lead_dict,
                "interactions_count": len(state.interactions or []),
                "last_activity_at": state.last_activity_at,
            }
    except Exception as exc:
        logger.warning("handoff_context_csm_failed",
                       handoff_id=handoff_id, error=str(exc)[:200])

    # ── 2. Sofia stats (count msgs, primeiro contato) ──
    stats_row = db.fetch_one(
        """SELECT MIN(m.created_at) AS first_seen_at,
                  MAX(m.created_at) AS last_seen_at,
                  COUNT(*) FILTER (WHERE m.role = 'user') AS lead_msgs,
                  COUNT(*) FILTER (WHERE m.role = 'assistant') AS sofia_msgs,
                  COUNT(*) AS total_msgs
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE s.phone = %s AND s.tenant_id = %s""",
        (phone, tenant_id),
    ) or {}
    stats_block = {
        "first_seen_at": (
            stats_row.get("first_seen_at").isoformat()
            if stats_row.get("first_seen_at") else None
        ),
        "last_seen_at": (
            stats_row.get("last_seen_at").isoformat()
            if stats_row.get("last_seen_at") else None
        ),
        "lead_msgs": int(stats_row.get("lead_msgs") or 0),
        "sofia_msgs": int(stats_row.get("sofia_msgs") or 0),
        "total_msgs": int(stats_row.get("total_msgs") or 0),
    }

    # ── 3. Capabilities whitelist (highlight por intent) ──
    intent = _infer_intent_from_reason(handoff.get("reason"))
    highlight_cats = _INTENT_HIGHLIGHT_CATEGORIES.get(intent, ())

    capabilities_block: list[dict] = []
    try:
        from src.services.csm.capabilities import get_capabilities_service

        caps = get_capabilities_service().list_for_persona("anonymous")
        # Ordena: highlighted primeiro, depois alfabético
        def _key(c):
            highlighted = (c.category or "").lower() in highlight_cats
            return (0 if highlighted else 1, c.label_user or "")
        caps_sorted = sorted(caps[:20], key=_key)
        for c in caps_sorted[:12]:
            capabilities_block.append({
                "code": c.code,
                "label": c.label_user,
                "category": c.category,
                "requires_consent": bool(c.requires_consent),
                "highlighted": (c.category or "").lower() in highlight_cats,
            })
    except Exception as exc:
        logger.warning("handoff_context_caps_failed",
                       handoff_id=handoff_id, error=str(exc)[:200])

    # ── 4. Timing + SLA ──
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    def _delta_seconds(ts):
        if not ts:
            return None
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return int((now - ts).total_seconds())

    sla_target = int(handoff.get("sla_target_seconds") or 0)
    age_seconds = _delta_seconds(handoff.get("created_at")) or 0
    claim_age = _delta_seconds(handoff.get("claimed_at"))
    timing_block = {
        "created_at": handoff["created_at"].isoformat()
            if handoff.get("created_at") else None,
        "claimed_at": handoff["claimed_at"].isoformat()
            if handoff.get("claimed_at") else None,
        "resolved_at": handoff["resolved_at"].isoformat()
            if handoff.get("resolved_at") else None,
        "sla_target_seconds": sla_target,
        "sla_breached_at": handoff["sla_breached_at"].isoformat()
            if handoff.get("sla_breached_at") else None,
        "age_seconds": age_seconds,
        "claim_age_seconds": claim_age,
        # Predição: True se ainda não claimed E age > 80% do SLA
        "sla_at_risk": (
            sla_target > 0
            and not handoff.get("claimed_at")
            and not handoff.get("sla_breached_at")
            and age_seconds > sla_target * 0.8
        ),
    }

    return jsonify({
        "status": "ok",
        "handoff_id": str(handoff["id"]),
        "intent_inferred": intent,
        "lead": {
            "phone": phone,
            "tenant_id": tenant_id,
            "reason": handoff.get("reason"),
            "context_summary": handoff.get("context_summary"),
            **stats_block,
        },
        "csm": csm_block,
        "capabilities": capabilities_block,
        "timing": timing_block,
    })


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


@bp.get("/api/admin/handoff/<handoff_id>/messages")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def handoff_messages(handoff_id: str):
    """Histórico de mensagens do handoff pro chat do operador.

    Retorna 2 segmentos:
      • snapshot: conversation_log do escalate (pré-handoff)
      • live: msgs em sofia_messages após o handoff.created_at
        (operador + lead durante atendimento humano)

    Live é fonte da verdade pra polling real-time do chat. Snapshot
    é histórico do que Sofia conversou antes do escalate, útil pro
    operador entender contexto.
    """
    db = get_postgres()
    handoff = db.fetch_one(
        """SELECT id, phone, tenant_id, conversation_log, created_at
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not handoff:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    # Snapshot pré-handoff (Sofia + lead, salvo no momento do escalate)
    snapshot = handoff.get("conversation_log") or []
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except Exception:
            snapshot = []

    # Live: msgs em sofia_messages do mesmo phone, criadas após o handoff.
    # Filtra por sessions com phone matching (handoff_id na sofia_sessions
    # FK pode estar nulo em sessões legadas — usar phone é mais robusto).
    live_rows = db.fetch_all(
        """SELECT m.id, m.role, m.content, m.created_at,
                  m.metadata, m.tool_name
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE s.phone = %s
             AND m.created_at > %s
           ORDER BY m.created_at ASC
           LIMIT 200""",
        (handoff["phone"], handoff["created_at"]),
    )
    live = []
    for r in live_rows:
        md = r.get("metadata") or {}
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except Exception:
                md = {}
        if not isinstance(md, dict):
            md = {}

        item = {
            "id": int(r["id"]),
            "role": r["role"],
            "content": r.get("content"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        if md.get("actor"):
            item["actor"] = md["actor"]  # 'human' | 'sofia'
        if md.get("operator_user_id"):
            item["operator_user_id"] = str(md["operator_user_id"])
        if md.get("deleted") is True:
            item["deleted"] = True
            item["deleted_at"] = md.get("deleted_at")
        if md.get("edited_at"):
            item["edited_at"] = md["edited_at"]
            # Conta de edições — não retornamos o histórico completo no GET
            # pra não vazar conteúdo intermediário acidentalmente. Histórico
            # fica só no DB pra auditoria.
            item["edit_count"] = len(md.get("edit_history") or [])
        live.append(item)

    return jsonify({
        "status": "ok",
        "handoff_id": str(handoff["id"]),
        "phone": handoff["phone"],
        "snapshot": snapshot,
        "live": live,
    })


@bp.post("/api/admin/handoff/<handoff_id>/send")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def handoff_send(handoff_id: str):
    """Operador envia mensagem pro lead via WhatsApp + persiste.

    Pipeline:
      1. Valida handoff existe e está em estado 'claimed' (operador
         tem que ter reivindicado primeiro pra evitar 2 humanos
         atendendo o mesmo lead).
      2. Valida que claimed_by_user_id é o user atual (anti-hijack).
      3. Persiste msg em sofia_messages (role='assistant' +
         metadata.actor='human' + operator_user_id).
      4. Publica em sofia:outbound stream → delivery-worker manda via
         Evolution.
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"status": "error", "reason": "text_required"}), 400
    if len(text) > 4000:
        return jsonify({"status": "error", "reason": "text_too_long"}), 400

    user_id = (getattr(g, "user", {}) or {}).get("sub")
    if not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    db = get_postgres()
    handoff = db.fetch_one(
        """SELECT id, phone, tenant_id, status, claimed_by_user_id, trace_id
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not handoff:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    if handoff["status"] != "claimed":
        return jsonify({
            "status": "error", "reason": "handoff_not_claimed",
            "current_status": handoff["status"],
        }), 409
    if str(handoff.get("claimed_by_user_id") or "") != str(user_id):
        return jsonify({
            "status": "error", "reason": "not_claim_owner",
        }), 403

    # Persiste msg como assistant com actor=human
    session = db.fetch_one(
        """SELECT id FROM aia_health_sofia_sessions
           WHERE phone = %s
             AND tenant_id = %s
           ORDER BY started_at DESC LIMIT 1""",
        (handoff["phone"], handoff["tenant_id"]),
    )
    session_id = session["id"] if session else None

    metadata = {
        "actor": "human",
        "operator_user_id": str(user_id),
        "handoff_id": str(handoff_id),
    }
    if session_id:
        try:
            db.execute(
                """INSERT INTO aia_health_sofia_messages
                       (session_id, tenant_id, role, content, metadata)
                   VALUES (%s, %s, 'assistant', %s, %s::jsonb)""",
                (session_id, handoff["tenant_id"], text, json.dumps(metadata)),
            )
        except Exception as exc:
            logger.warning(
                "handoff_send_persist_failed",
                handoff_id=handoff_id, error=str(exc)[:200],
            )

    # Publica no outbound pra Evolution mandar
    try:
        get_event_bus().publish(Streams.OUTBOUND, {
            "tenant_id": handoff["tenant_id"],
            "trace_id": str(handoff.get("trace_id") or ""),
            "phone": handoff["phone"],
            "message_type": "text",
            "text": text,
            "metadata": {
                "reason": "human_handoff_reply",
                "handoff_id": str(handoff_id),
                "operator_user_id": str(user_id),
            },
        })
    except Exception as exc:
        logger.exception(
            "handoff_send_publish_failed",
            handoff_id=handoff_id, error=str(exc)[:200],
        )
        return jsonify({"status": "error", "reason": "publish_failed"}), 500

    write_audit(
        action="handoff_message_sent",
        actor=str(user_id),
        resource_type="handoff",
        resource_id=handoff_id,
        payload={"chars": len(text)},
    )
    return jsonify({"status": "ok"})


def _load_mutable_message(handoff_id: str, msg_id: str, user_id: str):
    """Carrega msg + handoff e valida permissão pra editar/deletar.

    Retorna (handoff, msg, metadata, error_response). Se error_response não
    é None, abortar com ele (já é (json, status)).

    Validações (em ordem, parar no primeiro fail):
        1. Handoff existe e está claimed pelo user atual
        2. Msg existe + pertence ao mesmo phone do handoff
        3. Msg.role == 'assistant' AND metadata.actor == 'human'
        4. metadata.operator_user_id == user_id (anti-hijack entre operadores)
        5. Msg não foi deletada antes
        6. Created_at dentro da janela de mutação (5min)
    """
    db = get_postgres()
    handoff = db.fetch_one(
        """SELECT id, phone, tenant_id, status, claimed_by_user_id
           FROM aia_health_human_handoff_queue WHERE id = %s""",
        (handoff_id,),
    )
    if not handoff:
        return None, None, None, (jsonify({
            "status": "error", "reason": "handoff_not_found",
        }), 404)
    if handoff["status"] != "claimed":
        return None, None, None, (jsonify({
            "status": "error", "reason": "handoff_not_claimed",
            "current_status": handoff["status"],
        }), 409)
    if str(handoff.get("claimed_by_user_id") or "") != str(user_id):
        return None, None, None, (jsonify({
            "status": "error", "reason": "not_claim_owner",
        }), 403)

    msg = db.fetch_one(
        """SELECT m.id, m.role, m.content, m.metadata, m.created_at,
                  m.session_id, s.phone AS session_phone
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE m.id = %s""",
        (msg_id,),
    )
    if not msg:
        return None, None, None, (jsonify({
            "status": "error", "reason": "message_not_found",
        }), 404)
    if msg["session_phone"] != handoff["phone"]:
        return None, None, None, (jsonify({
            "status": "error", "reason": "message_not_in_handoff",
        }), 404)

    md = msg.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except Exception:
            md = {}
    if not isinstance(md, dict):
        md = {}

    if msg["role"] != "assistant" or md.get("actor") != "human":
        return None, None, None, (jsonify({
            "status": "error", "reason": "only_human_messages_mutable",
        }), 403)

    if str(md.get("operator_user_id") or "") != str(user_id):
        return None, None, None, (jsonify({
            "status": "error", "reason": "not_message_owner",
        }), 403)

    if md.get("deleted") is True:
        return None, None, None, (jsonify({
            "status": "error", "reason": "message_already_deleted",
        }), 409)

    # Janela de mutação: created_at deve estar a < N segundos atrás.
    # Comparação em SQL (timezone-safe) pra evitar drift entre app/db.
    db2 = get_postgres()
    in_window = db2.fetch_one(
        """SELECT (created_at > NOW() - (%s || ' seconds')::interval) AS ok
           FROM aia_health_sofia_messages WHERE id = %s""",
        (str(MESSAGE_MUTATION_WINDOW_SECONDS), msg_id),
    )
    if not in_window or not in_window.get("ok"):
        return None, None, None, (jsonify({
            "status": "error", "reason": "edit_window_expired",
            "window_seconds": MESSAGE_MUTATION_WINDOW_SECONDS,
        }), 409)

    return handoff, msg, md, None


@bp.patch("/api/admin/handoff/<handoff_id>/messages/<msg_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def handoff_message_edit(handoff_id: str, msg_id: str):
    """Edita conteúdo de uma msg do operador.

    Mantém histórico completo em metadata.edit_history[] pra audit.
    Janela de mutação 5min — depois msg vira imutável.
    """
    body = request.get_json(silent=True) or {}
    new_content = (body.get("content") or "").strip()
    if not new_content:
        return jsonify({"status": "error", "reason": "content_required"}), 400
    if len(new_content) > 4000:
        return jsonify({"status": "error", "reason": "content_too_long"}), 400

    user_id = (getattr(g, "user", {}) or {}).get("sub")
    if not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    handoff, msg, md, err = _load_mutable_message(handoff_id, msg_id, user_id)
    if err:
        return err

    if msg["content"] == new_content:
        # No-op — evita poluir audit chain
        return jsonify({"status": "ok", "noop": True})

    # Append no histórico, preserva original e timestamps
    history = list(md.get("edit_history") or [])
    history.append({
        "previous_content": msg["content"],
        "edited_at_db": None,  # preenchido via NOW() abaixo
        "edited_by": str(user_id),
    })
    new_md = {
        **md,
        "edit_history": history,
        "last_edited_by": str(user_id),
    }

    db = get_postgres()
    updated = db.fetch_one(
        """UPDATE aia_health_sofia_messages
              SET content = %s,
                  metadata = jsonb_set(
                      %s::jsonb,
                      '{edited_at}',
                      to_jsonb(NOW()::text)
                  )
            WHERE id = %s
            RETURNING id, content, metadata, created_at""",
        (new_content, json.dumps(new_md), msg_id),
    )

    write_audit(
        action="handoff_message_edited",
        actor=str(user_id),
        tenant_id=handoff["tenant_id"],
        resource_type="sofia_message",
        resource_id=str(msg_id),
        payload={
            "handoff_id": str(handoff_id),
            "old_chars": len(msg["content"] or ""),
            "new_chars": len(new_content),
            "edit_count": len(history),
        },
    )
    logger.info(
        "handoff_message_edited",
        handoff_id=str(handoff_id), msg_id=str(msg_id),
        operator=str(user_id), edit_count=len(history),
    )
    return jsonify({"status": "ok", "message_id": int(updated["id"])})


@bp.delete("/api/admin/handoff/<handoff_id>/messages/<msg_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def handoff_message_delete(handoff_id: str, msg_id: str):
    """Soft delete: marca metadata.deleted=true mas preserva content.

    UI mostra '[mensagem apagada]' mas auditor consegue ver o original
    via metadata.previous_content_at_delete.
    """
    user_id = (getattr(g, "user", {}) or {}).get("sub")
    if not user_id:
        return jsonify({"status": "error", "reason": "no_user"}), 401

    handoff, msg, md, err = _load_mutable_message(handoff_id, msg_id, user_id)
    if err:
        return err

    new_md = {
        **md,
        "deleted": True,
        "deleted_by": str(user_id),
        "previous_content_at_delete": msg["content"],
    }
    db = get_postgres()
    db.execute(
        """UPDATE aia_health_sofia_messages
              SET metadata = jsonb_set(
                      %s::jsonb,
                      '{deleted_at}',
                      to_jsonb(NOW()::text)
                  )
            WHERE id = %s""",
        (json.dumps(new_md), msg_id),
    )

    write_audit(
        action="handoff_message_deleted",
        actor=str(user_id),
        tenant_id=handoff["tenant_id"],
        resource_type="sofia_message",
        resource_id=str(msg_id),
        payload={
            "handoff_id": str(handoff_id),
            "deleted_chars": len(msg["content"] or ""),
        },
    )
    logger.info(
        "handoff_message_deleted",
        handoff_id=str(handoff_id), msg_id=str(msg_id),
        operator=str(user_id),
    )
    return jsonify({"status": "ok"})


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
