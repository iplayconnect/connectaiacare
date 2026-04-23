"""Proactive Scheduler — worker background que dispara check-ins, lembretes
e relatórios proativamente, independente de care_events ativos.

Responsabilidades:
    - Polling periódico (15s) da tabela aia_health_proactive_schedules
    - Avalia cron_expression contra timezone do paciente
    - Dispara mensagem via template + channel configurado
    - Registra fire em aia_health_scheduled_fires
    - Grava heartbeat (detecção de scheduler parado)
    - Retry + escalação de não-resposta
    - Learning: atualiza observed_response_avg_min

Concorrência: usa pg_try_advisory_lock pra garantir single-writer mesmo
com múltiplos workers Gunicorn (mesmo padrão do checkin_scheduler).

Diferente do checkin_scheduler (que opera DENTRO de care_events ativos),
este é agnóstico de evento — é o coração do B2C.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from src.services.evolution import get_evolution
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Lock advisory único pra esse scheduler (evita colisão com checkin_scheduler)
PROACTIVE_LOCK_KEY = 728349127

POLL_INTERVAL_SEC = 15


class ProactiveScheduler:
    def __init__(self):
        self.db = get_postgres()
        self.evo = get_evolution()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    # ══════════════════════════════════════════════════════════════════
    # Ciclo de vida
    # ══════════════════════════════════════════════════════════════════

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("proactive_scheduler_already_running", worker_id=self._worker_id)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="proactive-scheduler", daemon=True,
        )
        self._thread.start()
        logger.info(
            "proactive_scheduler_started",
            worker_id=self._worker_id,
            poll_interval=POLL_INTERVAL_SEC,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=30)

    # ══════════════════════════════════════════════════════════════════
    # Loop principal
    # ══════════════════════════════════════════════════════════════════

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            # Dois locks: um por tick do scheduler (mantém single-writer)
            try:
                if self._try_acquire_lock():
                    try:
                        self._tick()
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("proactive_scheduler_tick_error", error=str(exc))

            # Sleep interruptível
            self._stop_event.wait(POLL_INTERVAL_SEC)

    def _try_acquire_lock(self) -> bool:
        """pg_try_advisory_lock — non-blocking. True se conseguimos o lock."""
        try:
            row = self.db.fetch_one(
                "SELECT pg_try_advisory_lock(%s) AS got",
                (PROACTIVE_LOCK_KEY,),
            )
            return bool(row and row.get("got"))
        except Exception as exc:
            logger.warning("proactive_lock_acquire_failed", error=str(exc))
            return False

    def _release_lock(self) -> None:
        try:
            self.db.execute(
                "SELECT pg_advisory_unlock(%s)", (PROACTIVE_LOCK_KEY,),
            )
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    # Tick: avalia todas as schedules ativas, dispara as devidas
    # ══════════════════════════════════════════════════════════════════

    def _tick(self) -> None:
        tick_start = time.time()
        checked = 0
        dispatched = 0
        errors = 0

        schedules = self.db.fetch_all(
            """
            SELECT id, tenant_id, subject_type, subject_id, template_code,
                   channel, cron_expression, timezone,
                   response_window_min, max_retries, retry_interval_min,
                   last_fired_at, consecutive_no_response
            FROM aia_health_proactive_schedules
            WHERE active = TRUE
              AND (paused_until IS NULL OR paused_until < NOW())
            ORDER BY last_fired_at NULLS FIRST
            LIMIT 200
            """
        )

        now_utc = datetime.now(timezone.utc)

        for sched in schedules:
            checked += 1
            try:
                if self._should_fire(sched, now_utc):
                    if self._fire(sched, now_utc):
                        dispatched += 1
            except Exception as exc:
                errors += 1
                logger.warning(
                    "proactive_schedule_fire_error",
                    schedule_id=str(sched["id"]), error=str(exc),
                )

        # Processa responses pending → atualiza learning pattern
        try:
            self._reconcile_recent_responses()
        except Exception as exc:
            logger.warning("proactive_reconcile_error", error=str(exc))

        # Processa lembretes de medicação (independente dos proactive_schedules)
        try:
            med_fired, med_missed = self._tick_medication_reminders()
            dispatched += med_fired
        except Exception as exc:
            logger.warning("medication_reminders_tick_error", error=str(exc))

        # Heartbeat (detecção de scheduler parado)
        try:
            self._write_heartbeat(checked, dispatched, errors)
        except Exception as exc:
            logger.warning("proactive_heartbeat_error", error=str(exc))

        logger.debug(
            "proactive_tick_complete",
            checked=checked, dispatched=dispatched, errors=errors,
            elapsed_ms=int((time.time() - tick_start) * 1000),
        )

    # ══════════════════════════════════════════════════════════════════
    # Cron evaluation + dispatch
    # ══════════════════════════════════════════════════════════════════

    def _should_fire(self, sched: dict, now_utc: datetime) -> bool:
        """Verifica se o cron bate com o 'agora' no timezone do paciente.

        Uso simplificado: evaluamos apenas se estamos no minuto correto.
        Protegido por last_fired_at (não dispara 2x no mesmo minuto).
        """
        tz_name = sched.get("timezone") or "America/Sao_Paulo"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/Sao_Paulo")

        now_local = now_utc.astimezone(tz)
        cron = (sched.get("cron_expression") or "").strip()
        if not cron:
            return False

        if not self._cron_match(cron, now_local):
            return False

        # Protege contra re-fire no mesmo minuto
        last = sched.get("last_fired_at")
        if last:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            minutes_ago = (now_utc - last).total_seconds() / 60
            if minutes_ago < 1.5:
                return False

        return True

    @staticmethod
    def _cron_match(cron: str, when: datetime) -> bool:
        """Parser cron simples: 5 campos (minuto hora dia-mês mês dia-semana).

        Suporta '*', 'N', 'N,M,O', 'a-b'. Não suporta '/step' (overkill aqui).
        """
        parts = cron.split()
        if len(parts) != 5:
            return False
        minute, hour, dom, month, dow = parts

        # Python weekday: segunda=0..domingo=6; cron: domingo=0..sábado=6
        # Vamos usar isoweekday (segunda=1..domingo=7) e mapear cron (dom=0 ou 7).
        iso_dow = when.isoweekday()  # 1..7
        cron_dow = iso_dow % 7       # 1..6, 0(domingo)

        return (
            ProactiveScheduler._field_match(minute, when.minute)
            and ProactiveScheduler._field_match(hour, when.hour)
            and ProactiveScheduler._field_match(dom, when.day)
            and ProactiveScheduler._field_match(month, when.month)
            and ProactiveScheduler._field_match(dow, cron_dow, also=[iso_dow if iso_dow == 7 else None])
        )

    @staticmethod
    def _field_match(field: str, value: int, also: list | None = None) -> bool:
        if field == "*":
            return True
        # Lista "1,2,3"
        if "," in field:
            return str(value) in [p.strip() for p in field.split(",")]
        # Range "1-5"
        if "-" in field:
            try:
                a, b = field.split("-")
                if int(a) <= value <= int(b):
                    return True
            except ValueError:
                return False
            return False
        # Valor exato
        try:
            ok = int(field) == value
            if ok:
                return True
            if also:
                return any(a == int(field) for a in also if a is not None)
            return False
        except ValueError:
            return False

    # ══════════════════════════════════════════════════════════════════
    # Dispatch — grava fire + envia WhatsApp
    # ══════════════════════════════════════════════════════════════════

    def _fire(self, sched: dict, now_utc: datetime) -> bool:
        """Renderiza template + envia via canal + grava fire."""
        subject = self._load_subject(sched["subject_type"], str(sched["subject_id"]))
        if not subject or not subject.get("phone"):
            logger.info(
                "proactive_fire_skipped_no_phone",
                schedule_id=str(sched["id"]),
            )
            return False

        template = self.db.fetch_one(
            """
            SELECT message_body, buttons, channel
            FROM aia_health_schedule_templates
            WHERE tenant_id = %s AND code = %s
            """,
            (sched["tenant_id"], sched["template_code"]),
        )
        if not template:
            logger.warning(
                "proactive_template_not_found",
                code=sched["template_code"], tenant=sched["tenant_id"],
            )
            return False

        rendered = self._render_template(template["message_body"], subject)

        # Grava o fire ANTES de enviar (idempotência contra crash)
        fire = self.db.insert_returning(
            """
            INSERT INTO aia_health_scheduled_fires
                (schedule_id, tenant_id, scheduled_for, channel,
                 rendered_message, status)
            VALUES (%s, %s, %s, %s, %s, 'scheduled')
            RETURNING id
            """,
            (
                sched["id"], sched["tenant_id"], now_utc,
                sched["channel"], rendered,
            ),
        )

        # Envia WhatsApp
        sent_ok = False
        err_msg = None
        external_ref = None
        try:
            if sched["channel"] == "whatsapp":
                resp = self.evo.send_text(subject["phone"], rendered)
                external_ref = self._extract_msg_id(resp)
                sent_ok = True
        except Exception as exc:
            err_msg = str(exc)[:500]

        # Atualiza fire + schedule
        if sent_ok:
            self.db.execute(
                """
                UPDATE aia_health_scheduled_fires
                SET status = 'fired', fired_at = NOW(),
                    external_ref = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (external_ref, fire["id"]),
            )
            self.db.execute(
                """
                UPDATE aia_health_proactive_schedules
                SET last_fired_at = NOW(),
                    total_fires = total_fires + 1,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (sched["id"],),
            )
            logger.info(
                "proactive_fire_sent",
                schedule_id=str(sched["id"]),
                template=sched["template_code"],
                phone_prefix=subject["phone"][:4],
            )
            return True
        else:
            self.db.execute(
                """
                UPDATE aia_health_scheduled_fires
                SET status = 'failed', error_message = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (err_msg, fire["id"]),
            )
            logger.warning("proactive_fire_failed", error=err_msg)
            return False

    def _load_subject(self, subject_type: str, subject_id: str) -> dict | None:
        """Carrega dados básicos do subject (phone + nome) via tabela correspondente.

        Usa COALESCE entre patient/caregiver/family_member nativas —
        abordagem backward-compatible conforme feedback Opus.
        """
        if subject_type == "patient":
            # aia_health_patients não tem phone direto; puxar via care_events
            # (proxy: último care_event do paciente → caregiver_phone)
            row = self.db.fetch_one(
                """
                SELECT p.full_name, p.nickname,
                       (SELECT caregiver_phone FROM aia_health_care_events
                        WHERE patient_id = p.id ORDER BY opened_at DESC LIMIT 1) AS phone
                FROM aia_health_patients p
                WHERE p.id = %s
                """,
                (subject_id,),
            )
            if row and row.get("phone"):
                return {
                    "phone": row["phone"],
                    "first_name": self._first_name(row.get("nickname") or row["full_name"]),
                    "full_name": row["full_name"],
                }
        elif subject_type == "caregiver":
            row = self.db.fetch_one(
                "SELECT full_name, phone FROM aia_health_caregivers WHERE id = %s",
                (subject_id,),
            )
            if row:
                return {
                    "phone": row.get("phone"),
                    "first_name": self._first_name(row["full_name"]),
                    "full_name": row["full_name"],
                }
        elif subject_type == "family_member":
            # Tabela futura aia_health_family_members — fallback seguro por ora
            return None
        return None

    @staticmethod
    def _first_name(full_name: str | None) -> str:
        if not full_name:
            return "amigo(a)"
        return full_name.strip().split()[0]

    @staticmethod
    def _render_template(template: str, subject: dict) -> str:
        """Substitui placeholders {{first_name}}, {{full_name}}, {{date}}."""
        out = template
        out = out.replace("{{first_name}}", subject.get("first_name", ""))
        out = out.replace("{{full_name}}", subject.get("full_name", ""))
        out = out.replace("{{date}}",
                          datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"))
        return out

    @staticmethod
    def _extract_msg_id(resp) -> str | None:
        if not isinstance(resp, dict):
            return None
        key = resp.get("key") or {}
        return key.get("id") if isinstance(key, dict) else None

    # ══════════════════════════════════════════════════════════════════
    # Lembretes de medicação (integração com medication_events)
    # ══════════════════════════════════════════════════════════════════

    def _tick_medication_reminders(self) -> tuple[int, int]:
        """Envia lembretes de medicação que estão vencendo + marca missed.

        Retorna (fired_count, missed_count).
        """
        from src.services.medication_event_service import get_medication_event_service
        from src.services.evolution import get_evolution

        med_svc = get_medication_event_service()
        evo = get_evolution()

        fired = 0
        missed = 0

        # Materializa events pra próximas 24h (idempotente)
        try:
            med_svc.materialize_for_all_active_patients(horizon_hours=24)
        except Exception as exc:
            logger.warning("medication_materialize_error", error=str(exc))

        # Envia lembretes pendentes
        pending = med_svc.get_pending_reminders(lookahead_minutes=15)
        for event in pending:
            try:
                # Tenta pegar phone do paciente via proxy (care_event mais recente)
                phone_row = self.db.fetch_one(
                    """
                    SELECT caregiver_phone
                    FROM aia_health_care_events
                    WHERE patient_id = %s
                    ORDER BY opened_at DESC
                    LIMIT 1
                    """,
                    (str(event["patient_id"]),),
                )
                phone = phone_row.get("caregiver_phone") if phone_row else None
                if not phone:
                    continue

                # Renderiza mensagem com tom acolhedor
                patient_row = self.db.fetch_one(
                    "SELECT nickname, full_name FROM aia_health_patients WHERE id = %s",
                    (str(event["patient_id"]),),
                )
                first_name = self._first_name_from_nick_or_full(
                    (patient_row or {}).get("nickname"),
                    (patient_row or {}).get("full_name"),
                )

                dose = event.get("dose") or ""
                med = event.get("medication_name") or "medicação"
                instr = event.get("special_instructions") or ""

                scheduled_dt = event.get("scheduled_at")
                if scheduled_dt and scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
                tz = ZoneInfo("America/Sao_Paulo")
                time_str = scheduled_dt.astimezone(tz).strftime("%H:%M") if scheduled_dt else ""

                text = (
                    f"🔔 Oi, {first_name}!\n\n"
                    f"Daqui a pouco ({time_str}) é hora de tomar:\n"
                    f"*{med} {dose}*\n"
                )
                if instr:
                    text += f"\n_{instr}_\n"
                text += (
                    "\nResponda:\n"
                    "✅ se já tomou ou vai tomar agora\n"
                    "⏰ se vai tomar daqui a pouco\n"
                    "❌ se não vai tomar essa dose"
                )

                resp = evo.send_text(phone, text)
                external_ref = self._extract_msg_id(resp)
                med_svc.mark_reminder_sent(
                    str(event["id"]), channel="whatsapp", external_ref=external_ref,
                )
                fired += 1
                logger.info(
                    "medication_reminder_sent",
                    event_id=str(event["id"]),
                    medication=med,
                    phone_prefix=phone[:4],
                )
            except Exception as exc:
                logger.warning(
                    "medication_reminder_failed",
                    event_id=str(event.get("id")), error=str(exc),
                )

        # Marca missed eventos que ultrapassaram janela
        try:
            overdue = med_svc.get_overdue()
            for event in overdue:
                med_svc.mark_missed(str(event["id"]))
                missed += 1
                logger.info(
                    "medication_marked_missed",
                    event_id=str(event["id"]),
                    medication=event.get("medication_name"),
                )
                # Detecta 3 missed consecutivos → alerta familiar (próxima iteração)
        except Exception as exc:
            logger.warning("medication_overdue_error", error=str(exc))

        return fired, missed

    @staticmethod
    def _first_name_from_nick_or_full(nick: str | None, full: str | None) -> str:
        """Primeiro nome honrando títulos brasileiros."""
        candidate = nick or full or ""
        parts = [p for p in candidate.strip().split() if p]
        if not parts:
            return "amigo(a)"
        first = parts[0].strip(".")
        if first.lower() in {"dona", "dn", "sra", "sr", "dr", "dra", "senhor", "senhora"} and len(parts) > 1:
            return parts[1]
        return parts[0]

    # ══════════════════════════════════════════════════════════════════
    # Learning — atualiza observed_response_avg_min
    # ══════════════════════════════════════════════════════════════════

    def _reconcile_recent_responses(self) -> None:
        """Atualiza métricas de resposta com base em fires recentes
        que já têm responded_at preenchido pelo webhook de inbound WhatsApp.

        A correlação inbound→fire é feita externamente pelo handler de
        mensagem WhatsApp — aqui só consolidamos.
        """
        # Estatística em SQL puro é mais rápida do que carregar + calcular em Python.
        self.db.execute(
            """
            UPDATE aia_health_proactive_schedules ps
            SET observed_response_avg_min = sub.avg_min,
                observed_response_p95_min = sub.p95_min,
                total_responses = sub.resp_count,
                updated_at = NOW()
            FROM (
                SELECT schedule_id,
                       AVG(response_duration_seconds)::INT / 60 AS avg_min,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY response_duration_seconds)::INT / 60 AS p95_min,
                       COUNT(*) AS resp_count
                FROM aia_health_scheduled_fires
                WHERE responded_at IS NOT NULL
                  AND response_duration_seconds IS NOT NULL
                  AND fired_at > NOW() - INTERVAL '30 days'
                GROUP BY schedule_id
                HAVING COUNT(*) >= 5
            ) sub
            WHERE ps.id = sub.schedule_id
            """
        )

    # ══════════════════════════════════════════════════════════════════
    # Heartbeat
    # ══════════════════════════════════════════════════════════════════

    def _write_heartbeat(self, checked: int, dispatched: int, errors: int) -> None:
        self.db.execute(
            """
            INSERT INTO aia_health_scheduler_heartbeat
                (worker_id, last_tick_at, schedules_checked,
                 fires_dispatched, errors_last_tick, meta)
            VALUES (%s, NOW(), %s, %s, %s, %s)
            ON CONFLICT (worker_id) DO UPDATE SET
                last_tick_at = EXCLUDED.last_tick_at,
                schedules_checked = aia_health_scheduler_heartbeat.schedules_checked + EXCLUDED.schedules_checked,
                fires_dispatched = aia_health_scheduler_heartbeat.fires_dispatched + EXCLUDED.fires_dispatched,
                errors_last_tick = EXCLUDED.errors_last_tick,
                updated_at = NOW()
            """,
            (
                self._worker_id, checked, dispatched, errors,
                self.db.json_adapt({"version": "1.0"}),
            ),
        )


_instance: ProactiveScheduler | None = None


def get_proactive_scheduler() -> ProactiveScheduler:
    global _instance
    if _instance is None:
        _instance = ProactiveScheduler()
    return _instance
