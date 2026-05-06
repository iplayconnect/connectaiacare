"""Sub-agent factory — resolve qual agent ativar pra um turno.

Decisão baseada em:
    - is_anonymous (phone resolveu ou não)
    - profile (medico, cuidador_pro, familia, paciente_b2c, ...)
    - intent (do classifier, quando anonymous)

Phase C v1: caminho anônimo (commercial, support) implementado;
            perfis identificados → PassthroughSofiaAgent.

Phase C v2 PR 3: cuidador/cuidador_pro → CareSofiaAgent atrás de
                 feature flag CARE_AGENT_ENABLED (default off pra
                 rollout gradual). Outros perfis identificados (medico,
                 enfermeiro, familia, paciente_b2c) continuam no
                 passthrough até PRs subsequentes.
"""
from __future__ import annotations

import os
from typing import Optional

from src.services.sofia_agents.base import AgentContext, BaseSofiaAgent
from src.services.sofia_agents.care import CareSofiaAgent
from src.services.sofia_agents.commercial import CommercialSofiaAgent
from src.services.sofia_agents.passthrough import PassthroughSofiaAgent
from src.services.sofia_agents.support import SupportSofiaAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Singletons (agents são stateless, podem ser compartilhados)
_commercial = CommercialSofiaAgent()
_support = SupportSofiaAgent()
_passthrough = PassthroughSofiaAgent()
_care = CareSofiaAgent()


def _care_agent_enabled() -> bool:
    """Feature flag pra rollout gradual.

    Default OFF — Phase C v2 PR 3 deploya código mas cuidadores
    continuam no passthrough até flag ser ligada por tenant ou global.

    Pra ativar: setar CARE_AGENT_ENABLED=true no .env do
    sofia-inbound-worker. Restart workers absorve a mudança.

    Phase C v2.x (futuro): permitir override por tenant via
    aia_health_tenant_config.feature_flags JSONB.
    """
    return os.getenv("CARE_AGENT_ENABLED", "false").lower() in ("true", "1", "yes")


# Profiles que CareSofiaAgent atende (quando flag ativa)
_CARE_PROFILES = frozenset({"cuidador", "cuidador_pro"})


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

    # ─── Identificado ────────────────────────────────────────────
    # Phase C v2 PR 3: cuidador/cuidador_pro → CareSofiaAgent (se flag)
    if _care_agent_enabled() and profile and profile.lower() in _CARE_PROFILES:
        logger.info(
            "factory_routed_to_care_agent",
            profile=profile,
        )
        return _care

    # Outros perfis identificados (medico, enfermeiro, familia,
    # paciente_b2c) ou cuidador com flag desligada → passthrough legado
    return _passthrough
