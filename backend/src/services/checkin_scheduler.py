"""Check-in Scheduler — worker background que dispara ações temporais do care event.

Varre `aia_health_care_event_checkins` a cada N segundos em busca de check-ins
com `scheduled_for <= NOW()` e `status='scheduled'`. Para cada um, executa a ação
correspondente ao `kind`:

    - pattern_analysis    → roda PatternDetectionService + envia alerta ao cuidador
    - status_update       → pergunta ao cuidador como o paciente está
    - closure_check       → decide encerrar o evento (ou manter se resposta recente)
    - post_escalation     → escalação para próximo nível (se nível atual não respondeu)

Concorrência (2+ workers Gunicorn):
    Usa pg_try_advisory_lock para garantir que APENAS UM worker roda o loop em
    cada tick. Os outros pegam o lock em retry, sem duplicar mensagens.

Lifecycle:
    - Thread daemon iniciada no `app.py` quando `ENABLE_SCHEDULER=true`.
    - Graceful shutdown via signal (SIGTERM propaga pro gunicorn, que mata o thread).
"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.care_event_service import get_care_event_service
from src.services.evolution import get_evolution
from src.services.patient_service import get_patient_service
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Lock advisory do Postgres — número arbitrário único pra esse scheduler
SCHEDULER_ADVISORY_LOCK_ID = 20260420

# Intervalo entre varreduras (segundos)
DEFAULT_POLL_INTERVAL_SECONDS = 30

# Max check-ins processados por tick (evita congestionamento)
MAX_PER_TICK = 20


class CheckinScheduler:
    def __init__(self, poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS):
        self.poll_interval = poll_interval
        self.db = get_postgres()
        self.events = get_care_event_service()
        self.patients = get_patient_service()
        self.evo = get_evolution()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- lifecycle ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="CheckinScheduler", daemon=True)
        self._thread.start()
        logger.info("checkin_scheduler_started", poll_interval=self.poll_interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("checkin_scheduler_stopped")

    # ---------- loop principal ----------
    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick_with_lock()
            except Exception:
                logger.error("scheduler_tick_error", traceback=traceback.format_exc())
            # Wait interruptible (pra stop rápido)
            self._stop.wait(self.poll_interval)

    def _tick_with_lock(self) -> None:
        """Tenta adquirir advisory lock; se não pegar, outro worker está cuidando."""
        with self.db.get_cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (SCHEDULER_ADVISORY_LOCK_ID,))
            got = cur.fetchone()
            locked = bool(got and got[0]) if not isinstance(got, dict) else bool(list(got.values())[0])

        if not locked:
            # Outro worker rodou. Tudo bem.
            return

        try:
            self._tick()
        finally:
            with self.db.get_cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (SCHEDULER_ADVISORY_LOCK_ID,))

    def _tick(self) -> None:
        due = self.events.list_due_checkins(limit=MAX_PER_TICK)
        if not due:
            return

        logger.info("scheduler_tick_processing", count=len(due))

        # Também expira events que passaram do TTL sem resolver
        self._expire_stale_events()

        for checkin in due:
            try:
                self._handle_checkin(checkin)
            except Exception as exc:
                logger.error(
                    "checkin_handler_error",
                    checkin_id=str(checkin["id"]),
                    kind=checkin.get("kind"),
                    error=str(exc),
                )
                self.events.mark_checkin_failed(str(checkin["id"]), str(exc))

    def _expire_stale_events(self) -> None:
        """Marca como expired qualquer evento ativo cujo expires_at passou."""
        rows = self.db.fetch_all(
            """
            SELECT id FROM aia_health_care_events
            WHERE expires_at <= NOW()
              AND status NOT IN ('resolved', 'expired')
            LIMIT 50
            """
        )
        for r in rows:
            self.events.expire_silent(str(r["id"]))

    # ---------- handlers por kind ----------
    def _handle_checkin(self, checkin: dict) -> None:
        kind = checkin.get("kind")
        handler = {
            "pattern_analysis": self._handle_pattern_analysis,
            "status_update": self._handle_status_update,
            "closure_check": self._handle_closure_check,
            "post_escalation": self._handle_post_escalation,
        }.get(kind)

        if not handler:
            logger.warning("checkin_unknown_kind", kind=kind, checkin_id=str(checkin["id"]))
            self.events.mark_checkin_failed(str(checkin["id"]), f"unknown_kind: {kind}")
            return

        handler(checkin)

    # ---------- pattern_analysis ----------
    def _handle_pattern_analysis(self, checkin: dict) -> None:
        # Import local pra evitar ciclo
        from src.services.pattern_detection_service import get_pattern_detection_service

        event = self.events.get_by_id(str(checkin["event_id"]))
        if not event or event["status"] in ("resolved", "expired"):
            self.events.mark_checkin_failed(str(checkin["id"]), "event_not_active")
            return

        patient = self.patients.get_by_id(str(event["patient_id"]))
        if not patient:
            self.events.mark_checkin_failed(str(checkin["id"]), "patient_missing")
            return

        # Transcrição do relato inicial
        initial_report_id = event.get("initial_report_id")
        transcript = ""
        if initial_report_id:
            r = self.db.fetch_one(
                "SELECT transcription FROM aia_health_reports WHERE id = %s",
                (initial_report_id,),
            )
            transcript = (r or {}).get("transcription") or ""

        result = get_pattern_detection_service().detect(
            patient_id=str(event["patient_id"]),
            current_event_id=str(event["id"]),
            current_transcript=transcript,
            current_event_tags=event.get("event_tags") or [],
            current_classification=event.get("current_classification"),
        )
        self.events.mark_pattern_analyzed(str(event["id"]))

        if not result.get("has_pattern"):
            # Sem padrão relevante — não incomoda o cuidador, só marca processado
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent="(sem padrão relevante detectado)",
            )
            return

        # Envia alerta ao cuidador via WhatsApp
        headline = result.get("headline") or "📋 Padrão identificado no histórico"
        observation = result.get("observation_suggestion")
        body_lines = [headline]
        if observation:
            body_lines.append(f"\n💡 Sugestão: {observation}")
        if (result.get("details") or []):
            body_lines.append("")
            body_lines.extend(f"• {d}" for d in result["details"][:3])

        message = "\n".join(body_lines)
        self.evo.send_text(checkin["caregiver_phone"], message)
        self.events.mark_checkin_sent(str(checkin["id"]), message_sent=message)
        self.events.append_message(
            str(event["id"]),
            {"role": "assistant", "kind": "pattern_alert", "text": message},
        )

        # Se o padrão sugerir escalação, atualiza classificação e dispara
        suggested = result.get("suggested_classification")
        if suggested and suggested != event.get("current_classification"):
            self.events.update_classification(
                str(event["id"]),
                suggested,
                reasoning=f"Escalação por padrão histórico: {result.get('kind')}",
            )
            # Escalação só acontece se chegou em urgent/critical
            from src.services.escalation_service import get_escalation_service
            esc = get_escalation_service()
            if esc.should_escalate(suggested):
                esc.escalate_initial(
                    event=self.events.get_by_id(str(event["id"])),
                    patient=patient,
                    classification=suggested,
                    analysis={"summary": headline},
                )

    # ---------- status_update ----------
    def _handle_status_update(self, checkin: dict) -> None:
        event = self.events.get_by_id(str(checkin["event_id"]))
        if not event or event["status"] in ("resolved", "expired"):
            self.events.mark_checkin_failed(str(checkin["id"]), "event_not_active")
            return

        patient = self.patients.get_by_id(str(event["patient_id"]))
        patient_ref = (
            patient.get("nickname") or patient.get("full_name")
        ) if patient else "o paciente"

        message = (
            f"👋 Como está *{patient_ref}* agora?\n\n"
            f"Os cuidados já foram iniciados? Houve mudança no quadro?\n\n"
            f"Pode responder em áudio ou texto, o que for mais prático pra você."
        )

        self.evo.send_text(checkin["caregiver_phone"], message)
        self.events.mark_checkin_sent(str(checkin["id"]), message_sent=message)
        self.events.touch_check_in(str(event["id"]))
        self.events.update_status(str(event["id"]), "awaiting_status_update")
        self.events.append_message(
            str(event["id"]),
            {"role": "assistant", "kind": "status_check_in", "text": message},
        )

    # ---------- closure_check ----------
    def _handle_closure_check(self, checkin: dict) -> None:
        event = self.events.get_by_id(str(checkin["event_id"]))
        if not event or event["status"] in ("resolved", "expired"):
            self.events.mark_checkin_failed(str(checkin["id"]), "event_not_active")
            return

        # Se houve resposta recente (dentro da janela de TTL), mantém aberto.
        # Se não houve nenhuma resposta nova desde o último status_update, expira.
        # Critério: last_check_in_at < expires_at - TTL → sem atualização recente
        had_recent_activity = False
        last_check = event.get("last_check_in_at")
        if last_check:
            ts = last_check if isinstance(last_check, datetime) else datetime.fromisoformat(str(last_check))
            age_min = (datetime.now(timezone.utc) - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))).total_seconds() / 60
            had_recent_activity = age_min < 15

        if had_recent_activity:
            # Mantém aberto — agenda próximo closure_check pra +15 min
            scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=15)
            self.events.schedule_checkin(
                event_id=str(event["id"]),
                tenant_id=event["tenant_id"],
                kind="closure_check",
                scheduled_for=scheduled_for,
            )
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent="(evento mantido aberto — atividade recente)",
            )
        else:
            # Sem atividade — encerra silenciosamente
            self.events.expire_silent(str(event["id"]))
            self.evo.send_text(
                checkin["caregiver_phone"],
                f"⏱️ Encerrando o evento do(a) paciente por inatividade. "
                f"Se houver novidade, basta me enviar um novo áudio."
            )
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent="(evento encerrado por inatividade)",
            )

    # ---------- post_escalation ----------
    def _handle_post_escalation(self, checkin: dict) -> None:
        event = self.events.get_by_id(str(checkin["event_id"]))
        if not event or event["status"] in ("resolved", "expired"):
            self.events.mark_checkin_failed(str(checkin["id"]), "event_not_active")
            return

        # Checa se houve resposta em alguma escalação anterior
        escalations = self.events.list_escalations_for_event(str(event["id"]))
        responded_any = any(e.get("status") == "responded" for e in escalations)

        if responded_any:
            # Alguém respondeu — não precisa escalar mais. Marca processado.
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent="(escalação anterior respondida — não escala mais)",
            )
            return

        # Ninguém respondeu — escalação para próximo nível
        patient = self.patients.get_by_id(str(event["patient_id"]))
        if not patient:
            self.events.mark_checkin_failed(str(checkin["id"]), "patient_missing")
            return

        from src.services.escalation_service import get_escalation_service
        esc = get_escalation_service()
        classification = event.get("current_classification") or "urgent"

        result = esc.escalate_next_level(event, patient, classification, analysis=None)
        if result:
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent=f"(escalou para {result.get('target_role')})",
            )
        else:
            self.events.mark_checkin_sent(
                str(checkin["id"]),
                message_sent="(sem próximos níveis disponíveis)",
            )


_scheduler_instance: CheckinScheduler | None = None


def get_scheduler() -> CheckinScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CheckinScheduler()
    return _scheduler_instance
