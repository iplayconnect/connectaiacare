"""Audit service — registra ações sensíveis em aia_health_audit_chain.

Hash-chain inviolável (cada linha referencia o hash da anterior). Atende LGPD
Art. 11 + CFM 2.314/2022. Schema da tabela vem da migration 001.

Uso típico em handlers:

    from src.services.audit_service import audit_log, AuditAction

    audit_log(
        action=AuditAction.PATIENT_UPDATE,
        resource_type="patient",
        resource_id=patient_id,
        payload={"changed": ["medications"]},
    )

actor é preenchido automaticamente a partir de g.user (JWT decodificado).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import g

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuditAction:
    """Ações canônicas. Adicionar conforme novos endpoints exigirem."""
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGIN_LOCKED = "auth.login_locked"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password_changed"
    PASSWORD_RESET = "auth.password_reset"
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
    PASSWORD_RESET_USED = "auth.password_reset_used"
    ACCOUNT_LOCKED = "auth.account_locked"

    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_AVATAR_UPLOAD = "user.avatar_upload"

    PROFILE_CREATE = "profile.create"
    PROFILE_UPDATE = "profile.update"
    PROFILE_DELETE = "profile.delete"

    PATIENT_CREATE = "patient.create"
    PATIENT_UPDATE = "patient.update"
    PATIENT_DELETE = "patient.delete"
    PATIENT_VIEW = "patient.view"

    EVENT_CLOSE = "event.close"
    TELECONSULTA_SIGN = "teleconsulta.sign"


def _stable_json(data: Any) -> str:
    """JSON canonical pra hash determinístico (sort_keys, separators)."""
    return json.dumps(data or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _last_hash(tenant_id: str) -> str | None:
    row = get_postgres().fetch_one(
        "SELECT curr_hash FROM aia_health_audit_chain "
        "WHERE tenant_id = %s ORDER BY id DESC LIMIT 1",
        (tenant_id,),
    )
    return row["curr_hash"] if row else None


def audit_log(
    *,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict | None = None,
    tenant_id: str | None = None,
    actor: str | None = None,
) -> None:
    """Insere uma linha na chain. Não levanta exceção (audit não pode bloquear).

    Args:
        action: ex AuditAction.PATIENT_UPDATE
        resource_type: "patient" / "user" / "event"
        resource_id: id do recurso afetado
        payload: dados adicionais (não-sensíveis — não logar PHI plaintext)
        tenant_id: override; default = g.user.tenant_id
        actor: override; default = g.user.sub (UUID do user)
    """
    try:
        # `g` é proxy do Flask — acessá-lo fora de app context lança
        # RuntimeError. Workers/schedulers chamam audit_log sem context.
        try:
            user_ctx = getattr(g, "user", None) or {}
        except RuntimeError:
            user_ctx = {}
        actor_id = actor or user_ctx.get("sub") or "system"
        tenant = tenant_id or user_ctx.get("tenant_id") or "connectaiacare_demo"

        data_str = _stable_json({
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload": payload or {},
            "actor": actor_id,
            "tenant_id": tenant,
        })
        data_hash = hashlib.sha256(data_str.encode("utf-8")).hexdigest()
        prev = _last_hash(tenant)
        curr_hash = hashlib.sha256(
            f"{prev or ''}{data_hash}".encode("utf-8")
        ).hexdigest()

        pg = get_postgres()
        pg.execute(
            """
            INSERT INTO aia_health_audit_chain
                (tenant_id, event_type, actor, resource_type, resource_id,
                 action, data_hash, prev_hash, curr_hash, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant,
                action.split(".")[0],
                actor_id,
                resource_type,
                resource_id,
                action,
                data_hash,
                prev,
                curr_hash,
                pg.json_adapt(payload or {}),
            ),
        )
    except Exception as exc:  # noqa: BLE001 — audit nunca quebra o fluxo
        logger.error("audit_log_failed", action=action, error=str(exc))
