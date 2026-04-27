-- ConnectaIACare — Risk Score Fase 2: Baseline Individual.
--
-- Fase 1 (migration 039) usa thresholds absolutos: 5 queixas/sem = high.
-- Mas o paciente João normalmente tem 5 queixas/sem (DPOC, baseline alto)
-- — pra ELE 5 é normal. A paciente Maria tipicamente tem 0-1 queixa/sem.
-- Ela ir pra 3 = sinal forte, mesmo que abaixo do threshold absoluto.
--
-- Baseline individual computa o padrão histórico de cada paciente e
-- calcula desvio robusto (z-score com median + MAD) em relação a ele.
--
-- A Fase 1 continua existindo (compatibilidade + score floor objetivo);
-- Fase 2 ADICIONA dimensão sem remover.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Baseline histórico por paciente (uma linha por paciente)
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_patient_baselines (
    patient_id UUID PRIMARY KEY REFERENCES aia_health_patients(id)
        ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,

    -- janela observada
    period_days INTEGER NOT NULL DEFAULT 60,
    weeks_observed INTEGER NOT NULL DEFAULT 0,

    -- estatística robusta por dimensão (median + MAD)
    -- complaints (queixas) por semana
    complaints_median NUMERIC(8,2),
    complaints_mad NUMERIC(8,2),
    complaints_history JSONB DEFAULT '[]'::jsonb,  -- contagens semanais

    -- adesão % por semana
    adherence_median NUMERIC(8,2),
    adherence_mad NUMERIC(8,2),
    adherence_history JSONB DEFAULT '[]'::jsonb,

    -- eventos urgent/critical por semana
    urgent_median NUMERIC(8,2),
    urgent_mad NUMERIC(8,2),
    urgent_history JSONB DEFAULT '[]'::jsonb,

    -- meta
    has_sufficient_data BOOLEAN NOT NULL DEFAULT FALSE,
    insufficient_reason TEXT,
    last_computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patient_baselines_tenant
    ON aia_health_patient_baselines(tenant_id, last_computed_at);


-- ════════════════════════════════════════════════════════════════
-- 2. Adiciona campos de desvio em risk_score (Fase 1 + Fase 2 lado a lado)
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_patient_risk_score
    -- z-score robusto: (current - median) / (1.4826 * MAD)
    ADD COLUMN IF NOT EXISTS baseline_complaints_z NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS baseline_adherence_z NUMERIC(6,2),  -- negativo = pior
    ADD COLUMN IF NOT EXISTS baseline_urgent_z NUMERIC(6,2),

    -- score 0-100 puramente baseado em desvio individual
    ADD COLUMN IF NOT EXISTS baseline_deviation_score INTEGER,

    -- score combinado: max(phase1, phase1 + bonus_phase2)
    ADD COLUMN IF NOT EXISTS combined_score INTEGER,
    ADD COLUMN IF NOT EXISTS combined_level TEXT,

    -- flag pra UI
    ADD COLUMN IF NOT EXISTS has_baseline BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN aia_health_patient_risk_score.baseline_deviation_score IS
    'Score 0-100 derivado APENAS dos desvios individuais. Não substitui o '
    'score absoluto (Fase 1) — adiciona dimensão.';
COMMENT ON COLUMN aia_health_patient_risk_score.combined_score IS
    'Score híbrido: Fase 1 como floor + bônus do desvio individual. '
    'Pode ser maior que Fase 1 quando paciente desviou MUITO do próprio '
    'baseline mesmo abaixo do threshold absoluto.';

COMMIT;
