-- ConnectaIACare — Sofia Care: fundações multi-persona (Sofia.1)
-- Data: 2026-04-25
--
-- Objetivo:
--   • Sofia clone dedicada pra saúde (container connectaiacare-sofia-service
--     virá em Sofia.2), com 5 personas distintas:
--     cuidador_pro, familia, medico/enfermeiro, admin_tenant, paciente_b2c
--   • Sessões + mensagens persistidas no mesmo Postgres
--   • Track de consumo de tokens (sem enforcement de cota nesta fase —
--     pacotes serão definidos após dados reais)
--   • Time window de atendimento configurável por operador (médico, admin)
--   • Audit de tool calls e decisões de gate pra LGPD/CFM
--
-- Não criamos:
--   • aia_health_sofia_plans (deferido — flexibilidade até termos métricas)
--   • Tabelas de voice (TTS/STT) — uso roda no api/sofia, log via audit
--
-- Modelo padrão: gemini-3.1-flash (LLM_PROVIDER=gemini em settings.py)

BEGIN;

-- =====================================================
-- Adicionar role 'paciente_b2c' ao CHECK constraint
-- =====================================================
ALTER TABLE aia_health_users
    DROP CONSTRAINT IF EXISTS aia_health_users_role_check;

ALTER TABLE aia_health_users
    ADD CONSTRAINT aia_health_users_role_check CHECK (role IN (
        'super_admin', 'admin_tenant', 'medico', 'enfermeiro',
        'cuidador_pro', 'familia', 'parceiro', 'paciente_b2c'
    ));

-- Plano contratado (B2C). NULL = sem plano (B2B/operadores).
-- Usado por quota_service pra reportar consumo. Não-restritivo nesta fase.
ALTER TABLE aia_health_users
    ADD COLUMN IF NOT EXISTS plan_sku TEXT,
    ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_active BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_users_plan ON aia_health_users(plan_sku)
    WHERE plan_sku IS NOT NULL;

-- =====================================================
-- aia_health_sofia_sessions — sessão de chat
-- =====================================================
-- Uma sessão por contexto contínuo. Reabre se inativa por > 1h.
CREATE TABLE IF NOT EXISTS aia_health_sofia_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    persona TEXT NOT NULL CHECK (persona IN (
        'cuidador_pro', 'familia', 'medico', 'enfermeiro',
        'admin_tenant', 'super_admin', 'paciente_b2c', 'parceiro', 'anonymous'
    )),
    -- Identificação alternativa pra entradas via WhatsApp (sem JWT)
    phone TEXT,                            -- E.164 sem +
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE SET NULL,
    -- Canal de origem
    channel TEXT NOT NULL DEFAULT 'web' CHECK (channel IN (
        'web', 'whatsapp', 'voice', 'api'
    )),
    -- Metadata da sessão (livre)
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sofia_sessions_user
    ON aia_health_sofia_sessions(tenant_id, user_id, last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_sofia_sessions_phone
    ON aia_health_sofia_sessions(phone, last_active_at DESC)
    WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sofia_sessions_active
    ON aia_health_sofia_sessions(last_active_at DESC)
    WHERE closed_at IS NULL;

-- =====================================================
-- aia_health_sofia_messages — histórico de chat
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_sofia_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES aia_health_sofia_sessions(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
    content TEXT,                          -- payload texto. Para áudio, salvar storage path em metadata.
    -- Tool call (quando role='tool' ou assistant chamou tool)
    tool_name TEXT,
    tool_input JSONB,
    tool_output JSONB,
    -- Tokens & modelo (custo)
    model TEXT,                            -- ex: gemini-3.1-flash
    tokens_in INTEGER,
    tokens_out INTEGER,
    -- Áudio (se aplicável)
    audio_url TEXT,
    audio_duration_ms INTEGER,
    -- Misc
    metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sofia_messages_session
    ON aia_health_sofia_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sofia_messages_tenant_ts
    ON aia_health_sofia_messages(tenant_id, created_at DESC);

-- =====================================================
-- aia_health_sofia_token_usage — agregado mensal por user
-- =====================================================
-- Granularidade: 1 linha por (user, mês civil, plan_sku). UPSERT
-- incremental conforme messages chegam. Permite reportar uso e
-- gatilhar billing/limites futuros sem mudar schema.
CREATE TABLE IF NOT EXISTS aia_health_sofia_token_usage (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    phone TEXT,                            -- fallback p/ B2C anônimo via WhatsApp
    period_year INTEGER NOT NULL,          -- ex 2026
    period_month INTEGER NOT NULL,         -- 1-12
    plan_sku TEXT,                         -- snapshot no momento do consumo
    -- Métricas
    messages_count INTEGER NOT NULL DEFAULT 0,
    tokens_in_total BIGINT NOT NULL DEFAULT 0,
    tokens_out_total BIGINT NOT NULL DEFAULT 0,
    audio_minutes_total NUMERIC(8,2) NOT NULL DEFAULT 0,
    tool_calls_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unicidade via dois partial indexes (mais simples que COALESCE no índice):
-- 1 row por (user, year, month) quando user_id existe; ou (phone, year, month)
-- quando user_id é NULL. quota_service garante deduplicação via SELECT+UPDATE.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sofia_usage_user_period
    ON aia_health_sofia_token_usage(tenant_id, user_id, period_year, period_month)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_sofia_usage_phone_period
    ON aia_health_sofia_token_usage(tenant_id, phone, period_year, period_month)
    WHERE user_id IS NULL AND phone IS NOT NULL;

-- =====================================================
-- aia_health_sofia_availability_rules — janela de atendimento
-- =====================================================
-- Aplicável a operadores (medico, enfermeiro, admin_tenant). Sem rule
-- cadastrada = sempre disponível. Pacientes/familiares ignoram esse gate.
CREATE TABLE IF NOT EXISTS aia_health_sofia_availability_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
    -- 0=domingo, 6=sábado (ISO domingo-first; usar enum se trocar)
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    time_start TIME NOT NULL,
    time_end TIME NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    -- Mensagem custom devolvida quando fora do horário
    out_of_hours_message TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (time_end > time_start)
);

CREATE INDEX IF NOT EXISTS idx_sofia_avail_user_dow
    ON aia_health_sofia_availability_rules(user_id, day_of_week)
    WHERE active = TRUE;

-- =====================================================
-- aia_health_sofia_audit — decisões de gate + tool calls
-- =====================================================
-- Complementa aia_health_audit_chain. Não usamos hash-chain aqui pq o
-- volume é alto (cada chat) e a chain ficaria muito longa. Esta tabela
-- é append-only mas sem prova criptográfica — suficiente pra LGPD/Art 9
-- e debug. Eventos sensíveis (tool call que mudou paciente) ainda vão
-- pro audit_chain principal via audit_log() do audit_service.
CREATE TABLE IF NOT EXISTS aia_health_sofia_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    session_id UUID REFERENCES aia_health_sofia_sessions(id) ON DELETE SET NULL,
    user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    persona TEXT,
    event_type TEXT NOT NULL,              -- gate_allow, gate_blocked_offhours, gate_blocked_quota, tool_call, error
    decision TEXT,                         -- allow, blocked
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sofia_audit_session
    ON aia_health_sofia_audit(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sofia_audit_tenant_ts
    ON aia_health_sofia_audit(tenant_id, created_at DESC);

-- =====================================================
-- Triggers
-- =====================================================
DROP TRIGGER IF EXISTS trg_sofia_avail_updated_at ON aia_health_sofia_availability_rules;
CREATE TRIGGER trg_sofia_avail_updated_at
    BEFORE UPDATE ON aia_health_sofia_availability_rules
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_users_set_updated_at();

DROP TRIGGER IF EXISTS trg_sofia_usage_updated_at ON aia_health_sofia_token_usage;
CREATE TRIGGER trg_sofia_usage_updated_at
    BEFORE UPDATE ON aia_health_sofia_token_usage
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_users_set_updated_at();

COMMIT;
