"""Gerenciador de sessão de conversa WhatsApp.

Uma sessão representa uma conversa em andamento entre um cuidador e o sistema.
Estados:
    - idle (sem sessão registrada)
    - awaiting_patient_confirmation — cuidador enviou áudio inicial, aguardamos SIM/NÃO
    - active_with_patient — paciente confirmado; próximas mensagens (áudio ou texto)
      são tratadas como follow-up no contexto do paciente sem re-identificação.

TTL: 30 minutos de inatividade. Qualquer mensagem nova renova (`touch`/`append_message`).
Quando a sessão expira (janela de inatividade), o próximo áudio começa do zero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

SESSION_TTL_MINUTES = 30
# Máximo de mensagens acumuladas antes de sumarizar/truncar (protege context window).
MAX_MESSAGES_IN_CONTEXT = 40


class SessionManager:
    def __init__(self):
        self.db = get_postgres()

    # ---------- leitura ----------
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

    # ---------- escrita ----------
    def set(
        self,
        tenant_id: str,
        phone: str,
        state: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Upsert de sessão. Substitui context inteiro (não faz merge)."""
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

    def transition(
        self,
        tenant_id: str,
        phone: str,
        new_state: str,
        context_patch: dict[str, Any] | None = None,
    ) -> None:
        """Muda state da sessão existente mesclando `context_patch` ao context atual.

        Diferente de `set`, preserva campos do context que não estão no patch (p.ex.,
        preserva `messages` ao mudar de awaiting_patient_confirmation → active_with_patient).
        """
        existing = self.get(tenant_id, phone)
        new_context = dict(existing.get("context") or {}) if existing else {}
        if context_patch:
            new_context.update(context_patch)
        self.set(tenant_id, phone, state=new_state, context=new_context)

    def append_message(
        self,
        tenant_id: str,
        phone: str,
        message: dict[str, Any],
    ) -> None:
        """Acrescenta uma mensagem em `context.messages` e renova TTL.

        `message` deve ter ao menos {"role": "caregiver"|"assistant", "kind": "...",
        "text": "..."} e qualquer metadado adicional relevante. `timestamp` é adicionado
        automaticamente em ISO8601 UTC.

        Se não existe sessão ativa, no-op com warning.
        Se o número de mensagens exceder MAX_MESSAGES_IN_CONTEXT, remove as mais antigas
        mantendo a primeira (para não perder o ponto de partida da conversa) e as
        MAX_MESSAGES_IN_CONTEXT-1 mais recentes.
        """
        sess = self.get(tenant_id, phone)
        if not sess:
            logger.warning("append_message_no_session", phone=phone)
            return

        message_enriched = dict(message)
        message_enriched.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

        context = dict(sess.get("context") or {})
        messages = list(context.get("messages") or [])
        messages.append(message_enriched)

        # Truncamento defensivo — mantém primeira msg (seed da conversa) + últimas.
        if len(messages) > MAX_MESSAGES_IN_CONTEXT:
            head = messages[:1]
            tail = messages[-(MAX_MESSAGES_IN_CONTEXT - 1):]
            messages = head + tail
            logger.info("session_messages_truncated", phone=phone, kept=len(messages))

        context["messages"] = messages

        expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
        self.db.execute(
            """
            UPDATE aia_health_conversation_sessions
            SET context = %s,
                expires_at = %s,
                updated_at = NOW()
            WHERE tenant_id = %s AND phone = %s
            """,
            (self.db.json_adapt(context), expires, tenant_id, phone),
        )

    def touch(self, tenant_id: str, phone: str) -> None:
        """Renova TTL sem alterar state ou context."""
        expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
        self.db.execute(
            """
            UPDATE aia_health_conversation_sessions
            SET expires_at = %s, updated_at = NOW()
            WHERE tenant_id = %s AND phone = %s
            """,
            (expires, tenant_id, phone),
        )

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
