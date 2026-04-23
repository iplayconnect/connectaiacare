"""Medication Event Service — cada dose prevista + estado + adesão.

Responsabilidades:
    - Materializa events a partir de schedules (roda periodicamente)
    - Registra confirmação (taken/missed/refused)
    - Calcula % adesão por paciente / por medicamento
    - Correlaciona inbound WhatsApp com event aberto
    - Detecta padrões (3 missed consecutivos → escalação)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.medication_schedule_service import get_medication_schedule_service
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MedicationEventService:
    def __init__(self):
        self.db = get_postgres()
        self.schedules = get_medication_schedule_service()

    # ══════════════════════════════════════════════════════════════════
    # Materialização de events a partir de schedules
    # ══════════════════════════════════════════════════════════════════

    def materialize_for_patient(
        self,
        patient_id: str,
        horizon_hours: int = 24,
        tz: str = "America/Sao_Paulo",
    ) -> int:
        """Cria events pra próximas X horas baseado nos schedules ativos.

        Idempotente — ON CONFLICT não cria duplicata de mesmo (schedule, scheduled_at).
        Retorna número de events criados (novos).
        """
        schedules = self.schedules.list_active_for_patient(patient_id)
        now = datetime.now(timezone.utc)
        created = 0

        for sched in schedules:
            # PRN não gera lembrete
            if sched.get("schedule_type") == "prn":
                continue
            occurrences = self.schedules.compute_next_occurrences(
                sched, from_time=now, horizon_hours=horizon_hours, tz=tz,
            )
            for occ in occurrences:
                try:
                    self.db.execute(
                        """
                        INSERT INTO aia_health_medication_events
                            (schedule_id, patient_id, tenant_id, scheduled_at, status)
                        VALUES (%s, %s, %s, %s, 'scheduled')
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            sched["id"], patient_id,
                            sched["tenant_id"], occ,
                        ),
                    )
                    created += 1
                except Exception as exc:
                    logger.warning(
                        "event_materialize_failed",
                        schedule_id=str(sched["id"]), error=str(exc),
                    )

        if created:
            logger.info(
                "medication_events_materialized",
                patient_id=patient_id, count=created,
            )
        return created

    def materialize_for_all_active_patients(self, horizon_hours: int = 24) -> int:
        """Worker helper: roda materialização pra todos os pacientes com schedules ativos."""
        rows = self.db.fetch_all(
            """
            SELECT DISTINCT patient_id
            FROM aia_health_medication_schedules
            WHERE active = TRUE
              AND (ends_at IS NULL OR ends_at >= CURRENT_DATE)
              AND schedule_type <> 'prn'
            """
        )
        total = 0
        for r in rows:
            total += self.materialize_for_patient(
                str(r["patient_id"]), horizon_hours=horizon_hours,
            )
        return total

    # ══════════════════════════════════════════════════════════════════
    # Listagem / consulta
    # ══════════════════════════════════════════════════════════════════

    def list_upcoming(
        self, patient_id: str, hours: int = 24,
    ) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT e.*,
                   s.medication_name, s.dose, s.dose_form, s.special_instructions,
                   s.with_food, s.warnings
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.patient_id = %s
              AND e.scheduled_at >= NOW() - INTERVAL '2 hours'
              AND e.scheduled_at <= NOW() + make_interval(hours => %s)
            ORDER BY e.scheduled_at ASC
            LIMIT 80
            """,
            (patient_id, hours),
        )

    def list_history(
        self, patient_id: str, days: int = 7,
    ) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT e.*, s.medication_name, s.dose
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.patient_id = %s
              AND e.scheduled_at >= NOW() - make_interval(days => %s)
              AND e.scheduled_at <= NOW() + INTERVAL '1 hour'
            ORDER BY e.scheduled_at DESC
            LIMIT 200
            """,
            (patient_id, days),
        )

    def get_pending_reminders(
        self, lookahead_minutes: int = 15,
    ) -> list[dict]:
        """Events que precisam ter lembrete enviado agora (dentro dos próx N min)."""
        return self.db.fetch_all(
            """
            SELECT e.*,
                   s.medication_name, s.dose, s.special_instructions,
                   s.preferred_channels, s.reminder_advance_min,
                   s.patient_id
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.status = 'scheduled'
              AND e.scheduled_at - (s.reminder_advance_min || ' minutes')::interval <= NOW() + make_interval(mins => %s)
              AND e.scheduled_at > NOW() - INTERVAL '5 minutes'
              AND s.active = TRUE
              AND (s.paused_until IS NULL OR s.paused_until < NOW())
            ORDER BY e.scheduled_at ASC
            LIMIT 50
            """,
            (lookahead_minutes,),
        )

    def get_overdue(self, tolerance_minutes: int | None = None) -> list[dict]:
        """Events que tiveram lembrete enviado mas não foram confirmados dentro da janela."""
        return self.db.fetch_all(
            """
            SELECT e.*, s.medication_name, s.dose, s.tolerance_minutes, s.patient_id
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.status = 'reminder_sent'
              AND e.scheduled_at + (s.tolerance_minutes || ' minutes')::interval < NOW()
            ORDER BY e.scheduled_at ASC
            """
        )

    # ══════════════════════════════════════════════════════════════════
    # Atualização de estado
    # ══════════════════════════════════════════════════════════════════

    def mark_reminder_sent(
        self, event_id: str, channel: str, external_ref: str | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_medication_events
            SET status = 'reminder_sent',
                reminder_sent_at = NOW(),
                reminder_channel = %s,
                reminder_external_ref = %s
            WHERE id = %s AND status = 'scheduled'
            """,
            (channel, external_ref, event_id),
        )

    def mark_taken(
        self,
        event_id: str,
        confirmed_by: str = "patient",
        actual_dose: str | None = None,
        notes: str | None = None,
        response_external_ref: str | None = None,
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_medication_events
            SET status = 'taken',
                confirmed_at = NOW(),
                confirmed_by = %s,
                actual_dose_taken = COALESCE(%s, actual_dose_taken),
                notes = COALESCE(%s, notes),
                response_external_ref = %s
            WHERE id = %s
            """,
            (confirmed_by, actual_dose, notes, response_external_ref, event_id),
        )
        logger.info("medication_event_taken", event_id=event_id, by=confirmed_by)

    def mark_refused(self, event_id: str, notes: str | None = None) -> None:
        self.db.execute(
            """
            UPDATE aia_health_medication_events
            SET status = 'refused', confirmed_at = NOW(), notes = %s
            WHERE id = %s
            """,
            (notes, event_id),
        )

    def mark_missed(self, event_id: str) -> None:
        self.db.execute(
            "UPDATE aia_health_medication_events SET status = 'missed' WHERE id = %s",
            (event_id,),
        )

    def mark_skipped(self, event_id: str, reason: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_medication_events
            SET status = 'skipped', confirmed_at = NOW(), notes = %s
            WHERE id = %s
            """,
            (reason, event_id),
        )

    # ══════════════════════════════════════════════════════════════════
    # Adesão — métricas
    # ══════════════════════════════════════════════════════════════════

    def adherence_summary(
        self, patient_id: str, days: int = 30,
    ) -> dict:
        """Taxa de adesão nos últimos N dias (por paciente)."""
        row = self.db.fetch_one(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('taken')) AS taken,
                COUNT(*) FILTER (WHERE status IN ('missed')) AS missed,
                COUNT(*) FILTER (WHERE status IN ('refused')) AS refused,
                COUNT(*) FILTER (WHERE status IN ('skipped')) AS skipped,
                COUNT(*) AS total_completed
            FROM aia_health_medication_events
            WHERE patient_id = %s
              AND scheduled_at >= NOW() - make_interval(days => %s)
              AND scheduled_at < NOW()
              AND status NOT IN ('scheduled', 'reminder_sent', 'paused', 'cancelled')
            """,
            (patient_id, days),
        )
        total = (row or {}).get("total_completed") or 0
        taken = (row or {}).get("taken") or 0
        pct = round((taken / total * 100), 1) if total > 0 else None
        return {
            "taken": taken,
            "missed": (row or {}).get("missed") or 0,
            "refused": (row or {}).get("refused") or 0,
            "skipped": (row or {}).get("skipped") or 0,
            "total": total,
            "adherence_pct": pct,
            "period_days": days,
        }

    def adherence_by_medication(
        self, patient_id: str, days: int = 30,
    ) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT s.medication_name,
                   s.dose,
                   COUNT(*) FILTER (WHERE e.status = 'taken') AS taken,
                   COUNT(*) FILTER (WHERE e.status = 'missed') AS missed,
                   COUNT(*) FILTER (WHERE e.status IN ('refused','skipped')) AS refused_skipped,
                   COUNT(*) AS total,
                   ROUND(100.0 *
                         COUNT(*) FILTER (WHERE e.status = 'taken') /
                         NULLIF(COUNT(*) FILTER (WHERE e.status IN ('taken','missed','refused','skipped')), 0),
                         1) AS adherence_pct
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.patient_id = %s
              AND e.scheduled_at >= NOW() - make_interval(days => %s)
              AND e.scheduled_at < NOW()
            GROUP BY s.medication_name, s.dose
            ORDER BY s.medication_name
            """,
            (patient_id, days),
        )

    def detect_consecutive_missed(
        self, patient_id: str, threshold: int = 3,
    ) -> list[dict]:
        """Detecta schedules com N missed consecutivos recentes (alerta família)."""
        return self.db.fetch_all(
            """
            WITH recent AS (
                SELECT e.schedule_id, e.status, e.scheduled_at,
                       s.medication_name,
                       ROW_NUMBER() OVER (PARTITION BY e.schedule_id ORDER BY e.scheduled_at DESC) AS rn
                FROM aia_health_medication_events e
                JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
                WHERE e.patient_id = %s
                  AND e.scheduled_at >= NOW() - INTERVAL '7 days'
                  AND e.scheduled_at < NOW()
                  AND e.status IN ('taken', 'missed', 'refused', 'skipped')
            ),
            last_n AS (
                SELECT schedule_id, medication_name,
                       ARRAY_AGG(status ORDER BY scheduled_at DESC) AS recent_statuses,
                       COUNT(*) FILTER (WHERE status = 'missed' AND rn <= %s) AS missed_in_last_n
                FROM recent
                WHERE rn <= %s
                GROUP BY schedule_id, medication_name
            )
            SELECT *
            FROM last_n
            WHERE missed_in_last_n >= %s
            """,
            (patient_id, threshold, threshold, threshold),
        )

    # ══════════════════════════════════════════════════════════════════
    # Correlação com WhatsApp inbound
    # ══════════════════════════════════════════════════════════════════

    def find_open_event_for_confirmation(
        self, patient_id: str, now_utc: datetime | None = None,
    ) -> dict | None:
        """Encontra event mais recente com reminder_sent aguardando confirmação."""
        now_utc = now_utc or datetime.now(timezone.utc)
        return self.db.fetch_one(
            """
            SELECT e.*, s.medication_name
            FROM aia_health_medication_events e
            JOIN aia_health_medication_schedules s ON s.id = e.schedule_id
            WHERE e.patient_id = %s
              AND e.status = 'reminder_sent'
              AND e.scheduled_at > NOW() - INTERVAL '3 hours'
            ORDER BY e.scheduled_at DESC
            LIMIT 1
            """,
            (patient_id,),
        )


_instance: MedicationEventService | None = None


def get_medication_event_service() -> MedicationEventService:
    global _instance
    if _instance is None:
        _instance = MedicationEventService()
    return _instance
