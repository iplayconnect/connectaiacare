"""Sub-agent factory — resolve qual agent ativar pra um turno.

Decisão baseada em:
    - is_anonymous (phone resolveu ou não)
    - profile (medico, cuidador_pro, familia, paciente_b2c, ...)
    - intent (do classifier, quando anonymous)

Phase C v1 implementa só caminho anônimo (commercial, support).
Perfis identificados → PassthroughSofiaAgent → pipeline legado.
"""
from __future__ import annotations

from typing import Optional

from src.services.sofia_agents.base import AgentContext, BaseSofiaAgent
from src.services.sofia_agents.commercial import CommercialSofiaAgent
from src.services.sofia_agents.passthrough import PassthroughSofiaAgent
from src.services.sofia_agents.support import SupportSofiaAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Singletons (agents são stateless, podem ser compartilhados)
_commercial = CommercialSofiaAgent()
_support = SupportSofiaAgent()
_passthrough = PassthroughSofiaAgent()


def get_agent_for(
    *,
    is_anonymous: bool,
    profile: Optional[str],
    intent: Optional[str] = None,
) -> BaseSofiaAgent:
    """Resolve sub-agent. Returns sempre — em última instância
    PassthroughSofiaAgent garante que pipeline legado é chamado.
    """
    # Anonymous → roteia por intent
    if is_anonymous:
        if intent in ("interesse_servico_b2c", "interesse_servico_b2b", "agendar_demo"):
            return _commercial
        if intent == "suporte_cliente":
            return _support
        # spam_abuso → silenciar (Phase C v1: passa pra commercial que
        # vai responder de forma genérica; Phase C v2: SilenceAgent dedicado)
        if intent == "spam_abuso":
            return _commercial  # responde 1x e Sofia "não engajada"
        # unclear ou None → commercial (faz pergunta clarificadora)
        return _commercial

    # Identificado → Phase C v1 delega pro pipeline legado
    return _passthrough
