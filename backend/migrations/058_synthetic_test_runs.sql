-- ═══════════════════════════════════════════════════════════════════
-- 058 — Synthetic test runs registry
--
-- Persiste cada execução do harness de testes sintéticos. Vira:
--   * Timeline de qualidade do classificador (F1 ao longo do tempo)
--   * Detector de regressão (compara run novo vs baseline)
--   * Demo value: dashboard mostrando "nosso classificador é auditado
--     contra N cenários sintéticos N×/dia, F1 atual XX%"
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_synthetic_test_runs (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id text NOT NULL DEFAULT 'connectaiacare_demo',
    ran_at timestamptz NOT NULL DEFAULT NOW(),

    -- Configuração do run
    corpus_path text NOT NULL,
    corpus_size integer NOT NULL,
    mode text NOT NULL CHECK (mode IN ('tier1', 'cascade')),
    threshold numeric(5, 3) NOT NULL DEFAULT 0.85,

    -- Métricas agregadas
    accuracy numeric(5, 3) NOT NULL,
    f1_macro numeric(5, 3) NOT NULL,
    threshold_pass boolean NOT NULL,

    -- Detalhes (jsonb pra flexibilidade)
    per_class jsonb NOT NULL DEFAULT '{}'::jsonb,         -- {classe: {p,r,f1,support,tp,fp,fn}}
    confusion_matrix jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {classe: {classe_predita: count}}
    errors jsonb NOT NULL DEFAULT '[]'::jsonb,            -- lista de erros [{id,expected,predicted,difficulty}]
    cascade_stats jsonb,                                  -- só em mode=cascade

    -- Performance
    elapsed_seconds numeric(10, 2),

    -- Auditoria
    ran_by_user_id uuid,
    notes text,

    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synth_runs_tenant_ran_at
    ON aia_health_synthetic_test_runs(tenant_id, ran_at DESC);
CREATE INDEX IF NOT EXISTS idx_synth_runs_pass
    ON aia_health_synthetic_test_runs(tenant_id, threshold_pass, ran_at DESC);

COMMENT ON TABLE aia_health_synthetic_test_runs IS
    'Histórico de execuções dos testes sintéticos de classificação. '
    'Detector de regressão + demo value (dashboard admin).';
COMMENT ON COLUMN aia_health_synthetic_test_runs.mode IS
    'tier1=só extract_entities (qualidade do modelo); '
    'cascade=CascadeClassifier completo T1+T2+T3.';
COMMENT ON COLUMN aia_health_synthetic_test_runs.cascade_stats IS
    'Só preenchido em mode=cascade: {tier1_only, tier2_triggered, tier3_triggered}.';
