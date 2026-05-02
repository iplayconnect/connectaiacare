"""Smoke tests pra CSM v2 (Phase C v2.2).

Cobre dataclasses e roundtrip JSONB sem tocar Postgres real. Persistência
real fica em testes de integração.
"""
from __future__ import annotations

import pytest

from src.services.csm.care_lead_data import CareLeadData
from src.services.csm.flow_state import (
    INTENT_TO_FIELD,
    STAGE_REQUIREMENTS,
    ConversationStage,
    FlowState,
    QuestionIntent,
)
from src.services.csm.interaction import Interaction


class TestCareLeadData:
    def test_empty_default(self):
        ld = CareLeadData()
        assert ld.primeiro_nome is None
        assert ld.idades_idosos == []
        assert ld.dados_confirmados == []
        assert not ld.has("primeiro_nome")

    def test_merge_scalar_only_if_missing(self):
        ld = CareLeadData(primeiro_nome="Douglas")
        changed = ld.merge({"primeiro_nome": "Outro"})
        # Não sobrescreve valor existente
        assert ld.primeiro_nome == "Douglas"
        assert changed == []

    def test_merge_appends_to_lists_distinct(self):
        ld = CareLeadData()
        ld.merge({"idades_idosos": [90, 92]})
        assert ld.idades_idosos == [90, 92]
        ld.merge({"idades_idosos": [92, 94]})  # 92 dup
        assert ld.idades_idosos == [90, 92, 94]

    def test_merge_tracks_confirmados(self):
        ld = CareLeadData()
        ld.merge({"primeiro_nome": "Douglas", "count_idosos": 2})
        assert "primeiro_nome" in ld.dados_confirmados
        assert "count_idosos" in ld.dados_confirmados

    def test_has_with_empty_list(self):
        ld = CareLeadData(idades_idosos=[])
        assert not ld.has("idades_idosos")
        ld.idades_idosos.append(90)
        assert ld.has("idades_idosos")

    def test_missing(self):
        ld = CareLeadData(primeiro_nome="Douglas")
        miss = ld.missing(["primeiro_nome", "count_idosos", "dores"])
        assert miss == ["count_idosos", "dores"]

    def test_to_from_dict_roundtrip(self):
        ld = CareLeadData(
            primeiro_nome="Douglas",
            count_idosos=2,
            idades_idosos=[90, 92],
            dores=["queda", "esquecimento"],
            dados_confirmados=["primeiro_nome", "count_idosos"],
        )
        d = ld.to_dict()
        ld2 = CareLeadData.from_dict(d)
        assert ld2.primeiro_nome == "Douglas"
        assert ld2.count_idosos == 2
        assert ld2.idades_idosos == [90, 92]
        assert ld2.dores == ["queda", "esquecimento"]

    def test_from_dict_tolerates_extra_keys(self):
        ld = CareLeadData.from_dict({
            "primeiro_nome": "X",
            "campo_inexistente": "ignored",
        })
        assert ld.primeiro_nome == "X"


class TestFlowState:
    def test_default_warmup(self):
        fs = FlowState()
        assert fs.current_stage == ConversationStage.WARMUP
        assert not fs.warmup_complete

    def test_set_clear_pending(self):
        fs = FlowState()
        fs.set_pending(
            "Quantos idosos?",
            QuestionIntent.COUNT_IDOSOS,
            agent="commercial",
        )
        assert fs.pending_question == "Quantos idosos?"
        assert fs.pending_question_intent == QuestionIntent.COUNT_IDOSOS
        fs.clear_pending()
        assert fs.pending_question is None
        assert fs.pending_question_intent is None

    def test_advance_stage_marks_flags(self):
        fs = FlowState()
        assert fs.advance_stage(ConversationStage.IDENTIFICACAO) is True
        assert fs.warmup_complete
        assert fs.previous_stage == ConversationStage.WARMUP

        # Same stage = no-op
        assert fs.advance_stage(ConversationStage.IDENTIFICACAO) is False

        fs.advance_stage(ConversationStage.QUALIFICACAO)
        fs.advance_stage(ConversationStage.APROFUNDAMENTO)
        assert fs.qualification_complete

    def test_to_from_dict_roundtrip(self):
        fs = FlowState()
        fs.advance_stage(ConversationStage.QUALIFICACAO)
        fs.set_pending("X?", QuestionIntent.DOR_PRINCIPAL, agent="commercial")
        d = fs.to_dict()
        fs2 = FlowState.from_dict(d)
        assert fs2.current_stage == ConversationStage.QUALIFICACAO
        assert fs2.pending_question == "X?"
        assert fs2.pending_question_intent == QuestionIntent.DOR_PRINCIPAL

    def test_intent_to_field_covers_all_intents(self):
        for intent in QuestionIntent:
            assert intent in INTENT_TO_FIELD

    def test_stage_requirements_covers_all_stages(self):
        for stage in ConversationStage:
            assert stage in STAGE_REQUIREMENTS


class TestInteraction:
    def test_attach_user_response(self):
        it = Interaction(
            bot_message="Quantos idosos?",
            bot_intent=QuestionIntent.COUNT_IDOSOS,
        )
        assert not it.answered
        it.attach_user_response(
            "São dois", extracted={"count_idosos": 2}, confidence=0.9,
        )
        assert it.answered
        assert it.lead_message == "São dois"
        assert it.extracted_data == {"count_idosos": 2}
        assert it.extraction_confidence == 0.9

    def test_to_from_dict_roundtrip(self):
        it = Interaction(
            bot_message="Q?",
            bot_intent=QuestionIntent.PRIMEIRO_NOME,
            bot_agent="commercial",
            lead_message="Douglas",
            extracted_data={"primeiro_nome": "Douglas"},
            extraction_confidence=0.95,
            answered=True,
        )
        d = it.to_dict()
        it2 = Interaction.from_dict(d)
        assert it2.bot_message == "Q?"
        assert it2.bot_intent == QuestionIntent.PRIMEIRO_NOME
        assert it2.lead_message == "Douglas"
        assert it2.extracted_data == {"primeiro_nome": "Douglas"}
        assert it2.answered is True


class TestConversationStateInMemory:
    """Testes em memória — sem tocar Postgres. Persistência real
    em testes de integração."""

    def test_record_bot_question_sets_pending(self):
        from src.services.csm.conversation_state import ConversationState
        st = ConversationState(tenant_id="t1", client_id="5511")
        it = st.record_bot_question(
            "Quantos idosos?",
            QuestionIntent.COUNT_IDOSOS,
            agent="commercial",
        )
        assert it.bot_message == "Quantos idosos?"
        assert st.flow_state.pending_question == "Quantos idosos?"
        assert st.last_unanswered() is it

    def test_attach_user_response_pairs_with_pending(self):
        from src.services.csm.conversation_state import ConversationState
        st = ConversationState(tenant_id="t1", client_id="5511")
        st.record_bot_question(
            "Quantos idosos?",
            QuestionIntent.COUNT_IDOSOS,
        )
        it = st.attach_user_response(
            "Dois", extracted={"count_idosos": 2}, confidence=0.9,
        )
        assert it.answered
        assert st.flow_state.pending_question is None
        assert st.lead_data.count_idosos == 2

    def test_user_initiated_creates_unpaired(self):
        from src.services.csm.conversation_state import ConversationState
        st = ConversationState(tenant_id="t1", client_id="5511")
        it = st.attach_user_response(
            "Oi, sou Douglas",
            extracted={"primeiro_nome": "Douglas"},
        )
        assert it.lead_message == "Oi, sou Douglas"
        assert it.bot_message is None
        assert st.lead_data.primeiro_nome == "Douglas"

    def test_get_context_for_agent_smoke(self):
        from src.services.csm.conversation_state import ConversationState
        st = ConversationState(tenant_id="t1", client_id="5511")
        st.lead_data.merge({
            "primeiro_nome": "Douglas",
            "count_idosos": 2,
            "idades_idosos": [90, 92],
        })
        ctx = st.get_context_for_agent()
        assert ctx["primeiro_nome"] == "Douglas"
        assert ctx["has_primeiro_nome"] is True
        assert ctx["has_count_idosos"] is True
        assert ctx["count_idosos"] == 2
        assert ctx["idades_idosos"] == [90, 92]
        assert ctx["stage"] == "warmup"

    def test_auto_advance_stage(self):
        from src.services.csm.conversation_state import ConversationState
        st = ConversationState(tenant_id="t1", client_id="5511")
        # WARMUP requires primeiro_nome — não tem, não avança
        assert st.auto_advance_stage() is False
        # Coleta primeiro_nome — IDENTIFICACAO requer só
        # primeiro_nome no warmup→ident porque o stage seguinte
        # exige primeiro_nome+relacao+count_idosos pra IDENT.
        # Ou seja, sem relacao ainda não avança pra IDENT? Olhando
        # STAGE_REQUIREMENTS, IDENT requer ["primeiro_nome",
        # "relacao", "count_idosos"]. Vamos preencher tudo.
        st.lead_data.merge({
            "primeiro_nome": "Douglas",
            "relacao": "filho_a",
            "count_idosos": 2,
        })
        assert st.auto_advance_stage() is True
        assert st.flow_state.current_stage == ConversationStage.IDENTIFICACAO
        assert st.flow_state.warmup_complete

    def test_interactions_window_30(self):
        from src.services.csm.conversation_state import (
            INTERACTIONS_WINDOW,
            ConversationState,
        )
        st = ConversationState(tenant_id="t1", client_id="5511")
        for i in range(INTERACTIONS_WINDOW + 5):
            st.add_interaction(Interaction(bot_message=f"Q{i}"))
        assert len(st.interactions) == INTERACTIONS_WINDOW
        # Últimas mantidas
        assert st.interactions[-1].bot_message == f"Q{INTERACTIONS_WINDOW + 4}"
