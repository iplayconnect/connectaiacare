-- ConnectaIACare — Estende biometria de voz para PACIENTES.
--
-- A migration 003 só cobria cuidadores. Em casa onde paciente também
-- usa WhatsApp/voz da Sofia, precisamos distinguir voz do paciente da
-- voz do cuidador. Sem isso, sintomas reportados por terceiros podem
-- ser atribuídos ao paciente errado.
--
-- Estratégia: aia_health_voice_embeddings ganha:
--   - person_type ('caregiver'|'patient') — quem é a voz registrada.
--   - patient_id UUID NULL — populado quando person_type='patient'.
-- caregiver_id vira nullable (precisa um OU outro, nunca os dois).

BEGIN;

ALTER TABLE aia_health_voice_embeddings
    ADD COLUMN IF NOT EXISTS person_type TEXT
        NOT NULL DEFAULT 'caregiver'
        CHECK (person_type IN ('caregiver', 'patient')),
    ADD COLUMN IF NOT EXISTS patient_id UUID
        REFERENCES aia_health_patients(id) ON DELETE CASCADE;

-- caregiver_id agora é nullable porque a linha pode pertencer a paciente
ALTER TABLE aia_health_voice_embeddings
    ALTER COLUMN caregiver_id DROP NOT NULL;

-- Garante exatamente UM dos dois preenchido (XOR)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'voice_embeddings_xor_person'
    ) THEN
        ALTER TABLE aia_health_voice_embeddings
            ADD CONSTRAINT voice_embeddings_xor_person
            CHECK (
                (caregiver_id IS NOT NULL AND patient_id IS NULL AND person_type = 'caregiver')
                OR
                (patient_id IS NOT NULL AND caregiver_id IS NULL AND person_type = 'patient')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_voice_patient ON aia_health_voice_embeddings(patient_id)
    WHERE patient_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_voice_person_type ON aia_health_voice_embeddings(tenant_id, person_type);

-- ════════════════════════════════════════════════════════════════════
-- Consent log também ganha patient_id
-- ════════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_voice_consent_log
    ADD COLUMN IF NOT EXISTS person_type TEXT
        DEFAULT 'caregiver'
        CHECK (person_type IN ('caregiver', 'patient')),
    ADD COLUMN IF NOT EXISTS patient_id UUID
        REFERENCES aia_health_patients(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_consent_patient ON aia_health_voice_consent_log(patient_id)
    WHERE patient_id IS NOT NULL;

-- ════════════════════════════════════════════════════════════════════
-- Reports: amplia caregiver_voice_method pra incluir paciente
-- ════════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_reports
    ADD COLUMN IF NOT EXISTS reporter_person_type TEXT
        CHECK (reporter_person_type IN ('caregiver', 'patient', 'unknown'));

-- ════════════════════════════════════════════════════════════════════
-- VIEW: cobertura de biometria por tenant
-- ════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW aia_health_voice_coverage_summary AS
SELECT
    tenant_id,
    person_type,
    COUNT(DISTINCT COALESCE(caregiver_id, patient_id)) AS people_enrolled,
    COUNT(*) AS samples_total,
    AVG(quality_score)::NUMERIC(4,3) AS avg_quality,
    MIN(created_at) AS first_enrollment,
    MAX(created_at) AS last_enrollment
FROM aia_health_voice_embeddings
GROUP BY tenant_id, person_type;

COMMIT;
