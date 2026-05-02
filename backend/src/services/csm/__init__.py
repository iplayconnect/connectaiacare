"""csm — ConversationStateManager v2 (vertical care).

Port da arquitetura da ConnectaIA, adaptado pra Sofia Cuida.

Problema que resolve:
    Phase C v1 lia active_context (texto bruto) mas não tinha registro
    estruturado de "pergunta X = resposta Y, dado extraído Z". Resultado:
    em conversas longas Sofia repetia perguntas (test Douglas 2026-05-01:
    perguntou "Quantos idosos" 3× seguidas).

Solução:
    1 ConversationState por (tenant_id, client_id) com:
        • CareLeadData cumulativo (nome, idades_idosos, dores, etc.)
        • FlowState com pending_question + current_stage
        • Interactions[] (últimas 30 pareadas)

API principal:
    from src.services.csm import (
        ConversationState, CareLeadData, FlowState, Interaction,
        ConversationStage, QuestionIntent,
    )

    state = ConversationState.load(tenant_id="t1", client_id="5511...")
    state.lead_data.merge({"primeiro_nome": "Douglas"})
    state.add_interaction(...)
    state.save()
"""
from __future__ import annotations

from src.services.csm.capabilities import (
    Capability,
    CapabilitiesService,
    get_capabilities_service,
)
from src.services.csm.care_lead_data import CARE_LEAD_DATA_SCHEMA, CareLeadData
from src.services.csm.conversation_state import ConversationState
from src.services.csm.data_extractor import (
    DataExtractor,
    ExtractionResult,
    get_data_extractor,
)
from src.services.csm.flow_state import (
    ConversationStage,
    FlowState,
    QuestionIntent,
)
from src.services.csm.interaction import Interaction
from src.services.csm.user_memory import (
    UserMemorySnapshot,
    UserMemoryWriter,
    get_user_memory_writer,
)

__all__ = [
    "Capability",
    "CapabilitiesService",
    "CareLeadData",
    "CARE_LEAD_DATA_SCHEMA",
    "ConversationStage",
    "ConversationState",
    "DataExtractor",
    "ExtractionResult",
    "FlowState",
    "Interaction",
    "QuestionIntent",
    "UserMemorySnapshot",
    "UserMemoryWriter",
    "get_capabilities_service",
    "get_data_extractor",
    "get_user_memory_writer",
]
