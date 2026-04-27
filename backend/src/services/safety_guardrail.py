"""Safety Guardrail Layer — router determinístico de ações clínicas da Sofia.

Sofia tem inteligência (classifica, analisa padrão, propõe ação) mas NÃO
tem autoridade. Toda ação clínica passa por aqui antes de persistir/executar.

5 destinos possíveis:
    1. INFORMATIVA          → executa direto (com disclaimer auto-injetado)
    2. REGISTRA HISTÓRICO   → DB + notifica família se severity≥attention
    3. CONVOCA ATENDENTE    → fila review (atendente Isabel ou cuidador interno)
    4. EMERGÊNCIA REAL-TIME → bypass — Sofia já agiu, só registra + notifica
    5. MODIFICA PRESCRIÇÃO  → BLOQUEADO no piloto (precisa médico)

Circuit breaker: se >5% das ações em 5min caem na queue, pausa
automática de novas ações automáticas daquele tenant por 30min.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────── Tipos de ação ────────────────────────────

ACTION_INFORMATIVE = "informative"
ACTION_REGISTER_HISTORY = "register_history"
ACTION_INVOKE_ATTENDANT = "invoke_attendant"
ACTION_EMERGENCY_REALTIME = "emergency_realtime"
ACTION_MODIFY_PRESCRIPTION = "modify_prescription"

VALID_ACTION_TYPES = {
    ACTION_INFORMATIVE,
    ACTION_REGISTER_HISTORY,
    ACTION_INVOKE_ATTENDANT,
    ACTION_EMERGENCY_REALTIME,
    ACTION_MODIFY_PRESCRIPTION,
}

VALID_SEVERITIES = {"info", "attention", "urgent", "critical"}

# Resultado do route_action
DECIDE_EXECUTE = "execute"   # ação pode prosseguir
DECIDE_QUEUE = "queue"       # ação foi enfileirada pra revisão humana
DECIDE_REJECT = "reject"     # ação bloqueada (modify_prescription no piloto)
DECIDE_PAUSED = "paused"     # circuit breaker aberto pra esse tenant


# ──────────────────────────── Defaults ────────────────────────────

_DEFAULT_GUARDRAIL_SETTINGS = {
    "confidence_threshold": 0.85,
    "queue_review_timeout_seconds": 300,
    "auto_execute_on_timeout_critical": True,
    "circuit_breaker_max_queue_pct": 5,
    "circuit_breaker_window_seconds": 300,
    "circuit_breaker_pause_minutes": 30,
}


def _get_tenant_settings(tenant_id: str) -> dict:
    """Carrega settings + tenant_type + ramais de aia_health_tenant_config."""
    row = get_postgres().fetch_one(
        """SELECT tenant_type, default_attendant_ramal, default_internal_ramal,
                  guardrail_settings, escalation_policy
           FROM aia_health_tenant_config WHERE tenant_id = %s""",
        (tenant_id,),
    )
    if not row:
        return {
            "tenant_type": "b2c_individual",
            "default_attendant_ramal": None,
            "default_internal_ramal": None,
            "guardrail_settings": _DEFAULT_GUARDRAIL_SETTINGS.copy(),
        }
    settings = row.get("guardrail_settings") or _DEFAULT_GUARDRAIL_SETTINGS.copy()
    # Mescla defaults pra não quebrar se config velha não tem chaves novas
    for k, v in _DEFAULT_GUARDRAIL_SETTINGS.items():
        settings.setdefault(k, v)
    return {
        "tenant_type": row.get("tenant_type") or "b2c_individual",
        "default_attendant_ramal": row.get("default_attendant_ramal"),
        "default_internal_ramal": row.get("default_internal_ramal"),
        "guardrail_settings": settings,
    }


def _get_patient_routing(patient_id: str | None) -> dict:
    """Determina ramal e canal de escalação do paciente."""
    if not patient_id:
        return {"ramal": None, "channel": None}
    row = get_postgres().fetch_one(
        "SELECT ramal_extension, escalation_channel "
        "FROM aia_health_patients WHERE id = %s",
        (patient_id,),
    )
    if not row:
        return {"ramal": None, "channel": None}
    return {
        "ramal": row.get("ramal_extension"),
        "channel": row.get("escalation_channel"),
    }


# ──────────────────────────── Circuit breaker ────────────────────────────

def _get_circuit_state(tenant_id: str) -> dict:
    """Estado atual do circuit breaker pra esse tenant. Cria row se não existir."""
    row = get_postgres().fetch_one(
        "SELECT * FROM aia_health_safety_circuit_breaker WHERE tenant_id = %s",
        (tenant_id,),
    )
    if not row:
        get_postgres().execute(
            "INSERT INTO aia_health_safety_circuit_breaker (tenant_id) "
            "VALUES (%s) ON CONFLICT DO NOTHING",
            (tenant_id,),
        )
        return {"state": "closed", "open_until": None}
    return row


def _check_circuit_breaker(tenant_id: str, settings: dict) -> bool:
    """Retorna True se a ação pode prosseguir; False se circuit OPEN."""
    state = _get_circuit_state(tenant_id)
    now = datetime.now(timezone.utc)

    # Se está OPEN mas o tempo de pausa expirou, fecha automaticamente
    if state.get("state") == "open":
        open_until = state.get("open_until")
        if open_until and open_until < now:
            get_postgres().execute(
                "UPDATE aia_health_safety_circuit_breaker "
                "SET state = 'half_open', open_until = NULL WHERE tenant_id = %s",
                (tenant_id,),
            )
            audit_log(
                action="guardrail.circuit.closed",
                tenant_id=tenant_id,
                payload={"transitioned_to": "half_open"},
            )
            return True
        return False

    # Verifica se threshold foi atingido
    window_seconds = settings["circuit_breaker_window_seconds"]
    max_queue_pct = settings["circuit_breaker_max_queue_pct"]
    cutoff = now - timedelta(seconds=window_seconds)

    metrics = get_postgres().fetch_one(
        """SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status IN ('pending', 'auto_executed')) AS queued
           FROM aia_health_action_review_queue
           WHERE tenant_id = %s AND created_at > %s""",
        (tenant_id, cutoff),
    )
    total = int(metrics.get("total") or 0)
    queued = int(metrics.get("queued") or 0)

    # Mínimo 10 ações pra evitar trigger por baixo volume
    if total >= 10 and (queued / total * 100) > max_queue_pct:
        pause_minutes = settings["circuit_breaker_pause_minutes"]
        open_until = now + timedelta(minutes=pause_minutes)
        get_postgres().execute(
            """UPDATE aia_health_safety_circuit_breaker
               SET state = 'open', opened_at = NOW(), open_until = %s,
                   open_reason = %s, actions_total = %s, actions_queued = %s,
                   window_start = %s
               WHERE tenant_id = %s""",
            (
                open_until,
                f"queue_rate {queued}/{total} = {queued/total*100:.1f}% exceeds {max_queue_pct}%",
                total, queued, cutoff, tenant_id,
            ),
        )
        audit_log(
            action="guardrail.circuit.opened",
            tenant_id=tenant_id,
            payload={
                "queued": queued, "total": total,
                "rate_pct": round(queued/total*100, 1),
                "pause_until": open_until.isoformat(),
            },
        )
        return False
    return True


# ──────────────────────────── Routing core ────────────────────────────

def route_action(
    *,
    tenant_id: str,
    action_type: str,
    severity: str,
    summary: str,
    patient_id: str | None = None,
    sofia_session_id: str | None = None,
    triggered_by_tool: str | None = None,
    triggered_by_persona: str | None = None,
    sofia_confidence: float | None = None,
    details: dict | None = None,
) -> dict:
    """Decide o destino de uma ação clínica proposta pela Sofia.

    Returns:
        {
            "decision": "execute" | "queue" | "reject" | "paused",
            "reason": str,
            "queue_id": uuid | None (se queued),
            "target_channel": str | None,
            "target_ramal": str | None,
        }
    """
    if action_type not in VALID_ACTION_TYPES:
        return {"decision": DECIDE_REJECT, "reason": f"invalid_action_type:{action_type}"}
    if severity not in VALID_SEVERITIES:
        return {"decision": DECIDE_REJECT, "reason": f"invalid_severity:{severity}"}

    # Modify prescription bloqueado no piloto
    if action_type == ACTION_MODIFY_PRESCRIPTION:
        audit_log(
            action="guardrail.action.rejected",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={
                "action_type": action_type, "severity": severity,
                "summary": summary, "reason": "prescription_modification_blocked_pilot",
            },
        )
        return {
            "decision": DECIDE_REJECT,
            "reason": "prescription_modification_requires_doctor_approval",
        }

    tenant_settings = _get_tenant_settings(tenant_id)
    settings = tenant_settings["guardrail_settings"]
    tenant_type = tenant_settings["tenant_type"]

    # Circuit breaker check
    if not _check_circuit_breaker(tenant_id, settings):
        return {
            "decision": DECIDE_PAUSED,
            "reason": "circuit_breaker_open_for_tenant",
        }

    # Determina canal de escalação e ramal
    routing = _get_patient_routing(patient_id)
    target_channel = routing["channel"]
    target_ramal = routing["ramal"]

    # Fallback para tenant defaults
    if not target_channel:
        if tenant_type == "b2b_casa_geriatrica":
            target_channel = "casa_internal"
            target_ramal = target_ramal or tenant_settings["default_internal_ramal"]
        elif tenant_type == "b2b_clinica":
            target_channel = "clinica_internal"
            target_ramal = target_ramal or tenant_settings["default_internal_ramal"]
        else:  # b2c_individual
            target_channel = "attendant_isabel"
            target_ramal = target_ramal or tenant_settings["default_attendant_ramal"]

    confidence_threshold = float(settings["confidence_threshold"])
    timeout_seconds = int(settings["queue_review_timeout_seconds"])
    auto_critical = bool(settings["auto_execute_on_timeout_critical"])

    # ─── Routing por tipo ───

    if action_type == ACTION_INFORMATIVE:
        # Executa direto, mas registra audit
        audit_log(
            action="guardrail.action.executed",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={
                "action_type": action_type, "severity": severity,
                "tool": triggered_by_tool, "summary": summary[:200],
            },
        )
        return {
            "decision": DECIDE_EXECUTE,
            "reason": "informative_no_review_needed",
            "target_channel": target_channel,
            "target_ramal": target_ramal,
        }

    if action_type == ACTION_EMERGENCY_REALTIME:
        # Bypass — Sofia já tomou ação real-time. Só registramos.
        audit_log(
            action="guardrail.action.executed",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={
                "action_type": action_type, "severity": severity,
                "summary": summary[:200], "bypass_reason": "emergency_realtime",
            },
        )
        return {
            "decision": DECIDE_EXECUTE,
            "reason": "emergency_realtime_bypass",
            "target_channel": target_channel,
            "target_ramal": target_ramal,
        }

    # action_type in (register_history, invoke_attendant) — decide queue vs execute

    needs_review = (
        # Sempre revisão se severity alta
        severity in ("urgent", "critical")
        # Sempre revisão se invoca atendente
        or action_type == ACTION_INVOKE_ATTENDANT
        # Sempre revisão se confidence baixa (quando aplicável)
        or (sofia_confidence is not None and sofia_confidence < confidence_threshold)
    )

    if not needs_review:
        # register_history em severity baixa → executa direto
        audit_log(
            action="guardrail.action.executed",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={
                "action_type": action_type, "severity": severity,
                "tool": triggered_by_tool, "summary": summary[:200],
            },
        )
        return {
            "decision": DECIDE_EXECUTE,
            "reason": "low_severity_no_review",
            "target_channel": target_channel,
            "target_ramal": target_ramal,
        }

    # ENFILEIRA pra revisão humana
    auto_execute_after = None
    if severity == "critical" and auto_critical:
        auto_execute_after = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

    queue_row = get_postgres().insert_returning(
        """INSERT INTO aia_health_action_review_queue
            (tenant_id, patient_id, sofia_session_id, triggered_by_tool,
             triggered_by_persona, action_type, severity, summary, details,
             sofia_confidence, target_channel, target_ramal, auto_execute_after)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id""",
        (
            tenant_id, patient_id, sofia_session_id, triggered_by_tool,
            triggered_by_persona, action_type, severity, summary,
            json.dumps(details or {}),
            sofia_confidence, target_channel, target_ramal, auto_execute_after,
        ),
    )
    queue_id = queue_row["id"] if queue_row else None

    audit_log(
        action="guardrail.action.queued",
        tenant_id=tenant_id,
        resource_type="patient", resource_id=patient_id,
        payload={
            "queue_id": str(queue_id) if queue_id else None,
            "action_type": action_type, "severity": severity,
            "tool": triggered_by_tool, "summary": summary[:200],
            "target_channel": target_channel, "target_ramal": target_ramal,
            "auto_execute_after": auto_execute_after.isoformat() if auto_execute_after else None,
        },
    )

    return {
        "decision": DECIDE_QUEUE,
        "reason": "queued_for_human_review",
        "queue_id": str(queue_id) if queue_id else None,
        "target_channel": target_channel,
        "target_ramal": target_ramal,
        "auto_execute_after": auto_execute_after.isoformat() if auto_execute_after else None,
    }


# ──────────────────────────── Decision (humano resolve) ────────────────────────────

def decide_queued_action(
    *,
    queue_id: str,
    decision: str,  # 'approved' | 'rejected'
    decided_by_user_id: str | None = None,
    notes: str | None = None,
) -> dict:
    """Humano (familiar/atendente/cuidador) resolve uma ação enfileirada."""
    if decision not in ("approved", "rejected"):
        return {"ok": False, "error": "invalid_decision"}

    db = get_postgres()
    row = db.fetch_one(
        "SELECT * FROM aia_health_action_review_queue WHERE id = %s",
        (queue_id,),
    )
    if not row:
        return {"ok": False, "error": "not_found"}
    if row["status"] != "pending":
        return {"ok": False, "error": f"already_decided:{row['status']}"}

    new_status = "approved" if decision == "approved" else "rejected"
    db.execute(
        """UPDATE aia_health_action_review_queue
           SET status = %s, decision_at = NOW(),
               decided_by_user_id = %s, decision_notes = %s
           WHERE id = %s""",
        (new_status, decided_by_user_id, notes, queue_id),
    )

    audit_log(
        action=f"guardrail.action.{new_status}",
        tenant_id=row["tenant_id"],
        actor=decided_by_user_id,
        resource_type="patient",
        resource_id=str(row["patient_id"]) if row["patient_id"] else None,
        payload={
            "queue_id": queue_id,
            "action_type": row["action_type"],
            "severity": row["severity"],
            "notes": notes,
        },
    )
    return {"ok": True, "status": new_status, "row": _serialize_queue_row(row)}


def list_pending_queue(tenant_id: str, limit: int = 50) -> list[dict]:
    rows = get_postgres().fetch_all(
        """SELECT q.*, p.full_name AS patient_name, p.nickname AS patient_nickname
           FROM aia_health_action_review_queue q
           LEFT JOIN aia_health_patients p ON p.id = q.patient_id
           WHERE q.tenant_id = %s AND q.status = 'pending'
           ORDER BY
               CASE q.severity
                   WHEN 'critical' THEN 0 WHEN 'urgent' THEN 1
                   WHEN 'attention' THEN 2 ELSE 3 END,
               q.created_at ASC
           LIMIT %s""",
        (tenant_id, limit),
    )
    return [_serialize_queue_row(r) for r in rows]


def _serialize_queue_row(row: dict) -> dict:
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
    return out


# ──────────────────────────── Auto-execute timeout (cron) ────────────────────────────

def execute_pending_timeouts() -> int:
    """Chamado pelo scheduler. Verifica items com auto_execute_after < NOW
    e severity=critical → marca como auto_executed."""
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT id, tenant_id, patient_id, action_type, severity,
                  triggered_by_tool, summary, details
           FROM aia_health_action_review_queue
           WHERE status = 'pending'
             AND severity = 'critical'
             AND auto_execute_after IS NOT NULL
             AND auto_execute_after <= NOW()
           LIMIT 50"""
    )
    executed = 0
    for r in rows:
        db.execute(
            """UPDATE aia_health_action_review_queue
               SET status = 'auto_executed',
                   decision_at = NOW(),
                   decision_notes = 'Auto-executed: timeout in critical severity'
               WHERE id = %s AND status = 'pending'""",
            (r["id"],),
        )
        audit_log(
            action="guardrail.action.auto_executed",
            tenant_id=r["tenant_id"],
            resource_type="patient",
            resource_id=str(r["patient_id"]) if r["patient_id"] else None,
            payload={
                "queue_id": str(r["id"]),
                "action_type": r["action_type"],
                "severity": r["severity"],
                "tool": r.get("triggered_by_tool"),
            },
        )
        executed += 1

    # Expira items pending com auto_execute_after passado mas NÃO critical
    db.execute(
        """UPDATE aia_health_action_review_queue
           SET status = 'expired', decision_at = NOW(),
               decision_notes = 'Expired: timeout without human decision'
           WHERE status = 'pending'
             AND auto_execute_after IS NOT NULL
             AND auto_execute_after <= NOW()
             AND severity != 'critical'"""
    )
    return executed
