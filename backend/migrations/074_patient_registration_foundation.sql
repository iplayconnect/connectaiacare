-- =============================================================================
-- 074 — Foundation pra cadastro completo de paciente
-- =============================================================================
--
-- Decisão Alexandre+Henrique 2026-05-09:
--   Cadastro auto-declarado de condições, medicações, alergias com:
--   • Provenance por item (de onde veio cada dado)
--   • Sessão de registro (quem registrou, em que papel)
--   • Cross-validação condição × medicamento (soft prompt)
--   • Acúmulo de papéis (gestor pode ser tb enfermeiro/médico)
--   • Trigger de re-revisão quando muda condição/medicamento
--
-- Sem breaking change: campos JSONB existentes continuam funcionando
-- com formato antigo (array de strings). Novos formatos (objetos com
-- provenance) coexistem. Helper de leitura tolera ambos.
-- =============================================================================


-- 1. Acúmulo de papéis em users
-- ---------------------------------------------------------------------------
ALTER TABLE aia_health_users
    ADD COLUMN IF NOT EXISTS additional_roles TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

COMMENT ON COLUMN aia_health_users.additional_roles IS
    'Papéis adicionais ao role primário. Ex: gestor + enfermeiro. ' ||
    'Helper hasRole(user, X) checa role E additional_roles. ' ||
    'Henrique 2026-05-09: gestor de unidade clínica frequentemente ' ||
    'acumula função de enfermeiro ou médico responsável.';

CREATE INDEX IF NOT EXISTS idx_aia_users_additional_roles
    ON aia_health_users USING GIN(additional_roles);


-- 2. Sessões de registro de paciente
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aia_health_patient_registration_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    -- Quem está realizando o registro (NULL se B2C antes de criar conta)
    registered_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    -- Papel sob o qual está registrando (não o role do user, mas a função)
    registered_by_role TEXT NOT NULL CHECK (registered_by_role IN (
        'paciente_b2c',          -- auto-cadastro autônomo
        'familiar_responsavel',  -- familiar cadastrando o idoso
        'procurador',            -- representante legal (4.3 — diferido)
        'gestor_unidade',        -- gestor de lar / clínica
        'enfermeiro',            -- enfermeiro responsável
        'medico'                 -- médico responsável
    )),
    -- Documento de procuração (4.3 — só usado quando role=procurador)
    procuracao_document_url TEXT,
    procuracao_validated_at TIMESTAMPTZ,
    procuracao_validated_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    -- Consentimento LGPD (B2C / familiar)
    consent_lgpd_accepted_at TIMESTAMPTZ,
    consent_lgpd_ip TEXT,
    consent_lgpd_user_agent TEXT,
    -- Progresso do wizard
    last_completed_step INT NOT NULL DEFAULT 0,
    total_steps INT NOT NULL DEFAULT 7,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN (
        'in_progress', 'complete', 'abandoned'
    )),
    -- Auditoria
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    abandoned_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_aia_reg_sessions_patient
    ON aia_health_patient_registration_sessions(patient_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_aia_reg_sessions_status
    ON aia_health_patient_registration_sessions(status, started_at DESC);

COMMENT ON TABLE aia_health_patient_registration_sessions IS
    'Audit trail de cada tentativa de cadastro completo. 1 row por sessão ' ||
    'de wizard. Permite reabrir e continuar de onde parou.';


-- 3. Completude do cadastro (denormalizado em patient pra query rápida)
-- ---------------------------------------------------------------------------
ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS registration_completeness JSONB
        NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_self_review_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS active_registration_session_id UUID
        REFERENCES aia_health_patient_registration_sessions(id) ON DELETE SET NULL;

COMMENT ON COLUMN aia_health_patients.registration_completeness IS
    'JSONB com status por seção: ' ||
    '{demographics:complete, conditions:partial, medications:complete, ' ||
    'allergies:missing, functional_baseline:missing, responsibles:complete, ' ||
    'completion_percentage:67, last_updated_at:...}';

COMMENT ON COLUMN aia_health_patients.last_self_review_at IS
    'Última vez que paciente/responsável confirmou ou alterou seus dados. ' ||
    'Banner de re-revisão aparece se > 1 ano (Henrique 2026-05-09).';


-- 4. Verificação clínica de campos (audit por seção)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aia_health_patient_field_verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    -- Qual seção foi verificada
    section TEXT NOT NULL CHECK (section IN (
        'conditions', 'medications', 'allergies',
        'functional_baseline', 'responsibles',
        'demographics'
    )),
    -- Quem verificou
    verified_by_user_id UUID NOT NULL REFERENCES aia_health_users(id),
    verified_by_role TEXT NOT NULL CHECK (verified_by_role IN (
        'enfermeiro', 'medico', 'farmaceutico'
    )),
    -- Snapshot do conteúdo no momento da verificação (audit imutável)
    content_snapshot JSONB NOT NULL,
    notes TEXT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aia_patient_verif_recent
    ON aia_health_patient_field_verifications(patient_id, section, verified_at DESC);

COMMENT ON TABLE aia_health_patient_field_verifications IS
    'Cada vez que clínico (enfermeiro/médico/farmacêutico) confirma uma ' ||
    'seção do cadastro auto-declarado, registra aqui. Snapshot imutável ' ||
    'do conteúdo permite reconstituir audit mesmo se paciente alterar depois.';


-- 5. Trigger pra atualizar last_self_review_at quando paciente muda
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _aia_patient_touch_self_review()
RETURNS TRIGGER AS $$
BEGIN
    -- Só atualiza last_self_review_at se conditions, medications ou
    -- allergies mudou. Não dispara se foi só demographics ou metadata.
    IF (NEW.conditions IS DISTINCT FROM OLD.conditions
        OR NEW.medications IS DISTINCT FROM OLD.medications
        OR NEW.allergies IS DISTINCT FROM OLD.allergies) THEN
        NEW.last_self_review_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_aia_patient_touch_self_review
    ON aia_health_patients;
CREATE TRIGGER trg_aia_patient_touch_self_review
    BEFORE UPDATE ON aia_health_patients
    FOR EACH ROW EXECUTE FUNCTION _aia_patient_touch_self_review();
