-- ConnectaIACare — Safety Guardrail Layer.
--
-- Sofia tem inteligência (classifica, analisa padrão, propõe ação)
-- mas não tem autoridade. Toda ação clínica passa por um router que
-- decide o destino baseado em: tipo da ação, severity, tenant_type.
--
-- 5 destinos possíveis:
--   1. INFORMATIVA          → executa direto (com disclaimer auto-injetado)
--   2. REGISTRA HISTÓRICO   → DB + notifica família se severity≥attention
--   3. CONVOCA ATENDENTE    → fila review (atendente Isabel ou cuidador interno)
--   4. EMERGÊNCIA REAL-TIME → bypass + escala ramal + paralelo família
--   5. MODIFICA PRESCRIÇÃO  → BLOQUEADO no piloto (precisa médico)
--
-- Ramais (escalação humana):
--   - B2C individual: ramal próprio do paciente → atendente Isabel (ConnectaIA)
--   - B2B casa geriátrica/clínica: ramal compartilhado → cuidador interno
--
-- Circuit breaker: se >5% das ações em 5 min caem na queue, pausa
-- automática de novas ligações automáticas daquele tenant.

BEGIN;

-- =====================================================
-- 1. aia_health_patients — ramal próprio + canal de escalação
-- =====================================================
ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS ramal_extension TEXT,
    ADD COLUMN IF NOT EXISTS escalation_channel TEXT
        CHECK (escalation_channel IS NULL OR escalation_channel IN (
            'attendant_isabel',  -- atendente humano ConnectaIACare 24h
            'casa_internal',     -- cuidador interno da casa geriátrica
            'clinica_internal',  -- enfermagem/equipe da clínica
            'family_only'        -- só notifica família, sem ramal
        ));

CREATE INDEX IF NOT EXISTS idx_patients_ramal
    ON aia_health_patients(ramal_extension)
    WHERE ramal_extension IS NOT NULL;


-- =====================================================
-- 2. aia_health_tenant_config — tenant_type + ramal padrão
-- =====================================================
ALTER TABLE aia_health_tenant_config
    ADD COLUMN IF NOT EXISTS tenant_type TEXT
        CHECK (tenant_type IS NULL OR tenant_type IN (
            'b2c_individual',     -- idoso direto, sem clínica
            'b2b_casa_geriatrica',-- casa geriátrica com cuidador
            'b2b_clinica',        -- clínica com equipe médica
            'b2b_hospital'        -- hospital (futuro)
        )),
    ADD COLUMN IF NOT EXISTS default_attendant_ramal TEXT,
    ADD COLUMN IF NOT EXISTS default_internal_ramal TEXT,
    ADD COLUMN IF NOT EXISTS guardrail_settings JSONB NOT NULL DEFAULT '{
        "confidence_threshold": 0.85,
        "queue_review_timeout_seconds": 300,
        "auto_execute_on_timeout_critical": true,
        "circuit_breaker_max_queue_pct": 5,
        "circuit_breaker_window_seconds": 300,
        "circuit_breaker_pause_minutes": 30
    }'::JSONB;

-- Marca tenant default como b2c_individual (piloto)
INSERT INTO aia_health_tenant_config (tenant_id, tenant_type, central_name)
VALUES ('connectaiacare_demo', 'b2c_individual', 'ConnectaIA Care')
ON CONFLICT (tenant_id) DO UPDATE
    SET tenant_type = COALESCE(aia_health_tenant_config.tenant_type, 'b2c_individual');


-- =====================================================
-- 3. aia_health_action_review_queue — fila de decisões pendentes
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_action_review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE CASCADE,

    -- Origem (rastreabilidade)
    sofia_session_id UUID REFERENCES aia_health_sofia_sessions(id) ON DELETE SET NULL,
    triggered_by_tool TEXT,        -- ex 'create_care_event', 'check_medication_safety'
    triggered_by_persona TEXT,

    -- Detalhes da ação proposta
    action_type TEXT NOT NULL CHECK (action_type IN (
        'register_history',        -- só registra (severity attention+)
        'invoke_attendant',        -- escala ramal humano
        'emergency_realtime',      -- bypass — Sofia já agiu
        'modify_prescription'      -- bloqueado no piloto
    )),
    severity TEXT NOT NULL CHECK (severity IN (
        'info', 'attention', 'urgent', 'critical'
    )),
    summary TEXT NOT NULL,         -- 1-2 frases descrevendo a ação
    details JSONB NOT NULL DEFAULT '{}'::JSONB,  -- payload completo
    sofia_confidence NUMERIC(3,2),  -- 0.0-1.0 (quando aplicável)

    -- Roteamento
    target_channel TEXT NOT NULL CHECK (target_channel IN (
        'attendant_isabel', 'casa_internal', 'clinica_internal',
        'family_only', 'auto'
    )),
    target_ramal TEXT,             -- ramal a discar quando aprovar
    notified_user_ids UUID[] DEFAULT '{}',  -- familiares notificados

    -- Estado
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',           -- aguardando decisão
        'approved',          -- humano aprovou; ação executada
        'rejected',          -- humano rejeitou
        'auto_executed',     -- timeout + critical → executou por default
        'expired',           -- timeout sem critical → não executou
        'cancelled'          -- admin cancelou
    )),
    auto_execute_after TIMESTAMPTZ,  -- timestamp pra timeout
    decision_at TIMESTAMPTZ,
    decided_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    decision_notes TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_queue_pending
    ON aia_health_action_review_queue(tenant_id, created_at DESC)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_review_queue_patient
    ON aia_health_action_review_queue(patient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_queue_auto_exec
    ON aia_health_action_review_queue(auto_execute_after)
    WHERE status = 'pending' AND auto_execute_after IS NOT NULL;


-- =====================================================
-- 4. aia_health_safety_circuit_breaker — estado por tenant
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_safety_circuit_breaker (
    tenant_id TEXT PRIMARY KEY,

    -- Estado atual
    state TEXT NOT NULL DEFAULT 'closed' CHECK (state IN (
        'closed',     -- normal — Sofia opera
        'open',       -- pausada — todas ações automáticas suspensas
        'half_open'   -- testando recuperação (após pause expirar)
    )),
    opened_at TIMESTAMPTZ,
    open_until TIMESTAMPTZ,
    open_reason TEXT,

    -- Métricas rolling window (últimos N segundos)
    actions_total INTEGER NOT NULL DEFAULT 0,
    actions_queued INTEGER NOT NULL DEFAULT 0,
    actions_rejected INTEGER NOT NULL DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =====================================================
-- 5. Triggers updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION _touch_safety_review_queue()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_review_queue ON aia_health_action_review_queue;
CREATE TRIGGER trg_touch_review_queue
    BEFORE UPDATE ON aia_health_action_review_queue
    FOR EACH ROW EXECUTE FUNCTION _touch_safety_review_queue();

DROP TRIGGER IF EXISTS trg_touch_circuit_breaker ON aia_health_safety_circuit_breaker;
CREATE TRIGGER trg_touch_circuit_breaker
    BEFORE UPDATE ON aia_health_safety_circuit_breaker
    FOR EACH ROW EXECUTE FUNCTION _touch_safety_review_queue();


-- =====================================================
-- 6. Audit chain: novos action types
-- =====================================================
-- Apenas documenta, audit_service aceita qualquer string em 'action':
--   'guardrail.action.queued'        — ação caiu na queue
--   'guardrail.action.approved'      — humano aprovou
--   'guardrail.action.rejected'      — humano rejeitou
--   'guardrail.action.auto_executed' — timeout em critical
--   'guardrail.circuit.opened'       — pausa automática disparou
--   'guardrail.circuit.closed'       — recuperou


COMMIT;
