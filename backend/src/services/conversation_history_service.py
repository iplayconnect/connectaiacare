"""Conversation History Service — janela deslizante cross-canal.

Persistência unificada de mensagens (user + Sofia) na tabela
`aia_health_conversation_messages` e recuperação rápida dos últimos N
turnos como contexto pra LLM.

Cross-canal desde o dia 1 (ADR-027):
    - channel ∈ {whatsapp, alexa, voice_native, web, sms, internal}
    - session_context ∈ {onboarding, care_event, teleconsultation, companion, general}

Fluxos suportados:
    1. record_inbound(phone, content, channel=..., session_context=...)
       → grava mensagem do usuário com `direction=inbound` e `role=user`
    2. record_outbound(phone, content, ...)
       → grava resposta da Sofia (ou texto humano via Atente)
    3. get_window(phone, limit=5, session_context=None)
       → retorna últimas N mensagens ordenadas cronologicamente
         pronto pra montar como messages[] de LLM (system/user/assistant)
    4. as_llm_messages(window)
       → converte pro formato OpenAI/Anthropic-compat:
         [{"role": "user", "content": "..."}, ...]

Uso típico no pipeline/onboarding:

    history = get_conversation_history()
    history.record_inbound(phone, user_text, channel="whatsapp",
                          session_context="onboarding")
    window = history.get_window(phone, limit=5)
    llm_msgs = history.as_llm_messages(window)
    response = router.complete(messages=[{"role":"system", ...}] + llm_msgs + [...])
    history.record_outbound(phone, response_text, channel="whatsapp",
                           session_context="onboarding")

Observações:
    - Tenant fixo por enquanto (sofiacuida_b2c) — futuro: multi-tenant real
    - Sem PII encryption aqui (isso é responsabilidade do memory distiller
      na Onda C). A tabela é de trabalho operacional curto prazo.
    - Índice `idx_conv_msg_phone_time` garante queries rápidas por sliding window
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_TENANT = "sofiacuida_b2c"

# Tamanhos da janela por modo de operação
WINDOW_ONBOARDING = 8        # cadastro precisa de mais contexto
WINDOW_COMPANION = 15        # conversa do dia-a-dia exige mais memória curta
WINDOW_CARE_EVENT = 5        # clínico vai direto ao ponto
WINDOW_DEFAULT = 6


class ConversationHistoryService:
    def __init__(self):
        self.db = get_postgres()

    # ═══════════════════════════════════════════════════════════════
    # Persistência
    # ═══════════════════════════════════════════════════════════════

    def record_inbound(
        self,
        phone: str,
        content: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
        channel: str = "whatsapp",
        session_context: str = "general",
        session_id: str | None = None,
        subject_id: str | None = None,
        subject_type: str = "unknown",
        message_format: str = "text",
        content_raw_ref: str | None = None,
        external_id: str | None = None,
        reply_to_id: str | None = None,
        metadata: dict | None = None,
        safety_moderated: bool = False,
        safety_score: dict | None = None,
        safety_event_id: str | None = None,
    ) -> str:
        """Grava mensagem do USUÁRIO. Retorna UUID da linha criada."""
        return self._insert(
            phone=phone,
            tenant_id=tenant_id,
            channel=channel,
            direction="inbound",
            role="user",
            content=content,
            session_context=session_context,
            session_id=session_id,
            subject_id=subject_id,
            subject_type=subject_type,
            message_format=message_format,
            content_raw_ref=content_raw_ref,
            external_id=external_id,
            reply_to_id=reply_to_id,
            metadata=metadata,
            safety_moderated=safety_moderated,
            safety_score=safety_score,
            safety_event_id=safety_event_id,
            processing_agent=None,
        )

    def record_outbound(
        self,
        phone: str,
        content: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
        channel: str = "whatsapp",
        session_context: str = "general",
        session_id: str | None = None,
        subject_id: str | None = None,
        subject_type: str = "unknown",
        message_format: str = "text",
        processing_agent: str | None = "sofia",
        processing_duration_ms: int | None = None,
        metadata: dict | None = None,
        reply_to_id: str | None = None,
    ) -> str:
        """Grava resposta da SOFIA (ou humano via Atente)."""
        return self._insert(
            phone=phone,
            tenant_id=tenant_id,
            channel=channel,
            direction="outbound",
            role="assistant",
            content=content,
            session_context=session_context,
            session_id=session_id,
            subject_id=subject_id,
            subject_type=subject_type,
            message_format=message_format,
            processing_agent=processing_agent,
            processing_duration_ms=processing_duration_ms,
            metadata=metadata,
            reply_to_id=reply_to_id,
        )

    def _insert(
        self,
        *,
        phone: str,
        tenant_id: str,
        channel: str,
        direction: str,
        role: str,
        content: str,
        session_context: str,
        session_id: str | None = None,
        subject_id: str | None = None,
        subject_type: str = "unknown",
        message_format: str = "text",
        content_raw_ref: str | None = None,
        external_id: str | None = None,
        reply_to_id: str | None = None,
        metadata: dict | None = None,
        safety_moderated: bool = False,
        safety_score: dict | None = None,
        safety_event_id: str | None = None,
        processing_agent: str | None = None,
        processing_duration_ms: int | None = None,
    ) -> str:
        try:
            row = self.db.insert_returning(
                """
                INSERT INTO aia_health_conversation_messages
                    (tenant_id, subject_phone, subject_id, subject_type,
                     session_context, session_id, channel,
                     direction, role, message_format,
                     content, content_raw_ref, metadata,
                     safety_moderated, safety_score, safety_event_id,
                     processing_agent, processing_duration_ms,
                     external_id, reply_to_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tenant_id, phone, subject_id, subject_type,
                    session_context, session_id, channel,
                    direction, role, message_format,
                    content, content_raw_ref,
                    self.db.json_adapt(metadata) if metadata else None,
                    safety_moderated,
                    self.db.json_adapt(safety_score) if safety_score else None,
                    safety_event_id,
                    processing_agent, processing_duration_ms,
                    external_id, reply_to_id,
                ),
            )
            msg_id = str(row["id"]) if row else ""
            logger.debug(
                "conv_msg_recorded",
                phone=phone, direction=direction, channel=channel,
                session_context=session_context, msg_id=msg_id,
                content_len=len(content or ""),
            )
            return msg_id
        except Exception as exc:
            logger.error(
                "conv_msg_insert_failed",
                phone=phone, direction=direction, error=str(exc),
            )
            return ""

    # ═══════════════════════════════════════════════════════════════
    # Recuperação (janela deslizante)
    # ═══════════════════════════════════════════════════════════════

    def get_window(
        self,
        phone: str,
        *,
        limit: int = WINDOW_DEFAULT,
        session_context: str | None = None,
        tenant_id: str = DEFAULT_TENANT,
        since_minutes: int | None = None,
    ) -> list[dict]:
        """Últimas N mensagens (DESC pelo banco → retorna ASC pra LLM).

        Args:
            phone: número do usuário
            limit: quantas mensagens trazer (padrão 6 = 3 pares user/assistant)
            session_context: filtra por 'onboarding' | 'care_event' | ... ou None (todas)
            since_minutes: só pega mensagens dos últimos N minutos (None = sem limite)

        Returns:
            Lista ordenada cronologicamente (mais antiga primeiro).
            Cada item: {id, direction, role, content, received_at, channel,
                        session_context, message_format, metadata}
        """
        params: list[Any] = [tenant_id, phone]
        where = [
            "tenant_id = %s",
            "subject_phone = %s",
            "content IS NOT NULL",
            "content != ''",
        ]

        if session_context:
            where.append("session_context = %s")
            params.append(session_context)

        if since_minutes is not None:
            where.append("received_at >= %s")
            params.append(datetime.now(timezone.utc) - timedelta(minutes=since_minutes))

        params.append(limit)

        query = f"""
            SELECT id, direction, role, content, received_at, channel,
                   session_context, message_format, metadata,
                   safety_moderated, processing_agent
            FROM aia_health_conversation_messages
            WHERE {' AND '.join(where)}
            ORDER BY received_at DESC
            LIMIT %s
        """

        rows = self.db.fetch_all(query, tuple(params))
        # inverte pra ordem cronológica (mais antiga → mais recente)
        rows.reverse()
        return rows

    def as_llm_messages(
        self, window: list[dict], include_system: str | None = None,
    ) -> list[dict]:
        """Converte janela pro formato messages[] de LLM.

        Formato: [{"role": "user"|"assistant"|"system", "content": "..."}]
        Ignora mensagens sem conteúdo texto.

        Args:
            window: resultado de get_window()
            include_system: se fornecido, insere como primeira msg system
        """
        msgs: list[dict] = []
        if include_system:
            msgs.append({"role": "system", "content": include_system})

        for row in window:
            content = row.get("content") or ""
            role = row.get("role") or "user"
            # Normaliza role pra formato LLM
            if role not in ("user", "assistant", "system"):
                role = "user" if row.get("direction") == "inbound" else "assistant"
            if not content.strip():
                continue
            msgs.append({"role": role, "content": content})

        return msgs

    # ═══════════════════════════════════════════════════════════════
    # Queries utilitárias
    # ═══════════════════════════════════════════════════════════════

    def count_recent(
        self, phone: str, *,
        tenant_id: str = DEFAULT_TENANT,
        minutes: int = 60,
        direction: str | None = None,
    ) -> int:
        """Conta mensagens nos últimos N minutos (rate-limit, anti-abuse)."""
        params: list[Any] = [tenant_id, phone, datetime.now(timezone.utc) - timedelta(minutes=minutes)]
        where = ["tenant_id = %s", "subject_phone = %s", "received_at >= %s"]
        if direction:
            where.append("direction = %s")
            params.append(direction)

        row = self.db.fetch_one(
            f"SELECT COUNT(*) as n FROM aia_health_conversation_messages WHERE {' AND '.join(where)}",
            tuple(params),
        )
        return int(row["n"]) if row else 0

    def get_last_outbound(
        self, phone: str, *,
        tenant_id: str = DEFAULT_TENANT,
        session_context: str | None = None,
    ) -> dict | None:
        """Última mensagem enviada pela Sofia — útil pra detectar repetição."""
        where = [
            "tenant_id = %s",
            "subject_phone = %s",
            "direction = 'outbound'",
        ]
        params: list[Any] = [tenant_id, phone]
        if session_context:
            where.append("session_context = %s")
            params.append(session_context)

        return self.db.fetch_one(
            f"""
            SELECT id, content, received_at, metadata, processing_agent
            FROM aia_health_conversation_messages
            WHERE {' AND '.join(where)}
            ORDER BY received_at DESC
            LIMIT 1
            """,
            tuple(params),
        )

    def mark_safety(
        self, message_id: str, *,
        safety_event_id: str | None = None,
        safety_score: dict | None = None,
    ) -> None:
        """Atualiza flags de safety após moderação (caso tenha sido assincrona)."""
        if not message_id:
            return
        self.db.execute(
            """
            UPDATE aia_health_conversation_messages
            SET safety_moderated = TRUE,
                safety_event_id = COALESCE(%s, safety_event_id),
                safety_score = COALESCE(%s::jsonb, safety_score)
            WHERE id = %s
            """,
            (
                safety_event_id,
                self.db.json_adapt(safety_score) if safety_score else None,
                message_id,
            ),
        )


# Singleton
_instance: ConversationHistoryService | None = None


def get_conversation_history() -> ConversationHistoryService:
    global _instance
    if _instance is None:
        _instance = ConversationHistoryService()
    return _instance
