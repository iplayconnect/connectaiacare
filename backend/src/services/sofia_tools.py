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
# Tool registry
# ──────────────────────────────────────────────────────────────────


TOOL_REGISTRY = {
    "capture_lead": capture_lead,
    "schedule_demo": schedule_demo,
    "escalate_to_human_whatsapp": escalate_to_human_whatsapp,
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
