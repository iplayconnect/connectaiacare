"""BaseSofiaAgent — abstrata pra todos os sub-agents.

Cada sub-agent herda e implementa:
    - system_prompt: prompt focado no perfil
    - allowed_tools: lista de tool names permitidos
    - escalation_policy: critérios pra passar pra humano
    - process(): faz turno de conversação

Provê em comum:
    - Memory loading (active_context cross-channel)
    - Tool execution via tool registry
    - Audit log
    - Anti-hallucination guardrail (porting de voice)
    - Cost tracking
    - Streaming/chunking pra WhatsApp
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from src.services.audit_log_writer import write_audit
from src.services.identity_resolver import IdentityMatch
from src.services.tenant_resolver import TenantInfo
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AgentContext:
    """Contexto carregado pelo orchestrator antes de chamar o agent."""
    phone: str
    tenant: TenantInfo
    identity_match: Optional[IdentityMatch]  # None se anônimo
    trace_id: str
    session_id: Optional[str]
    sub_agent: str
    inbound_text: str
    active_context_messages: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # Phase C v2.4: snapshot do CSM (lead_data + flow_state +
    # has_X / should_ask_X / pending_question / dados_confirmados).
    # Veja ConversationState.get_context_for_agent().
    csm_context: dict = field(default_factory=dict)

    @property
    def profile(self) -> str:
        return self.identity_match.profile if self.identity_match else "anonymous"

    @property
    def is_anonymous(self) -> bool:
        return self.identity_match is None

    @property
    def full_name(self) -> Optional[str]:
        return self.identity_match.full_name if self.identity_match else None


@dataclass
class AgentResponse:
    """Resultado do turno do agent."""
    text: Optional[str] = None             # texto pro user (None = silenciado)
    chunks: list[str] = field(default_factory=list)  # se quiser quebrar em N msgs
    tools_called: list[dict] = field(default_factory=list)  # [{name, args, output}]
    handoff_initiated: bool = False
    handoff_reason: Optional[str] = None
    next_action: Optional[str] = None      # 'wait_user'|'wait_human'|'closed'
    metadata: dict = field(default_factory=dict)
    # Phase C v2.4: intent semântico da PERGUNTA que o agent fez (se
    # fez). Permite ao orchestrator marcar pending_question no CSM
    # pra próximo turno saber a qual pergunta o user respondeu.
    # Valores aceitos: nome de QuestionIntent enum (ex: "primeiro_nome",
    # "count_idosos", "dor_principal") ou None / "open_ended".
    next_question_intent: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "text_preview": (self.text or "")[:200] if self.text else None,
            "chunks_count": len(self.chunks),
            "tools_called_names": [t.get("name") for t in self.tools_called],
            "handoff_initiated": self.handoff_initiated,
            "handoff_reason": self.handoff_reason,
            "next_action": self.next_action,
        }


class BaseSofiaAgent(ABC):
    """Base abstrata. Subclasses definem comportamento específico."""

    name: str = "base"  # override em subclasse

    @abstractmethod
    def system_prompt(self, ctx: AgentContext) -> str:
        """System prompt construído com contexto do turno."""

    @abstractmethod
    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        """Lista de tool names que este agent pode chamar."""

    @abstractmethod
    def process(self, ctx: AgentContext) -> AgentResponse:
        """Executa o turno: lê inbound, decide resposta/tool, retorna."""

    # ── Helpers comuns ──

    def audit_turn(
        self,
        ctx: AgentContext,
        response: AgentResponse,
        duration_ms: int,
    ) -> None:
        """Persiste audit log do turno."""
        try:
            write_audit(
                action="sofia_agent_turn",
                actor="sofia",
                actor_role=self.name,
                tenant_id=ctx.tenant.id,
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
                payload={
                    "sub_agent": self.name,
                    "profile": ctx.profile,
                    "is_anonymous": ctx.is_anonymous,
                    "duration_ms": duration_ms,
                    "inbound_chars": len(ctx.inbound_text or ""),
                    **response.to_dict(),
                },
            )
        except Exception as exc:
            logger.warning("agent_audit_failed", error=str(exc), agent=self.name)

    def time_turn(self, fn):
        """Wrapper pra cronometrar process e injetar audit."""
        def wrapped(ctx: AgentContext) -> AgentResponse:
            started = time.perf_counter()
            try:
                response = fn(ctx)
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                logger.exception(
                    "agent_process_failed",
                    agent=self.name,
                    trace_id=ctx.trace_id,
                    duration_ms=duration_ms,
                    error_class=type(exc).__name__,
                )
                # Failsafe: escala pra humano em caso de exceção
                response = AgentResponse(
                    text=(
                        "Tive um probleminha técnico aqui. Vou pedir "
                        "pra um atendente humano te ajudar — me chama "
                        "de novo em instantes ou aguarda contato. 🙏"
                    ),
                    handoff_initiated=True,
                    handoff_reason=f"agent_exception_{type(exc).__name__}",
                    next_action="wait_human",
                )
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.audit_turn(ctx, response, duration_ms)
            return response
        return wrapped
