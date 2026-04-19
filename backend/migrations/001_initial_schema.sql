-- ConnectaIACare — Schema inicial
-- Prefixo: aia_health_* para distinguir de qualquer outro sistema
-- Data: 2026-04-19

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- Pacientes (residentes do SPA ou idosos em casa)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    external_id TEXT,
    full_name TEXT NOT NULL,
    nickname TEXT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('M', 'F', 'O')),
    photo_url TEXT,
    photo_local_path TEXT,
    care_unit TEXT,
    room_number TEXT,
    care_level TEXT,
    conditions JSONB DEFAULT '[]'::JSONB,
    medications JSONB DEFAULT '[]'::JSONB,
    allergies JSONB DEFAULT '[]'::JSONB,
    responsible JSONB DEFAULT '{}'::JSONB,
    metadata JSONB DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patients_tenant ON aia_health_patients(tenant_id);
CREATE INDEX IF NOT EXISTS idx_patients_name_trgm ON aia_health_patients USING gin(full_name gin_trgm_ops);
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =====================================================
-- Cuidadores profissionais
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_caregivers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    full_name TEXT NOT NULL,
    cpf TEXT,
    phone TEXT,
    role TEXT DEFAULT 'cuidador',
    shift TEXT,
    voice_embedding_json JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_caregivers_tenant ON aia_health_caregivers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_caregivers_phone ON aia_health_caregivers(phone);

-- =====================================================
-- Relatos (áudio do cuidador + transcrição + análise)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE SET NULL,
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,
    caregiver_name_claimed TEXT,
    caregiver_phone TEXT NOT NULL,

    audio_url TEXT,
    audio_duration_seconds INTEGER,

    transcription TEXT,
    transcription_confidence NUMERIC(4,3),

    extracted_entities JSONB DEFAULT '{}'::JSONB,

    analysis JSONB DEFAULT '{}'::JSONB,
    classification TEXT CHECK (classification IN ('routine','attention','urgent','critical')),
    needs_medical_attention BOOLEAN DEFAULT FALSE,

    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received','awaiting_confirmation','confirmed','analyzed','synced','error')),

    patient_identification_confidence NUMERIC(4,3),
    caregiver_identification_confidence NUMERIC(4,3),

    session_id UUID,
    partner_sync_status TEXT,
    partner_sync_at TIMESTAMPTZ,

    error_message TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,

    recorded_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_tenant ON aia_health_reports(tenant_id);
CREATE INDEX IF NOT EXISTS idx_reports_patient ON aia_health_reports(patient_id);
CREATE INDEX IF NOT EXISTS idx_reports_caregiver ON aia_health_reports(caregiver_id);
CREATE INDEX IF NOT EXISTS idx_reports_received ON aia_health_reports(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_classification ON aia_health_reports(classification);

-- =====================================================
-- Sessões de conversa (estado do fluxo WhatsApp)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_conversation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    phone TEXT NOT NULL,
    state TEXT NOT NULL,
    context JSONB DEFAULT '{}'::JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_phone ON aia_health_conversation_sessions(tenant_id, phone);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON aia_health_conversation_sessions(expires_at);

-- =====================================================
-- Auditoria imutável (hash-chain)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_audit_chain (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    resource_type TEXT,
    resource_id TEXT,
    action TEXT,
    data_hash TEXT NOT NULL,
    prev_hash TEXT,
    curr_hash TEXT NOT NULL,
    payload JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_ts ON aia_health_audit_chain(tenant_id, timestamp DESC);

-- =====================================================
-- Alertas gerados pelo motor de análise
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    report_id UUID REFERENCES aia_health_reports(id) ON DELETE SET NULL,
    level TEXT NOT NULL CHECK (level IN ('low','medium','high','critical')),
    title TEXT NOT NULL,
    description TEXT,
    recommended_actions JSONB DEFAULT '[]'::JSONB,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_tenant_created ON aia_health_alerts(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_patient ON aia_health_alerts(patient_id);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON aia_health_alerts(level) WHERE resolved_at IS NULL;

-- =====================================================
-- Trigger para updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION aia_health_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_patients_updated ON aia_health_patients;
CREATE TRIGGER trg_patients_updated BEFORE UPDATE ON aia_health_patients
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

DROP TRIGGER IF EXISTS trg_caregivers_updated ON aia_health_caregivers;
CREATE TRIGGER trg_caregivers_updated BEFORE UPDATE ON aia_health_caregivers
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

DROP TRIGGER IF EXISTS trg_reports_updated ON aia_health_reports;
CREATE TRIGGER trg_reports_updated BEFORE UPDATE ON aia_health_reports
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

DROP TRIGGER IF EXISTS trg_sessions_updated ON aia_health_conversation_sessions;
CREATE TRIGGER trg_sessions_updated BEFORE UPDATE ON aia_health_conversation_sessions
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

COMMIT;
