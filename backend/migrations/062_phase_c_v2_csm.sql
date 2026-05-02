-- ====================================================================
-- 062_phase_c_v2_csm.sql
--
-- Phase C v2 — ConversationStateManager
--
-- Adapta o CSM da ConnectaIA pra vertical care. Resolve sintoma
-- principal: Sofia repete perguntas em conversas longas. Causa:
-- contexto era texto bruto (active_context), sem registro
-- estruturado de "pergunta X = resposta Y, dado extraído Z".
--
-- 2 estruturas novas:
--   • aia_health_conversation_state (CSM por client_id/phone)
--   • aia_health_platform_capabilities (whitelist anti-invenção)
--
-- Idempotente.
-- ====================================================================

-- 1. CONVERSATION STATE (CSM core) ────────────────────────────────────
-- 1 row por (tenant_id, client_id) onde client_id é phone E.164
-- normalizado. Carrega lead_data cumulativo + flow_state +
-- interactions[] (últimas 30 pareadas).

CREATE TABLE IF NOT EXISTS aia_health_conversation_state (
    tenant_id TEXT NOT NULL,
    client_id TEXT NOT NULL,        -- phone E.164 normalizado
    user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE SET NULL,
    session_id UUID REFERENCES aia_health_sofia_sessions(id) ON DELETE SET NULL,

    -- LeadData cumulativo (vertical care). JSONB pra flexibilidade.
    -- Schema esperado em CARE_LEAD_DATA_SCHEMA (ver
    -- backend/src/services/csm/care_lead_data.py):
    --  {nome, primeiro_nome, telefone, email, cidade, relacao,
    --   count_idosos, idades_idosos[], moram_sozinhos,
    --   moram_em_ilpi, dores[], count_medicamentos,
    --   tem_dificuldade_medicacao, organizacao, cargo_b2b,
    --   ja_cliente_concorrente, quer_demo, intent_b2c_b2b,
    --   dados_confirmados[], dados_pendentes[]}
    lead_data JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- FlowState: stage atual + pergunta pendente.
    --  {current_stage, previous_stage, current_agent,
    --   warmup_complete, qualification_complete,
    --   pending_question, pending_question_intent,
    --   pending_question_agent, pending_question_at}
    flow_state JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Interactions: histórico pareado (últimas 30).
    --  [{id, ts, bot_message, bot_intent, lead_message,
    --    extracted_data, extraction_confidence, answered}]
    interactions JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Origem
    contact_origin TEXT DEFAULT 'inbound',  -- 'inbound'|'outbound'

    -- Metadados livres
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Tracking
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (tenant_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_csm_tenant_activity
    ON aia_health_conversation_state(tenant_id, last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_csm_session
    ON aia_health_conversation_state(session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_csm_user
    ON aia_health_conversation_state(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_csm_stage
    ON aia_health_conversation_state(tenant_id, (flow_state->>'current_stage'))
    WHERE flow_state->>'current_stage' IS NOT NULL;

COMMENT ON TABLE aia_health_conversation_state IS
'ConversationStateManager — single source of truth da conversa. Por
(tenant, client). Persiste lead_data cumulativo + flow_state com
pending_question + histórico pareado. Phase C v2 (port da ConnectaIA).';

COMMENT ON COLUMN aia_health_conversation_state.lead_data IS
'CareLeadData JSONB. Cada campo Optional, dados_confirmados[] rastreia
o que JÁ foi coletado pra agent não repetir.';

COMMENT ON COLUMN aia_health_conversation_state.flow_state IS
'FlowState JSONB. Crítico: pending_question + pending_question_intent
permite associar resposta do user à pergunta que Sofia fez.';


-- Trigger touch updated_at
CREATE OR REPLACE FUNCTION aia_health_csm_touch_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.last_activity_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_csm_touch ON aia_health_conversation_state;
CREATE TRIGGER trg_csm_touch
    BEFORE UPDATE ON aia_health_conversation_state
    FOR EACH ROW EXECUTE FUNCTION aia_health_csm_touch_updated_at();


-- 2. PLATFORM CAPABILITIES (whitelist anti-invenção) ──────────────────
-- Sofia comercial inventou "monitoramento batimento cardíaco" no log
-- Douglas. Solução: lista whitelist de capabilities reais. System
-- prompt do agent recebe a lista + regra "só fale dessas".

CREATE TABLE IF NOT EXISTS aia_health_platform_capabilities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT NOT NULL UNIQUE,
        -- ex: 'monitor_quedas', 'med_alerts', 'voice_calls_proativas'
    label_user TEXT NOT NULL,
        -- forma como Sofia menciona pro user. Ex:
        -- "monitoramento de quedas em tempo real"
    description_full TEXT NOT NULL,
        -- detalhada interna pro prompt do agent
    category TEXT NOT NULL,
        -- 'monitoramento' | 'medicacao' | 'voz_atendimento' |
        -- 'integracao_saude' | 'familia' | 'b2b_admin'
    public_facing BOOLEAN NOT NULL DEFAULT TRUE,
        -- pode mencionar em comunicação comercial?
    in_production BOOLEAN NOT NULL DEFAULT TRUE,
        -- feature já em produção? Roadmap futuro = false
    requires_consent BOOLEAN NOT NULL DEFAULT FALSE,
        -- precisa consent LGPD explícito? (ex: monitoramento voz)
    target_personas TEXT[] NOT NULL DEFAULT ARRAY['anonymous','familia','cuidador_pro'],
    audit_id_source UUID,  -- quem aprovou esta capability
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (category IN (
        'monitoramento', 'medicacao', 'voz_atendimento',
        'integracao_saude', 'familia', 'b2b_admin', 'outros'
    ))
);

CREATE INDEX IF NOT EXISTS idx_capabilities_public
    ON aia_health_platform_capabilities(public_facing, in_production);

COMMENT ON TABLE aia_health_platform_capabilities IS
'Whitelist de capabilities REAIS da plataforma. Injetada no system
prompt do commercial agent pra Sofia não inventar features
(bug Douglas log 2026-05-02 22:49: inventou monitoramento batimentos).';


-- 3. SEED capabilities iniciais ───────────────────────────────────────
-- Conservador: só features que CLARAMENTE existem em produção.
-- Mais capabilities adicionadas via UI admin ou migration futura.

INSERT INTO aia_health_platform_capabilities (
    code, label_user, description_full, category,
    public_facing, in_production, target_personas
) VALUES
(
    'whatsapp_atendimento_24h',
    'atendimento humano 24h pelo WhatsApp',
    'Cliente recebe resposta humana via WhatsApp a qualquer hora do dia/noite via Central 24h. SLA P1 <5min, P2 <30min, P3 <2h.',
    'voz_atendimento', TRUE, TRUE,
    ARRAY['anonymous','familia','cuidador_pro','paciente_b2c']
),
(
    'voice_call_sofia',
    'ligação telefônica com a Sofia (IA conversacional)',
    'Sofia faz e recebe ligações telefônicas reais via SIP+Grok Realtime. Pode acionar tools clínicas, registrar care events, escalar pra humano.',
    'voz_atendimento', TRUE, TRUE,
    ARRAY['anonymous','familia','cuidador_pro','paciente_b2c']
),
(
    'classificacao_relatos_clinicos',
    'classificação automática de relatos clínicos',
    'Cuidador manda áudio/texto sobre o idoso. Sofia transcreve, classifica em 8 event types (intercorrencia, sintoma_novo, medicacao, etc.) com cascata Tier 1+2+3.',
    'monitoramento', TRUE, TRUE,
    ARRAY['cuidador_pro','familia']
),
(
    'alertas_familia',
    'alertas pra família quando algo importante acontece',
    'Quando Sofia classifica evento como urgent/critical, dispara WhatsApp pra família responsável + escala pro time de atendimento.',
    'familia', TRUE, TRUE,
    ARRAY['anonymous','familia']
),
(
    'validacao_medicacao_beers_rename',
    'validação de medicações contra Beers Criteria e RENAME 2024',
    'Motor clínico valida prescrições contra Beers (medicações inadequadas pra idoso), interações farmacológicas, contraindicações, ajustes renal/hepático.',
    'medicacao', TRUE, TRUE,
    ARRAY['medico','enfermeiro','admin_tenant']
),
(
    'integracao_tecnosenior',
    'integração com Tecnosenior CareNote',
    'Plataforma integra com prontuário eletrônico Tecnosenior pra ILPIs que já usam.',
    'integracao_saude', TRUE, TRUE,
    ARRAY['admin_tenant','gestor_ilpi']
)
ON CONFLICT (code) DO NOTHING;


-- 4. Trigger touch updated_at em capabilities
DROP TRIGGER IF EXISTS trg_capabilities_touch
    ON aia_health_platform_capabilities;
CREATE TRIGGER trg_capabilities_touch
    BEFORE UPDATE ON aia_health_platform_capabilities
    FOR EACH ROW EXECUTE FUNCTION aia_health_csm_touch_updated_at();
