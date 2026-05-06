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


# ──────────── Drug safety review (chamado por voice-call-service) ────────────

@bp.post("/api/internal/drug-safety/review")
def internal_drug_safety_review():
    """Endpoint interno (sem JWT) chamado por voice-call-service quando
    Sofia voz/voip detecta menção a medicação e precisa rodar o
    pipeline farmacológico canônico (mesmo wrapper que CareSofiaAgent
    no WhatsApp usa).

    Phase C v2.x — unificação canal:
    Garante que TODOS os canais (WhatsApp/Voice/VoIP) consultam o
    MESMO knowledge graph (142 drugs, 93 interações, dose limits, ACB,
    fall risk, renal/hepatic, cascatas) via DrugSafetyService. Sem isso,
    voice/voip rodavam tools próprias com lógica antiga e drift de
    regras clínicas era inevitável.

    Auth: header X-Internal-Key opcional (mesmo padrão de outros
    endpoints internos via SOFIA_INTERNAL_KEY env). Se key configurada
    e header não bate, retorna 401.

    Body:
        {
            "prescriptions": [
                {"medication_name": "...", "dose": "...",
                 "times_of_day": [...], "route": "oral"}
            ],
            "patient_id": "uuid" (opcional, mas necessário pra cascade
                                  detection + idade pra Beers),
            "tenant_id": "..." (opcional, usado pra filtrar patient
                                load por tenant)
        }

    Response: {"status": "ok", "review": {...}} idêntico ao output
        de DrugSafetyService.safety_review_prescriptions.
    """
    import os
    expected_key = os.getenv("SOFIA_INTERNAL_KEY", "")
    if expected_key:
        provided = request.headers.get("X-Internal-Key", "")
        if provided != expected_key:
            return jsonify({
                "status": "error", "reason": "unauthorized",
            }), 401

    body = request.get_json(silent=True) or {}
    prescriptions = body.get("prescriptions") or []
    patient_id = body.get("patient_id")
    tenant_id = body.get("tenant_id")
    trace_id = body.get("trace_id")

    if not isinstance(prescriptions, list) or not prescriptions:
        return jsonify({
            "status": "error", "reason": "prescriptions_required_list",
        }), 400

    try:
        from src.services.drug_safety_context import (
            load_patient_safety_context,
        )
        from src.services.drug_safety_service import get_drug_safety_service

        patient_ctx = load_patient_safety_context(patient_id, tenant_id)
        svc = get_drug_safety_service()
        review = svc.safety_review_prescriptions(
            prescriptions=prescriptions, patient=patient_ctx,
        )

        # Audit pra observabilidade unificada (mesmo action que
        # sofia_tools.safety_review_prescriptions emite)
        try:
            audit_log(
                action="drug_safety_reviewed",
                actor="voice_call_service",
                tenant_id=tenant_id,
                trace_id=trace_id,
                resource_type="patient",
                resource_id=patient_id,
                payload={
                    "prescriptions_count": len(prescriptions),
                    "max_severity": review.get("max_severity"),
                    "requires_human_review": review.get("requires_human_review"),
                    "cascades_detected": len(review.get("cascades") or []),
                    "principles": [
                        r.get("principle_active") for r in review.get("results", [])
                    ],
                    "channel": "voice",
                },
            )
        except Exception:
            pass  # audit é best-effort

        return jsonify({"status": "ok", "review": review}), 200
    except Exception as exc:
        logger.exception("internal_drug_safety_review_failed")
        return jsonify({"status": "error", "reason": str(exc)[:200]}), 500


# ──────────── Conversation persist (chamado por voice-call-service) ────────────

@bp.post("/api/internal/conversation/persist-message")
def internal_conversation_persist_message():
    """Endpoint interno (sem JWT) chamado por voice-call-service e
    sofia-service voice_app pra persistir turnos em
    aia_health_conversation_messages — mesma tabela que CareSofiaAgent
    no WhatsApp escreve.

    Phase C v2.x — unificação canal Fase 2:
    UNIFICA persistência conversational entre WhatsApp/Voz/VoIP. Antes
    voice gravava só em aia_health_sofia_messages + active_context;
    WhatsApp gravava em aia_health_conversation_messages. Painel
    operador via histórico parcial. Agora todos canais escrevem na
    mesma tabela, channel='voice|voip|whatsapp|web' diferencia.

    Auth: header X-Internal-Key opcional (mesmo padrão).

    Body:
        {
            "tenant_id": "...",
            "phone": "5551...",
            "role": "user" | "assistant" | "system" | "tool",
            "direction": "inbound" | "outbound",
            "content": "...",
            "channel": "voice" | "voip" | "whatsapp" | "web" (default whatsapp),
            "message_format": "text" | "audio" | "image" (default text),
            "external_id": "trace_id ou msg_id externo" (opcional),
            "session_id": "uuid sofia/voice session" (opcional),
            "session_context": "discriminator livre" (opcional),
            "subject_id": "uuid caregiver/patient/user" (opcional),
            "subject_type": "caregiver|patient|user|family|anonymous" (opcional),
            "processing_agent": "care|commercial|grok_voice" (opcional),
            "processing_duration_ms": int (opcional),
            "metadata": {} (opcional),
            "safety_moderated": bool (default false)
        }

    Response: {"status": "ok", "message_id": "uuid"} ou
              {"status": "error", "reason": "..."}
    """
    import os
    expected_key = os.getenv("SOFIA_INTERNAL_KEY", "")
    if expected_key:
        provided = request.headers.get("X-Internal-Key", "")
        if provided != expected_key:
            return jsonify({
                "status": "error", "reason": "unauthorized",
            }), 401

    body = request.get_json(silent=True) or {}
    required = ("tenant_id", "phone", "role", "direction", "content")
    missing = [k for k in required if not body.get(k)]
    if missing:
        return jsonify({
            "status": "error", "reason": "missing_fields", "fields": missing,
        }), 400

    try:
        from src.services.conversation_persistence import persist_message
        msg_id = persist_message(
            tenant_id=body["tenant_id"],
            phone=body["phone"],
            role=body["role"],
            direction=body["direction"],
            content=body["content"],
            channel=body.get("channel") or "whatsapp",
            message_format=body.get("message_format") or "text",
            external_id=body.get("external_id"),
            session_id=body.get("session_id"),
            session_context=body.get("session_context"),
            subject_id=body.get("subject_id"),
            subject_type=body.get("subject_type"),
            processing_agent=body.get("processing_agent"),
            processing_duration_ms=body.get("processing_duration_ms"),
            metadata=body.get("metadata"),
            safety_moderated=bool(body.get("safety_moderated", False)),
            reply_to_id=body.get("reply_to_id"),
        )
        if msg_id is None:
            return jsonify({
                "status": "error", "reason": "persist_failed",
            }), 500
        return jsonify({
            "status": "ok", "message_id": msg_id,
        }), 200
    except Exception as exc:
        logger.exception("internal_conversation_persist_failed")
        return jsonify({
            "status": "error", "reason": str(exc)[:200],
        }), 500


# ──────────── Identity resolve (chamado por voice-call-service) ────────────

@bp.post("/api/internal/identity/resolve")
def internal_identity_resolve():
    """Endpoint interno (sem JWT) chamado por voice-call-service /
    sofia-service quando ligação SIP/Voz Web chega — resolve quem
    está ligando.

    Phase C v2.x — unificação canal Fase 3:
    Substitui voice-call-service/caller_resolver.py próprio. Backend
    tem identity_resolver com 5 lookups (users, caregivers,
    patients.proactive_call_phone, patients.responsible, phone_history)
    + cache Redis. Voice/sofia ganha mesma robustez e mesma resolução
    que CareSofiaAgent no WhatsApp usa.

    Auth: header X-Internal-Key opcional.

    Body:
        {
            "phone": "5551...",
            "tenant_id": "connectaiacare_demo" (opcional)
        }

    Response (formato voice-style pra compatibilidade com
    caller_resolver.resolve_caller existente — drop-in replacement):
        {
            "status": "ok",
            "patient_id": "uuid"|None,
            "caregiver_id": "uuid"|None,
            "user_id": "uuid"|None,
            "full_name": "...",
            "persona": "cuidador_pro|paciente_b2c|familia|medico|enfermeiro|anonymous",
            "phone_type": "personal|shared|unknown",
            "extra_context": {patient: dict|None, ...},
            "tenant_id": "..." (do match primary)
        }
    """
    import os
    expected_key = os.getenv("SOFIA_INTERNAL_KEY", "")
    if expected_key:
        provided = request.headers.get("X-Internal-Key", "")
        if provided != expected_key:
            return jsonify({
                "status": "error", "reason": "unauthorized",
            }), 401

    body = request.get_json(silent=True) or {}
    phone = body.get("phone")
    tenant_id = body.get("tenant_id")

    if not phone:
        return jsonify({
            "status": "error", "reason": "phone_required",
        }), 400

    try:
        from src.services.identity_resolver import get_identity_resolver
        identity = get_identity_resolver().resolve(phone, tenant_id=tenant_id)

        # Mapeia identity (objeto Identity com matches[]) pro formato
        # legacy voice-style (1 caller único — usa primary).
        primary = identity.primary
        if not primary:
            return jsonify({
                "status": "ok",
                "patient_id": None,
                "caregiver_id": None,
                "user_id": None,
                "full_name": "",
                "persona": "anonymous",
                "phone_type": "unknown",
                "extra_context": {},
                "tenant_id": tenant_id,
            }), 200

        # Persona derivada do profile do primary match
        persona = primary.profile or "anonymous"
        # Compatibilidade com caller_resolver: 'cuidador' → 'cuidador_pro'
        # caller_resolver historicamente sempre usou 'cuidador_pro'
        if persona == "cuidador":
            persona = "cuidador_pro"

        return jsonify({
            "status": "ok",
            "patient_id": primary.patient_id,
            "caregiver_id": primary.caregiver_id,
            "user_id": primary.user_id,
            "full_name": primary.full_name or "",
            "persona": persona,
            "phone_type": primary.extra.get("phone_type", "unknown") if primary.extra else "unknown",
            "extra_context": primary.extra or {},
            "tenant_id": primary.tenant_id,
            "confidence": primary.confidence,
            "matches_count": len(identity.matches),
        }), 200
    except Exception as exc:
        logger.exception("internal_identity_resolve_failed")
        return jsonify({
            "status": "error", "reason": str(exc)[:200],
        }), 500


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

# ──────────── Patient Risk Scoring ────────────

@bp.get("/api/safety/risk-score/<patient_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro", "cuidador_pro", "familia")
def get_risk_score(patient_id: str):
    row = get_postgres().fetch_one(
        "SELECT * FROM aia_health_patient_risk_score WHERE patient_id = %s",
        (patient_id,),
    )
    if not row:
        return jsonify({"status": "ok", "score": None, "message": "not_computed_yet"})
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return jsonify({"status": "ok", **out})


@bp.post("/api/safety/risk-score/<patient_id>/compute")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def compute_risk_score(patient_id: str):
    from src.services import risk_scoring
    result = risk_scoring.compute_for_patient(patient_id)
    return jsonify({"status": "ok", **result})


@bp.get("/api/safety/risk-score/high")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_high_risk():
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    from src.services import risk_scoring
    items = risk_scoring.list_high_risk(tenant_id, limit=int(request.args.get("limit", 20)))
    out = []
    for r in items:
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return jsonify({"status": "ok", "count": len(out), "items": out})


@bp.post("/api/safety/risk-score/recompute-all")
@require_role("super_admin")
def recompute_all_risk():
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    from src.services import risk_scoring
    result = risk_scoring.compute_for_all_active(tenant_id)
    return jsonify({"status": "ok", **result})


# ──────────── Baseline individual (Fase 2) ────────────

@bp.get("/api/safety/risk-score/<patient_id>/baseline")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def get_patient_baseline(patient_id: str):
    """Retorna o baseline individual do paciente (median + MAD por sinal,
    histórico semanal, flag has_sufficient_data)."""
    from src.services import risk_baseline
    base = risk_baseline.get_baseline(patient_id)
    if not base:
        return jsonify({
            "status": "ok", "has_baseline": False,
            "message": "not_computed_yet",
        })
    return jsonify({"status": "ok", "has_baseline": True, "baseline": base})


@bp.post("/api/safety/risk-score/<patient_id>/baseline/compute")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def compute_patient_baseline(patient_id: str):
    """Recomputa baseline desse paciente. Janela default 60d.

    Body opcional: { "period_days": 60 }
    """
    body = request.get_json(silent=True) or {}
    from src.services import risk_baseline
    result = risk_baseline.compute_baseline(
        patient_id,
        period_days=int(body.get("period_days") or risk_baseline.DEFAULT_PERIOD_DAYS),
    )
    return jsonify({"status": "ok", **result})


@bp.post("/api/safety/risk-score/baseline/recompute-all")
@require_role("super_admin")
def recompute_all_baselines():
    """Recomputa baseline de todos os pacientes ativos do tenant."""
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    from src.services import risk_baseline
    result = risk_baseline.compute_baseline_for_all_active(tenant_id)
    return jsonify({"status": "ok", **result})


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
