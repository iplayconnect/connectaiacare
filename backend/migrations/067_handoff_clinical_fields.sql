-- ═══════════════════════════════════════════════════════════════════
-- 067 — Campos clínicos em aia_health_human_handoff_queue
--
-- Phase C v2 introduz CareSofiaAgent que atende cuidador_pro e pode
-- escalar pra equipe CLÍNICA (em vez do comercial). Pra que o painel
-- de handoff diferencie comercial vs clinical e mostre patient/caregiver
-- claimáveis com contexto, adicionamos:
--
--   handoff_type   - 'commercial' (default) | 'clinical' | 'support'
--   patient_id     - FK paciente envolvido (opcional)
--   caregiver_id   - FK cuidador que escalou (opcional)
--
-- Aditiva, nullable, zero risco em prod. Rows existentes ficam com
-- handoff_type='commercial' (default).
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE aia_health_human_handoff_queue
    ADD COLUMN IF NOT EXISTS handoff_type TEXT
        NOT NULL DEFAULT 'commercial'
        CHECK (handoff_type IN ('commercial', 'clinical', 'support'));

ALTER TABLE aia_health_human_handoff_queue
    ADD COLUMN IF NOT EXISTS patient_id UUID;

ALTER TABLE aia_health_human_handoff_queue
    ADD COLUMN IF NOT EXISTS caregiver_id UUID;

-- FKs com ON DELETE SET NULL — handoff sobrevive se patient/caregiver
-- for arquivado, mas perde a referência (audit trail mantido).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_handoff_patient'
    ) THEN
        ALTER TABLE aia_health_human_handoff_queue
            ADD CONSTRAINT fk_handoff_patient
            FOREIGN KEY (patient_id) REFERENCES aia_health_patients(id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_handoff_caregiver'
    ) THEN
        ALTER TABLE aia_health_human_handoff_queue
            ADD CONSTRAINT fk_handoff_caregiver
            FOREIGN KEY (caregiver_id) REFERENCES aia_health_caregivers(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- Índices pra filtros comuns no painel
CREATE INDEX IF NOT EXISTS idx_handoff_type
    ON aia_health_human_handoff_queue(handoff_type)
    WHERE status IN ('pending', 'claimed');

CREATE INDEX IF NOT EXISTS idx_handoff_patient
    ON aia_health_human_handoff_queue(patient_id)
    WHERE patient_id IS NOT NULL;

COMMENT ON COLUMN aia_health_human_handoff_queue.handoff_type IS
    'Tipo de handoff: commercial (default — captura lead/dúvida), '
    'clinical (escala pra equipe clínica/médico — Phase C v2 CareSofiaAgent), '
    'support (suporte pós-venda — SupportSofiaAgent).';

COMMENT ON COLUMN aia_health_human_handoff_queue.patient_id IS
    'Paciente envolvido no handoff (preenchido por handoffs clínicos). '
    'NULL pra handoffs comerciais ou suporte sem paciente.';

COMMENT ON COLUMN aia_health_human_handoff_queue.caregiver_id IS
    'Cuidador que disparou handoff (handoffs clínicos via WhatsApp). '
    'NULL pra leads anônimos ou pacientes B2C self-reporting.';

COMMIT;
