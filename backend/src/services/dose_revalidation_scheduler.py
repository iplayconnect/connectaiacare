"""Dose Revalidation Scheduler — worker em background que re-roda o motor
de cruzamentos clínicos sobre as prescrições ATIVAS periodicamente.

Por que? As regras (interações, contraindicações, dose máxima) podem ser
adicionadas/alteradas pelo admin via /admin/regras-clinicas. Uma prescrição
que era segura na hora de criar pode passar a ser de alto risco depois que
uma nova interação é cadastrada, ou após o paciente ganhar uma condição
nova (ex: ganhar 'asma' faz propranolol virar contraindicação).

Comportamento:
    - Rodada principal: 1× / semana (default).
    - Para cada medication_schedule ativa: chama dose_validator.validate
      com o paciente atual.
    - Se severity ≥ warning_strong → cria alerta em aia_health_alerts,
      com dedupe por (patient, schedule, conjunto de issue codes) na
      última semana — evita spam.
    - Update last_revalidated_at e last_revalidation_severity na schedule
      pra UI mostrar.

Concorrência: pg_try_advisory_lock próprio (DOSE_REVALIDATION_LOCK_KEY).
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from datetime import datetime, timezone

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

DOSE_REVALIDATION_LOCK_KEY = 1428367219

# Intervalo entre ticks. Default: 6h. Em cada tick, escolhe schedules cujo
# last_revalidated_at é mais antigo que REVALIDATION_INTERVAL_HOURS.
TICK_INTERVAL_SEC = int(os.getenv("DOSE_REVAL_TICK_SEC", "21600"))  # 6h
REVALIDATION_INTERVAL_HOURS = int(
    os.getenv("DOSE_REVALIDATION_INTERVAL_HOURS", "168")
)  # 7 dias
BATCH_SIZE = int(os.getenv("DOSE_REVAL_BATCH_SIZE", "100"))


class DoseRevalidationScheduler:
    def __init__(self):
        self.db = get_postgres()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="dose-revalidation", daemon=True,
        )
        self._thread.start()
        logger.info(
            "dose_revalidation_started",
            worker_id=self._worker_id,
            tick_sec=TICK_INTERVAL_SEC,
            reval_interval_h=REVALIDATION_INTERVAL_HOURS,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=30)

    # ──────────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        # Pequeno delay no boot pra evitar race com migrações/seeds.
        self._stop_event.wait(60)
        while not self._stop_event.is_set():
            try:
                if self._try_acquire_lock():
                    try:
                        n = self._tick()
                        if n:
                            logger.info(
                                "dose_revalidation_tick_done",
                                schedules_processed=n,
                            )
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("dose_revalidation_tick_error", error=str(exc))
            self._stop_event.wait(TICK_INTERVAL_SEC)

    def _try_acquire_lock(self) -> bool:
        row = self.db.fetch_one(
            "SELECT pg_try_advisory_lock(%s) AS got", (DOSE_REVALIDATION_LOCK_KEY,),
        )
        return bool(row and row.get("got"))

    def _release_lock(self) -> None:
        try:
            self.db.execute(
                "SELECT pg_advisory_unlock(%s)", (DOSE_REVALIDATION_LOCK_KEY,),
            )
        except Exception:
            pass

    def _tick(self) -> int:
        """Pega o batch de schedules elegíveis e revalida cada uma."""
        from src.services import dose_validator  # late import (cycle-safe)

        rows = self.db.fetch_all(
            f"""
            SELECT s.id, s.tenant_id, s.patient_id, s.medication_name,
                   s.dose, s.times_of_day, s.route, s.schedule_type,
                   p.full_name AS patient_name, p.birth_date,
                   p.allergies, p.conditions
            FROM aia_health_medication_schedules s
            LEFT JOIN aia_health_patients p ON p.id = s.patient_id
            WHERE s.active = TRUE
              AND s.verification_status IN ('confirmed', 'needs_review')
              AND (
                  s.last_revalidated_at IS NULL
                  OR s.last_revalidated_at <
                     NOW() - INTERVAL '{REVALIDATION_INTERVAL_HOURS} hours'
              )
            ORDER BY s.last_revalidated_at ASC NULLS FIRST
            LIMIT {BATCH_SIZE}
            """,
        )
        processed = 0
        for r in rows:
            try:
                self._revalidate_one(r, dose_validator)
                processed += 1
            except Exception as exc:
                logger.error(
                    "dose_revalidation_one_failed",
                    schedule_id=str(r.get("id")),
                    error=str(exc),
                )
        return processed

    def _revalidate_one(self, row: dict, dose_validator) -> None:
        sched_id = row["id"]
        tenant_id = row["tenant_id"]
        patient_id = row["patient_id"]
        # times_of_day vem do PG como list[time] — converte pra "HH:MM"
        tods_raw = row.get("times_of_day") or []
        tods = []
        for t in tods_raw:
            if hasattr(t, "strftime"):
                tods.append(t.strftime("%H:%M"))
            elif isinstance(t, str):
                tods.append(t[:5])

        patient = {
            "id": patient_id,
            "full_name": row.get("patient_name"),
            "birth_date": row.get("birth_date"),
            "allergies": row.get("allergies") or [],
            "conditions": row.get("conditions") or [],
        }

        try:
            result = dose_validator.validate(
                medication_name=row["medication_name"],
                dose=row["dose"],
                times_of_day=tods,
                route=(row.get("route") or "oral").lower(),
                patient=patient,
                schedule_type=row.get("schedule_type"),
            ).to_dict()
        except Exception as exc:
            logger.exception(
                "dose_revalidation_validator_failed",
                schedule_id=str(sched_id),
            )
            return

        severity = result.get("severity")
        # Sempre marca timestamps na schedule pra UI/observabilidade
        self.db.execute(
            """
            UPDATE aia_health_medication_schedules
            SET last_revalidated_at = NOW(),
                last_revalidation_severity = %s
            WHERE id = %s
            """,
            (severity, sched_id),
        )

        if severity not in ("warning_strong", "block"):
            return

        # Dedupe: se já houver alerta aberto OU criado nos últimos 7 dias
        # com o MESMO conjunto de issue codes pra essa schedule, skip.
        issue_codes = sorted({
            i.get("code") for i in (result.get("issues") or []) if i.get("code")
        })
        recent = self.db.fetch_one(
            """
            SELECT id FROM aia_health_alerts
            WHERE patient_id = %s
              AND tenant_id = %s
              AND metadata ? 'revalidation_schedule_id'
              AND metadata->>'revalidation_schedule_id' = %s
              AND COALESCE(metadata->>'issue_codes_key', '') = %s
              AND (
                  resolved_at IS NULL
                  OR created_at > NOW() - INTERVAL '7 days'
              )
            LIMIT 1
            """,
            (
                str(patient_id),
                tenant_id,
                str(sched_id),
                ",".join(issue_codes),
            ),
        )
        if recent:
            return

        # Mapeamento de severity → level do alerta
        level = "high" if severity == "block" else "medium"
        title = f"Revalidação semanal: {row['medication_name']} ({row['dose']})"
        first_issue = (result.get("issues") or [{}])[0].get("message", "")
        description = (
            f"O motor de cruzamentos detectou risco em prescrição ativa. "
            f"Severity: {severity}. {first_issue}"
        )
        recommended = [
            "Revisar a prescrição com o médico responsável",
            "Avaliar se há alternativa terapêutica",
            "Confirmar dados de função renal/hepática se aplicável",
        ]
        metadata = {
            "validation": result,
            "revalidation_schedule_id": str(sched_id),
            "issue_codes_key": ",".join(issue_codes),
            "source": "dose_revalidation_scheduler",
        }
        self.db.execute(
            """
            INSERT INTO aia_health_alerts
                (tenant_id, patient_id, level, title, description,
                 recommended_actions, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                str(patient_id),
                level,
                title,
                description,
                recommended,
                json.dumps(metadata),
            ),
        )
        logger.info(
            "dose_revalidation_alert_created",
            schedule_id=str(sched_id),
            patient_id=str(patient_id),
            severity=severity,
        )


_singleton: DoseRevalidationScheduler | None = None


def get_dose_revalidation_scheduler() -> DoseRevalidationScheduler:
    global _singleton
    if _singleton is None:
        _singleton = DoseRevalidationScheduler()
    return _singleton
