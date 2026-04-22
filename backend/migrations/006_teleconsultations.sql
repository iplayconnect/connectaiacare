-- ConnectaIACare — Migration 006: Teleconsultations + persona médica demo
-- Data: 2026-04-21
--
-- Implementa ADR-023: sessão de teleconsulta com state machine de 9 estados,
-- SOAP estruturado, prescrição mockada, FHIR Bundle, compliance CFM 2.314/2022.
--
-- Também adiciona tabela leve de "doctors" (mockada na demo, mas estrutura
-- real pra quando integrar CRM/CFM via API).

BEGIN;

-- =====================================================
-- 1. DOCTORS — persona médica (mockada hoje, real depois)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    full_name TEXT NOT NULL,
    crm_number TEXT,                        -- ex: "CRM/RS 12345"
    crm_state TEXT,                         -- "RS", "SP", etc
    specialties TEXT[] DEFAULT ARRAY[]::TEXT[],
    photo_url TEXT,
    phone TEXT,
    email TEXT,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE, -- flag pra UI mostrar "persona demo"
    active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_doctors_tenant ON aia_health_doctors(tenant_id);

DROP TRIGGER IF EXISTS trg_doctors_updated ON aia_health_doctors;
CREATE TRIGGER trg_doctors_updated
    BEFORE UPDATE ON aia_health_doctors
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- =====================================================
-- 2. TELECONSULTATIONS — sessão de consulta completa
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_teleconsultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    human_id SERIAL,  -- #0001, #0002 pra referência humana
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',

    -- Relacionamentos
    care_event_id UUID REFERENCES aia_health_care_events(id) ON DELETE SET NULL,
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    doctor_id UUID REFERENCES aia_health_doctors(id) ON DELETE SET NULL,

    -- Denormalizado pra auditoria (caso medico.name mude depois)
    doctor_name_snapshot TEXT,
    doctor_crm_snapshot TEXT,

    -- State machine (ADR-023)
    state TEXT NOT NULL DEFAULT 'scheduling'
        CHECK (state IN ('scheduling','pre_check','consent_recording',
                         'identity_verification','active','closing',
                         'documentation','signed','closed')),

    -- Sala LiveKit
    livekit_room_name TEXT,
    livekit_room_sid TEXT,
    livekit_metadata JSONB DEFAULT '{}'::JSONB,

    -- Consentimento
    consent_recorded_at TIMESTAMPTZ,
    consent_audio_hash TEXT,                    -- SHA256 do áudio do "autorizo"
    consent_transcription TEXT,                 -- transcrição do consentimento

    -- Identidade
    identity_verified_at TIMESTAMPTZ,
    identity_method TEXT CHECK (identity_method IN ('security_question','document_photo','phone_auth') OR identity_method IS NULL),
    identity_question TEXT,
    identity_answer_hash TEXT,

    -- Transcrição (completa, batch pós-consulta)
    transcription_full TEXT,
    transcription_language TEXT NOT NULL DEFAULT 'pt-BR',
    transcription_duration_seconds INT,

    -- Estruturado pós-processamento (output dos agentes)
    anamnesis JSONB,                            -- História Doença Atual estruturada
    diagnosis_suggestions JSONB DEFAULT '[]'::JSONB,
    soap JSONB,                                 -- {subjective, objective, assessment, plan}
    prescription JSONB DEFAULT '[]'::JSONB,     -- lista de medicamentos validados
    fhir_bundle JSONB,                          -- Bundle R4 completo pra interop

    -- Assinatura
    signed_at TIMESTAMPTZ,
    signed_by_doctor_name TEXT,
    signed_by_doctor_crm TEXT,
    signature_method TEXT CHECK (signature_method IN ('mock','vidaas','icp_brasil') OR signature_method IS NULL),
    signature_ref TEXT,                         -- ID externo (Vidaas) ou null

    -- Timeline
    scheduled_for TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INT GENERATED ALWAYS AS (
        CASE
            WHEN ended_at IS NOT NULL AND started_at IS NOT NULL
            THEN EXTRACT(EPOCH FROM (ended_at - started_at))::INT
            ELSE NULL
        END
    ) STORED,

    -- Sync TotalCare
    totalcare_care_note_id BIGINT,              -- ID da care-note criada pós-sign

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_teleconsult_tenant ON aia_health_teleconsultations(tenant_id);
CREATE INDEX IF NOT EXISTS idx_teleconsult_patient ON aia_health_teleconsultations(patient_id);
CREATE INDEX IF NOT EXISTS idx_teleconsult_care_event ON aia_health_teleconsultations(care_event_id);
CREATE INDEX IF NOT EXISTS idx_teleconsult_doctor ON aia_health_teleconsultations(doctor_id);
CREATE INDEX IF NOT EXISTS idx_teleconsult_state ON aia_health_teleconsultations(tenant_id, state)
    WHERE state NOT IN ('signed','closed');
CREATE INDEX IF NOT EXISTS idx_teleconsult_scheduled ON aia_health_teleconsultations(scheduled_for)
    WHERE state = 'scheduling';

DROP TRIGGER IF EXISTS trg_teleconsult_updated ON aia_health_teleconsultations;
CREATE TRIGGER trg_teleconsult_updated
    BEFORE UPDATE ON aia_health_teleconsultations
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- =====================================================
-- 3. SEED: persona médica demo
-- =====================================================
-- Dra. Ana Silva — CRM/RS 12345 (demo, claramente marcada com is_demo=true)
-- Maurício e qualquer operador pode "vestir" esta persona durante a demo.
INSERT INTO aia_health_doctors (
    tenant_id, full_name, crm_number, crm_state, specialties,
    photo_url, email, is_demo, metadata
) VALUES (
    'connectaiacare_demo',
    'Dra. Ana Silva',
    'CRM/RS 12345',
    'RS',
    ARRAY['Geriatria', 'Clínica Médica'],
    NULL,  -- pode ser populada depois com imagem
    'ana.silva@demo.connectaia.com.br',
    TRUE,
    jsonb_build_object(
        'bio', 'Persona médica de demonstração. Em produção, qualquer médico ativo no CFM acessa com seu CRM validado.',
        'demo_note', 'CRM 12345 é número fictício para fins de demonstração'
    )
) ON CONFLICT DO NOTHING;


-- =====================================================
-- 4. Atualizar tenant_config pra incluir Atente fallback (ADR-022)
-- =====================================================
-- Schema do escalation_policy JSONB: lista de roles por classificação.
-- Adicionamos 'atente' como último nível em critical/urgent.
UPDATE aia_health_tenant_config
SET escalation_policy = jsonb_build_object(
        'critical',  jsonb_build_array('central','nurse','doctor','family_1','family_2','family_3','atente'),
        'urgent',    jsonb_build_array('central','nurse','family_1','atente'),
        'attention', jsonb_build_array('central','atente'),
        'routine',   jsonb_build_array()
    ),
    -- Campos pra contato Atente (a preencher quando tiver o número oficial)
    metadata = metadata || jsonb_build_object(
        'atente_central_phone',  COALESCE(metadata->>'atente_central_phone', ''),
        'atente_central_name',   'Central Atente 24h',
        'atente_escalation_priority', 'high',
        'adr_022_applied_at', NOW()::TEXT
    ),
    updated_at = NOW()
WHERE tenant_id = 'connectaiacare_demo';


COMMIT;

-- Confirmação
SELECT 'doctors' AS tabela, COUNT(*) AS total FROM aia_health_doctors
UNION ALL
SELECT 'teleconsultations', COUNT(*) FROM aia_health_teleconsultations;

SELECT tenant_id, escalation_policy->'critical' AS critical_policy
FROM aia_health_tenant_config;
