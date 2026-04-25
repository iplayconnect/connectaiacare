-- ConnectaIACare — F4: dose ajustada por função renal + cruzamento vitais
-- Data: 2026-04-25
--
-- Esta migration habilita 2 famílias de cruzamentos:
--   1. Dose vs função renal (ClCr Cockcroft-Gault):
--      • Adiciona campos creatinina/peso/altura no aia_health_patients
--      • Adiciona regras de ajuste renal por princípio ativo
--   2. Sinais vitais ↔ medicação:
--      • PA baixa + anti-hipertensivo
--      • FC<60 + β-bloqueador
--      • Glicemia baixa + sulfonilureia/insulina
--      • K+ alto + IECA/ARA
--      Reusa aia_health_vital_signs (migration 004) — só leitura.

BEGIN;

-- =====================================================
-- 1. Patients: campos pra calcular ClCr
-- =====================================================
ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS weight_kg NUMERIC(5,2),
    ADD COLUMN IF NOT EXISTS height_cm SMALLINT,
    ADD COLUMN IF NOT EXISTS serum_creatinine_mg_dl NUMERIC(4,2),
    ADD COLUMN IF NOT EXISTS serum_creatinine_measured_at TIMESTAMPTZ;

-- =====================================================
-- 2. aia_health_drug_renal_adjustments
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_drug_renal_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    principle_active TEXT NOT NULL,
    -- Faixa de ClCr (mL/min/1.73m²) onde a regra se aplica
    clcr_min INTEGER NOT NULL,        -- inclusive
    clcr_max INTEGER,                 -- exclusive (NULL = sem teto)
    -- Ação recomendada nessa faixa
    action TEXT NOT NULL CHECK (action IN (
        'avoid', 'reduce_50pct', 'reduce_75pct',
        'increase_interval', 'monitor', 'no_adjustment'
    )),
    rationale TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'kdigo',
    source_ref TEXT,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.9,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_renal_adj_principle
    ON aia_health_drug_renal_adjustments(principle_active, clcr_min)
    WHERE active = TRUE;

-- ── Seed regras renais Fase 1 ──
-- Metformina
INSERT INTO aia_health_drug_renal_adjustments
    (principle_active, clcr_min, clcr_max, action, rationale, source)
VALUES
    ('metformina', 0, 30, 'avoid',
     'Contraindicado se ClCr < 30 mL/min — risco acidose lática.', 'kdigo'),
    ('metformina', 30, 45, 'reduce_50pct',
     'ClCr 30-45: dose máxima 1g/dia, monitorar ClCr a cada 3 meses.', 'kdigo'),
    ('metformina', 45, NULL, 'no_adjustment',
     'ClCr ≥45: dose padrão.', 'kdigo'),

-- Digoxina
    ('digoxina', 0, 30, 'reduce_50pct',
     'ClCr <30: reduzir dose 50% (excreção renal predominante).', 'lexicomp'),
    ('digoxina', 30, 50, 'reduce_75pct',
     'ClCr 30-50: reduzir 25%.', 'lexicomp'),

-- Furosemida (paradoxo: precisa dose MAIOR em IRC, não menor)
    ('furosemida', 0, 30, 'monitor',
     'IRC: pode precisar dose mais alta. Monitorar resposta diurética + K+.', 'kdigo'),

-- Atenolol (renal)
    ('atenolol', 0, 30, 'reduce_50pct',
     'ClCr <30: reduzir dose 50% (excreção renal).', 'lexicomp'),
    ('atenolol', 30, 60, 'reduce_50pct',
     'ClCr 30-60: máximo 50mg/dia.', 'lexicomp'),

-- Enalapril/captopril (IECA — ajuste em IRC)
    ('enalapril', 0, 30, 'reduce_50pct',
     'ClCr <30: iniciar 2.5mg, monitorar K+ e creatinina.', 'kdigo'),
    ('captopril', 0, 30, 'reduce_50pct',
     'ClCr <30: ajustar dose, monitorar K+.', 'kdigo'),

-- AINEs (todos contraindicados em DRC mod-grave)
    ('ibuprofeno', 0, 60, 'avoid',
     'AINEs contraindicados se ClCr <60 — risco lesão renal aguda.', 'kdigo'),
    ('naproxeno', 0, 60, 'avoid',
     'AINEs contraindicados se ClCr <60.', 'kdigo'),
    ('diclofenaco', 0, 60, 'avoid',
     'AINEs contraindicados se ClCr <60.', 'kdigo'),
    ('cetoprofeno', 0, 60, 'avoid',
     'AINEs contraindicados se ClCr <60.', 'kdigo'),

-- Tramadol
    ('tramadol', 0, 30, 'increase_interval',
     'ClCr <30: intervalo 12h, máximo 200mg/dia.', 'lexicomp'),

-- Paracetamol em hepato/renal — sem ajuste renal típico
    ('paracetamol', 0, 999, 'no_adjustment',
     'Paracetamol: sem ajuste renal (metabolismo hepático).', 'manual'),

-- Sinvastatina, atorvastatina — sem ajuste renal usual
    ('sinvastatina', 0, 999, 'no_adjustment', 'Sem ajuste renal.', 'manual'),
    ('atorvastatina', 0, 999, 'no_adjustment', 'Sem ajuste renal.', 'manual');

-- =====================================================
-- 3. aia_health_drug_vital_constraints
-- =====================================================
-- Regras pra alertar quando vitais recentes contraindicam administrar
-- a medicação. Ex: PA<110 + anti-hipertensivo, FC<60 + β-bloqueador,
-- glicemia<70 + sulfonilureia, K+>5.5 + IECA/ARA.

CREATE TABLE IF NOT EXISTS aia_health_drug_vital_constraints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Match por principle OU class
    principle_active TEXT,
    therapeutic_class TEXT,
    -- Vital monitorado
    vital_field TEXT NOT NULL CHECK (vital_field IN (
        'bp_systolic', 'bp_diastolic', 'heart_rate',
        'glucose_mg_dl', 'oxygen_saturation', 'temperature_celsius',
        'potassium_meq_l'   -- requer cadastro labs futuro; placeholder
    )),
    -- Operador: lt|le|gt|ge
    operator TEXT NOT NULL CHECK (operator IN ('lt','le','gt','ge')),
    threshold NUMERIC(8,2) NOT NULL,
    -- Janela de tempo pra considerar leitura (minutos pra trás)
    window_minutes INTEGER NOT NULL DEFAULT 1440,  -- default 24h
    severity TEXT NOT NULL CHECK (severity IN ('block', 'warning_strong', 'warning')),
    rationale TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (principle_active IS NOT NULL OR therapeutic_class IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_vital_constraints_principle
    ON aia_health_drug_vital_constraints(principle_active)
    WHERE active = TRUE AND principle_active IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vital_constraints_class
    ON aia_health_drug_vital_constraints(therapeutic_class)
    WHERE active = TRUE AND therapeutic_class IS NOT NULL;

-- ── Seed regras vitais Fase 1 ──

-- PA baixa + anti-hipertensivo
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('ieca', 'bp_systolic', 'lt', 110,
     'warning_strong',
     'PA sistólica <110 mmHg + IECA: risco de hipotensão sintomática, queda, IRA.',
     'Adiar dose. Reavaliar PA. Considerar redução de dose se persistir.',
     'manual'),
    ('ara', 'bp_systolic', 'lt', 110,
     'warning_strong',
     'PA sistólica <110 + ARA: hipotensão sintomática + queda.',
     'Adiar dose. Reavaliar.', 'manual'),
    ('betabloqueador', 'bp_systolic', 'lt', 100,
     'warning_strong',
     'PA <100 + β-bloqueador: hipotensão.', 'Adiar dose. Reavaliar.', 'manual'),
    ('diuretico_tiazidico', 'bp_systolic', 'lt', 110,
     'warning',
     'PA <110 + tiazídico: avaliar suspensão temporária.',
     'Avaliar com médico. Não suspender unilateralmente em uso crônico.',
     'manual'),
    ('diuretico_alca', 'bp_systolic', 'lt', 100,
     'warning',
     'PA <100 + diurético de alça: risco hipotensão postural + IRA.',
     'Reavaliar volemia.', 'manual');

-- FC baixa + β-bloq / digoxina
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('betabloqueador', 'heart_rate', 'lt', 55,
     'warning_strong',
     'FC <55 + β-bloqueador: bradicardia sintomática, BAV.',
     'Adiar dose. ECG se FC <50 ou sintomática.', 'manual');

INSERT INTO aia_health_drug_vital_constraints
    (principle_active, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('digoxina', 'heart_rate', 'lt', 50,
     'warning_strong',
     'FC <50 + digoxina: risco bloqueio AV / toxicidade digital.',
     'Suspender. Verificar nível sérico digoxina.', 'manual');

-- Glicemia baixa + sulfonilureia/insulina
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('sulfonilureia', 'glucose_mg_dl', 'lt', 90,
     'warning_strong',
     'Glicemia <90 + sulfonilureia: risco hipoglicemia.',
     'Adiar dose. Considerar redução pela próxima.', 'manual'),
    ('biguanida', 'glucose_mg_dl', 'lt', 70,
     'warning',
     'Glicemia <70: hipoglicemia (raro com metformina, mas pode ocorrer com combinações).',
     'Avaliar refeição.', 'manual');

-- SatO2 baixa + opioide / BZD
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('opioide', 'oxygen_saturation', 'lt', 92,
     'warning_strong',
     'SatO2 <92% + opioide: risco depressão respiratória.',
     'Adiar dose. Naloxona disponível.', 'manual'),
    ('bzd', 'oxygen_saturation', 'lt', 92,
     'warning_strong',
     'SatO2 <92% + BZD: risco depressão respiratória.',
     'Adiar dose.', 'manual');

COMMIT;
