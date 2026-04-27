"""Proactive Caller — worker que decide DINAMICAMENTE quando ligar pra paciente.

Diferente do proactive_scheduler.py (que dispara WhatsApp via cron) e do
checkin_scheduler.py (que opera dentro de care_event ativo), este worker:

  1. Roda a cada 5min (configurável)
  2. Para cada paciente ativo com sofia_proactive_calls_enabled=true:
     - Verifica janela horária preferida (timezone do paciente)
     - Verifica DND ativo
     - Verifica intervalo mínimo desde última ligação
     - Computa trigger_score baseado em sinais clínicos:
         * Risk score atual (criticality)
         * Doses não tomadas nas últimas 24h
         * Eventos urgent/critical abertos
         * Tempo desde último contato
     - Se score >= threshold E está em janela: dispara ligação
  3. TODA decisão (will_call OU skip relevante) vai pra
     aia_health_proactive_call_decisions — auditável e analisável.

Concorrência: pg_try_advisory_lock próprio (lock_key=9582364718).

Safety: respeita Safety Guardrail circuit breaker — se está aberto, skip total.

Escopo: B2C primário (paciente individual). Casas geriátricas / clínicas
podem desabilitar setando sofia_proactive_calls_enabled=false em massa.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from datetime import datetime, time as dtime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Lock advisory único — não colide com outros schedulers
PROACTIVE_CALLER_LOCK_KEY = 9582364718

TICK_INTERVAL_SEC = int(os.getenv("PROACTIVE_CALLER_TICK_SEC", "300"))

# URL interna do voice-call-service (igual ao usado por communications_routes)
VOICE_CALL_SERVICE_URL = os.getenv(
    "VOICE_CALL_SERVICE_URL", "http://voice-call-service:5040"
)

# Threshold default — pode ser sobrescrito por tenant em
# tenant_config.proactive_caller_settings.trigger_threshold
DEFAULT_TRIGGER_THRESHOLD = 50

# Score mínimo pra LOGAR decisão de skip (evita inflar tabela)
MIN_SCORE_TO_LOG_SKIP = 25


# ────────────────────────────────────────────────────────────────────
# Decisão por paciente
# ────────────────────────────────────────────────────────────────────

def _compute_trigger_score(
    *,
    risk_level: str | None,
    risk_score: int | None,
    missed_doses_24h: int,
    open_urgent_events: int,
    hours_since_last_call: float | None,
) -> tuple[int, dict]:
    """Score 0-100. Quanto maior, mais relevante ligar agora.

    Breakdown explica cada parcela do score — útil pra calibrar.
    """
    score = 0
    parts: dict[str, int] = {}

    # Risk score do paciente — peso máximo
    if risk_level == "critical":
        parts["risk_critical"] = 60
    elif risk_level == "high":
        parts["risk_high"] = 35
    elif risk_level == "moderate":
        parts["risk_moderate"] = 15

    # Adesão — sinal forte
    if missed_doses_24h >= 3:
        parts["missed_doses_3plus"] = 40
    elif missed_doses_24h >= 1:
        parts["missed_doses_1to2"] = 20

    # Eventos urgentes abertos
    if open_urgent_events >= 2:
        parts["urgent_events_2plus"] = 35
    elif open_urgent_events == 1:
        parts["urgent_events_1"] = 20

    # Tempo sem contato — penalty se ligamos faz pouco, bonus se faz tempo
    if hours_since_last_call is None:
        # Nunca ligamos — bonus moderado pra fazer primeiro contato
        parts["no_prior_call"] = 10
    elif hours_since_last_call < 4:
        # Ligamos faz pouco — desincentivo forte (não duplicar)
        parts["recent_call_penalty"] = -100
    elif hours_since_last_call > 48:
        # Faz muito tempo — bonus
        parts["gap_48h_plus"] = 15
    elif hours_since_last_call > 24:
        parts["gap_24h_plus"] = 8

    score = sum(parts.values())
    return score, parts


def _is_within_call_window(
    *, now_utc: datetime, timezone_name: str,
    window_start: dtime, window_end: dtime,
) -> bool:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")
    local = now_utc.astimezone(tz)
    local_time = local.time()
    if window_start <= window_end:
        return window_start <= local_time <= window_end
    # Janela atravessa meia-noite (ex: 22:00 → 06:00)
    return local_time >= window_start or local_time <= window_end


def _resolve_call_phone(patient_row: dict) -> str | None:
    """Retorna telefone E.164 sem +. Tenta:
       1. patient.proactive_call_phone (override explícito)
       2. patient.responsible.nurse_override.phone
       3. patient.responsible.family[0].phone
    """
    phone = patient_row.get("proactive_call_phone")
    if phone:
        return _normalize_phone(phone)

    responsible = patient_row.get("responsible") or {}
    if isinstance(responsible, dict):
        nurse = responsible.get("nurse_override") or {}
        if nurse.get("phone"):
            return _normalize_phone(nurse["phone"])
        family = responsible.get("family") or []
        if isinstance(family, list) and family:
            for f in family:
                if isinstance(f, dict) and f.get("phone"):
                    return _normalize_phone(f["phone"])
    return None


def _normalize_phone(p: str) -> str:
    """Remove +, espaços, parênteses. Retorna só dígitos."""
    if not p:
        return ""
    return "".join(ch for ch in p if ch.isdigit())


def _resolve_scenario_code(
    patient_row: dict, tenant_settings: dict,
) -> str | None:
    """Override do paciente > default do tenant > hardcoded fallback."""
    code = patient_row.get("proactive_scenario_code")
    if code:
        return code
    code = (tenant_settings or {}).get("default_scenario_code")
    if code:
        return code
    return "paciente_checkin_matinal"


# ────────────────────────────────────────────────────────────────────
# Sinais clínicos — queries leves
# ────────────────────────────────────────────────────────────────────

def _gather_signals(patient_id: str) -> dict:
    """Coleta os sinais necessários pra decisão. Uma query agregada por sinal."""
    db = get_postgres()
    out: dict = {
        "risk_level": None,
        "risk_score": None,
        "missed_doses_24h": 0,
        "open_urgent_events": 0,
        "hours_since_last_call": None,
    }

    # Risk score atual
    row = db.fetch_one(
        """SELECT score, level
           FROM aia_health_patient_risk_score
           WHERE patient_id = %s""",
        (patient_id,),
    )
    if row:
        out["risk_score"] = row.get("score")
        out["risk_level"] = row.get("level")

    # Doses não tomadas (24h)
    row = db.fetch_one(
        """SELECT COUNT(*) AS n
           FROM aia_health_medication_events
           WHERE patient_id = %s
             AND status IN ('missed', 'refused')
             AND scheduled_at > NOW() - INTERVAL '24 hours'""",
        (patient_id,),
    )
    out["missed_doses_24h"] = int(row.get("n") or 0) if row else 0

    # Eventos urgent/critical abertos
    row = db.fetch_one(
        """SELECT COUNT(*) AS n
           FROM aia_health_care_events
           WHERE patient_id = %s
             AND current_classification IN ('urgent', 'critical')
             AND status NOT IN ('resolved', 'expired')""",
        (patient_id,),
    )
    out["open_urgent_events"] = int(row.get("n") or 0) if row else 0

    # Última ligação proativa registrada
    row = db.fetch_one(
        """SELECT EXTRACT(EPOCH FROM (NOW() - MAX(evaluated_at))) / 3600
                  AS hours_since
           FROM aia_health_proactive_call_decisions
           WHERE patient_id = %s AND decision = 'will_call'""",
        (patient_id,),
    )
    if row and row.get("hours_since") is not None:
        out["hours_since_last_call"] = float(row["hours_since"])

    return out


# ────────────────────────────────────────────────────────────────────
# Dispatch da chamada via voice-call-service
# ────────────────────────────────────────────────────────────────────

def _dispatch_call(
    *, tenant_id: str, patient_row: dict,
    scenario_code: str, phone: str,
) -> tuple[str | None, str | None]:
    """Chama POST /api/voice-call/dial diretamente no voice-call-service.

    Retorna (call_id, error). Um dos dois é None.
    """
    db = get_postgres()
    scenario = db.fetch_one(
        """SELECT id, code, label, system_prompt, voice, allowed_tools,
                  post_call_actions, max_duration_seconds
           FROM aia_health_call_scenarios
           WHERE code = %s AND active = TRUE
           LIMIT 1""",
        (scenario_code,),
    )
    if not scenario:
        return None, f"scenario_not_found:{scenario_code}"

    payload = {
        "destination": phone,
        "scenario_id": str(scenario["id"]),
        "scenario_code": scenario_code,
        "scenario_system_prompt": scenario.get("system_prompt"),
        "scenario_voice": scenario.get("voice") or "ara",
        "scenario_allowed_tools": scenario.get("allowed_tools") or [],
        "patient_id": str(patient_row["id"]),
        "tenant_id": tenant_id,
        "full_name": patient_row.get("full_name"),
        "extra_context": {
            "patient": {
                "nickname": patient_row.get("nickname"),
                "care_level": patient_row.get("care_level"),
            },
            "scenario_label": scenario.get("label"),
            "trigger": "proactive_caller",
        },
    }

    try:
        resp = httpx.post(
            f"{VOICE_CALL_SERVICE_URL}/api/voice-call/dial",
            json=payload, timeout=15.0,
        )
        if resp.status_code >= 400:
            return None, f"voice_call_http_{resp.status_code}: {resp.text[:200]}"
        body = resp.json()
        return body.get("call_id") or "dispatched", None
    except httpx.HTTPError as exc:
        return None, f"http_error: {exc}"


# ────────────────────────────────────────────────────────────────────
# Persistência da decisão
# ────────────────────────────────────────────────────────────────────

def _record_decision(
    *,
    tenant_id: str,
    patient_id: str,
    decision: str,
    trigger_score: int,
    breakdown: dict,
    call_id: str | None = None,
    error: str | None = None,
    notes: str | None = None,
) -> None:
    db = get_postgres()
    db.execute(
        """INSERT INTO aia_health_proactive_call_decisions
            (tenant_id, patient_id, decision, trigger_score, breakdown,
             call_id, error, notes)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)""",
        (
            tenant_id, patient_id, decision, trigger_score,
            _json_dumps(breakdown), call_id, error, notes,
        ),
    )


def _json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, default=str)


# ────────────────────────────────────────────────────────────────────
# Avaliação por paciente
# ────────────────────────────────────────────────────────────────────

def evaluate_and_maybe_call(
    *,
    tenant_id: str,
    patient_row: dict,
    tenant_settings: dict,
    threshold: int,
    now_utc: datetime,
    circuit_open: bool,
) -> str:
    """Avalia um paciente. Retorna decisão (string) — também loga.

    Side effect: pode disparar ligação via voice-call-service.
    """
    patient_id = str(patient_row["id"])

    # Master switch
    if not patient_row.get("sofia_proactive_calls_enabled"):
        return "skip_disabled"

    # Circuit breaker do tenant
    if circuit_open:
        # Logamos só se o paciente teria score relevante
        signals = _gather_signals(patient_id)
        score, parts = _compute_trigger_score(
            risk_level=signals["risk_level"],
            risk_score=signals["risk_score"],
            missed_doses_24h=signals["missed_doses_24h"],
            open_urgent_events=signals["open_urgent_events"],
            hours_since_last_call=signals["hours_since_last_call"],
        )
        if score >= MIN_SCORE_TO_LOG_SKIP:
            _record_decision(
                tenant_id=tenant_id, patient_id=patient_id,
                decision="skip_circuit_open", trigger_score=score,
                breakdown={"signals": signals, "score_parts": parts},
            )
        return "skip_circuit_open"

    # DND
    dnd = patient_row.get("do_not_disturb_until")
    if dnd and dnd > now_utc:
        return "skip_dnd"

    # Janela horária
    window_start = patient_row.get("preferred_call_window_start") or dtime(8, 0)
    window_end = patient_row.get("preferred_call_window_end") or dtime(21, 0)
    tz_name = patient_row.get("proactive_call_timezone") or "America/Sao_Paulo"

    if not _is_within_call_window(
        now_utc=now_utc, timezone_name=tz_name,
        window_start=window_start, window_end=window_end,
    ):
        return "skip_outside_window"

    # Coleta sinais clínicos
    signals = _gather_signals(patient_id)
    score, parts = _compute_trigger_score(
        risk_level=signals["risk_level"],
        risk_score=signals["risk_score"],
        missed_doses_24h=signals["missed_doses_24h"],
        open_urgent_events=signals["open_urgent_events"],
        hours_since_last_call=signals["hours_since_last_call"],
    )

    # Intervalo mínimo entre ligações
    min_hours = int(patient_row.get("min_hours_between_calls") or 4)
    if (
        signals["hours_since_last_call"] is not None
        and signals["hours_since_last_call"] < min_hours
    ):
        if score >= MIN_SCORE_TO_LOG_SKIP:
            _record_decision(
                tenant_id=tenant_id, patient_id=patient_id,
                decision="skip_too_soon", trigger_score=score,
                breakdown={"signals": signals, "score_parts": parts,
                           "min_hours": min_hours},
            )
        return "skip_too_soon"

    # Score abaixo do threshold
    if score < threshold:
        if score >= MIN_SCORE_TO_LOG_SKIP:
            _record_decision(
                tenant_id=tenant_id, patient_id=patient_id,
                decision="skip_low_score", trigger_score=score,
                breakdown={"signals": signals, "score_parts": parts,
                           "threshold": threshold},
            )
        return "skip_low_score"

    # ── A partir daqui: decisão é WILL_CALL ──

    phone = _resolve_call_phone(patient_row)
    if not phone:
        _record_decision(
            tenant_id=tenant_id, patient_id=patient_id,
            decision="skip_no_phone", trigger_score=score,
            breakdown={"signals": signals, "score_parts": parts},
        )
        return "skip_no_phone"

    scenario_code = _resolve_scenario_code(patient_row, tenant_settings)
    if not scenario_code:
        _record_decision(
            tenant_id=tenant_id, patient_id=patient_id,
            decision="skip_no_scenario", trigger_score=score,
            breakdown={"signals": signals, "score_parts": parts},
        )
        return "skip_no_scenario"

    # Dispara
    call_id, err = _dispatch_call(
        tenant_id=tenant_id, patient_row=patient_row,
        scenario_code=scenario_code, phone=phone,
    )

    if err:
        _record_decision(
            tenant_id=tenant_id, patient_id=patient_id,
            decision="failed_dispatch", trigger_score=score,
            breakdown={
                "signals": signals, "score_parts": parts,
                "scenario_code": scenario_code,
                "phone_last4": phone[-4:] if phone else None,
            },
            error=err,
        )
        return "failed_dispatch"

    _record_decision(
        tenant_id=tenant_id, patient_id=patient_id,
        decision="will_call", trigger_score=score,
        breakdown={
            "signals": signals, "score_parts": parts,
            "scenario_code": scenario_code,
            "phone_last4": phone[-4:] if phone else None,
        },
        call_id=call_id,
    )
    return "will_call"


# ────────────────────────────────────────────────────────────────────
# Tick — varre todos os tenants ativos
# ────────────────────────────────────────────────────────────────────

def tick() -> dict:
    """Uma rodada completa de avaliação. Retorna sumário pra log."""
    db = get_postgres()
    now_utc = datetime.now(timezone.utc)

    # Lista tenants ativos
    tenants = db.fetch_all(
        """SELECT tenant_id, proactive_caller_settings, guardrail_settings
           FROM aia_health_tenant_config
           WHERE active = TRUE"""
    )
    summary = {
        "tenants_evaluated": 0,
        "patients_evaluated": 0,
        "calls_dispatched": 0,
        "by_decision": {},
    }

    for tenant in tenants or []:
        tenant_id = tenant["tenant_id"]
        settings = tenant.get("proactive_caller_settings") or {}
        threshold = int(settings.get("trigger_threshold") or DEFAULT_TRIGGER_THRESHOLD)
        summary["tenants_evaluated"] += 1

        # Estado do circuit breaker desse tenant
        cb = db.fetch_one(
            """SELECT state, open_until
               FROM aia_health_safety_circuit_breaker
               WHERE tenant_id = %s""",
            (tenant_id,),
        )
        circuit_open = bool(
            cb and cb.get("state") == "open"
            and (not cb.get("open_until") or cb["open_until"] > now_utc)
        )

        # Pacientes ativos elegíveis
        patients = db.fetch_all(
            """SELECT id, tenant_id, full_name, nickname, care_level,
                      responsible, sofia_proactive_calls_enabled,
                      preferred_call_window_start, preferred_call_window_end,
                      min_hours_between_calls, do_not_disturb_until,
                      proactive_call_phone, proactive_scenario_code,
                      proactive_call_timezone
               FROM aia_health_patients
               WHERE tenant_id = %s
                 AND active = TRUE
                 AND sofia_proactive_calls_enabled = TRUE""",
            (tenant_id,),
        )

        for p in patients or []:
            try:
                decision = evaluate_and_maybe_call(
                    tenant_id=tenant_id, patient_row=dict(p),
                    tenant_settings=settings, threshold=threshold,
                    now_utc=now_utc, circuit_open=circuit_open,
                )
                summary["patients_evaluated"] += 1
                if decision == "will_call":
                    summary["calls_dispatched"] += 1
                summary["by_decision"][decision] = (
                    summary["by_decision"].get(decision, 0) + 1
                )
            except Exception as exc:
                logger.exception(
                    "proactive_caller_patient_eval_failed patient=%s",
                    p.get("id"),
                )
                summary["by_decision"]["error"] = (
                    summary["by_decision"].get("error", 0) + 1
                )

    return summary


# ────────────────────────────────────────────────────────────────────
# Worker / scheduler infra
# ────────────────────────────────────────────────────────────────────

class ProactiveCallerWorker:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="proactive-caller", daemon=True,
        )
        self._thread.start()
        logger.info(
            "proactive_caller_started worker_id=%s tick=%ds",
            self._worker_id, TICK_INTERVAL_SEC,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _try_acquire_lock(self) -> bool:
        row = get_postgres().fetch_one(
            "SELECT pg_try_advisory_lock(%s) AS got",
            (PROACTIVE_CALLER_LOCK_KEY,),
        )
        return bool(row and row.get("got"))

    def _release_lock(self) -> None:
        try:
            get_postgres().execute(
                "SELECT pg_advisory_unlock(%s)",
                (PROACTIVE_CALLER_LOCK_KEY,),
            )
        except Exception:
            pass

    def _loop(self) -> None:
        # Pequeno delay no boot pra não competir com outros schedulers
        self._stop_event.wait(60)
        while not self._stop_event.is_set():
            try:
                if self._try_acquire_lock():
                    try:
                        t0 = time.monotonic()
                        s = tick()
                        dt = time.monotonic() - t0
                        if s.get("calls_dispatched", 0) > 0 or s.get(
                            "patients_evaluated", 0
                        ) > 0:
                            logger.info(
                                "proactive_caller_tick took=%.1fs summary=%s",
                                dt, s,
                            )
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("proactive_caller_tick_error: %s", exc)
            self._stop_event.wait(TICK_INTERVAL_SEC)


_singleton: ProactiveCallerWorker | None = None


def get_proactive_caller() -> ProactiveCallerWorker:
    global _singleton
    if _singleton is None:
        _singleton = ProactiveCallerWorker()
    return _singleton
