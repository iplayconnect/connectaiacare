"""Tests pra CapabilitiesService (Phase C v2.5)."""
from __future__ import annotations

import pytest

from src.services.csm.capabilities import (
    Capability,
    CapabilitiesService,
)


SEED_ROWS = [
    {
        "code": "whatsapp_atendimento_24h",
        "label_user": "atendimento humano 24h pelo WhatsApp",
        "description_full": "Cliente recebe resposta humana via WhatsApp 24/7.",
        "category": "voz_atendimento",
        "public_facing": True,
        "in_production": True,
        "requires_consent": False,
        "target_personas": ["anonymous", "familia", "cuidador_pro"],
        "notes": None,
    },
    {
        "code": "voice_call_sofia",
        "label_user": "ligação telefônica com a Sofia",
        "description_full": "Sofia faz e recebe ligações via SIP+Grok Realtime.",
        "category": "voz_atendimento",
        "public_facing": True,
        "in_production": True,
        "requires_consent": True,
        "target_personas": ["anonymous", "familia"],
        "notes": None,
    },
    {
        "code": "validacao_medicacao_beers_rename",
        "label_user": "validação de medicações Beers/RENAME",
        "description_full": "Motor clínico valida prescrições.",
        "category": "medicacao",
        "public_facing": True,
        "in_production": True,
        "requires_consent": False,
        "target_personas": ["medico", "enfermeiro", "admin_tenant"],
        "notes": None,
    },
    {
        "code": "feature_oculta_b2b_only",
        "label_user": "feature B2B interna",
        "description_full": "Não exibir pra anônimos.",
        "category": "b2b_admin",
        "public_facing": False,  # private
        "in_production": True,
        "requires_consent": False,
        "target_personas": ["admin_tenant"],
        "notes": None,
    },
]


@pytest.fixture
def svc(mock_db):
    """CapabilitiesService com mock_db pré-populado."""
    mock_db.fetch_all_response = SEED_ROWS
    return CapabilitiesService()


class TestCapabilityFromRow:
    def test_basic(self):
        cap = Capability.from_row(SEED_ROWS[0])
        assert cap.code == "whatsapp_atendimento_24h"
        assert cap.public_facing is True
        assert "anonymous" in cap.target_personas


class TestListing:
    def test_list_all_filters_public(self, svc):
        caps = svc.list_all(public_only=True)
        codes = [c.code for c in caps]
        assert "whatsapp_atendimento_24h" in codes
        assert "feature_oculta_b2b_only" not in codes  # filtered out

    def test_list_all_with_private(self, svc):
        caps = svc.list_all(public_only=False)
        codes = [c.code for c in caps]
        assert "feature_oculta_b2b_only" in codes

    def test_list_for_persona_anonymous(self, svc):
        caps = svc.list_for_persona("anonymous")
        codes = [c.code for c in caps]
        assert "whatsapp_atendimento_24h" in codes
        assert "voice_call_sofia" in codes
        # Beers tem target_personas=[medico,enfermeiro,admin_tenant] — não pra anonymous
        assert "validacao_medicacao_beers_rename" not in codes

    def test_list_for_persona_medico(self, svc):
        caps = svc.list_for_persona("medico")
        codes = [c.code for c in caps]
        assert "validacao_medicacao_beers_rename" in codes
        # WhatsApp tem [anonymous, familia, cuidador_pro] — não inclui medico
        assert "whatsapp_atendimento_24h" not in codes

    def test_list_by_category(self, svc):
        caps = svc.list_by_category("voz_atendimento")
        codes = [c.code for c in caps]
        assert "whatsapp_atendimento_24h" in codes
        assert "voice_call_sofia" in codes
        assert "validacao_medicacao_beers_rename" not in codes


class TestPromptFormat:
    def test_format_includes_anti_invencao_rule(self, svc):
        block = svc.format_for_prompt(persona="anonymous")
        assert "ANTI-INVENÇÃO" in block
        assert "NUNCA invente" in block
        assert "atendimento humano 24h" in block

    def test_format_inclui_consent_flag(self, svc):
        block = svc.format_for_prompt(persona="anonymous")
        # voice_call_sofia tem requires_consent=True
        assert "requer consent LGPD" in block

    def test_format_omite_capability_de_outra_persona(self, svc):
        block = svc.format_for_prompt(persona="anonymous")
        # validacao Beers é pra medico/enfermeiro
        assert "Beers" not in block

    def test_format_empty_fallback(self, mock_db):
        mock_db.fetch_all_response = []
        svc_empty = CapabilitiesService()
        block = svc_empty.format_for_prompt(persona="anonymous")
        assert "checar com o time" in block

    def test_format_db_failure_fallback(self, mock_db):
        # Simula erro na query
        def _fail(query, params):
            raise RuntimeError("db down")
        mock_db.fetch_all_fn = _fail
        svc_fail = CapabilitiesService()
        block = svc_fail.format_for_prompt(persona="anonymous")
        # Cache vazio + fallback msg
        assert "checar com o time" in block


class TestCache:
    def test_cache_reuses_until_invalidate(self, svc, mock_db):
        # 1ª chamada: vai ao DB
        svc.list_all()
        n_queries_1 = len(mock_db.queries_matching("FROM aia_health_platform_capabilities"))
        # 2ª chamada: cache
        svc.list_all()
        n_queries_2 = len(mock_db.queries_matching("FROM aia_health_platform_capabilities"))
        assert n_queries_1 == n_queries_2 == 1

        svc.invalidate()
        svc.list_all()
        n_queries_3 = len(mock_db.queries_matching("FROM aia_health_platform_capabilities"))
        assert n_queries_3 == 2
