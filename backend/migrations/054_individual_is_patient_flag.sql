-- ConnectaIACare — Refatora modelo: individual NÃO é tenant_type
-- nem licensing_model. É uma flag por paciente.
--
-- Correção arquitetural (Alexandre): "B2C direto no ID_CPF, não
-- vamos queimar uma posição de Tenant para um único usuário, mas
-- podemos pensar em casos de usuários com 3 cuidadores manhã/tarde/
-- noite."
--
-- Decisão final:
--   * 1 tenant B2C agrega N pacientes (cada um com CPF, dados
--     próprios, cuidadores próprios). Privacy via patient_id + RBAC.
--   * Paciente que reporta sobre si mesmo (idoso solo sem cuidador)
--     vira flag `is_self_reporting = TRUE` no aia_health_patients.
--     Não é mais tenant_type=individual nem licensing_model=individual.
--   * Plantão por paciente: 3 cuidadores rotativos (manhã/tarde/noite)
--     resolve via aia_health_caregiver_patient_assignments + plantões
--     já cadastrados em aia_health_shift_schedules.
--   * licensing_model fica binário: b2b_organization (ILPI/clínica/
--     hospital) | b2c_per_patient (família/domicílio).

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. Remove 'individual' de tenant_type — modo defensivo
-- ════════════════════════════════════════════════════════════════════
-- Drop constraint primeiro (sem nome rígido — descobre dinamicamente).
-- Depois normaliza valores fora do conjunto pra 'B2C' (default seguro).
-- Por último adiciona a nova constraint com o conjunto reduzido.

DO $$
DECLARE
    v_constraint_name TEXT;
BEGIN
    -- Descobre nome real da CHECK constraint (Postgres pode auto-nomear
    -- diferente do esperado dependendo da ordem de definição).
    SELECT conname INTO v_constraint_name
    FROM pg_constraint
    WHERE conrelid = 'aia_health_tenant_config'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%tenant_type%';

    IF v_constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE aia_health_tenant_config DROP CONSTRAINT %I',
            v_constraint_name
        );
    END IF;
END $$;

-- Agora sem constraint, normaliza qualquer valor fora do conjunto novo
UPDATE aia_health_tenant_config
   SET tenant_type = 'B2C'
 WHERE tenant_type IS NULL
    OR tenant_type NOT IN ('ILPI', 'clinica', 'hospital', 'B2C');

ALTER TABLE aia_health_tenant_config
    ADD CONSTRAINT aia_health_tenant_config_tenant_type_check
    CHECK (tenant_type IN ('ILPI', 'clinica', 'hospital', 'B2C'));


-- ════════════════════════════════════════════════════════════════════
-- 2. Simplifica licensing_model — mesmo modo defensivo
-- ════════════════════════════════════════════════════════════════════

DO $$
DECLARE
    v_constraint_name TEXT;
BEGIN
    SELECT conname INTO v_constraint_name
    FROM pg_constraint
    WHERE conrelid = 'aia_health_tenant_config'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%licensing_model%';

    IF v_constraint_name IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE aia_health_tenant_config DROP CONSTRAINT %I',
            v_constraint_name
        );
    END IF;
END $$;

UPDATE aia_health_tenant_config
   SET licensing_model = 'b2c_per_patient'
 WHERE licensing_model IS NULL
    OR licensing_model NOT IN ('b2b_organization', 'b2c_per_patient');

ALTER TABLE aia_health_tenant_config
    ADD CONSTRAINT aia_health_tenant_config_licensing_model_check
    CHECK (licensing_model IN ('b2b_organization', 'b2c_per_patient'));


-- ════════════════════════════════════════════════════════════════════
-- 3. Paciente: flag is_self_reporting + CPF dedicado
-- ════════════════════════════════════════════════════════════════════
-- is_self_reporting=TRUE → paciente fala direto com Sofia (sem
-- cuidador intermediário). Sofia carrega prompt acolhedor. Tom em
-- primeira pessoa.
--
-- CPF é o "login" estável do paciente em B2C — número permanece
-- mesmo que troque de telefone/cuidador. Index único por tenant.

ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS is_self_reporting BOOLEAN
        NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cpf TEXT;

COMMENT ON COLUMN aia_health_patients.is_self_reporting IS
'TRUE quando paciente fala direto com Sofia (idoso solo, sem cuidador '
'intermediário). Sofia ajusta tom, persona e fluxo de pergunta.';

COMMENT ON COLUMN aia_health_patients.cpf IS
'CPF do paciente — identificador estável (não muda com troca de '
'telefone). Usado em B2C como login natural.';

-- Único por tenant (CPF pode repetir em tenants distintos se for
-- mesma pessoa atendida por 2 instituições, raro mas possível).
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_cpf_per_tenant
    ON aia_health_patients(tenant_id, cpf)
    WHERE cpf IS NOT NULL;


-- ════════════════════════════════════════════════════════════════════
-- 4. Relação cuidador ↔ paciente (N:M)
-- ════════════════════════════════════════════════════════════════════
-- Em ILPI: cuidador atende N pacientes do lar (relação implícita
-- "todo cuidador atende todo paciente do tenant"). Mas em B2C com 3
-- cuidadores manhã/tarde/noite por paciente, cada cuidador tem
-- alocação específica. Precisa relação explícita.

CREATE TABLE IF NOT EXISTS aia_health_caregiver_patient_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    caregiver_id UUID NOT NULL REFERENCES aia_health_caregivers(id)
        ON DELETE CASCADE,
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id)
        ON DELETE CASCADE,

    -- Tipo de relação clínica/familiar
    relationship TEXT NOT NULL DEFAULT 'professional'
        CHECK (relationship IN (
            'professional',  -- cuidador profissional contratado
            'family',        -- familiar (filho, esposa, neto)
            'volunteer'      -- voluntário/vizinho que apoia
        )),

    is_primary BOOLEAN NOT NULL DEFAULT FALSE,  -- principal cuidador
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (caregiver_id, patient_id)
);

CREATE INDEX IF NOT EXISTS idx_caregiver_patient_tenant
    ON aia_health_caregiver_patient_assignments(tenant_id, active);

CREATE INDEX IF NOT EXISTS idx_caregiver_patient_caregiver
    ON aia_health_caregiver_patient_assignments(caregiver_id)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_caregiver_patient_patient
    ON aia_health_caregiver_patient_assignments(patient_id)
    WHERE active = TRUE;

DROP TRIGGER IF EXISTS trg_caregiver_patient_updated
    ON aia_health_caregiver_patient_assignments;
CREATE TRIGGER trg_caregiver_patient_updated
    BEFORE UPDATE ON aia_health_caregiver_patient_assignments
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- ════════════════════════════════════════════════════════════════════
-- 5. VIEW: cuidadores ativos por paciente (com plantão atual)
-- ════════════════════════════════════════════════════════════════════
-- Usada pelo voice_biometrics_service: pool de busca pra um áudio
-- direcionado a paciente X = só os cuidadores assigned a X que estão
-- de plantão agora. Ex.: paciente em B2C com 3 cuidadores rotativos
-- → pool de 1 voz no horário (cuidador da manhã às 10h).

CREATE OR REPLACE VIEW aia_health_active_caregivers_by_patient AS
SELECT
    a.patient_id,
    a.caregiver_id,
    c.full_name AS caregiver_name,
    c.phone,
    c.phone_type,
    s.shift_name,
    s.starts_at,
    s.ends_at
FROM aia_health_caregiver_patient_assignments a
JOIN aia_health_caregivers c ON c.id = a.caregiver_id
LEFT JOIN aia_health_shift_schedules s
    ON s.caregiver_id = a.caregiver_id
   AND s.active = TRUE
   AND CURRENT_TIME BETWEEN s.starts_at AND s.ends_at
   AND EXTRACT(ISODOW FROM CURRENT_DATE)::INT = ANY(s.weekdays)
WHERE a.active = TRUE
  AND c.active = TRUE;


COMMIT;
