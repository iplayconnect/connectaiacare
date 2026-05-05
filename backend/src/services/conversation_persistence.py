"""Persistência multi-channel pra `aia_health_conversation_messages`.

Tabela genérica que cobre WhatsApp + voz + outros canais futuros.
Diferente de `sofia_persistence` (que escreve em `aia_health_sofia_*`,
específica do agent novo Commercial/Support), aqui é a fonte de verdade
audit-friendly de TODA mensagem trocada — independente de qual sub-agent
processou (commercial, support, passthrough, futuro CareSofiaAgent etc).

Phase C v2 PR 1: fecha gap silencioso identificado no synthetic test
(2026-05-05) — pipeline legado NÃO persistia turnos de perfis
identificados, deixando memória conversacional incompleta. Agora o
orchestrator chama `persist_message` ANTES e DEPOIS do agent process,
garantindo:

  - Audit trail LGPD-completo (toda msg fica logada com tenant scope)
  - Memória cross-channel pra futuros agents reusarem contexto
  - Fonte única de verdade pra UI de handoff/operador

Best-effort: falha NÃO bloqueia o turn (logger.warning). Não usa
transação cross-table — se a chamada falhar não corrompe state.

API:

    from src.services.conversation_persistence import persist_message

    # User msg inbound
    persist_message(
        tenant_id=tenant.id,
        phone="5551999000888",
        role="user",
        direction="inbound",
        content="Diazepam pra dormir, pode dar?",
        channel="whatsapp",
        external_id=trace_id,
        subject_id=identity.primary.caregiver_id if identity.primary else None,
        subject_type="caregiver" if identity.primary else "anonymous",
        metadata={"profile": "cuidador_pro"},
    )

    # Assistant msg outbound (após agent.process)
    persist_message(
        tenant_id=tenant.id,
        phone="5551999000888",
        role="assistant",
        direction="outbound",
        content=response.text,
        channel="whatsapp",
        external_id=trace_id,
        processing_agent=agent.name,
        processing_duration_ms=duration_ms,
    )
"""
from __future__ import annotations

import json
from typing import Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Roles permitidos pelo schema (NOT NULL)
_VALID_ROLES = frozenset({"user", "assistant", "system", "tool"})
# Direções permitidas
_VALID_DIRECTIONS = frozenset({"inbound", "outbound"})
# Subject types comuns (livre, mas padrão facilita query)
_COMMON_SUBJECT_TYPES = frozenset({
    "anonymous", "caregiver", "patient", "user", "family", "operator",
})


def persist_message(
    *,
    tenant_id: str,
    phone: str,
    role: str,
    direction: str,
    content: str,
    channel: str = "whatsapp",
    message_format: str = "text",
    external_id: Optional[str] = None,
    session_id: Optional[str] = None,
    session_context: Optional[str] = None,
    subject_id: Optional[str] = None,
    subject_type: Optional[str] = None,
    processing_agent: Optional[str] = None,
    processing_duration_ms: Optional[int] = None,
    metadata: Optional[dict] = None,
    safety_moderated: bool = False,
    reply_to_id: Optional[str] = None,
) -> Optional[str]:
    """Persiste uma mensagem em `aia_health_conversation_messages`.

    Best-effort. Validação leve (role/direction). Em falha, retorna
    None e loga warning — chamador NÃO precisa tratar exceção.

    Args:
        tenant_id: tenant scope (REQ pra isolamento LGPD)
        phone: identificador canal-agnóstico (E.164 sem +)
        role: 'user' | 'assistant' | 'system' | 'tool'
        direction: 'inbound' | 'outbound'
        content: texto da mensagem (pode ser truncado se gigante)
        channel: 'whatsapp' (default) | 'voice' | 'web' | 'sms'
        message_format: 'text' (default) | 'audio' | 'image' | 'document'
        external_id: trace_id ou ID externo (Evolution msg_id)
        session_id: UUID da sessão (legacy ou sofia)
        session_context: discriminator livre (ex 'sofia_inbound', 'voice_call')
        subject_id: UUID do user/caregiver/patient identificado (None se anon)
        subject_type: 'caregiver' | 'patient' | 'user' | 'family' | 'anonymous'
        processing_agent: nome do sub-agent que processou (commercial,
            care, passthrough_legacy, etc) — só pra direction=outbound
        processing_duration_ms: latência do turn — só pra direction=outbound
        metadata: dict livre pra audit (intent, scenario, flags)
        safety_moderated: TRUE se foi guardrail-replaced
        reply_to_id: UUID da msg que está respondendo (thread)

    Returns:
        UUID da row inserida (str) ou None se falhou.
    """
    # Validação defensiva — schema check_constraint vai rejeitar
    # mas erro de DB é mais barulhento que erro Python aqui
    if role not in _VALID_ROLES:
        logger.warning(
            "conversation_persist_invalid_role",
            role=role, valid=list(_VALID_ROLES),
        )
        return None
    if direction not in _VALID_DIRECTIONS:
        logger.warning(
            "conversation_persist_invalid_direction",
            direction=direction, valid=list(_VALID_DIRECTIONS),
        )
        return None
    if not tenant_id:
        logger.warning("conversation_persist_missing_tenant")
        return None

    # Truncamento defensivo pra content gigante (caso usuário cole txt 50k)
    if content and len(content) > 50000:
        content = content[:50000] + "\n[truncated]"

    try:
        db = get_postgres()
        # Importante: usar insert_returning (commit=True) — fetch_one
        # tem commit=False (otimizado pra SELECT) e provoca rollback
        # silencioso de INSERTs feitos via fetch_one. Bug detectado em
        # smoke test 2026-05-05: id voltava preenchido mas SELECT
        # subsequente em outra conexão via 0 rows.
        row = db.insert_returning(
            """INSERT INTO aia_health_conversation_messages (
                  tenant_id, subject_phone, subject_id, subject_type,
                  session_id, session_context,
                  channel, direction, role, message_format, content,
                  metadata, received_at, safety_moderated,
                  processing_agent, processing_duration_ms,
                  external_id, reply_to_id
               ) VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s,
                  %s::jsonb, NOW(), %s,
                  %s, %s, %s, %s
               )
               RETURNING id::text AS id""",
            (
                tenant_id, phone, subject_id, subject_type,
                session_id, session_context,
                channel, direction, role, message_format, content,
                json.dumps(metadata or {}), safety_moderated,
                processing_agent, processing_duration_ms,
                external_id, reply_to_id,
            ),
        )
        return (row or {}).get("id")
    except Exception as exc:
        logger.warning(
            "conversation_persist_failed",
            tenant_id=tenant_id,
            role=role,
            direction=direction,
            channel=channel,
            error=str(exc)[:200],
        )
        return None
