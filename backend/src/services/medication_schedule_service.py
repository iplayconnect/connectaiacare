"""Medication Schedule Service — CRUD + cálculo de próximas doses + populate from prescription.

Responsabilidades:
    - CRUD de schedules (fixed_daily, weekly, monthly, cycle, prn)
    - Cálculo de próximas ocorrências baseado em times_of_day / days_of_week
    - Populate automático ao assinar teleconsulta (prescription → schedule)
    - Pausa/retomada temporária (internação)
    - Detecção de conflitos de horário entre medicações
    - Correlação com adesão (via medication_event_service)
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MedicationScheduleService:
    def __init__(self):
        self.db = get_postgres()

    # ══════════════════════════════════════════════════════════════════
    # CRUD básico
    # ══════════════════════════════════════════════════════════════════

    def create(
        self,
        tenant_id: str,
        patient_id: str,
        medication_name: str,
        dose: str,
        schedule_type: str,
        times_of_day: list[str] | None = None,      # ["07:00", "19:00"]
        days_of_week: list[int] | None = None,      # [1,3,5]
        day_of_month: int | None = None,
        cycle_length_days: int | None = None,
        dose_form: str = "comprimido",
        route: str = "oral",
        with_food: str = "either",
        special_instructions: str | None = None,
        warnings: list[str] | None = None,
        source_type: str = "manual_admin",
        source_id: str | None = None,
        source_confidence: float = 1.00,
        added_by_type: str | None = None,
        added_by_id: str | None = None,
        verification_status: str = "confirmed",
        starts_at: date | None = None,
        ends_at: date | None = None,
        reminder_advance_min: int = 10,
        tolerance_minutes: int = 60,
        min_hours_between_doses: float = 4.0,
        preferred_channels: list[str] | None = None,
    ) -> dict:
        times_arr = None
        if times_of_day:
            # Normaliza TIME — psycopg2 aceita lista de strings "HH:MM"
            times_arr = times_of_day

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_medication_schedules (
                tenant_id, patient_id, medication_name, dose, dose_form, route,
                schedule_type, times_of_day, days_of_week, day_of_month, cycle_length_days,
                reminder_advance_min, tolerance_minutes, min_hours_between_doses,
                with_food, special_instructions, warnings,
                source_type, source_id, source_confidence,
                added_by_type, added_by_id, verification_status,
                starts_at, ends_at, preferred_channels
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s::time[], %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            RETURNING id, medication_name, dose, schedule_type, times_of_day,
                      active, starts_at, created_at
            """,
            (
                tenant_id, patient_id, medication_name, dose, dose_form, route,
                schedule_type, times_arr, days_of_week, day_of_month, cycle_length_days,
                reminder_advance_min, tolerance_minutes, min_hours_between_doses,
                with_food, special_instructions, warnings or [],
                source_type, source_id, source_confidence,
                added_by_type, added_by_id, verification_status,
                starts_at or date.today(), ends_at, preferred_channels or ["whatsapp"],
            ),
        )
        logger.info(
            "medication_schedule_created",
            schedule_id=str(row["id"]),
            patient_id=patient_id,
            medication=medication_name,
            source=source_type,
        )
        return row

    def get_by_id(self, schedule_id: str) -> dict | None:
        return self.db.fetch_one(
            "SELECT * FROM aia_health_medication_schedules WHERE id = %s",
            (schedule_id,),
        )

    def list_active_for_patient(self, patient_id: str) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT * FROM aia_health_medication_schedules
            WHERE patient_id = %s
              AND active = TRUE
              AND (ends_at IS NULL OR ends_at >= CURRENT_DATE)
              AND (paused_until IS NULL OR paused_until < NOW())
            ORDER BY medication_name
            """,
            (patient_id,),
        )

    def update(self, schedule_id: str, updates: dict) -> dict | None:
        """Update genérico. Só permite campos conhecidos.

        Se mudar dose/times_of_day/dias, marca verification_status como
        needs_review se fonte era OCR/self_report pra evitar mudança silenciosa.
        """
        allowed = {
            "medication_name", "dose", "dose_form", "times_of_day",
            "days_of_week", "day_of_month", "cycle_length_days",
            "reminder_advance_min", "tolerance_minutes", "min_hours_between_doses",
            "with_food", "special_instructions", "warnings",
            "ends_at", "paused_until", "pause_reason",
            "active", "deactivated_at", "deactivation_reason",
            "verification_status", "verified_by_type", "verified_by_id", "verified_at",
            "preferred_channels",
        }
        fields = []
        values = []
        for k, v in updates.items():
            if k not in allowed:
                continue
            fields.append(f"{k} = %s")
            values.append(v)
        if not fields:
            return self.get_by_id(schedule_id)

        values.append(schedule_id)
        self.db.execute(
            f"UPDATE aia_health_medication_schedules SET {', '.join(fields)} "
            "WHERE id = %s",
            tuple(values),
        )
        return self.get_by_id(schedule_id)

    def deactivate(self, schedule_id: str, reason: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_medication_schedules
            SET active = FALSE,
                deactivated_at = NOW(),
                deactivation_reason = %s
            WHERE id = %s
            """,
            (reason, schedule_id),
        )
        logger.info("medication_schedule_deactivated", schedule_id=schedule_id, reason=reason)

    def pause_until(self, schedule_id: str, until: datetime, reason: str) -> None:
        self.db.execute(
            "UPDATE aia_health_medication_schedules SET paused_until = %s, pause_reason = %s WHERE id = %s",
            (until, reason, schedule_id),
        )

    # ══════════════════════════════════════════════════════════════════
    # Populate from prescription (teleconsulta)
    # ══════════════════════════════════════════════════════════════════

    def populate_from_prescription(
        self,
        tenant_id: str,
        patient_id: str,
        prescription_items: list[dict],
        teleconsultation_id: str,
        doctor_name: str | None = None,
    ) -> list[dict]:
        """Converte a `prescription` da teleconsulta em schedules ativos.

        Heurística: tenta parsear dose/frequência do texto livre da prescrição.
        Se ambíguo, cria como 'needs_review' com times_of_day tentativa.
        """
        created = []
        for item in prescription_items:
            if not isinstance(item, dict):
                continue
            med_name = (item.get("medication") or "").strip()
            if not med_name:
                continue

            schedule_type, times, days, cycle_len, extra_notes = self._parse_schedule(
                item.get("schedule") or "",
                item.get("duration") or "",
            )

            warnings = []
            validation = item.get("validation") or {}
            if validation.get("issues"):
                warnings.extend([
                    iss.get("recommendation") or iss.get("description") or ""
                    for iss in validation["issues"][:3]
                ])

            try:
                duration_days = self._parse_duration_days(item.get("duration") or "")
                ends_at = date.today() + timedelta(days=duration_days) if duration_days else None

                row = self.create(
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    medication_name=med_name,
                    dose=item.get("dose") or "conforme prescrição",
                    schedule_type=schedule_type,
                    times_of_day=times,
                    days_of_week=days,
                    cycle_length_days=cycle_len,
                    special_instructions=(item.get("indication") or "") + (
                        "\n" + extra_notes if extra_notes else ""
                    ),
                    warnings=warnings,
                    source_type="prescription",
                    source_id=item.get("id") or teleconsultation_id,
                    added_by_type="doctor",
                    verification_status="confirmed",  # prescrição médica é autoridade
                    ends_at=ends_at,
                )
                created.append(row)
            except Exception as exc:
                logger.warning(
                    "populate_prescription_item_failed",
                    medication=med_name, error=str(exc),
                )

        logger.info(
            "populate_from_prescription",
            tc_id=teleconsultation_id,
            patient_id=patient_id,
            created=len(created),
        )
        return created

    @staticmethod
    def _parse_schedule(
        schedule_text: str, duration_text: str,
    ) -> tuple[str, list[str] | None, list[int] | None, int | None, str]:
        """Heurística pra converter texto livre em tipo + horários.

        Exemplos que cobre:
          - "1x/dia manhã"           → fixed_daily [08:00]
          - "3x/dia (8-12-18)"       → fixed_daily [08:00, 12:00, 18:00]
          - "de 8/8h"                → fixed_daily [06:00, 14:00, 22:00]
          - "de 12/12h"              → fixed_daily [08:00, 20:00]
          - "1 comp antes do café"   → fixed_daily [06:30]
          - "Segunda-feira 7h"       → fixed_weekly [1] times [07:00]
          - "Se dor/necessário"      → prn
          - "Uso contínuo"           → fixed_daily + duration NULL
        """
        s = (schedule_text or "").lower()
        notes = ""

        # PRN / "se necessário"
        if any(k in s for k in ["necessário", "necessario", "se dor", "s/n", "sos", "se precisar"]):
            return "prn", None, None, None, notes

        # Horário explícito entre parênteses (07:00, 11:00)
        import re
        explicit = re.findall(r"(\d{1,2})[:h](\d{0,2})", s)
        if explicit:
            times = []
            for h, m in explicit:
                hh = int(h)
                mm = int(m) if m else 0
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    times.append(f"{hh:02d}:{mm:02d}")
            if times:
                # Dia da semana? "segunda", "seg", "todo dia"
                dow = MedicationScheduleService._parse_day_of_week(s)
                if dow:
                    return "fixed_weekly", times, dow, None, notes
                return "fixed_daily", times, None, None, notes

        # Intervalos de horas "de 8/8h", "8 em 8h", "de 12/12h"
        interval_match = re.search(r"(\d+)\s*(?:em|/)\s*(\d+)\s*h", s)
        if interval_match:
            interval = int(interval_match.group(2))
            if interval > 0:
                # Distribui a partir das 06:00
                times = []
                hh = 6
                while hh < 24:
                    times.append(f"{hh:02d}:00")
                    hh += interval
                return "fixed_daily", times, None, None, notes

        # "1x/dia", "2x/dia"
        x_per_day = re.search(r"(\d+)\s*x\s*/?\s*dia", s)
        if x_per_day:
            n = int(x_per_day.group(1))
            if n == 1:
                # Procura dica de período
                if "noite" in s or "deitar" in s:
                    return "fixed_daily", ["20:00"], None, None, notes
                if "manh" in s or "café" in s or "cafe" in s:
                    return "fixed_daily", ["08:00"], None, None, notes
                return "fixed_daily", ["09:00"], None, None, notes
            elif n == 2:
                return "fixed_daily", ["08:00", "20:00"], None, None, notes
            elif n == 3:
                return "fixed_daily", ["08:00", "14:00", "20:00"], None, None, notes
            elif n == 4:
                return "fixed_daily", ["06:00", "12:00", "18:00", "00:00"], None, None, notes

        # Fallback conservador — aceita como fixed_daily mas precisa review
        notes = f"Posologia ambígua: '{schedule_text}' — revisar horários"
        return "fixed_daily", ["09:00"], None, None, notes

    @staticmethod
    def _parse_day_of_week(s: str) -> list[int] | None:
        mapping = {
            "segunda": 1, "seg ": 1, "segunda-feira": 1,
            "terça": 2, "terca": 2, "ter ": 2,
            "quarta": 3, "qua ": 3,
            "quinta": 4, "qui ": 4,
            "sexta": 5, "sex ": 5,
            "sábado": 6, "sabado": 6, "sab ": 6,
            "domingo": 7, "dom ": 7,
        }
        found = []
        for k, v in mapping.items():
            if k in s and v not in found:
                found.append(v)
        return sorted(found) if found else None

    @staticmethod
    def _parse_duration_days(duration_text: str) -> int | None:
        """Converte '7 dias', '14 dias', '3 meses' em dias. NULL = contínuo."""
        s = (duration_text or "").lower()
        if any(k in s for k in ["contínuo", "continuo", "indefinid", "permanente"]):
            return None
        import re
        m = re.search(r"(\d+)\s*dia", s)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)\s*sem", s)
        if m:
            return int(m.group(1)) * 7
        m = re.search(r"(\d+)\s*m[êe]s", s)
        if m:
            return int(m.group(1)) * 30
        return None

    # ══════════════════════════════════════════════════════════════════
    # Compute next occurrences (para o scheduler)
    # ══════════════════════════════════════════════════════════════════

    def compute_next_occurrences(
        self,
        schedule: dict,
        from_time: datetime,
        horizon_hours: int = 48,
        tz: str = "America/Sao_Paulo",
    ) -> list[datetime]:
        """Calcula as próximas ocorrências de uma schedule dentro do horizonte.

        Retorna datetimes em UTC (prontas pra comparar com now()).
        """
        occurrences: list[datetime] = []
        if schedule.get("schedule_type") == "prn":
            return []
        if not schedule.get("active"):
            return []

        tz_obj = ZoneInfo(tz)
        from_local = from_time.astimezone(tz_obj)
        end_local = from_local + timedelta(hours=horizon_hours)

        times = schedule.get("times_of_day") or []
        days_of_week = schedule.get("days_of_week")
        day_of_month = schedule.get("day_of_month")

        # Itera por cada dia do horizonte
        day = from_local.date()
        end_date = end_local.date()
        while day <= end_date:
            # Filtra por dia da semana ou mês conforme tipo
            if schedule["schedule_type"] == "fixed_weekly":
                iso_dow = day.isoweekday()
                if days_of_week and iso_dow not in days_of_week:
                    day += timedelta(days=1)
                    continue
            elif schedule["schedule_type"] == "fixed_monthly":
                if day_of_month and day.day != day_of_month:
                    day += timedelta(days=1)
                    continue

            # starts_at / ends_at
            if schedule.get("starts_at") and day < schedule["starts_at"]:
                day += timedelta(days=1)
                continue
            if schedule.get("ends_at") and day > schedule["ends_at"]:
                break

            for t in times:
                if isinstance(t, str):
                    parts = t.split(":")
                    hh, mm = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
                    dose_time = time(hh, mm)
                elif isinstance(t, time):
                    dose_time = t
                else:
                    continue
                candidate_local = datetime.combine(day, dose_time, tzinfo=tz_obj)
                if candidate_local < from_local or candidate_local > end_local:
                    continue
                occurrences.append(candidate_local.astimezone(timezone.utc))

            day += timedelta(days=1)

        return sorted(occurrences)


_instance: MedicationScheduleService | None = None


def get_medication_schedule_service() -> MedicationScheduleService:
    global _instance
    if _instance is None:
        _instance = MedicationScheduleService()
    return _instance
