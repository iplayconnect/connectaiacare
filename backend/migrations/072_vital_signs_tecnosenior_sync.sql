-- =============================================================================
-- 072 — Sync de vital signs pro TotalCare (Tecnosenior health measures bulk)
-- =============================================================================
--
-- Quando Sofia detecta uma medida via voz/texto/foto, persiste local em
-- aia_health_vital_signs imediatamente. Depois que cuidador confirma o
-- conjunto via diálogo, a gente faz bulk POST pro TotalCare.
--
-- Decisões (alinhadas com Matheus 2026-05-08):
--   • Tecnosenior usa ALL-OR-NOTHING no bulk (rejeita tudo se 1 medida
--     bate validação deles). Nossa filter_valid_for_persistence já
--     filtra valores impossíveis ANTES, então o bulk deve sempre passar.
--   • Resposta retorna array ordenado por measured_at com {id} de cada
--     medida criada — fazemos mapping local UUID → tecnosenior INT id.
--   • Idempotency-Key vai como header, mesmo UUID compartilhado entre
--     todas as medidas do mesmo batch (vira batch_id local).
--
-- Migração idempotente.
-- =============================================================================

-- 1. Colunas de sync direto na vital_signs (1 row = 1 medida)
ALTER TABLE aia_health_vital_signs
    ADD COLUMN IF NOT EXISTS tecnosenior_measure_id INT,
    ADD COLUMN IF NOT EXISTS tecnosenior_synced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tecnosenior_sync_batch_id UUID,
    ADD COLUMN IF NOT EXISTS tecnosenior_sync_error TEXT,
    ADD COLUMN IF NOT EXISTS confirmed_by_caregiver_at TIMESTAMPTZ;

COMMENT ON COLUMN aia_health_vital_signs.tecnosenior_measure_id IS
    'ID retornado pelo TotalCare após bulk POST. NULL = ainda não sincronizado.';
COMMENT ON COLUMN aia_health_vital_signs.tecnosenior_sync_batch_id IS
    'UUID compartilhado entre todas as medidas do mesmo bulk (vira ' ||
    'Idempotency-Key na request). Permite retry seguro.';
COMMENT ON COLUMN aia_health_vital_signs.confirmed_by_caregiver_at IS
    'Sofia só envia pro TotalCare medidas confirmadas pelo cuidador. ' ||
    'NULL = ainda em buffer/pending confirmation.';

CREATE INDEX IF NOT EXISTS idx_aia_vital_signs_pending_sync
    ON aia_health_vital_signs(patient_id, confirmed_by_caregiver_at)
    WHERE tecnosenior_synced_at IS NULL
      AND confirmed_by_caregiver_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_aia_vital_signs_batch
    ON aia_health_vital_signs(tecnosenior_sync_batch_id)
    WHERE tecnosenior_sync_batch_id IS NOT NULL;


-- 2. Auditoria de batches (1 row por bulk POST tentado)
CREATE TABLE IF NOT EXISTS aia_health_vital_signs_sync_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    tecnosenior_patient_id INT,        -- ID resolvido no momento do bulk
    measures_count INT NOT NULL,        -- quantas medidas no batch
    measures_succeeded INT NOT NULL DEFAULT 0,
    measures_failed INT NOT NULL DEFAULT 0,
    idempotency_key UUID NOT NULL,      -- UUID enviado como Idempotency-Key
    request_payload JSONB,              -- payload completo enviado (audit)
    response_payload JSONB,             -- resposta crua do TotalCare
    sync_error TEXT,                    -- null se sucesso
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE(idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_aia_vital_sync_batches_patient
    ON aia_health_vital_signs_sync_batches(patient_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_aia_vital_sync_batches_failed
    ON aia_health_vital_signs_sync_batches(started_at DESC)
    WHERE sync_error IS NOT NULL;

COMMENT ON TABLE aia_health_vital_signs_sync_batches IS
    'Audit dos bulk POSTs feitos pro TotalCare. Útil pra debug, retry ' ||
    'manual via admin, e idempotência local (não retentar mesmo batch_id).';
