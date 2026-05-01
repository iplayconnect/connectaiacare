"""AuditLogWriter — persistência de eventos audit imutável.

Tabela aia_health_audit_log (migration 061) é append-only:
triggers Postgres recusam UPDATE/DELETE.

Usage:
    write_audit(
        action="webhook_received",
        actor="sofia",
        tenant_id=tid,
        trace_id=trace_id,
        payload={"phone_redacted": "55519****", "msg_type": "text"},
    )

Princípios:
    - JAMAIS persistir conteúdo clínico bruto (PII) — usar sempre
      versão redacted. PII completa fica em aia_health_sofia_messages
      com retention/access control próprios.
    - Toda chamada deve incluir trace_id pra correlação E2E.
    - Falhas no audit log NÃO derrubam request (best-effort, mas log
      warning loud).
    - Particionar mensalmente quando >10M rows (Phase E).

Ações canônicas (use estas strings):
    inbound_received, outbound_sent
    intent_classified, identity_resolved, tenant_resolved
    session_started, session_closed, session_continued_cross_channel
    tool_called, tool_failed, guardrail_decision
    handoff_initiated, handoff_claimed, handoff_resolved
    lead_captured, lead_qualified, lead_converted, lead_lost
    lgpd_consent_accepted, lgpd_data_export_requested,
    lgpd_data_deletion_requested
    pii_redacted
    rate_limit_exceeded, quota_exhausted
    white_label_override_used
    webhook_unknown_instance
"""
from __future__ import annotations

import json
from typing import Optional, Union

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def write_audit(
    *,
    action: str,
    actor: Optional[str] = None,
    actor_role: Optional[str] = None,
    tenant_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[Union[str, "UUID"]] = None,  # type: ignore  # noqa
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[str]:
    """Persiste linha em aia_health_audit_log. Best-effort: não
    derruba request em caso de falha. Returns id do row inserido
    ou None.
    """
    try:
        row = get_postgres().insert_returning(
            """INSERT INTO aia_health_audit_log (
                tenant_id, trace_id, session_id, action, actor, actor_role,
                resource_type, resource_id, payload, ip_address, user_agent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id""",
            (
                tenant_id,
                str(trace_id) if trace_id else None,
                str(session_id) if session_id else None,
                action,
                actor,
                actor_role,
                resource_type,
                resource_id,
                json.dumps(payload or {}),
                ip_address,
                user_agent,
            ),
        )
        return str(row["id"]) if row else None
    except Exception as exc:
        logger.warning(
            "audit_log_write_failed",
            action=action,
            error=str(exc)[:200],
        )
        return None


# ──────────────────────────────────────────────────────────────────
# PII redaction helper
# ──────────────────────────────────────────────────────────────────


def redact_phone(phone: Optional[str]) -> Optional[str]:
    """5551984928518 → 55519****8518 (mantém DDI+DDD+último 4)."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 10:
        return "***"
    return f"{digits[:5]}****{digits[-4:]}"


def redact_email(email: Optional[str]) -> Optional[str]:
    """alex@example.com → a***@example.com"""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def redact_cpf(cpf: Optional[str]) -> Optional[str]:
    """123.456.789-00 → ***.***.789-**"""
    if not cpf:
        return None
    digits = "".join(c for c in cpf if c.isdigit())
    if len(digits) != 11:
        return "***"
    return f"***.***.{digits[6:9]}-**"


def redact_full_name(name: Optional[str]) -> Optional[str]:
    """Alexandre Veras → A. Veras (primeira letra + último sobrenome)."""
    if not name or not name.strip():
        return None
    parts = name.strip().split()
    if len(parts) == 1:
        return f"{parts[0][0]}***"
    return f"{parts[0][0]}. {parts[-1]}"


def redact_payload(payload: dict) -> dict:
    """Aplica redaction recursiva em chaves conhecidas de PII.

    Não usar pra audit clinic content (tem retention própria).
    """
    if not payload:
        return {}
    out: dict = {}
    for k, v in payload.items():
        if isinstance(v, dict):
            out[k] = redact_payload(v)
        elif isinstance(v, list):
            out[k] = [redact_payload(i) if isinstance(i, dict) else i for i in v]
        elif k in {"phone", "telefone", "caregiver_phone", "responsible_phone"}:
            out[k] = redact_phone(str(v) if v else None)
        elif k in {"email", "e_mail"}:
            out[k] = redact_email(str(v) if v else None)
        elif k == "cpf":
            out[k] = redact_cpf(str(v) if v else None)
        elif k in {"full_name", "name", "patient_name", "caregiver_name"}:
            out[k] = redact_full_name(str(v) if v else None)
        else:
            out[k] = v
    return out
