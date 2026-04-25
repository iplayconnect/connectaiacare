"""Orchestrator — escolhe o sub-agent correto por persona e dispara.

Sofia.2 (atual): roteamento simples persona → 1 agent. Single dispatch.

Sofia.3+ (roadmap): classifier intent-based pode disparar fan-out
paralelo (ex: clinical + caregiver pra emergência) e merge_responses.
A interface aqui (`handle_turn`) já está estável pra essa evolução.
"""
from __future__ import annotations

import logging

from src import persistence
from src.agents.base_agent import BaseAgent
from src.agents.caregiver_agent import CaregiverAgent
from src.agents.clinical_agent import ClinicalAgent
from src.agents.family_agent import FamilyAgent
from src.agents.patient_agent import PatientAgent
from src.agents.platform_agent import PlatformAgent

logger = logging.getLogger(__name__)


# Mapa persona → sub-agent. parceiro reutiliza FamilyAgent (read-only),
# anonymous cai em PlatformAgent (FAQ genérico).
PERSONA_AGENT: dict[str, type[BaseAgent]] = {
    "cuidador_pro": CaregiverAgent,
    "familia": FamilyAgent,
    "parceiro": FamilyAgent,
    "paciente_b2c": PatientAgent,
    "medico": ClinicalAgent,
    "enfermeiro": ClinicalAgent,
    "admin_tenant": PlatformAgent,
    "super_admin": PlatformAgent,
    "anonymous": PlatformAgent,
}


def get_agent_for_persona(persona: str) -> type[BaseAgent]:
    return PERSONA_AGENT.get(persona, PlatformAgent)


def handle_turn(
    *,
    persona_ctx: dict,
    user_message: str,
    channel: str = "web",
) -> dict:
    """Resolve sessão (cria ou continua) e despacha pro agent.

    Retorna {text, session_id, tokens_in, tokens_out, model, agent, tool_calls}.
    """
    persona = persona_ctx.get("persona") or "anonymous"
    tenant_id = persona_ctx.get("tenant_id") or "connectaiacare_demo"

    session = persistence.get_or_create_session(
        tenant_id=tenant_id,
        persona=persona,
        user_id=persona_ctx.get("user_id"),
        phone=persona_ctx.get("phone"),
        caregiver_id=persona_ctx.get("caregiver_id"),
        patient_id=persona_ctx.get("patient_id"),
        channel=channel,
    )

    AgentClass = get_agent_for_persona(persona)
    persistence.audit(
        tenant_id=tenant_id,
        session_id=str(session["id"]),
        user_id=persona_ctx.get("user_id"),
        persona=persona,
        event_type="dispatch",
        decision="allow",
        details={"agent": AgentClass.__name__, "channel": channel},
    )

    result = AgentClass.run(
        session_id=str(session["id"]),
        tenant_id=tenant_id,
        persona_ctx=persona_ctx,
        user_message=user_message,
    )
    return {**result, "session_id": str(session["id"])}


def initial_greeting(persona_ctx: dict) -> str:
    """Saudação inicial usada pela FAB de voz (sem chamar LLM)."""
    persona = persona_ctx.get("persona") or "anonymous"
    AgentClass = get_agent_for_persona(persona)
    return AgentClass.greet(persona_ctx)
