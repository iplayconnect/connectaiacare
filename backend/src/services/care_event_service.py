"""Serviço central de Eventos de Cuidado (ADR-018).

Um CareEvent é o objeto clínico principal: cada áudio do cuidador abre um evento
com ciclo de vida completo, timeline, escalação hierárquica, check-ins proativos
e encerramento categorizado.

Estados do ciclo:
    analyzing → awaiting_ack → pattern_analyzed → escalating →
    awaiting_status_update → resolved | expired

Múltiplos eventos podem estar ATIVOS ao mesmo tempo para o MESMO cuidador, desde
que sejam para PACIENTES DIFERENTES (constraint unique parcial no DB).

API pública:
    open(tenant, patient, caregiver_phone, ...)
    get_active_by_caregiver_patient(tenant, phone, patient_id)
    list_active_by_caregiver(tenant, phone)
    list_active(tenant)
    find_active_by_id(event_id)
    append_message(event_id, message)
    update_classification(event_id, classification, reasoning)
    schedule_checkin(event_id, kind, scheduled_for, ...)
    record_escalation(event_id, target_role, phone, channel, ...)
    resolve(event_id, closed_by, closed_reason, notes)
    expire_silent(event_id)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.postgres import get_postgres
from src.services.tenant_config_service import get_tenant_config_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Estados do ciclo de vida
STATUS_ANALYZING = "analyzing"
STATUS_AWAITING_ACK = "awaiting_ack"
STATUS_PATTERN_ANALYZED = "pattern_analyzed"
STATUS_ESCALATING = "escalating"
STATUS_AWAITING_STATUS_UPDATE = "awaiting_status_update"
STATUS_RESOLVED = "resolved"
STATUS_EXPIRED = "expired"

ACTIVE_STATUSES = (
    STATUS_ANALYZING,
    STATUS_AWAITING_ACK,
    STATUS_PATTERN_ANALYZED,
    STATUS_ESCALATING,
    STATUS_AWAITING_STATUS_UPDATE,
)

DEFAULT_EVENT_TTL_MIN = 30
MAX_MESSAGES_IN_CONTEXT = 40


class CareEventService:
    def __init__(self):
        self.db = get_postgres()
        self.tenant_cfg = get_tenant_config_service()

    # ---------- criação ----------
    def open(
        self,
        tenant_id: str,
        patient_id: str,
        caregiver_phone: str,
        caregiver_id: str | None = None,
        initial_classification: str | None = None,
        event_type: str | None = None,
        event_tags: list[str] | None = None,
        initial_report_id: str | None = None,
        initial_transcript: str | None = None,
    ) -> dict:
        """Abre novo evento de cuidado OU reusa ativo existente.

        Se já existe evento ativo para (tenant, caregiver_phone, patient_id),
        retorna o existente (sem criar duplicata) — unique constraint do DB garante.
        """
        # Check de idempotência: já existe ativo pro par cuidador+paciente?
        existing = self.get_active_by_caregiver_patient(tenant_id, caregiver_phone, patient_id)
        if existing:
            logger.info(
                "care_event_reuse_existing",
                event_id=str(existing["id"]),
                patient_id=patient_id,
            )
            return existing

        timings = self.tenant_cfg.get_timings(tenant_id, initial_classification)
        ttl_min = timings.get("closure_decision_after_min", DEFAULT_EVENT_TTL_MIN)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_min)

        initial_context: dict[str, Any] = {"messages": []}
        if initial_transcript:
            initial_context["messages"].append({
                "role": "caregiver",
                "kind": "audio",
                "text": initial_transcript,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_care_events (
                tenant_id, patient_id, caregiver_phone, caregiver_id,
                initial_classification, current_classification,
                event_type, event_tags, status, context,
                initial_report_id, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, human_id, tenant_id, patient_id, caregiver_phone,
                      current_classification, event_type, status, opened_at, expires_at
            """,
            (
                tenant_id, patient_id, caregiver_phone, caregiver_id,
                initial_classification, initial_classification,
                event_type, event_tags or [], STATUS_ANALYZING,
                self.db.json_adapt(initial_context),
                initial_report_id, expires_at,
            ),
        )
        logger.info(
            "care_event_opened",
            event_id=str(row["id"]),
            human_id=row["human_id"],
            patient_id=patient_id,
            caregiver_phone=caregiver_phone,
            classification=initial_classification,
        )
        return row

    # ---------- leitura ----------
    def get_by_id(self, event_id: str) -> dict | None:
        return self.db.fetch_one(
            """
            SELECT id, human_id, tenant_id, patient_id, caregiver_phone, caregiver_id,
                   initial_classification, current_classification, event_type, event_tags,
                   status, context, summary, reasoning,
                   opened_at, pattern_analyzed_at, first_escalation_at, last_check_in_at,
                   resolved_at, closed_by, closed_reason, closure_notes,
                   expires_at, initial_report_id
            FROM aia_health_care_events
            WHERE id = %s
            """,
            (event_id,),
        )

    def get_active_by_caregiver_patient(
        self, tenant_id: str, caregiver_phone: str, patient_id: str
    ) -> dict | None:
        return self.db.fetch_one(
            """
            SELECT id, human_id, tenant_id, patient_id, caregiver_phone,
                   current_classification, status, context, event_type, event_tags,
                   opened_at, expires_at
            FROM aia_health_care_events
            WHERE tenant_id = %s
              AND caregiver_phone = %s
              AND patient_id = %s
              AND status NOT IN ('resolved', 'expired')
              AND expires_at > NOW()
            ORDER BY opened_at DESC
            LIMIT 1
            """,
            (tenant_id, caregiver_phone, patient_id),
        )

    def list_active_by_caregiver(self, tenant_id: str, caregiver_phone: str) -> list[dict]:
        """Lista todos os eventos ativos de um cuidador (pode ter N, 1 por paciente)."""
        return self.db.fetch_all(
            """
            SELECT e.id, e.human_id, e.patient_id, e.caregiver_phone,
                   e.current_classification, e.status, e.event_type,
                   e.opened_at, e.expires_at,
                   p.full_name AS patient_name, p.nickname AS patient_nickname
            FROM aia_health_care_events e
            JOIN aia_health_patients p ON p.id = e.patient_id
            WHERE e.tenant_id = %s
              AND e.caregiver_phone = %s
              AND e.status NOT IN ('resolved', 'expired')
              AND e.expires_at > NOW()
            ORDER BY e.opened_at DESC
            """,
            (tenant_id, caregiver_phone),
        )

    def list_active(self, tenant_id: str, limit: int = 100) -> list[dict]:
        """Dashboard: todos os eventos ativos do tenant."""
        return self.db.fetch_all(
            """
            SELECT e.id, e.human_id, e.patient_id, e.caregiver_phone,
                   e.current_classification, e.status, e.event_type,
                   e.summary, e.opened_at, e.expires_at,
                   p.full_name AS patient_name, p.nickname AS patient_nickname,
                   p.photo_url AS patient_photo,
                   p.care_unit AS patient_care_unit
            FROM aia_health_care_events e
            JOIN aia_health_patients p ON p.id = e.patient_id
            WHERE e.tenant_id = %s
              AND e.status NOT IN ('resolved', 'expired')
              AND e.expires_at > NOW()
            ORDER BY
              CASE e.current_classification
                WHEN 'critical' THEN 1 WHEN 'urgent' THEN 2
                WHEN 'attention' THEN 3 ELSE 4
              END,
              e.opened_at DESC
            LIMIT %s
            """,
            (tenant_id, limit),
        )

    def list_by_patient(
        self, patient_id: str, include_closed: bool = True, limit: int = 50
    ) -> list[dict]:
        """Timeline de eventos de um paciente (dashboard individual)."""
        where_status = "" if include_closed else " AND status NOT IN ('resolved','expired')"
        return self.db.fetch_all(
            f"""
            SELECT id, human_id, caregiver_phone, current_classification, status,
                   event_type, event_tags, summary, reasoning,
                   opened_at, resolved_at, closed_by, closed_reason, closure_notes
            FROM aia_health_care_events
            WHERE patient_id = %s {where_status}
            ORDER BY opened_at DESC
            LIMIT %s
            """,
            (patient_id, limit),
        )

    # ---------- mutação de contexto ----------
    def append_message(self, event_id: str, message: dict) -> None:
        """Append mensagem em context.messages + renova expires_at."""
        event = self.get_by_id(event_id)
        if not event:
            logger.warning("care_event_not_found_on_append", event_id=event_id)
            return

        msg = dict(message)
        msg.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        context = dict(event.get("context") or {})
        messages = list(context.get("messages") or [])
        messages.append(msg)

        if len(messages) > MAX_MESSAGES_IN_CONTEXT:
            head = messages[:1]
            tail = messages[-(MAX_MESSAGES_IN_CONTEXT - 1):]
            messages = head + tail

        context["messages"] = messages

        # Renova expires_at com o TTL configurado
        tenant_id = event["tenant_id"]
        timings = self.tenant_cfg.get_timings(tenant_id, event.get("current_classification"))
        ttl_min = timings.get("closure_decision_after_min", DEFAULT_EVENT_TTL_MIN)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_min)

        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET context = %s, expires_at = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (self.db.json_adapt(context), expires_at, event_id),
        )

    def update_status(self, event_id: str, new_status: str) -> None:
        if new_status not in (
            STATUS_ANALYZING, STATUS_AWAITING_ACK, STATUS_PATTERN_ANALYZED,
            STATUS_ESCALATING, STATUS_AWAITING_STATUS_UPDATE,
            STATUS_RESOLVED, STATUS_EXPIRED,
        ):
            raise ValueError(f"status invalido: {new_status}")
        self.db.execute(
            "UPDATE aia_health_care_events SET status = %s, updated_at = NOW() WHERE id = %s",
            (new_status, event_id),
        )
        logger.info("care_event_status_change", event_id=event_id, status=new_status)

    def update_classification(
        self, event_id: str, classification: str, reasoning: str | None = None
    ) -> None:
        """Atualiza classificação atual (pode escalar ou desclassificar durante o ciclo)."""
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET current_classification = %s,
                reasoning = COALESCE(%s, reasoning),
                updated_at = NOW()
            WHERE id = %s
            """,
            (classification, reasoning, event_id),
        )
        logger.info(
            "care_event_classification_updated",
            event_id=event_id,
            classification=classification,
        )

    def update_summary(self, event_id: str, summary: str) -> None:
        self.db.execute(
            "UPDATE aia_health_care_events SET summary = %s, updated_at = NOW() WHERE id = %s",
            (summary, event_id),
        )

    def mark_pattern_analyzed(self, event_id: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET pattern_analyzed_at = NOW(),
                status = CASE WHEN status IN ('analyzing','awaiting_ack') THEN 'pattern_analyzed' ELSE status END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (event_id,),
        )

    def touch_check_in(self, event_id: str) -> None:
        self.db.execute(
            "UPDATE aia_health_care_events SET last_check_in_at = NOW(), updated_at = NOW() WHERE id = %s",
            (event_id,),
        )

    def mark_first_escalation(self, event_id: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET first_escalation_at = COALESCE(first_escalation_at, NOW()),
                status = 'escalating',
                updated_at = NOW()
            WHERE id = %s
            """,
            (event_id,),
        )

    # ---------- encerramento ----------
    def resolve(
        self,
        event_id: str,
        closed_by: str,
        closed_reason: str,
        closure_notes: str | None = None,
    ) -> None:
        """Encerra o evento com categoria de desfecho.

        closed_by: 'system_auto' | 'caregiver' | 'nurse' | 'doctor' | 'operator'
        closed_reason: 'cuidado_iniciado' | 'encaminhado_hospital' | 'transferido' |
                       'sem_intercorrencia' | 'falso_alarme' | 'paciente_estavel' |
                       'expirou_sem_feedback' | 'obito' | 'outro'
        """
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET status = 'resolved',
                resolved_at = NOW(),
                closed_by = %s,
                closed_reason = %s,
                closure_notes = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (closed_by, closed_reason, closure_notes, event_id),
        )
        logger.info(
            "care_event_resolved",
            event_id=event_id,
            closed_by=closed_by,
            closed_reason=closed_reason,
        )

    def expire_silent(self, event_id: str) -> None:
        """Expira evento silenciosamente por TTL (sem feedback)."""
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET status = 'expired',
                resolved_at = NOW(),
                closed_by = 'system_auto',
                closed_reason = 'expirou_sem_feedback',
                updated_at = NOW()
            WHERE id = %s AND status NOT IN ('resolved','expired')
            """,
            (event_id,),
        )
        logger.info("care_event_expired", event_id=event_id)

    # ---------- check-ins agendados ----------
    def schedule_checkin(
        self,
        event_id: str,
        tenant_id: str,
        kind: str,
        scheduled_for: datetime,
        channel: str = "whatsapp",
    ) -> str:
        """Agenda um check-in proativo. Retorna ID do checkin."""
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_care_event_checkins (
                event_id, tenant_id, kind, scheduled_for, channel, status
            ) VALUES (%s, %s, %s, %s, %s, 'scheduled')
            RETURNING id
            """,
            (event_id, tenant_id, kind, scheduled_for, channel),
        )
        return str(row["id"])

    def list_due_checkins(self, limit: int = 50) -> list[dict]:
        """Busca check-ins com scheduled_for vencido. Usado pelo scheduler."""
        return self.db.fetch_all(
            """
            SELECT c.id, c.event_id, c.tenant_id, c.kind, c.scheduled_for, c.channel,
                   e.patient_id, e.caregiver_phone, e.current_classification, e.status AS event_status
            FROM aia_health_care_event_checkins c
            JOIN aia_health_care_events e ON e.id = c.event_id
            WHERE c.status = 'scheduled'
              AND c.scheduled_for <= NOW()
              AND e.status NOT IN ('resolved', 'expired')
            ORDER BY c.scheduled_for
            LIMIT %s
            """,
            (limit,),
        )

    def mark_checkin_sent(
        self, checkin_id: str, message_sent: str, external_ref: str | None = None
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_care_event_checkins
            SET status = 'sent', sent_at = NOW(), message_sent = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (message_sent, checkin_id),
        )

    def mark_checkin_responded(
        self, checkin_id: str, response_text: str, classification: str | None = None
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_care_event_checkins
            SET status = 'responded', response_received_at = NOW(),
                response_text = %s, response_classification = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (response_text, classification, checkin_id),
        )

    def mark_checkin_failed(self, checkin_id: str, error: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_care_event_checkins
            SET status = 'failed', error_message = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (error, checkin_id),
        )

    def find_pending_checkin(
        self, event_id: str, kind: str | None = None
    ) -> dict | None:
        """Busca checkin sent aguardando resposta (usado ao receber msg do cuidador)."""
        if kind:
            return self.db.fetch_one(
                """
                SELECT id, event_id, kind, scheduled_for, sent_at
                FROM aia_health_care_event_checkins
                WHERE event_id = %s AND kind = %s AND status = 'sent'
                ORDER BY sent_at DESC NULLS LAST LIMIT 1
                """,
                (event_id, kind),
            )
        return self.db.fetch_one(
            """
            SELECT id, event_id, kind, scheduled_for, sent_at
            FROM aia_health_care_event_checkins
            WHERE event_id = %s AND status = 'sent'
            ORDER BY sent_at DESC NULLS LAST LIMIT 1
            """,
            (event_id,),
        )

    # ---------- escalação ----------
    def record_escalation(
        self,
        event_id: str,
        tenant_id: str,
        target_role: str,
        target_name: str | None,
        target_phone: str,
        channel: str,
        message_content: str | None = None,
        external_ref: str | None = None,
    ) -> str:
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_escalation_log (
                event_id, tenant_id, target_role, target_name, target_phone,
                channel, message_content, status, sent_at, external_ref
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'sent', NOW(), %s)
            RETURNING id
            """,
            (event_id, tenant_id, target_role, target_name, target_phone,
             channel, message_content, external_ref),
        )
        self.mark_first_escalation(event_id)
        return str(row["id"])

    def update_escalation_status(
        self, escalation_id: str, new_status: str, response_summary: str | None = None
    ) -> None:
        ts_col = {
            "delivered": "delivered_at", "read": "read_at", "responded": "responded_at",
        }.get(new_status)
        if ts_col:
            self.db.execute(
                f"""
                UPDATE aia_health_escalation_log
                SET status = %s, {ts_col} = NOW(),
                    response_summary = COALESCE(%s, response_summary),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_status, response_summary, escalation_id),
            )
        else:
            self.db.execute(
                """
                UPDATE aia_health_escalation_log
                SET status = %s,
                    response_summary = COALESCE(%s, response_summary),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_status, response_summary, escalation_id),
            )

    def list_escalations_for_event(self, event_id: str) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT id, target_role, target_name, target_phone, channel,
                   message_content, status, sent_at, delivered_at, read_at,
                   responded_at, response_summary, external_ref
            FROM aia_health_escalation_log
            WHERE event_id = %s
            ORDER BY created_at
            """,
            (event_id,),
        )


_care_event_instance: CareEventService | None = None


def get_care_event_service() -> CareEventService:
    global _care_event_instance
    if _care_event_instance is None:
        _care_event_instance = CareEventService()
    return _care_event_instance
