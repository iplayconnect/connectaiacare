"""Gerenciador de sessão de conversa WhatsApp (estado do fluxo)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_TTL_MINUTES = 30


class SessionManager:
    """Estados possíveis:
    - idle (sem sessão)
    - awaiting_patient_confirmation — cuidador enviou áudio, aguardamos SIM/NÃO
    - processing — relato sendo analisado
    """

    def __init__(self):
        self.db = get_postgres()

    def get(self, tenant_id: str, phone: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT id, state, context, expires_at
            FROM aia_health_conversation_sessions
            WHERE tenant_id = %s AND phone = %s AND expires_at > NOW()
            """,
            (tenant_id, phone),
        )
        return row

    def set(self, tenant_id: str, phone: str, state: str, context: dict[str, Any] | None = None) -> None:
        expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
        self.db.execute(
            """
            INSERT INTO aia_health_conversation_sessions (tenant_id, phone, state, context, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, phone) DO UPDATE
                SET state = EXCLUDED.state,
                    context = EXCLUDED.context,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            """,
            (tenant_id, phone, state, self.db.json_adapt(context or {}), expires),
        )
        logger.info("session_set", phone=phone, state=state)

    def clear(self, tenant_id: str, phone: str) -> None:
        self.db.execute(
            "DELETE FROM aia_health_conversation_sessions WHERE tenant_id = %s AND phone = %s",
            (tenant_id, phone),
        )
        logger.info("session_cleared", phone=phone)


_session_instance: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_instance
    if _session_instance is None:
        _session_instance = SessionManager()
    return _session_instance
