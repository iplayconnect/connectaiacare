"""Caregiver wellness events — separados do prontuário do paciente.

Decisão arquitetural (Alexandre 2026-05-09):
    Relatos com event_type='apoio_emocional' NÃO devem ser registrados
    em aia_health_care_events (prontuário do paciente). São sobre o
    CUIDADOR. Aqui ficam as 4 operações principais:
        1. create_event(...) — chamada pelo pipeline em vez de
           events.open() quando event_type=apoio_emocional
        2. notify_managers(...) — manda alerta pros admin_tenant do
           tenant via outbound stream (WhatsApp)
        3. list_open(...) — pra UI do gestor
        4. acknowledge / resolve — gestor lida no painel

Reusa identity_resolver pra mapear caregiver via phone (mesma lógica
do pipeline atual).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.services.event_bus import Streams, get_event_bus
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


_VALID_SEVERITY = {"routine", "attention", "urgent", "critical"}
_VALID_STATUS = {"open", "acknowledged", "resolved", "escalated"}


class CaregiverWellnessService:
    def __init__(self):
        self.db = get_postgres()

    # ─── Create ──────────────────────────────────────────────────

    def create_event(
        self,
        *,
        tenant_id: str,
        caregiver_phone: str,
        raw_text: str,
        severity: str = "routine",
        summary: str | None = None,
        caregiver_id: str | None = None,
        source_channel: str = "whatsapp",
        source_report_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Cria um wellness event. Notifica gestores em severity ≥ attention.

        Retorna o evento criado ou None se inserção falhou.
        """
        if severity not in _VALID_SEVERITY:
            severity = "routine"
        try:
            row = self.db.fetch_one(
                """INSERT INTO aia_health_caregiver_wellness_events (
                    tenant_id, caregiver_id, caregiver_phone, raw_text,
                    summary, severity, source_channel, source_report_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text AS id, tenant_id, caregiver_id::text AS caregiver_id,
                          caregiver_phone, severity, summary, status, created_at""",
                (
                    tenant_id, caregiver_id, caregiver_phone, raw_text,
                    summary or raw_text[:200], severity, source_channel,
                    source_report_id,
                ),
            )
            if not row:
                return None
        except Exception:
            logger.exception(
                "wellness_create_failed",
                extra={"tenant_id": tenant_id, "phone_redacted": caregiver_phone[-4:]},
            )
            return None

        event_id = row["id"]
        # Notifica gestores em severity ≥ attention. Routine fica registrado
        # silenciosamente (Sofia já acolheu na conversa).
        if severity in ("attention", "urgent", "critical"):
            try:
                notified = self.notify_managers(
                    tenant_id=tenant_id,
                    event_id=event_id,
                    severity=severity,
                    summary=summary or raw_text[:200],
                    caregiver_phone=caregiver_phone,
                )
                if notified:
                    self.db.execute(
                        """UPDATE aia_health_caregiver_wellness_events
                           SET notified_managers = %s, notified_at = NOW()
                           WHERE id = %s""",
                        (notified, event_id),
                    )
            except Exception:
                logger.exception("wellness_notify_managers_failed", extra={"event_id": event_id})

        logger.info(
            "wellness_event_created",
            extra={
                "event_id": event_id,
                "tenant_id": tenant_id,
                "severity": severity,
                "caregiver_id": caregiver_id,
            },
        )
        return dict(row) if row else None

    # ─── Notify ──────────────────────────────────────────────────

    def notify_managers(
        self,
        *,
        tenant_id: str,
        event_id: str,
        severity: str,
        summary: str,
        caregiver_phone: str,
    ) -> list[str]:
        """Resolve gestores do tenant + dispara mensagem via outbound stream.

        Hoje resolve via role admin_tenant (todos os admin_tenant ativos
        do tenant viram destinatários). Futuro: campo gestor_responsavel
        explícito por unidade.

        Retorna lista de user_ids notificados.
        """
        managers = self.db.fetch_all(
            """SELECT id::text AS id, full_name, phone, email
               FROM aia_health_users
               WHERE tenant_id = %s
                 AND role = 'admin_tenant'
                 AND active = TRUE
                 AND phone IS NOT NULL""",
            (tenant_id,),
        )
        if not managers:
            logger.warning(
                "wellness_no_managers_to_notify",
                extra={"tenant_id": tenant_id, "event_id": event_id},
            )
            return []

        severity_label = {
            "attention": "ATENÇÃO",
            "urgent": "URGENTE",
            "critical": "CRÍTICO",
        }.get(severity, severity.upper())

        text = (
            f"[BEM-ESTAR · {severity_label}]\n\n"
            f"Cuidador (phone {caregiver_phone}) reportou sinal de fadiga/burnout.\n\n"
            f"Resumo: {summary[:300]}\n\n"
            f"NÃO é evento clínico do paciente — é gestão de pessoas. "
            f"Acolher e avaliar continuidade do atendimento.\n\n"
            f"Detalhes em /admin/system/operations/wellness "
            f"(event_id={event_id})."
        )

        notified_ids: list[str] = []
        bus = get_event_bus()
        for mgr in managers:
            try:
                bus.publish(Streams.OUTBOUND, {
                    "tenant_id": tenant_id,
                    "phone": mgr["phone"],
                    "message_type": "text",
                    "text": text,
                    "metadata": {
                        "reason": "caregiver_wellness_alert",
                        "wellness_event_id": event_id,
                        "severity": severity,
                    },
                })
                notified_ids.append(mgr["id"])
            except Exception:
                logger.warning(
                    "wellness_notify_publish_failed",
                    extra={"manager_id": mgr["id"], "event_id": event_id},
                )
        return notified_ids

    # ─── Query ───────────────────────────────────────────────────

    def list_open(
        self,
        *,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        where = ["status IN ('open', 'acknowledged')"]
        params: list = []
        if tenant_id:
            where.append("tenant_id = %s")
            params.append(tenant_id)
        params.append(limit)
        rows = self.db.fetch_all(
            f"""SELECT w.id::text AS id, w.tenant_id, w.caregiver_id::text AS caregiver_id,
                       c.full_name AS caregiver_name,
                       w.caregiver_phone, w.summary, w.raw_text, w.severity,
                       w.source_channel, w.status, w.notified_managers,
                       w.notified_at, w.acknowledged_at, w.resolved_at,
                       w.created_at, w.updated_at
                FROM aia_health_caregiver_wellness_events w
                LEFT JOIN aia_health_caregivers c ON c.id = w.caregiver_id
                WHERE {' AND '.join(where)}
                ORDER BY
                  CASE w.severity
                    WHEN 'critical' THEN 0
                    WHEN 'urgent' THEN 1
                    WHEN 'attention' THEN 2
                    ELSE 3
                  END,
                  w.created_at DESC
                LIMIT %s""",
            tuple(params),
        )
        return list(rows)

    def get_event(self, event_id: str) -> dict | None:
        row = self.db.fetch_one(
            """SELECT w.id::text AS id, w.tenant_id, w.caregiver_id::text AS caregiver_id,
                      c.full_name AS caregiver_name, c.phone AS caregiver_phone_canonical,
                      w.caregiver_phone, w.summary, w.raw_text, w.severity,
                      w.source_channel, w.status,
                      w.notified_managers, w.notified_at,
                      w.acknowledged_by_user_id::text AS acknowledged_by_user_id,
                      w.acknowledged_at, w.resolution_summary,
                      w.resolved_by_user_id::text AS resolved_by_user_id,
                      w.resolved_at, w.created_at, w.updated_at
               FROM aia_health_caregiver_wellness_events w
               LEFT JOIN aia_health_caregivers c ON c.id = w.caregiver_id
               WHERE w.id = %s""",
            (event_id,),
        )
        return dict(row) if row else None

    # ─── Workflow ────────────────────────────────────────────────

    def acknowledge(
        self, event_id: str, *, user_id: str | None,
    ) -> bool:
        try:
            self.db.execute(
                """UPDATE aia_health_caregiver_wellness_events
                   SET status = 'acknowledged',
                       acknowledged_by_user_id = %s,
                       acknowledged_at = NOW()
                   WHERE id = %s
                     AND status = 'open'""",
                (user_id, event_id),
            )
            return True
        except Exception:
            logger.exception("wellness_ack_failed", extra={"event_id": event_id})
            return False

    def resolve(
        self,
        event_id: str,
        *,
        user_id: str | None,
        summary: str | None,
    ) -> bool:
        try:
            self.db.execute(
                """UPDATE aia_health_caregiver_wellness_events
                   SET status = 'resolved',
                       resolved_by_user_id = %s,
                       resolved_at = NOW(),
                       resolution_summary = %s
                   WHERE id = %s
                     AND status IN ('open', 'acknowledged')""",
                (user_id, summary, event_id),
            )
            return True
        except Exception:
            logger.exception("wellness_resolve_failed", extra={"event_id": event_id})
            return False


_instance: CaregiverWellnessService | None = None


def get_caregiver_wellness() -> CaregiverWellnessService:
    global _instance
    if _instance is None:
        _instance = CaregiverWellnessService()
    return _instance
