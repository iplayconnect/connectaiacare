-- ConnectaIACare — Patient Risk Scoring Engine.
--
-- Hoje Sofia "decide via LLM" se evento é critical/urgent. GPT crítica:
-- não há thresholds determinísticos pra escala. Risk engine MVP: 3 sinais
-- agregados por paciente, score 0-100 com hierarquia clara.
--
-- Sinais Fase 1 (deterministic):
--   1. Frequência de queixas registradas (care_events) últimos 7d
--   2. Adesão medicação últimos 7d (% confirmadas vs planejadas)
--   3. Padrão Sofia: # interações de severity≥urgent últimos 7d
--
-- Score = peso × normalização. Hierarquia: 0-25 baixo, 26-50 moderado,
-- 51-75 alto, 76-100 crítico.

BEGIN;

CREATE TABLE IF NOT EXISTS aia_health_patient_risk_score (
    patient_id UUID PRIMARY KEY REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,

    -- Score agregado 0-100
    score INTEGER NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100),
    risk_level TEXT NOT NULL DEFAULT 'baixo' CHECK (risk_level IN (
        'baixo', 'moderado', 'alto', 'critico'
    )),

    -- Componentes (cada sinal contribui)
    signal_complaints_7d INTEGER NOT NULL DEFAULT 0,
    signal_complaints_score INTEGER NOT NULL DEFAULT 0,

    signal_adherence_pct NUMERIC(5,2),
    signal_adherence_score INTEGER NOT NULL DEFAULT 0,

    signal_urgent_events_7d INTEGER NOT NULL DEFAULT 0,
    signal_urgent_events_score INTEGER NOT NULL DEFAULT 0,

    -- Tendência (delta vs cálculo anterior)
    trend TEXT CHECK (trend IS NULL OR trend IN ('improving', 'stable', 'worsening')),
    previous_score INTEGER,

    -- Detalhes pra UI mostrar (rationale)
    breakdown JSONB NOT NULL DEFAULT '{}'::JSONB,

    last_computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_tenant_level
    ON aia_health_patient_risk_score(tenant_id, risk_level);
CREATE INDEX IF NOT EXISTS idx_risk_high
    ON aia_health_patient_risk_score(score DESC)
    WHERE risk_level IN ('alto', 'critico');


-- Trigger updated_at
CREATE OR REPLACE FUNCTION _touch_patient_risk_score()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_risk_score ON aia_health_patient_risk_score;
CREATE TRIGGER trg_touch_risk_score
    BEFORE UPDATE ON aia_health_patient_risk_score
    FOR EACH ROW EXECUTE FUNCTION _touch_patient_risk_score();

COMMIT;
