-- ConnectaIACare — Migration 005: Eventos de Cuidado + Tenant Config
-- Data: 2026-04-20
--
-- Transforma o modelo de "sessão conversacional única por cuidador" em
-- "evento de cuidado por paciente" com ciclo de vida clínico completo,
-- timings configuráveis por tenant, escalação hierárquica e pattern detection
-- via embeddings pgvector (ADR-018).
--
-- Aposenta: aia_health_conversation_sessions (renomeada para legacy_*)
-- Adiciona: aia_health_care_events (novo modelo central)
--           aia_health_tenant_config (timings + políticas por tenant)
--           aia_health_escalation_log (trilha de escalações disparadas)
--           aia_health_care_event_checkins (pings proativos enviados)
-- Altera:   aia_health_reports (link com care_event_id opcional)
--           aia_health_patients.responsible (esquema rico: central/enfermeira/família[])
--           aia_health_reports (embedding pgvector pra pattern detection semântica)

BEGIN;

-- pgvector já está disponível (ADR-004)
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 1. TENANT CONFIG — protocolos e timings por SPA/cliente
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_tenant_config (
    tenant_id TEXT PRIMARY KEY,

    -- Contatos "da casa" (SPA/ILPI) — aplicam a TODOS os pacientes do tenant
    central_phone TEXT,                  -- Número 24h centralizado
    central_name TEXT DEFAULT 'Central',
    nurse_phone TEXT,                    -- Enfermeira principal (fallback se central não responder)
    nurse_name TEXT,
    doctor_phone TEXT,
    doctor_name TEXT,

    -- Timings do protocolo de evento (minutos)
    -- Pode ser sobrescrito por classificação — ver `timings` jsonb abaixo
    pattern_analysis_after_min INT NOT NULL DEFAULT 5,  -- quando rodar análise de padrão histórico
    check_in_after_min INT NOT NULL DEFAULT 10,         -- quando pingar cuidador
    closure_decision_after_min INT NOT NULL DEFAULT 30, -- quando decidir fechar automaticamente

    -- Escalation thresholds: em quanto tempo sem resposta escala para o próximo nível
    escalation_level1_wait_min INT NOT NULL DEFAULT 5,  -- espera resposta da central/enfermeira
    escalation_level2_wait_min INT NOT NULL DEFAULT 10, -- espera resposta do familiar nível 1
    escalation_level3_wait_min INT NOT NULL DEFAULT 10, -- familiar nível 2

    -- Overrides por classificação clínica (jsonb pra flexibilidade sem ALTER TABLE)
    -- Ex: {"critical":{"pattern_analysis_after_min":2,"check_in_after_min":5},
    --      "urgent":{"check_in_after_min":8}}
    timings JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Política de escalação por classificação
    -- Ex: {"critical":["central","nurse","doctor","family_1","family_2","family_3"],
    --      "urgent":["central","nurse","family_1"],
    --      "attention":["central"],
    --      "routine":[]}
    escalation_policy JSONB NOT NULL DEFAULT '{
        "critical": ["central", "nurse", "doctor", "family_1", "family_2", "family_3"],
        "urgent": ["central", "nurse", "family_1"],
        "attention": ["central"],
        "routine": []
    }'::JSONB,

    -- Feature flags por tenant
    features JSONB NOT NULL DEFAULT '{
        "proactive_checkin": true,
        "pattern_detection": true,
        "sofia_voice_calls": true,
        "medmonitor_integration": false
    }'::JSONB,

    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger pra updated_at
CREATE OR REPLACE FUNCTION aia_health_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenant_config_updated ON aia_health_tenant_config;
CREATE TRIGGER trg_tenant_config_updated
    BEFORE UPDATE ON aia_health_tenant_config
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

-- Seed do tenant de demo
INSERT INTO aia_health_tenant_config (
    tenant_id, central_name, central_phone, nurse_name, nurse_phone
) VALUES (
    'connectaiacare_demo',
    'Central SPA Vida Plena',
    NULL, -- a preencher em produção com número real
    'Enfermeira Plantão',
    NULL
)
ON CONFLICT (tenant_id) DO NOTHING;


-- =====================================================
-- 2. PATIENTS.responsible — expandir para árvore hierárquica
-- =====================================================
-- Schema esperado em `responsible` (jsonb):
-- {
--   "nurse_override": {"name": "...", "phone": "..."}  -- opcional, se paciente tem enfermeira dedicada
--   "family": [
--     {"name": "...", "relationship": "filho(a)|cônjuge|irmão|...", "phone": "...", "level": 1},
--     {"name": "...", "phone": "...", "level": 2},
--     {"name": "...", "phone": "...", "level": 3}
--   ]
-- }
-- Não exige migração de dados existentes — chaves antigas ("name","phone","relationship"
-- no topo) continuam funcionando como family[0] legacy via código adapter.

COMMENT ON COLUMN aia_health_patients.responsible IS
'Árvore de contatos. Schema: {nurse_override?:{name,phone}, family:[{name,relationship,phone,level}]}. Legado: {name,phone,relationship} no topo = family[0].';


-- =====================================================
-- 3. CARE EVENTS — evento clínico com ciclo de vida
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_care_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    human_id SERIAL,  -- ID legível (#0001, #0002) para humanos

    -- Identificação do evento
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    caregiver_phone TEXT NOT NULL,  -- WhatsApp de quem reportou
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,

    -- Classificação inicial e atual (pode evoluir durante o ciclo)
    initial_classification TEXT CHECK (initial_classification IN ('routine','attention','urgent','critical')),
    current_classification TEXT CHECK (current_classification IN ('routine','attention','urgent','critical')),

    -- Tipo clínico do evento (inferido do relato: queda, dispneia, confusão, dor_toracica, etc.)
    event_type TEXT,
    event_tags TEXT[] DEFAULT ARRAY[]::TEXT[],

    -- Estado do protocolo
    -- analyzing → awaiting_ack → pattern_analyzed → escalating → awaiting_status_update → resolved|expired
    status TEXT NOT NULL DEFAULT 'analyzing'
        CHECK (status IN ('analyzing','awaiting_ack','pattern_analyzed','escalating',
                           'awaiting_status_update','resolved','expired')),

    -- Contexto acumulado da conversa (messages, snapshots, etc.)
    context JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Resumo clínico pro dashboard
    summary TEXT,
    reasoning TEXT,

    -- Lifecycle timestamps
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pattern_analyzed_at TIMESTAMPTZ,
    first_escalation_at TIMESTAMPTZ,
    last_check_in_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,

    -- Encerramento
    closed_by TEXT,                      -- 'system_auto' | 'caregiver' | 'nurse' | 'doctor' | 'operator'
    closed_reason TEXT CHECK (closed_reason IN (
        NULL, 'cuidado_iniciado', 'encaminhado_hospital', 'transferido',
        'sem_intercorrencia', 'falso_alarme', 'paciente_estavel',
        'expirou_sem_feedback', 'obito', 'outro'
    )),
    closure_notes TEXT,

    -- Expiração natural (30 min padrão, renovável)
    expires_at TIMESTAMPTZ NOT NULL,

    -- Relação com report inicial (pode ter N reports num mesmo evento em follow-ups)
    initial_report_id UUID REFERENCES aia_health_reports(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_care_events_tenant ON aia_health_care_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_care_events_patient ON aia_health_care_events(patient_id);
CREATE INDEX IF NOT EXISTS idx_care_events_caregiver_phone ON aia_health_care_events(tenant_id, caregiver_phone);
CREATE INDEX IF NOT EXISTS idx_care_events_status ON aia_health_care_events(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_care_events_active ON aia_health_care_events(tenant_id, expires_at)
    WHERE status NOT IN ('resolved', 'expired');
CREATE INDEX IF NOT EXISTS idx_care_events_opened_at ON aia_health_care_events(tenant_id, opened_at DESC);

-- Unique constraint: 1 evento ATIVO por (cuidador, paciente) — previne duplicação
-- em caso de áudios rapidamente reenviados. Múltiplos eventos ativos para mesmo
-- cuidador são permitidos DESDE QUE para pacientes diferentes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_care_events_unique_active
    ON aia_health_care_events(tenant_id, caregiver_phone, patient_id)
    WHERE status NOT IN ('resolved', 'expired');

DROP TRIGGER IF EXISTS trg_care_events_updated ON aia_health_care_events;
CREATE TRIGGER trg_care_events_updated
    BEFORE UPDATE ON aia_health_care_events
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- =====================================================
-- 4. CHECK-INS PROATIVOS — pings agendados pelo orchestrator
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_care_event_checkins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL REFERENCES aia_health_care_events(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,

    -- Tipo do check-in
    kind TEXT NOT NULL CHECK (kind IN (
        'pattern_analysis',     -- t+5min: análise de padrão histórico
        'status_update',        -- t+10min: "como está agora?"
        'closure_check',        -- t+30min: decisão de encerrar
        'post_escalation',      -- após escalação: "conseguiu falar com a enfermeira?"
        'custom'
    )),

    scheduled_for TIMESTAMPTZ NOT NULL,   -- quando o orchestrator vai disparar
    sent_at TIMESTAMPTZ,                  -- quando efetivamente foi enviado
    channel TEXT DEFAULT 'whatsapp' CHECK (channel IN ('whatsapp', 'sms', 'voice')),
    message_sent TEXT,                    -- texto/script enviado

    response_received_at TIMESTAMPTZ,
    response_text TEXT,
    response_classification TEXT,         -- intent da resposta: "improved"|"worsened"|"stable"|"handed_over"|"no_response"

    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled','sent','responded','skipped','failed')),
    error_message TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkins_due ON aia_health_care_event_checkins(scheduled_for)
    WHERE status = 'scheduled';
CREATE INDEX IF NOT EXISTS idx_checkins_event ON aia_health_care_event_checkins(event_id);

DROP TRIGGER IF EXISTS trg_checkins_updated ON aia_health_care_event_checkins;
CREATE TRIGGER trg_checkins_updated
    BEFORE UPDATE ON aia_health_care_event_checkins
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- =====================================================
-- 5. ESCALATION LOG — trilha de notificações hierárquicas
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_escalation_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL REFERENCES aia_health_care_events(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,

    -- Destinatário
    target_role TEXT NOT NULL CHECK (target_role IN (
        'central', 'nurse', 'doctor', 'family_1', 'family_2', 'family_3'
    )),
    target_name TEXT,
    target_phone TEXT NOT NULL,

    channel TEXT NOT NULL CHECK (channel IN ('whatsapp', 'voice', 'sms')),
    message_content TEXT,

    -- Status da notificação
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued',      -- agendada
            'sent',        -- mensagem/ligação disparada
            'delivered',   -- WhatsApp entregue / ligação atendida
            'read',        -- WhatsApp lido / ligação escutou
            'responded',   -- pessoa respondeu
            'no_answer',   -- ligação não atendida / WhatsApp não lido em N min
            'failed'
        )),

    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    responded_at TIMESTAMPTZ,
    response_summary TEXT,

    -- Referência externa (ex: sofia_call_id, evolution_message_id)
    external_ref TEXT,

    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_escalation_event ON aia_health_escalation_log(event_id, created_at);
CREATE INDEX IF NOT EXISTS idx_escalation_status ON aia_health_escalation_log(status, sent_at);

DROP TRIGGER IF EXISTS trg_escalation_updated ON aia_health_escalation_log;
CREATE TRIGGER trg_escalation_updated
    BEFORE UPDATE ON aia_health_escalation_log
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- =====================================================
-- 6. REPORTS — ligação com care_event + embedding pra busca semântica
-- =====================================================
-- care_event_id: NULL permitido durante período de transição/migração
ALTER TABLE aia_health_reports
    ADD COLUMN IF NOT EXISTS care_event_id UUID REFERENCES aia_health_care_events(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_reports_care_event ON aia_health_reports(care_event_id);

-- Embedding do relato (transcrição + análise) pra pattern detection semântica.
-- 768 dimensões = modelo `text-embedding-3-small` (OpenAI) ou equivalente.
-- Usamos OpenAI embeddings por estar disponível; alternativa: sentence-transformers locais.
-- Nullable: relatos antigos antes da mudança ficam sem embedding até backfill.
ALTER TABLE aia_health_reports
    ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Índice HNSW para busca de vizinhos semânticos (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_reports_embedding
    ON aia_health_reports USING hnsw (embedding vector_cosine_ops);


-- =====================================================
-- 7. MIGRAÇÃO DE conversation_sessions PARA LEGACY
-- =====================================================
-- A tabela existia mas estava subutilizada. Renomeamos pra sinalizar deprecation
-- sem perder dados. Pode ser dropada após 1 release estável do novo modelo.
ALTER TABLE IF EXISTS aia_health_conversation_sessions
    RENAME TO aia_health_legacy_conversation_sessions;


COMMIT;
