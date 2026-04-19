-- ConnectaIACare — Voice Biometrics Schema
-- Extensão pgvector + tabelas de embeddings e consent log

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- Voice Embeddings (256-dim Resemblyzer)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_voice_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    caregiver_id UUID NOT NULL REFERENCES aia_health_caregivers(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    embedding VECTOR(256) NOT NULL,
    sample_label TEXT NOT NULL DEFAULT 'enrollment',
    audio_duration_ms INTEGER,
    quality_score NUMERIC(4,3),
    consent_ip TEXT,
    consent_given_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_voice_caregiver ON aia_health_voice_embeddings(caregiver_id);
CREATE INDEX IF NOT EXISTS idx_voice_tenant ON aia_health_voice_embeddings(tenant_id);

-- Index IVFFlat para busca por similaridade (pgvector)
-- IMPORTANTE: só criar depois de ter ~100 embeddings no tenant para o index valer a pena.
-- Para demo com poucos cuidadores, full-scan é mais rápido.
-- CREATE INDEX ON aia_health_voice_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- =====================================================
-- Consent Log (LGPD — histórico de consentimentos)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_voice_consent_log (
    id BIGSERIAL PRIMARY KEY,
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    action TEXT NOT NULL CHECK (action IN (
        'consent_given','consent_revoked','data_accessed','data_deleted','enrollment_added'
    )),
    ip_address TEXT,
    user_agent TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consent_caregiver ON aia_health_voice_consent_log(caregiver_id);
CREATE INDEX IF NOT EXISTS idx_consent_created ON aia_health_voice_consent_log(created_at DESC);

-- =====================================================
-- Coluna de identificação de cuidador na tabela reports
-- (ampliar para armazenar resultado da biometria)
-- =====================================================
ALTER TABLE aia_health_reports
    ADD COLUMN IF NOT EXISTS caregiver_voice_method TEXT CHECK (caregiver_voice_method IN ('1:1','1:N','phone','manual','none')),
    ADD COLUMN IF NOT EXISTS caregiver_voice_candidates JSONB DEFAULT '[]'::JSONB;

COMMIT;
