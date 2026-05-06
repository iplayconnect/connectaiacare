"""Tools que sub-agents da Super Sofia podem chamar.

Phase C v1: 3 tools focadas em fluxo de lead anônimo.
    - capture_lead              → cria/atualiza aia_health_leads
    - schedule_demo             → gera link ConnectaLive (placeholder
                                   até Phase C decidir port)
    - escalate_to_human_whatsapp → cria entry em handoff_queue +
                                   notifica Central 24h via Evolution

Cada tool:
    - Schema input via dataclass + validação
    - Idempotency key (mesma tool com mesmos args = 1 efeito)
    - Audit log
    - Returns dict serializável

Tool registry (`get_tool_registry()`) permite executar por nome.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from src.services.audit_log_writer import write_audit
from src.services.event_bus import Streams, get_event_bus
from src.services.idempotency import is_first_occurrence, hash_payload
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────

CENTRAL_24H_PHONE = "5551997354484"

# Placeholder link ConnectaLive (Phase C decide se porta módulo
# da ConnectaIA ou usa link genérico)
CONNECTALIVE_DEMO_LINK_DEFAULT = (
    "https://connectaiacare.com.br/agendar-demo"
)


# ──────────────────────────────────────────────────────────────────
# Tool result
# ──────────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    ok: bool
    data: dict
    error: Optional[str] = None
    idempotent_skip: bool = False  # tool foi chamada mas já tinha sido executada


# ──────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────


def capture_lead(
    *,
    phone: str,
    intent: str,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    organization: Optional[str] = None,
    role_self_declared: Optional[str] = None,
    confidence: Optional[float] = None,
    source_channel: str = "whatsapp",
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Cria/atualiza lead em aia_health_leads.

    Idempotência: phone + intent + dia → mesmo lead row updated.
    Não cria duplicado quando Sofia chama 2x no mesmo turno.
    """
    if not phone:
        return ToolResult(ok=False, data={}, error="phone_required")

    idem_key = f"{phone}:{intent}:lead"
    if not is_first_occurrence("capture_lead", idem_key, ttl_seconds=3600):
        # Não bloqueia — só skipa criar duplicado. Atualiza row existente.
        logger.info(
            "capture_lead_idempotent_skip",
            phone=phone, trace_id=trace_id,
        )

    db = get_postgres()
    try:
        # Tenta encontrar lead recente (últimos 7 dias) com mesmo phone
        existing = db.fetch_one(
            """SELECT id, status, notes FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '7 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        new_note = {"at": "now()", "text": notes} if notes else None

        if existing:
            # Update fields se vieram preenchidos
            updates = []
            params: list = []
            for col, val in [
                ("full_name", full_name),
                ("email", email),
                ("organization", organization),
                ("role_self_declared", role_self_declared),
            ]:
                if val:
                    updates.append(f"{col} = %s")
                    params.append(val)
            if confidence is not None:
                updates.append("confidence = %s")
                params.append(float(confidence))
            updates.append("intent = %s")
            params.append(intent)
            updates.append("last_contact_at = NOW()")
            if new_note:
                updates.append(
                    "notes = COALESCE(notes, '[]'::jsonb) || jsonb_build_array("
                    "jsonb_build_object('at', NOW()::text, 'text', %s::text))"
                )
                params.append(new_note["text"])
            params.append(existing["id"])
            db.execute(
                f"UPDATE aia_health_leads SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            lead_id = str(existing["id"])
            action = "updated"
        else:
            row = db.insert_returning(
                """INSERT INTO aia_health_leads (
                    phone, full_name, email, organization, role_self_declared,
                    intent, confidence, source_channel, source_metadata,
                    notes, last_contact_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                RETURNING id""",
                (
                    phone, full_name, email, organization, role_self_declared,
                    intent,
                    float(confidence) if confidence is not None else None,
                    source_channel,
                    json.dumps({"trace_id": trace_id} if trace_id else {}),
                    json.dumps(
                        [{"at": "now()", "text": notes}] if notes else []
                    ),
                ),
            )
            lead_id = str(row["id"]) if row else "?"
            action = "created"

        write_audit(
            action=f"lead_{action}",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            resource_type="lead",
            resource_id=lead_id,
            payload={
                "intent": intent,
                "has_name": bool(full_name),
                "has_email": bool(email),
                "has_org": bool(organization),
            },
        )
        return ToolResult(ok=True, data={"lead_id": lead_id, "action": action})
    except Exception as exc:
        logger.exception("capture_lead_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def schedule_demo(
    *,
    phone: str,
    full_name: Optional[str] = None,
    organization: Optional[str] = None,
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Gera link de agendamento de demo via ConnectaLive (placeholder
    Phase C v1 — link genérico). Atualiza lead pra demo_scheduled.

    Phase C v2: integração real com módulo ConnectaLive (cria sala
    com hora marcada, sends invite Google Calendar, etc.).
    """
    if not phone:
        return ToolResult(ok=False, data={}, error="phone_required")

    idem_key = f"{phone}:schedule_demo"
    if not is_first_occurrence("schedule_demo", idem_key, ttl_seconds=86400):
        logger.info("schedule_demo_idempotent_skip", phone=phone)

    demo_link = CONNECTALIVE_DEMO_LINK_DEFAULT
    db = get_postgres()
    try:
        # Atualiza lead se existir
        existing = db.fetch_one(
            """SELECT id FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '7 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if existing:
            db.execute(
                """UPDATE aia_health_leads
                      SET status = 'demo_scheduled',
                          demo_scheduled_at = NOW(),
                          demo_link = %s,
                          updated_at = NOW()
                    WHERE id = %s""",
                (demo_link, existing["id"]),
            )
            lead_id = str(existing["id"])
        else:
            # Cria lead minimal
            row = db.insert_returning(
                """INSERT INTO aia_health_leads (
                    phone, full_name, organization, intent,
                    source_channel, status, demo_scheduled_at, demo_link,
                    last_contact_at
                ) VALUES (%s, %s, %s, %s, 'whatsapp', 'demo_scheduled', NOW(), %s, NOW())
                RETURNING id""",
                (phone, full_name, organization, "agendar_demo", demo_link),
            )
            lead_id = str(row["id"]) if row else "?"

        write_audit(
            action="demo_scheduled",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            resource_type="lead",
            resource_id=lead_id,
            payload={"demo_link": demo_link},
        )
        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "demo_link": demo_link,
            "message_for_sofia": (
                f"Demo agendada via ConnectaLive. Link: {demo_link}. "
                "Avise o user do link e que o time comercial entrará "
                "em contato em até 24h pra confirmar horário."
            ),
        })
    except Exception as exc:
        logger.exception("schedule_demo_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def escalate_to_human_whatsapp(
    *,
    phone: str,
    reason: str,
    summary: str,
    urgency: str = "P3",
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_log: Optional[list] = None,
) -> ToolResult:
    """Cria entry em aia_health_human_handoff_queue + dispara Sofia
    notifica Central 24h via Evolution.

    O envio pra Central é assíncrono via sofia:outbound stream
    (delivery-worker pega).

    Idempotência: 1 handoff por phone por hora (anti-loop).
    """
    if not phone or not reason or not summary:
        return ToolResult(ok=False, data={}, error="missing_required_fields")

    # Phone normalization (bug fix 2026-05-03): WhatsApp pode mandar
    # com/sem o "9" do celular, e idempotency baseada em phone bruto
    # criava handoffs duplicados pra mesmo lead em formatos diferentes.
    # Usa forma canônica E.164 BR (13 dígitos com 9 quando móvel).
    from src.services.identity_resolver import normalize_phone_e164_br
    canonical_phone = normalize_phone_e164_br(phone) or phone

    idem_key = f"{canonical_phone}:handoff"
    if not is_first_occurrence("escalate_to_human", idem_key, ttl_seconds=3600):
        logger.info("escalate_idempotent_skip", phone=canonical_phone, trace_id=trace_id)
        return ToolResult(
            ok=True, data={},
            idempotent_skip=True,
            error="already_escalated_in_last_hour",
        )

    valid_urgency = urgency if urgency in ("P1", "P2", "P3") else "P3"
    sla_seconds = {"P1": 300, "P2": 1800, "P3": 7200}[valid_urgency]

    db = get_postgres()
    try:
        # Persiste com phone canônico pra evitar duplicação cross-format
        # (ex: "555194267222" e "5551994267222" eram tratados como leads
        # diferentes — agora ambos viram "5551994267222").
        phone = canonical_phone
        row = db.insert_returning(
            """INSERT INTO aia_health_human_handoff_queue (
                trace_id, phone, tenant_id, channel, reason,
                context_summary, conversation_log,
                triggered_by, priority, status, sla_target_seconds
            ) VALUES (%s, %s, %s, 'whatsapp', %s, %s, %s::jsonb, 'sofia', %s, 'pending', %s)
            RETURNING id""",
            (
                trace_id, phone, tenant_id, reason, summary,
                json.dumps(conversation_log or []),
                valid_urgency, sla_seconds,
            ),
        )
        handoff_id = str(row["id"]) if row else "?"

        # Dispara mensagem pra Central via outbound stream
        try:
            central_text = (
                f"[HANDOFF · {valid_urgency}]\n\n"
                f"Phone do user: {phone}\n"
                f"Motivo: {reason}\n"
                f"Tenant: {tenant_id or 'central (lead anônimo)'}\n"
                f"Trace: {trace_id}\n\n"
                f"Resumo da conversa:\n{summary[:1000]}\n\n"
                f"Reivindique em /admin/system/operations/handoff "
                f"(handoff_id={handoff_id}).\n\n"
                "— Sofia · ConnectaIACare"
            )
            get_event_bus().publish(Streams.OUTBOUND, {
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "phone": CENTRAL_24H_PHONE,
                "message_type": "text",
                "text": central_text,
                "metadata": {"reason": "central_24h_handoff_notify", "handoff_id": handoff_id},
            })
            db.execute(
                "UPDATE aia_health_human_handoff_queue "
                "SET notified_central_at = NOW() WHERE id = %s",
                (handoff_id,),
            )
        except Exception as exc:
            logger.warning(
                "central_notify_publish_failed",
                handoff_id=handoff_id, error=str(exc)[:200],
            )

        write_audit(
            action="handoff_initiated",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            session_id=session_id,
            resource_type="handoff",
            resource_id=handoff_id,
            payload={
                "reason": reason,
                "urgency": valid_urgency,
                "sla_seconds": sla_seconds,
            },
        )
        return ToolResult(ok=True, data={
            "handoff_id": handoff_id,
            "urgency": valid_urgency,
            "sla_target_seconds": sla_seconds,
            "central_notified_via_stream": True,
        })
    except Exception as exc:
        logger.exception("escalate_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


# ──────────────────────────────────────────────────────────────────
# Care tools (Phase C v2 PR 2) — pharmacovigilância + report clínico
#
# Wrappers finos sobre serviços canônicos. Não duplicam regras —
# delegam pra dose_validator/cascade_detector via DrugSafetyService.
# ──────────────────────────────────────────────────────────────────


def safety_review_prescriptions(
    *,
    prescriptions: list,
    patient_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Avalia uma ou mais prescrições contra o knowledge graph
    farmacológico (142 drugs, 93 interações, 151 dose limits, 51 ACB,
    38 fall risk, 45 renal, 166 hepatic, 10 cascatas).

    Pipeline interno (DrugSafetyService):
        - dose_validator.validate() — 11 checks integrados pra cada med
        - cascade_detector.detect_cascades() — dimensão 13 (cascatas
          de prescrição)

    Idempotência: NÃO aplica — review é puramente consultiva, sem efeito
    colateral em DB. Pode ser chamada N vezes por turno.

    Args:
        prescriptions: lista de dicts {medication_name, dose, times_of_day}.
        patient_id: UUID do paciente (necessário pra cascade detection).
        tenant_id: scope multi-tenant.

    Returns:
        ToolResult.data com:
          results[]: ValidationResult.to_dict pra cada prescription
          cascades[]: cascatas detectadas (vazio se sem patient_id)
          max_severity: 'block' | 'warning_strong' | 'warning' | 'info' | None
          requires_human_review: bool — se True, agent DEVE alertar +
            escalar pra Henrique/médico
          meta: contagens
    """
    if not prescriptions or not isinstance(prescriptions, list):
        return ToolResult(
            ok=False, data={}, error="prescriptions_required_list",
        )

    try:
        from src.services.drug_safety_context import load_patient_safety_context
        from src.services.drug_safety_service import get_drug_safety_service

        # Patient ctx via helper compartilhado (mesmo usado pelo
        # endpoint HTTP /api/internal/drug-safety/review chamado pelo
        # voice-call-service). UMA fonte de verdade pro patient_ctx
        # cross-canal — qualquer mudança no schema clínico reflete
        # nos 3 canais (WhatsApp/Voice/VoIP) automaticamente.
        patient_ctx = load_patient_safety_context(patient_id, tenant_id)

        svc = get_drug_safety_service()
        review = svc.safety_review_prescriptions(
            prescriptions=prescriptions, patient=patient_ctx,
        )

        write_audit(
            action="drug_safety_reviewed",
            actor="sofia",
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
            },
        )
        return ToolResult(ok=True, data=review)
    except Exception as exc:
        logger.exception(
            "safety_review_failed",
            trace_id=trace_id, error=str(exc)[:200],
        )
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def register_caregiver_report(
    *,
    caregiver_id: str,
    caregiver_phone: str,
    patient_id: str,
    report_type: str,
    summary: str,
    details: Optional[dict] = None,
    severity: str = "info",
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Registra report do cuidador em aia_health_reports.

    Schema atual é orientado a relatos de áudio (transcription/analysis)
    mas aceita texto também. Pra report textual sem áudio:
        - transcription = summary (texto enviado pelo cuidador)
        - extracted_entities = details (dados estruturados extraídos)
        - classification = report_type
        - needs_medical_attention = severity in ('attention','urgent')
        - metadata armazena severity + report_type pra retrieval rápido

    Tipos comuns: 'rotina_diaria', 'mudanca_comportamento', 'queda',
    'sinal_vital', 'recusa_medicacao', 'agitacao', 'medicacao_administrada',
    'outro'.

    Severity: 'info' | 'attention' | 'urgent'. `urgent` força
    needs_medical_attention=TRUE pra alertar equipe clínica.

    Idempotência: 1 report do mesmo caregiver+patient+type por hora
    (anti-spam — cuidador mandar 5x "tudo bem" não cria 5 reports).
    """
    if not all([caregiver_id, caregiver_phone, patient_id, report_type, summary]):
        return ToolResult(
            ok=False, data={}, error="missing_required_fields",
        )
    if severity not in ("info", "attention", "urgent"):
        severity = "info"

    idem_key = f"{caregiver_id}:{patient_id}:{report_type}"
    if not is_first_occurrence("caregiver_report", idem_key, ttl_seconds=3600):
        logger.info(
            "caregiver_report_idempotent_skip",
            caregiver_id=caregiver_id,
            patient_id=patient_id,
            report_type=report_type,
            trace_id=trace_id,
        )
        return ToolResult(
            ok=True, data={}, idempotent_skip=True,
            error="similar_report_in_last_hour",
        )

    needs_attention = severity in ("attention", "urgent")
    # `classification` no schema = criticalidade clínica (CHECK:
    # routine|attention|urgent|critical), NÃO é tipo de relato.
    # Map severity → classification:
    #   severity=info     → classification='routine'
    #   severity=attention→ classification='attention'
    #   severity=urgent   → classification='urgent'
    classification = (
        "routine" if severity == "info"
        else severity  # 'attention' ou 'urgent' batem direto
    )
    # report_type vai pra metadata (audit) e extracted_entities
    # (painel mostra)
    metadata_blob = {
        "report_type": report_type,
        "severity": severity,
        "source_channel": "whatsapp",
        "trace_id": trace_id,
    }
    extracted_blob = dict(details or {})
    extracted_blob.setdefault("report_type", report_type)

    db = get_postgres()
    try:
        row = db.insert_returning(
            """INSERT INTO aia_health_reports (
                tenant_id, caregiver_id, caregiver_phone, patient_id,
                transcription, classification, extracted_entities,
                needs_medical_attention, status,
                metadata, received_at, reporter_person_type
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb,
                      %s, 'received',
                      %s::jsonb, NOW(), 'caregiver')
            RETURNING id::text AS id""",
            (
                tenant_id, caregiver_id, caregiver_phone, patient_id,
                summary[:5000], classification,
                json.dumps(extracted_blob),
                needs_attention,
                json.dumps(metadata_blob),
            ),
        )
        report_id = (row or {}).get("id")
        write_audit(
            action="caregiver_report_registered",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            resource_type="report",
            resource_id=report_id,
            payload={
                "caregiver_id": caregiver_id,
                "patient_id": patient_id,
                "type": report_type,
                "severity": severity,
                "needs_medical_attention": needs_attention,
            },
        )
        return ToolResult(ok=True, data={
            "report_id": report_id,
            "severity": severity,
            "needs_medical_attention": needs_attention,
        })
    except Exception as exc:
        logger.exception(
            "caregiver_report_failed",
            caregiver_id=caregiver_id, patient_id=patient_id,
            trace_id=trace_id, error=str(exc)[:200],
        )
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def escalate_to_human_clinical(
    *,
    phone: str,
    reason: str,
    summary: str,
    patient_id: Optional[str] = None,
    caregiver_id: Optional[str] = None,
    drug_safety_findings: Optional[dict] = None,
    urgency: str = "P2",
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_log: Optional[list] = None,
) -> ToolResult:
    """Variant clínica do escalate_to_human_whatsapp.

    Diferença: campos extras pra contexto clínico (drug_safety_findings,
    patient_id, caregiver_id) que vão pro contexto de quem reivindicar
    o handoff. Notifica grupo de plantão CLÍNICO (Henrique/médico) em
    vez do comercial.

    Idempotência: 1 handoff clínico por phone+patient por 30min.
    """
    if not phone or not reason or not summary:
        return ToolResult(ok=False, data={}, error="missing_required_fields")

    from src.services.identity_resolver import normalize_phone_e164_br
    canonical_phone = normalize_phone_e164_br(phone) or phone

    idem_key = f"{canonical_phone}:{patient_id or 'no_patient'}:clinical_handoff"
    if not is_first_occurrence("escalate_clinical", idem_key, ttl_seconds=1800):
        logger.info(
            "clinical_escalate_idempotent_skip",
            phone=canonical_phone,
            patient_id=patient_id,
            trace_id=trace_id,
        )
        return ToolResult(
            ok=True, data={}, idempotent_skip=True,
            error="similar_clinical_escalate_in_last_30min",
        )

    valid_urgency = urgency if urgency in ("P1", "P2", "P3") else "P2"
    sla_seconds = {"P1": 300, "P2": 1800, "P3": 7200}[valid_urgency]

    # Enriquece summary com findings clínicas (cuidador clica e vê tudo
    # de uma vez no painel — sem precisar abrir N abas).
    enriched_summary = summary
    if drug_safety_findings:
        ds = drug_safety_findings
        max_sev = ds.get("max_severity") or "?"
        principles = []
        for r in ds.get("results", []) or []:
            p = r.get("principle_active")
            sev = r.get("severity")
            if p:
                principles.append(f"{p}({sev})")
        cascades = len(ds.get("cascades") or [])
        enriched_summary += (
            f"\n\n[DRUG SAFETY] max_severity={max_sev}; "
            f"meds={', '.join(principles) or 'n/a'}; "
            f"cascades={cascades}"
        )

    db = get_postgres()
    try:
        phone = canonical_phone
        row = db.insert_returning(
            """INSERT INTO aia_health_human_handoff_queue (
                trace_id, phone, tenant_id, channel, reason,
                context_summary, conversation_log,
                triggered_by, priority, status, sla_target_seconds,
                handoff_type, patient_id, caregiver_id
            ) VALUES (%s, %s, %s, 'whatsapp', %s, %s, %s::jsonb,
                      'sofia', %s, 'pending', %s,
                      'clinical', %s, %s)
            RETURNING id""",
            (
                trace_id, phone, tenant_id, reason, enriched_summary,
                json.dumps(conversation_log or []),
                valid_urgency, sla_seconds,
                patient_id, caregiver_id,
            ),
        )
        handoff_id = str(row["id"]) if row else "?"

        # Dispara notificação pra Central 24h CLÍNICA (mesmo phone do
        # comercial por enquanto — Phase C v2.x criará canal clínico
        # dedicado quando Henrique tiver número operacional).
        try:
            central_text = (
                f"[HANDOFF CLÍNICO · {valid_urgency}]\n\n"
                f"Phone do cuidador: {phone}\n"
                f"Motivo: {reason}\n"
                f"Tenant: {tenant_id}\n"
                f"Patient: {patient_id or 'n/a'}\n"
                f"Caregiver: {caregiver_id or 'n/a'}\n"
                f"Trace: {trace_id}\n\n"
                f"Resumo:\n{enriched_summary[:1500]}\n\n"
                f"Reivindique em /admin/system/operations/handoff "
                f"(handoff_id={handoff_id}).\n\n"
                "— Sofia · ConnectaIACare (Care)"
            )
            get_event_bus().publish(Streams.OUTBOUND, {
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "phone": CENTRAL_24H_PHONE,
                "message_type": "text",
                "text": central_text,
                "metadata": {
                    "reason": "central_24h_clinical_handoff_notify",
                    "handoff_id": handoff_id,
                    "handoff_type": "clinical",
                },
            })
            db.execute(
                "UPDATE aia_health_human_handoff_queue "
                "SET notified_central_at = NOW() WHERE id = %s",
                (handoff_id,),
            )
        except Exception as exc:
            logger.warning(
                "clinical_central_notify_failed",
                handoff_id=handoff_id, error=str(exc)[:200],
            )

        write_audit(
            action="clinical_handoff_initiated",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            session_id=session_id,
            resource_type="handoff",
            resource_id=handoff_id,
            payload={
                "reason": reason,
                "urgency": valid_urgency,
                "patient_id": patient_id,
                "caregiver_id": caregiver_id,
                "drug_safety_max_severity": (
                    (drug_safety_findings or {}).get("max_severity")
                ),
            },
        )
        return ToolResult(ok=True, data={
            "handoff_id": handoff_id,
            "handoff_type": "clinical",
            "urgency": valid_urgency,
            "central_notified_via_stream": True,
        })
    except Exception as exc:
        logger.exception(
            "clinical_escalate_failed", trace_id=trace_id,
            error=str(exc)[:200],
        )
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


# ──────────────────────────────────────────────────────────────────
# Commercial funnel tools (migration 068) — Sofia comercial completa
#
# Ferramentas pra Sofia conduzir lead do primeiro contato até a venda:
# consultar planos, agendar demo com data/hora, agendar ligação de
# retorno, registrar atividade no timeline, enviar proposta, consultar
# status, atualizar score de qualificação.
#
# Todas operam sobre as 5 tabelas da migration 068 + aia_health_leads
# (migration 061). Idempotência onde faz sentido (avoid duplicate demo
# scheduling pro mesmo dia, avoid duplicate proposal pra mesmo plano).
# ──────────────────────────────────────────────────────────────────


def query_plans(
    *,
    target_persona: Optional[str] = None,
    public_only: bool = True,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Consulta catálogo de planos pra Sofia apresentar a leads.

    Args:
        target_persona: filtro 'individual'|'familia'|'ilpi'|'clinica'|
            'hospital'|'parceiro'. Se None, retorna todos ativos.
        public_only: só planos publicáveis (default True). super_admin
            pode passar False pra ver enterprise não-públicos.

    Returns:
        ToolResult.data com:
          plans: [{sku, name, target_persona, target_segment,
                   price_monthly_cents, price_setup_cents, currency,
                   billing_period, max_patients, max_caregivers,
                   max_messages_month, max_voice_minutes_month,
                   features, pitch_short, pitch_full, differentials}]
          count: int
    """
    db = get_postgres()
    where = ["active = TRUE"]
    params: list = []
    if public_only:
        where.append("public = TRUE")
    if target_persona:
        where.append("target_persona = %s")
        params.append(target_persona)

    try:
        rows = db.fetch_all(
            f"""SELECT id::text AS id, sku, name, target_persona, target_segment,
                       price_monthly_cents, price_setup_cents, currency,
                       billing_period, max_patients, max_caregivers,
                       max_messages_month, max_voice_minutes_month,
                       features, pitch_short, pitch_full, differentials,
                       active, public
                FROM aia_health_plans
                WHERE {' AND '.join(where)}
                ORDER BY price_monthly_cents NULLS LAST, name""",
            tuple(params),
        )
        return ToolResult(ok=True, data={
            "plans": rows,
            "count": len(rows),
        })
    except Exception as exc:
        logger.exception("query_plans_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def schedule_demo_with_calendar(
    *,
    phone: str,
    scheduled_at: str,                  # ISO 8601 com timezone (ex: '2026-05-08T14:00:00-03:00')
    duration_minutes: int = 30,
    full_name: Optional[str] = None,
    organization: Optional[str] = None,
    plan_focus_sku: Optional[str] = None,
    notes: Optional[str] = None,
    meeting_provider: str = "connectalive",
    timezone: str = "America/Sao_Paulo",
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Agenda demo COM data/hora. Substitui schedule_demo placeholder
    (que só setava status sem horário real).

    - Garante que existe lead (cria minimal se phone não bate)
    - Cria row em aia_health_lead_demos com scheduled_at + duration
    - Atualiza lead.status='demo_scheduled' + demo_scheduled_at
    - Idempotência: 1 demo por (lead, mesmo dia) — evita Sofia agendar
      2x se LLM repetir tool call

    Phase D futuro: integrar com Google Calendar API pra criar evento
    real + invite pro lead. Hoje cria placeholder no DB e time humano
    confirma + manda link real.
    """
    if not phone or not scheduled_at:
        return ToolResult(
            ok=False, data={}, error="phone_and_scheduled_at_required",
        )

    db = get_postgres()
    try:
        # Resolve plan_id se SKU passada
        plan_id = None
        if plan_focus_sku:
            row = db.fetch_one(
                "SELECT id::text AS id FROM aia_health_plans WHERE sku = %s AND active = TRUE",
                (plan_focus_sku,),
            )
            if row:
                plan_id = row["id"]

        # Garante lead
        existing = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '90 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if existing:
            lead_id = existing["id"]
            db.execute(
                """UPDATE aia_health_leads
                      SET status = 'demo_scheduled',
                          demo_scheduled_at = %s::timestamptz,
                          full_name = COALESCE(%s, full_name),
                          organization = COALESCE(%s, organization),
                          last_contact_at = NOW(),
                          updated_at = NOW()
                    WHERE id = %s""",
                (scheduled_at, full_name, organization, lead_id),
            )
        else:
            row = db.insert_returning(
                """INSERT INTO aia_health_leads (
                    phone, full_name, organization, intent,
                    source_channel, status, demo_scheduled_at,
                    last_contact_at
                ) VALUES (%s, %s, %s, 'agendar_demo', 'whatsapp',
                          'demo_scheduled', %s::timestamptz, NOW())
                RETURNING id::text AS id""",
                (phone, full_name, organization, scheduled_at),
            )
            lead_id = row["id"] if row else None

        if not lead_id:
            return ToolResult(
                ok=False, data={}, error="failed_to_create_or_find_lead",
            )

        # Idempotência: já tem demo scheduled na MESMA data pra esse lead?
        same_day = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_lead_demos
               WHERE lead_id = %s
                 AND scheduled_at::date = %s::timestamptz::date
                 AND status IN ('scheduled', 'confirmed')""",
            (lead_id, scheduled_at),
        )
        if same_day:
            logger.info(
                "schedule_demo_idempotent_skip_same_day",
                lead_id=lead_id, trace_id=trace_id,
            )
            return ToolResult(
                ok=True, data={
                    "lead_id": lead_id,
                    "demo_id": same_day["id"],
                    "scheduled_at": scheduled_at,
                    "message_for_sofia": (
                        "Já tinha uma demo agendada pra esse mesmo dia. "
                        "Confirme com o lead que mantemos esse horário, "
                        "e o time humano vai confirmar o link em até 24h."
                    ),
                },
                idempotent_skip=True,
            )

        # Cria demo
        demo_row = db.insert_returning(
            """INSERT INTO aia_health_lead_demos (
                lead_id, scheduled_by_actor, scheduled_at,
                duration_minutes, timezone, meeting_provider,
                plan_focus_id, notes, status
            ) VALUES (%s, 'sofia', %s::timestamptz, %s, %s, %s,
                      %s, %s, 'scheduled')
            RETURNING id::text AS id""",
            (lead_id, scheduled_at, duration_minutes, timezone,
             meeting_provider, plan_id, notes),
        )
        demo_id = demo_row["id"] if demo_row else None

        # Activity timeline
        db.execute(
            """INSERT INTO aia_health_lead_activities (
                lead_id, activity_type, actor_type, actor_name,
                summary, details, related_demo_id, importance
            ) VALUES (%s, 'demo_scheduled', 'sofia',
                      'Sofia (capture_lead)', %s,
                      %s::jsonb, %s, 'important')""",
            (
                lead_id,
                f"Demo agendada pra {scheduled_at} ({duration_minutes}min, {meeting_provider})",
                json.dumps({
                    "scheduled_at": scheduled_at,
                    "duration_minutes": duration_minutes,
                    "plan_focus_sku": plan_focus_sku,
                    "notes": notes,
                }),
                demo_id,
            ),
        )

        write_audit(
            action="demo_scheduled_with_calendar",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            resource_type="lead_demo",
            resource_id=demo_id,
            payload={
                "lead_id": lead_id,
                "scheduled_at": scheduled_at,
                "plan_focus_sku": plan_focus_sku,
            },
        )
        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "demo_id": demo_id,
            "scheduled_at": scheduled_at,
            "duration_minutes": duration_minutes,
            "message_for_sofia": (
                f"Demo agendada pra {scheduled_at} ({duration_minutes}min). "
                "Avise o lead que vai receber confirmação por WhatsApp/email "
                "em até 24h com o link da reunião."
            ),
        })
    except Exception as exc:
        logger.exception(
            "schedule_demo_with_calendar_failed", trace_id=trace_id,
        )
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def schedule_callback_call(
    *,
    phone: str,
    scheduled_at: str,                  # ISO 8601
    call_type: str = "follow_up",
    full_name: Optional[str] = None,
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Agenda ligação de retorno. Quando lead pede 'me liga depois' ou
    Sofia decide que precisa follow-up — cria row em lead_calls com
    next_action_at preenchido, sem outcome ainda (será preenchido
    quando ligação rolar).

    auto_dialer/comercial humano lê /api/admin/leads/calls/upcoming pra
    saber o que ligar.

    Idempotência: 1 callback agendado por (lead, dia).
    """
    if not phone or not scheduled_at:
        return ToolResult(
            ok=False, data={}, error="phone_and_scheduled_at_required",
        )
    valid_types = (
        "discovery", "follow_up", "callback", "proposal", "closing",
        "support", "qualification",
    )
    if call_type not in valid_types:
        call_type = "follow_up"

    db = get_postgres()
    try:
        existing = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '90 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if not existing:
            row = db.insert_returning(
                """INSERT INTO aia_health_leads (
                    phone, full_name, intent, source_channel, status,
                    last_contact_at
                ) VALUES (%s, %s, 'duvida_geral', 'whatsapp',
                          'qualified', NOW())
                RETURNING id::text AS id""",
                (phone, full_name),
            )
            lead_id = row["id"] if row else None
        else:
            lead_id = existing["id"]

        if not lead_id:
            return ToolResult(
                ok=False, data={}, error="lead_not_resolved",
            )

        # Idempotência por dia + tipo
        same_day = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_lead_calls
               WHERE lead_id = %s
                 AND next_action_at::date = %s::timestamptz::date
                 AND call_type = %s
                 AND outcome IS NULL""",
            (lead_id, scheduled_at, call_type),
        )
        if same_day:
            return ToolResult(
                ok=True, data={
                    "lead_id": lead_id,
                    "call_id": same_day["id"],
                    "message_for_sofia": "Já tem callback agendado pra esse dia.",
                },
                idempotent_skip=True,
            )

        call_row = db.insert_returning(
            """INSERT INTO aia_health_lead_calls (
                lead_id, direction, called_by_actor,
                started_at, call_type,
                summary, next_action, next_action_at
            ) VALUES (%s, 'outbound', 'auto_dialer',
                      NOW(), %s,
                      'Callback agendado pelo Sofia',
                      %s, %s::timestamptz)
            RETURNING id::text AS id""",
            (lead_id, call_type, call_type, scheduled_at),
        )
        call_id = call_row["id"] if call_row else None

        db.execute(
            """INSERT INTO aia_health_lead_activities (
                lead_id, activity_type, actor_type, actor_name,
                summary, details, related_call_id, importance
            ) VALUES (%s, 'callback_scheduled', 'sofia',
                      'Sofia', %s, %s::jsonb, %s, 'normal')""",
            (
                lead_id,
                f"Callback agendado pra {scheduled_at} ({call_type})",
                json.dumps({"scheduled_at": scheduled_at, "type": call_type, "notes": notes}),
                call_id,
            ),
        )

        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "call_id": call_id,
            "scheduled_at": scheduled_at,
            "message_for_sofia": (
                f"Callback registrado. Nosso time vai te ligar em "
                f"{scheduled_at}. Quer que eu mande lembrete por WhatsApp "
                "uma hora antes?"
            ),
        })
    except Exception as exc:
        logger.exception("schedule_callback_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def register_lead_activity(
    *,
    phone: str,
    activity_type: str,
    summary: str,
    details: Optional[dict] = None,
    importance: str = "normal",
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Anota observação no timeline do lead. Sofia usa pra registrar
    pontos relevantes que não disparam outras tools (ex: "lead pediu
    pra ver caso de uso similar", "mencionou que já avalia outro
    fornecedor").

    Args:
        activity_type: 'note_added' (default), 'qualification_signal',
            'objection_raised', 'positive_feedback', 'concern_raised'
        importance: 'minor'|'normal'|'important'|'critical'
    """
    if not phone or not summary:
        return ToolResult(
            ok=False, data={}, error="phone_and_summary_required",
        )
    valid_imp = ("minor", "normal", "important", "critical")
    if importance not in valid_imp:
        importance = "normal"

    db = get_postgres()
    try:
        existing = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '90 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if not existing:
            return ToolResult(
                ok=False, data={}, error="lead_not_found",
            )
        lead_id = existing["id"]

        db.execute(
            """INSERT INTO aia_health_lead_activities (
                lead_id, activity_type, actor_type, actor_name,
                summary, details, importance
            ) VALUES (%s, %s, 'sofia', 'Sofia (note)',
                      %s, %s::jsonb, %s)""",
            (
                lead_id, activity_type, summary[:500],
                json.dumps(details or {}), importance,
            ),
        )
        # Atualiza last_contact_at
        db.execute(
            "UPDATE aia_health_leads SET last_contact_at = NOW() WHERE id = %s",
            (lead_id,),
        )
        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "activity_type": activity_type,
            "message_for_sofia": "Anotei aqui no histórico do lead.",
        })
    except Exception as exc:
        logger.exception("register_lead_activity_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def send_proposal(
    *,
    phone: str,
    plan_sku: str,
    custom_price_monthly_cents: Optional[int] = None,
    custom_price_setup_cents: Optional[int] = None,
    discount_percent: Optional[float] = None,
    valid_until: Optional[str] = None,    # ISO date YYYY-MM-DD
    sent_via: str = "whatsapp",
    notes: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Envia proposta comercial. Cria row em aia_health_lead_proposals
    + atualiza lead.status='proposal_sent' + dispara mensagem WhatsApp
    pro lead com link da proposta (Phase D: gera PDF; hoje placeholder).

    Idempotência: 1 proposta ativa por (lead, plano) — se tentar enviar
    de novo o mesmo plano, retorna a existente.

    Phase D futuro:
      - Gerar PDF via template + dados negociados
      - Mandar email com PDF anexo
      - Track abertura via pixel/UTM
    """
    if not phone or not plan_sku:
        return ToolResult(
            ok=False, data={}, error="phone_and_plan_sku_required",
        )
    if sent_via not in ("email", "whatsapp", "in_demo", "voice_call"):
        sent_via = "whatsapp"

    db = get_postgres()
    try:
        # Resolve plan
        plan = db.fetch_one(
            """SELECT id::text AS id, name, price_monthly_cents,
                      price_setup_cents
               FROM aia_health_plans
               WHERE sku = %s AND active = TRUE""",
            (plan_sku,),
        )
        if not plan:
            return ToolResult(
                ok=False, data={}, error=f"plan_not_found:{plan_sku}",
            )
        plan_id = plan["id"]

        existing = db.fetch_one(
            """SELECT id::text AS id FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '90 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if not existing:
            return ToolResult(
                ok=False, data={}, error="lead_not_found",
            )
        lead_id = existing["id"]

        # Idempotência: já tem proposta ativa pra esse plano?
        existing_prop = db.fetch_one(
            """SELECT id::text AS id, status, valid_until
               FROM aia_health_lead_proposals
               WHERE lead_id = %s AND plan_id = %s
                 AND status IN ('sent', 'viewed')
               ORDER BY sent_at DESC LIMIT 1""",
            (lead_id, plan_id),
        )
        if existing_prop:
            return ToolResult(
                ok=True, data={
                    "lead_id": lead_id,
                    "proposal_id": existing_prop["id"],
                    "message_for_sofia": (
                        "Já tinha proposta enviada pra esse plano. "
                        "Mantenha contato e confirme se o lead recebeu."
                    ),
                },
                idempotent_skip=True,
            )

        # Defaults
        from datetime import date, timedelta
        if not valid_until:
            valid_until = (date.today() + timedelta(days=30)).isoformat()

        prop_row = db.insert_returning(
            """INSERT INTO aia_health_lead_proposals (
                lead_id, plan_id, sent_by_actor,
                custom_price_monthly_cents, custom_price_setup_cents,
                discount_percent, valid_until,
                sent_via, status
            ) VALUES (%s, %s, 'sofia', %s, %s, %s, %s::date,
                      %s, 'sent')
            RETURNING id::text AS id""",
            (
                lead_id, plan_id,
                custom_price_monthly_cents, custom_price_setup_cents,
                discount_percent, valid_until,
                sent_via,
            ),
        )
        proposal_id = prop_row["id"] if prop_row else None

        db.execute(
            """UPDATE aia_health_leads SET
                  status = 'proposal_sent',
                  last_contact_at = NOW(),
                  updated_at = NOW()
               WHERE id = %s""",
            (lead_id,),
        )

        db.execute(
            """INSERT INTO aia_health_lead_activities (
                lead_id, activity_type, actor_type, actor_name,
                summary, details, related_proposal_id, importance
            ) VALUES (%s, 'proposal_sent', 'sofia', 'Sofia',
                      %s, %s::jsonb, %s, 'important')""",
            (
                lead_id,
                f"Proposta enviada: {plan['name']} (validade {valid_until})",
                json.dumps({
                    "plan_sku": plan_sku,
                    "custom_price_monthly_cents": custom_price_monthly_cents,
                    "discount_percent": discount_percent,
                    "valid_until": valid_until,
                    "notes": notes,
                }),
                proposal_id,
            ),
        )

        write_audit(
            action="proposal_sent",
            actor="sofia",
            tenant_id=tenant_id,
            trace_id=trace_id,
            resource_type="proposal",
            resource_id=proposal_id,
            payload={"lead_id": lead_id, "plan_sku": plan_sku},
        )

        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "proposal_id": proposal_id,
            "plan_sku": plan_sku,
            "valid_until": valid_until,
            "message_for_sofia": (
                f"Proposta do plano {plan['name']} foi registrada. "
                "Avise o lead que recebeu, peça pra revisar e dê prazo "
                f"até {valid_until}. Time comercial vai entrar em contato."
            ),
        })
    except Exception as exc:
        logger.exception("send_proposal_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def get_lead_status(
    *,
    phone: str,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Consulta status atual do lead pelo phone. Útil pra Sofia saber:
        - É um lead novo, qualificado, em demo, com proposta?
        - Tem demo agendada?
        - Tem proposta pendente?
    Sem precisar perguntar isso pro lead.
    """
    if not phone:
        return ToolResult(ok=False, data={}, error="phone_required")

    db = get_postgres()
    try:
        lead = db.fetch_one(
            """SELECT id::text AS id, full_name, organization,
                      role_self_declared, intent, status,
                      qualification_score, demo_scheduled_at,
                      converted_to_tenant_id, last_contact_at,
                      created_at,
                      jsonb_array_length(COALESCE(notes, '[]'::jsonb)) AS notes_count
               FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '180 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if not lead:
            return ToolResult(ok=True, data={
                "found": False,
                "message_for_sofia": (
                    "Phone não bate com nenhum lead recente — é um novo "
                    "contato. Comece capturando nome e contexto."
                ),
            })

        # Demo upcoming?
        upcoming_demo = db.fetch_one(
            """SELECT id::text AS id, scheduled_at, status, meeting_url
               FROM aia_health_lead_demos
               WHERE lead_id = %s AND status IN ('scheduled', 'confirmed')
                 AND scheduled_at > NOW()
               ORDER BY scheduled_at ASC LIMIT 1""",
            (lead["id"],),
        )

        # Proposta ativa?
        active_proposal = db.fetch_one(
            """SELECT p.id::text AS id, p.status, p.valid_until,
                      pl.sku AS plan_sku, pl.name AS plan_name
               FROM aia_health_lead_proposals p
               JOIN aia_health_plans pl ON pl.id = p.plan_id
               WHERE p.lead_id = %s AND p.status IN ('sent', 'viewed')
               ORDER BY p.sent_at DESC LIMIT 1""",
            (lead["id"],),
        )

        # Última activity
        last_activity = db.fetch_one(
            """SELECT activity_type, summary, occurred_at
               FROM aia_health_lead_activities
               WHERE lead_id = %s
               ORDER BY occurred_at DESC LIMIT 1""",
            (lead["id"],),
        )

        return ToolResult(ok=True, data={
            "found": True,
            "lead": lead,
            "upcoming_demo": upcoming_demo,
            "active_proposal": active_proposal,
            "last_activity": last_activity,
            "message_for_sofia": (
                f"Lead em estágio '{lead['status']}' "
                f"({'com demo agendada' if upcoming_demo else 'sem demo'}, "
                f"{'proposta ativa' if active_proposal else 'sem proposta'}). "
                "Use esse contexto pra continuar a conversa de onde parou."
            ),
        })
    except Exception as exc:
        logger.exception("get_lead_status_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


def update_lead_qualification(
    *,
    phone: str,
    qualification_score: int,           # 0-100
    new_status: Optional[str] = None,   # avança status se especificado
    reason: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ToolResult:
    """Sofia atualiza score de qualificação do lead baseado em sinais
    captados na conversa (orçamento, urgência, decisão de compra,
    fit do produto).

    Heurística sugerida pra Sofia (orientação no system prompt):
      - 0-30: lead frio (curiosidade, sem orçamento, sem urgência)
      - 30-60: lead morno (interesse claro, sem decisão)
      - 60-80: lead quente (orçamento+urgência+decisor)
      - 80+: lead pronto pra fechar (pediu proposta/contrato)
    """
    if not phone or qualification_score is None:
        return ToolResult(
            ok=False, data={}, error="phone_and_score_required",
        )
    score = max(0, min(int(qualification_score), 100))
    valid_statuses = (
        "new", "qualified", "demo_scheduled", "in_demo",
        "proposal_sent", "converted", "lost",
    )

    db = get_postgres()
    try:
        existing = db.fetch_one(
            """SELECT id::text AS id, qualification_score, status
               FROM aia_health_leads
               WHERE phone = %s AND created_at > NOW() - INTERVAL '90 days'
               ORDER BY created_at DESC LIMIT 1""",
            (phone,),
        )
        if not existing:
            return ToolResult(
                ok=False, data={}, error="lead_not_found",
            )
        lead_id = existing["id"]
        old_score = existing.get("qualification_score") or 0

        updates = ["qualification_score = %s", "updated_at = NOW()"]
        params: list = [score]

        if new_status and new_status in valid_statuses:
            updates.append("status = %s")
            params.append(new_status)
            if new_status == "qualified":
                updates.append("qualified_at = NOW()")

        params.append(lead_id)
        db.execute(
            f"UPDATE aia_health_leads SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )

        db.execute(
            """INSERT INTO aia_health_lead_activities (
                lead_id, activity_type, actor_type, actor_name,
                summary, details, importance
            ) VALUES (%s, 'qualification_updated', 'sofia', 'Sofia',
                      %s, %s::jsonb, %s)""",
            (
                lead_id,
                f"Score: {old_score} → {score}" + (f" (status: {new_status})" if new_status else ""),
                json.dumps({
                    "old_score": old_score, "new_score": score,
                    "new_status": new_status, "reason": reason,
                }),
                "important" if score >= 60 else "normal",
            ),
        )

        return ToolResult(ok=True, data={
            "lead_id": lead_id,
            "old_score": old_score,
            "new_score": score,
            "new_status": new_status,
            "message_for_sofia": (
                f"Score atualizado de {old_score} pra {score}."
                + (f" Status agora é '{new_status}'." if new_status else "")
            ),
        })
    except Exception as exc:
        logger.exception("update_lead_qualification_failed", trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])


# ──────────────────────────────────────────────────────────────────
# Tool registry
# ──────────────────────────────────────────────────────────────────


TOOL_REGISTRY = {
    "capture_lead": capture_lead,
    "schedule_demo": schedule_demo,           # legado — placeholder
    "escalate_to_human_whatsapp": escalate_to_human_whatsapp,
    # Care tools (Phase C v2)
    "safety_review_prescriptions": safety_review_prescriptions,
    "register_caregiver_report": register_caregiver_report,
    "escalate_to_human_clinical": escalate_to_human_clinical,
    # Commercial funnel tools (migration 068 — Phase D Comercial)
    "query_plans": query_plans,
    "schedule_demo_with_calendar": schedule_demo_with_calendar,
    "schedule_callback_call": schedule_callback_call,
    "register_lead_activity": register_lead_activity,
    "send_proposal": send_proposal,
    "get_lead_status": get_lead_status,
    "update_lead_qualification": update_lead_qualification,
}


def execute_tool(
    name: str,
    args: dict,
    *,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> ToolResult:
    """Executa tool por nome. Adiciona tenant/trace/session
    automaticamente. Validação básica de args."""
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return ToolResult(ok=False, data={}, error=f"unknown_tool:{name}")
    safe_args = dict(args or {})
    safe_args.setdefault("tenant_id", tenant_id)
    safe_args.setdefault("trace_id", trace_id)
    if name == "escalate_to_human_whatsapp":
        safe_args.setdefault("session_id", session_id)
    try:
        result = fn(**safe_args)
        logger.info(
            "tool_executed",
            tool=name, ok=result.ok,
            idempotent_skip=result.idempotent_skip,
            tenant_id=tenant_id, trace_id=trace_id,
        )
        return result
    except TypeError as exc:
        # Args inválidos
        return ToolResult(ok=False, data={}, error=f"invalid_args: {str(exc)[:120]}")
    except Exception as exc:
        logger.exception("tool_exec_failed", tool=name, trace_id=trace_id)
        return ToolResult(ok=False, data={}, error=str(exc)[:200])
