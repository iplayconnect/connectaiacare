"""ConversationState — aggregate root do CSM v2.

Single source of truth da conversa. 1 row por (tenant_id, client_id) na
tabela aia_health_conversation_state (migration 062).

Composição:
    state = ConversationState(
        tenant_id, client_id,
        lead_data: CareLeadData,
        flow_state: FlowState,
        interactions: list[Interaction],   # janela últimas 30
        ...
    )

Uso típico no orchestrator:

    state = ConversationState.load(tenant_id, client_id) or \
            ConversationState.create(tenant_id, client_id, session_id=...)

    # Ao receber msg do user
    pending = state.flow_state.pending_question_intent
    if pending and state.last_unanswered():
        state.last_unanswered().attach_user_response(user_text)

    # Após Sofia gerar resposta
    state.add_interaction(Interaction(
        bot_message=bot_text,
        bot_intent=QuestionIntent.COUNT_IDOSOS,
        bot_agent="commercial",
    ))
    state.flow_state.set_pending(bot_text, QuestionIntent.COUNT_IDOSOS)

    # Persistir
    state.save()

    # Ao construir prompt do agent
    ctx = state.get_context_for_agent()
    # → {has_primeiro_nome: True, primeiro_nome: "Douglas",
    #    should_ask_count_idosos: True, ...}
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from src.services.csm.care_lead_data import CareLeadData
from src.services.csm.flow_state import (
    INTENT_TO_FIELD,
    ConversationStage,
    FlowState,
    QuestionIntent,
)
from src.services.csm.interaction import Interaction
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Janela de interactions mantida em memória / banco
INTERACTIONS_WINDOW = 30


@dataclass
class ConversationState:
    """Aggregate root da CSM v2."""

    tenant_id: str
    client_id: str  # phone E.164 normalizado

    # FK opcionais
    user_id: Optional[str] = None
    patient_id: Optional[str] = None
    session_id: Optional[str] = None

    # Conteúdo
    lead_data: CareLeadData = field(default_factory=CareLeadData)
    flow_state: FlowState = field(default_factory=FlowState)
    interactions: list[Interaction] = field(default_factory=list)

    # Metadata
    contact_origin: str = "inbound"  # 'inbound' | 'outbound'
    metadata: dict[str, Any] = field(default_factory=dict)

    # Timestamps (preenchidos pelo banco)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_activity_at: Optional[str] = None

    # ──────────────────────────────────────────────────────────────
    # Persistência
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ConversationState":
        """Reconstrói de uma row de aia_health_conversation_state."""
        lead_data_raw = row.get("lead_data") or {}
        flow_state_raw = row.get("flow_state") or {}
        interactions_raw = row.get("interactions") or []

        # JSONB pode vir como str dependendo do driver
        if isinstance(lead_data_raw, str):
            lead_data_raw = json.loads(lead_data_raw)
        if isinstance(flow_state_raw, str):
            flow_state_raw = json.loads(flow_state_raw)
        if isinstance(interactions_raw, str):
            interactions_raw = json.loads(interactions_raw)

        return cls(
            tenant_id=row["tenant_id"],
            client_id=row["client_id"],
            user_id=str(row["user_id"]) if row.get("user_id") else None,
            patient_id=str(row["patient_id"]) if row.get("patient_id") else None,
            session_id=str(row["session_id"]) if row.get("session_id") else None,
            lead_data=CareLeadData.from_dict(lead_data_raw),
            flow_state=FlowState.from_dict(flow_state_raw),
            interactions=[Interaction.from_dict(i) for i in interactions_raw],
            contact_origin=row.get("contact_origin") or "inbound",
            metadata=row.get("metadata") or {},
            created_at=row["created_at"].isoformat() if row.get("created_at") else None,
            updated_at=row["updated_at"].isoformat() if row.get("updated_at") else None,
            last_activity_at=(
                row["last_activity_at"].isoformat()
                if row.get("last_activity_at") else None
            ),
        )

    @classmethod
    def load(
        cls,
        tenant_id: str,
        client_id: str,
    ) -> Optional["ConversationState"]:
        """Carrega state existente. None se não existe."""
        try:
            row = get_postgres().fetch_one(
                """SELECT * FROM aia_health_conversation_state
                   WHERE tenant_id = %s AND client_id = %s""",
                (tenant_id, client_id),
            )
        except Exception as exc:
            logger.warning(
                "csm_load_failed",
                tenant_id=tenant_id, client_id=client_id, error=str(exc)[:200],
            )
            return None
        return cls.from_row(row) if row else None

    @classmethod
    def load_or_create(
        cls,
        tenant_id: str,
        client_id: str,
        *,
        user_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        session_id: Optional[str] = None,
        contact_origin: str = "inbound",
    ) -> "ConversationState":
        """Carrega state existente OU cria novo (sem persistir ainda).

        O .save() seguinte faz upsert atômico.
        """
        existing = cls.load(tenant_id, client_id)
        if existing:
            # Atualiza FKs opcionais se vieram novos
            if user_id and not existing.user_id:
                existing.user_id = user_id
            if patient_id and not existing.patient_id:
                existing.patient_id = patient_id
            if session_id:
                existing.session_id = session_id
            return existing
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            user_id=user_id,
            patient_id=patient_id,
            session_id=session_id,
            contact_origin=contact_origin,
        )

    def save(self) -> bool:
        """Upsert em aia_health_conversation_state. Best-effort:
        retorna False em falha mas NÃO levanta."""
        # Trim interactions pra janela
        if len(self.interactions) > INTERACTIONS_WINDOW:
            self.interactions = self.interactions[-INTERACTIONS_WINDOW:]

        lead_json = json.dumps(self.lead_data.to_dict())
        flow_json = json.dumps(self.flow_state.to_dict())
        interactions_json = json.dumps([i.to_dict() for i in self.interactions])
        metadata_json = json.dumps(self.metadata or {})

        try:
            get_postgres().execute(
                """INSERT INTO aia_health_conversation_state (
                    tenant_id, client_id, user_id, patient_id, session_id,
                    lead_data, flow_state, interactions,
                    contact_origin, metadata
                ) VALUES (%s, %s, %s, %s, %s,
                          %s::jsonb, %s::jsonb, %s::jsonb,
                          %s, %s::jsonb)
                ON CONFLICT (tenant_id, client_id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, aia_health_conversation_state.user_id),
                    patient_id = COALESCE(EXCLUDED.patient_id, aia_health_conversation_state.patient_id),
                    session_id = COALESCE(EXCLUDED.session_id, aia_health_conversation_state.session_id),
                    lead_data = EXCLUDED.lead_data,
                    flow_state = EXCLUDED.flow_state,
                    interactions = EXCLUDED.interactions,
                    contact_origin = EXCLUDED.contact_origin,
                    metadata = EXCLUDED.metadata""",
                (
                    self.tenant_id, self.client_id, self.user_id,
                    self.patient_id, self.session_id,
                    lead_json, flow_json, interactions_json,
                    self.contact_origin, metadata_json,
                ),
            )
            return True
        except Exception as exc:
            logger.warning(
                "csm_save_failed",
                tenant_id=self.tenant_id, client_id=self.client_id,
                error=str(exc)[:200],
            )
            return False

    # ──────────────────────────────────────────────────────────────
    # Mutação
    # ──────────────────────────────────────────────────────────────

    def add_interaction(self, interaction: Interaction) -> None:
        """Append + trim janela."""
        self.interactions.append(interaction)
        if len(self.interactions) > INTERACTIONS_WINDOW:
            self.interactions = self.interactions[-INTERACTIONS_WINDOW:]

    def last_unanswered(self) -> Optional[Interaction]:
        """Retorna última interaction com bot_message mas sem
        lead_message. Usado pra parear próxima resposta do user."""
        for i in reversed(self.interactions):
            if i.bot_message and not i.answered:
                return i
        return None

    def attach_user_response(
        self,
        user_text: str,
        *,
        extracted: Optional[dict[str, Any]] = None,
        confidence: float = 0.0,
    ) -> Optional[Interaction]:
        """Encontra última interaction não respondida e anexa
        resposta do user. Retorna a interaction modificada (ou None
        se nada pendente — nesse caso cria interaction "user_initiated"
        sem bot_message)."""
        pending = self.last_unanswered()
        if pending:
            pending.attach_user_response(
                user_text, extracted=extracted, confidence=confidence,
            )
            # Aplica extracted ao lead_data
            if extracted:
                self.lead_data.merge(extracted)
            # Limpa pending question do flow_state
            self.flow_state.clear_pending()
            return pending
        # User mandou msg sem pergunta pendente (ex: 1ª msg, ou
        # mudança de assunto). Cria interaction só com lead_message.
        new = Interaction(
            lead_message=user_text,
            extracted_data=extracted or {},
            extraction_confidence=confidence,
            answered=True,
        )
        self.add_interaction(new)
        if extracted:
            self.lead_data.merge(extracted)
        return new

    def record_bot_question(
        self,
        bot_text: str,
        intent: QuestionIntent,
        *,
        agent: Optional[str] = None,
    ) -> Interaction:
        """Registra que Sofia fez uma pergunta. Cria nova interaction
        com bot side preenchido + atualiza flow_state.pending_question.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        new = Interaction(
            bot_message=bot_text,
            bot_intent=intent,
            bot_agent=agent,
        )
        self.add_interaction(new)
        self.flow_state.set_pending(
            bot_text, intent, agent=agent, at_iso=now_iso,
        )
        return new

    # ──────────────────────────────────────────────────────────────
    # Context pro agent prompt
    # ──────────────────────────────────────────────────────────────

    def get_context_for_agent(self) -> dict[str, Any]:
        """Snapshot estruturado pra injetar no system prompt do agent.

        Returns:
            {
                # Identificação rápida
                "primeiro_nome": "Douglas",
                "tem_nome": True,
                "stage": "qualificacao",
                # Dados confirmados (já capturados)
                "dados_confirmados": ["primeiro_nome", "count_idosos"],
                # Has flags (boolean por campo)
                "has_count_idosos": True,
                "count_idosos": 2,
                "has_idades_idosos": True,
                "idades_idosos": [90, 92],
                ...
                # Should-ask flags (campo esperado pelo stage,
                # ainda não preenchido)
                "should_ask_dores": True,
                "should_ask_intent_b2c_b2b": True,
                # Pending question (último Q sem A)
                "pending_question": "...",
                "pending_question_intent": "count_idosos",
                # Última interaction pareada (resumo)
                "last_interaction": {...},
            }
        """
        ld = self.lead_data
        ctx: dict[str, Any] = {
            "stage": self.flow_state.current_stage.value,
            "warmup_complete": self.flow_state.warmup_complete,
            "qualification_complete": self.flow_state.qualification_complete,
            "dados_confirmados": list(ld.dados_confirmados),
            "tem_nome": ld.has("primeiro_nome"),
        }

        # Espelha valores escalares principais (agent prompt usa direto)
        for f in (
            "primeiro_nome", "nome", "email", "cidade", "estado",
            "relacao", "count_idosos", "idades_idosos",
            "moram_sozinhos", "moram_em_ilpi",
            "dores", "count_medicamentos", "tem_dificuldade_medicacao",
            "organizacao", "cargo_b2b", "ja_cliente_concorrente",
            "concorrente_nome", "quer_demo", "intent_b2c_b2b",
        ):
            v = getattr(ld, f, None)
            ctx[f"has_{f}"] = ld.has(f)
            if ld.has(f):
                ctx[f] = v

        # Should-ask: campos esperados no stage atual e ainda
        # não capturados.
        expected = self.flow_state.expected_fields()
        missing = ld.missing(expected)
        for f in missing:
            ctx[f"should_ask_{f}"] = True

        # Pending question (resolve bug Douglas)
        if self.flow_state.pending_question:
            ctx["pending_question"] = self.flow_state.pending_question
            if self.flow_state.pending_question_intent:
                ctx["pending_question_intent"] = (
                    self.flow_state.pending_question_intent.value
                )
            if self.flow_state.pending_question_agent:
                ctx["pending_question_agent"] = (
                    self.flow_state.pending_question_agent
                )

        # Última interaction (pra dar continuidade narrativa)
        if self.interactions:
            last = self.interactions[-1]
            ctx["last_interaction"] = {
                "bot_message": last.bot_message,
                "lead_message": last.lead_message,
                "bot_intent": last.bot_intent.value if last.bot_intent else None,
                "answered": last.answered,
            }

        return ctx

    # ──────────────────────────────────────────────────────────────
    # Avanço de stage
    # ──────────────────────────────────────────────────────────────

    def auto_advance_stage(self) -> bool:
        """Avança stage se requirements do próximo já foram
        preenchidos. Retorna True se houve mudança.
        """
        order = [
            ConversationStage.WARMUP,
            ConversationStage.IDENTIFICACAO,
            ConversationStage.QUALIFICACAO,
            ConversationStage.APROFUNDAMENTO,
            ConversationStage.APRESENTACAO_VALOR,
            ConversationStage.ENCAMINHAMENTO,
        ]
        current_idx = order.index(self.flow_state.current_stage) \
            if self.flow_state.current_stage in order else 0
        # Só tenta avançar 1 nível por turno (evita pular etapas)
        next_idx = current_idx + 1
        if next_idx >= len(order):
            return False
        next_stage = order[next_idx]
        from src.services.csm.flow_state import STAGE_REQUIREMENTS
        required = STAGE_REQUIREMENTS.get(next_stage, [])
        if all(self.lead_data.has(f) for f in required):
            return self.flow_state.advance_stage(next_stage)
        return False
