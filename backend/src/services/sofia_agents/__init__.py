"""Sub-agents profile-aware da Super Sofia (Phase C).

Cada sub-agent é especializado em um perfil/situação:
    - clinical: medico/enfermeiro
    - caregiver: cuidador_pro
    - family: familia
    - patient_b2c: paciente_b2c (idoso solo)
    - admin: super_admin/admin_tenant
    - commercial: lead anônimo com intent comercial
    - support: lead anônimo com intent suporte
    - onboarding_b2c: lead com intent_servico_b2c (entra fluxo
                      assinatura — máquina de estados existente)

Factory `get_agent_for(profile, intent)` resolve qual sub-agent
ativar pra um turno.
"""
from .base import BaseSofiaAgent, AgentContext, AgentResponse
from .factory import get_agent_for

__all__ = ["BaseSofiaAgent", "AgentContext", "AgentResponse", "get_agent_for"]
