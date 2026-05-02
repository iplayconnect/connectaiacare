"""FlowState — estado de fluxo da conversa (stage + pending_question).

Crítico pra resolver o bug do test Douglas: Sofia perguntou "Quantos
idosos" 3× porque não tinha registro de "fiz X pergunta, esperando Y
intent". FlowState mantém essa âncora.

Stages refletem funil comercial vertical care, não o flow_state da
ConnectaIA (BBMD/trabalhista). Mapeamento:

    BBMD (origem)              →  Care (port)
    ────────────────────────────────────────
    inicial / aberturra         → warmup
    diagnostico                 → identificacao
    qualificacao                → qualificacao
    proposta_apresentada        → apresentacao_valor
    fechamento                  → encaminhamento (lead pronto pra
                                  humano OU agendamento demo)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ConversationStage(str, Enum):
    """Funil de qualificação Sofia comercial (vertical care)."""

    WARMUP = "warmup"
    """Pré-qualificação. Sofia se apresenta, abre espaço, capta
    primeiro nome + intent (b2c/b2b)."""

    IDENTIFICACAO = "identificacao"
    """Sofia identifica relação com idoso (filho_a, neto_a,
    cuidador_pro, self), conta de idosos, idades."""

    QUALIFICACAO = "qualificacao"
    """Dores principais (queda, esquecimento, medicação, isolamento,
    dependência financeira). Mora sozinho? ILPI?"""

    APROFUNDAMENTO = "aprofundamento"
    """Sofia explora dor priorizada. Caso B2B: cargo, # leitos, sistema
    atual. Caso B2C: rotina do idoso, suporte familiar."""

    APRESENTACAO_VALOR = "apresentacao_valor"
    """Sofia apresenta capability whitelist relevante pra dor (sem
    inventar — usa platform_capabilities)."""

    ENCAMINHAMENTO = "encaminhamento"
    """Lead pronto. Sofia oferece: (1) demo agendada, (2) handoff
    humano via Central, (3) trial WhatsApp 24h, conforme intent."""

    ENCERRAMENTO = "encerramento"
    """Conversa fechada. Sofia agradece, mantém canal aberto pra
    follow-up futuro."""


class QuestionIntent(str, Enum):
    """Intent semântico da pergunta que Sofia está fazendo.

    Usado pra parear "última pergunta" com "próxima resposta" e pra
    extractor saber qual campo do CareLeadData preencher.
    """

    # Identificação
    PRIMEIRO_NOME = "primeiro_nome"
    NOME_COMPLETO = "nome_completo"
    EMAIL = "email"
    CIDADE = "cidade"
    RELACAO_IDOSO = "relacao_idoso"

    # Quadro do idoso
    COUNT_IDOSOS = "count_idosos"
    IDADES_IDOSOS = "idades_idosos"
    MORAM_SOZINHOS = "moram_sozinhos"
    MORAM_EM_ILPI = "moram_em_ilpi"

    # Saúde
    DOR_PRINCIPAL = "dor_principal"
    COUNT_MEDICAMENTOS = "count_medicamentos"
    DIFICULDADE_MEDICACAO = "dificuldade_medicacao"

    # B2B
    ORGANIZACAO = "organizacao"
    CARGO_B2B = "cargo_b2b"
    JA_CLIENTE_CONCORRENTE = "ja_cliente_concorrente"

    # Intent
    QUER_DEMO = "quer_demo"
    INTENT_B2C_B2B = "intent_b2c_b2b"

    # Genérico (catch-all)
    OPEN_ENDED = "open_ended"


# Mapa: QuestionIntent → campo(s) do CareLeadData que ele preenche.
# Usado pelo DataExtractor pra saber "intent X expects field Y".
INTENT_TO_FIELD: dict[QuestionIntent, list[str]] = {
    QuestionIntent.PRIMEIRO_NOME: ["primeiro_nome"],
    QuestionIntent.NOME_COMPLETO: ["nome", "primeiro_nome"],
    QuestionIntent.EMAIL: ["email"],
    QuestionIntent.CIDADE: ["cidade", "estado"],
    QuestionIntent.RELACAO_IDOSO: ["relacao"],
    QuestionIntent.COUNT_IDOSOS: ["count_idosos"],
    QuestionIntent.IDADES_IDOSOS: ["idades_idosos"],
    QuestionIntent.MORAM_SOZINHOS: ["moram_sozinhos"],
    QuestionIntent.MORAM_EM_ILPI: ["moram_em_ilpi"],
    QuestionIntent.DOR_PRINCIPAL: ["dores"],
    QuestionIntent.COUNT_MEDICAMENTOS: ["count_medicamentos"],
    QuestionIntent.DIFICULDADE_MEDICACAO: ["tem_dificuldade_medicacao"],
    QuestionIntent.ORGANIZACAO: ["organizacao"],
    QuestionIntent.CARGO_B2B: ["cargo_b2b"],
    QuestionIntent.JA_CLIENTE_CONCORRENTE: ["ja_cliente_concorrente",
                                            "concorrente_nome"],
    QuestionIntent.QUER_DEMO: ["quer_demo"],
    QuestionIntent.INTENT_B2C_B2B: ["intent_b2c_b2b"],
    QuestionIntent.OPEN_ENDED: [],
}


# Campos esperados em cada stage (pra detectar quando avançar).
STAGE_REQUIREMENTS: dict[ConversationStage, list[str]] = {
    ConversationStage.WARMUP: ["primeiro_nome"],
    ConversationStage.IDENTIFICACAO: [
        "primeiro_nome", "relacao", "count_idosos",
    ],
    ConversationStage.QUALIFICACAO: [
        "primeiro_nome", "relacao", "count_idosos",
        "idades_idosos", "dores",
    ],
    ConversationStage.APROFUNDAMENTO: [
        "primeiro_nome", "relacao", "count_idosos",
        "idades_idosos", "dores", "intent_b2c_b2b",
    ],
    ConversationStage.APRESENTACAO_VALOR: [
        "primeiro_nome", "relacao", "count_idosos",
        "idades_idosos", "dores", "intent_b2c_b2b",
    ],
    ConversationStage.ENCAMINHAMENTO: [
        "primeiro_nome", "intent_b2c_b2b",
    ],
    ConversationStage.ENCERRAMENTO: [],
}


@dataclass
class FlowState:
    """Estado do fluxo conversacional. JSONB serializado em
    aia_health_conversation_state.flow_state.
    """

    current_stage: ConversationStage = ConversationStage.WARMUP
    previous_stage: Optional[ConversationStage] = None
    current_agent: Optional[str] = None  # 'commercial', 'support', etc.

    warmup_complete: bool = False
    qualification_complete: bool = False

    # Pergunta pendente (resolve "Sofia esquece o que perguntou")
    pending_question: Optional[str] = None
    pending_question_intent: Optional[QuestionIntent] = None
    pending_question_agent: Optional[str] = None
    pending_question_at: Optional[str] = None  # ISO timestamp

    # ─── Persistência ────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "FlowState":
        if not data:
            return cls()
        stage = data.get("current_stage")
        prev_stage = data.get("previous_stage")
        intent = data.get("pending_question_intent")
        return cls(
            current_stage=ConversationStage(stage) if stage else ConversationStage.WARMUP,
            previous_stage=ConversationStage(prev_stage) if prev_stage else None,
            current_agent=data.get("current_agent"),
            warmup_complete=bool(data.get("warmup_complete", False)),
            qualification_complete=bool(data.get("qualification_complete", False)),
            pending_question=data.get("pending_question"),
            pending_question_intent=QuestionIntent(intent) if intent else None,
            pending_question_agent=data.get("pending_question_agent"),
            pending_question_at=data.get("pending_question_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "current_stage": self.current_stage.value,
            "warmup_complete": self.warmup_complete,
            "qualification_complete": self.qualification_complete,
        }
        if self.previous_stage:
            out["previous_stage"] = self.previous_stage.value
        if self.current_agent:
            out["current_agent"] = self.current_agent
        if self.pending_question:
            out["pending_question"] = self.pending_question
            if self.pending_question_intent:
                out["pending_question_intent"] = self.pending_question_intent.value
            if self.pending_question_agent:
                out["pending_question_agent"] = self.pending_question_agent
            if self.pending_question_at:
                out["pending_question_at"] = self.pending_question_at
        return out

    # ─── Mutação ─────────────────────────────────────────────────

    def set_pending(
        self,
        question: str,
        intent: QuestionIntent,
        *,
        agent: Optional[str] = None,
        at_iso: Optional[str] = None,
    ) -> None:
        self.pending_question = question
        self.pending_question_intent = intent
        self.pending_question_agent = agent
        if at_iso:
            self.pending_question_at = at_iso

    def clear_pending(self) -> None:
        self.pending_question = None
        self.pending_question_intent = None
        self.pending_question_agent = None
        self.pending_question_at = None

    def advance_stage(self, new_stage: ConversationStage) -> bool:
        """Avança pra novo stage se diferente do atual. Retorna True
        se houve mudança."""
        if new_stage == self.current_stage:
            return False
        self.previous_stage = self.current_stage
        self.current_stage = new_stage
        if new_stage == ConversationStage.IDENTIFICACAO:
            self.warmup_complete = True
        if new_stage in (
            ConversationStage.APROFUNDAMENTO,
            ConversationStage.APRESENTACAO_VALOR,
            ConversationStage.ENCAMINHAMENTO,
        ):
            self.qualification_complete = True
        return True

    def expected_fields(self) -> list[str]:
        return STAGE_REQUIREMENTS.get(self.current_stage, [])
