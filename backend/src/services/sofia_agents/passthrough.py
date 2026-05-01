"""PassthroughSofiaAgent — fallback compat layer pra perfis identificados
em Phase C v1.

Phase C v1 (este PR) foca em **caminho do lead anônimo** (commercial,
support). Pra perfis cadastrados (cuidador, família, médico, etc.),
delega de volta pro pipeline.handle_webhook legado — preserva
comportamento clínico atual sem regressão.

Phase C v2 (PR futuro): substituir cada um por subagent dedicado
(ClinicalSofiaAgent, CaregiverSofiaAgent, FamilySofiaAgent, etc).
"""
from __future__ import annotations

from src.services.sofia_agents.base import (
    AgentContext, AgentResponse, BaseSofiaAgent,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PassthroughSofiaAgent(BaseSofiaAgent):
    """Não responde — sinaliza pro orchestrator passar pro pipeline
    legado. Phase C v2 vai substituir."""

    name = "passthrough_legacy"

    def system_prompt(self, ctx: AgentContext) -> str:
        return ""  # não usado

    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        return []

    def process(self, ctx: AgentContext) -> AgentResponse:
        logger.info(
            "sofia_passthrough_to_legacy_pipeline",
            trace_id=ctx.trace_id,
            tenant_id=ctx.tenant.id,
            profile=ctx.profile,
        )
        return AgentResponse(
            text=None,
            next_action="passthrough_legacy",
            metadata={
                "reason": "phase_c_v1_only_handles_anonymous_leads",
                "profile": ctx.profile,
            },
        )
