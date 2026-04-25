-- ConnectaIACare — Anlodipino + interação sinvastatina (FDA 2011)
-- Data: 2026-04-25
--
-- Anlodipino (BCCa di-hidropiridínico) é um anti-hipertensivo MUITO usado
-- em geriatria. Ainda não estava no catálogo. Além de adicionar:
--
-- INTERAÇÃO MAJOR: Anlodipino inibe CYP3A4 → eleva nível de sinvastatina
-- → risco MIOPATIA / RABDOMIÓLISE.
-- FDA 2011 limitou sinvastatina a 20mg/dia quando combinada com anlodipino.
-- Lexicomp: severity major.

BEGIN;

-- =====================================================
-- 1. Anlodipino + outros BCCa di-hidropiridínicos
-- =====================================================
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, source, source_ref, confidence, notes)
VALUES
    ('anlodipino', 'oral', 10, 'mg', 'ccb_dihidropiridinico',
     'anvisa',
     'Bulário ANVISA: 5-10mg 1×/dia.',
     0.95,
     'Idoso: iniciar 2.5mg. Edema dose-dependente.'),
    ('nifedipino', 'oral', 60, 'mg', 'ccb_dihidropiridinico',
     'anvisa',
     'Bulário: liberação prolongada até 60mg/dia.',
     0.9,
     'Beers: nifedipino IR (não-prolongada) está entre os medicamentos a evitar em idoso (queda PA súbita)'),
    ('felodipino', 'oral', 10, 'mg', 'ccb_dihidropiridinico',
     'anvisa', 'Bulário: 2.5-10mg 1×/dia.', 0.9, NULL),
    ('lercanidipino', 'oral', 20, 'mg', 'ccb_dihidropiridinico',
     'anvisa', 'Bulário: 10-20mg 1×/dia.', 0.9, NULL)
ON CONFLICT (principle_active, route, age_group_min) DO NOTHING;

-- Aliases brasileiros
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type) VALUES
    ('Norvasc', 'anlodipino', 'brand'),
    ('Pressat', 'anlodipino', 'brand'),
    ('Naxpil', 'anlodipino', 'brand'),
    ('Anlo', 'anlodipino', 'misspelling'),
    ('Amlodipina', 'anlodipino', 'synonym'),
    ('Adalat', 'nifedipino', 'brand'),
    ('Adalat Oros', 'nifedipino', 'brand'),
    ('Adalat Retard', 'nifedipino', 'brand'),
    ('Splendil', 'felodipino', 'brand'),
    ('Zanidip', 'lercanidipino', 'brand')
ON CONFLICT (lower(alias)) DO NOTHING;

-- =====================================================
-- 2. INTERAÇÃO: Sinvastatina × Anlodipino (FDA major)
-- =====================================================
-- Lex-ordering: anlodipino (a) < sinvastatina (s)
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, source_ref, confidence)
VALUES
    ('anlodipino', 'sinvastatina', 'major',
     'CYP3A4 inhibition → ↑ simvastatin levels',
     'Anlodipino inibe CYP3A4 fracamente, aumentando concentração de sinvastatina e risco de miopatia/rabdomiólise — especialmente em idoso e doses altas.',
     'FDA 2011: limitar sinvastatina a 20mg/dia quando combinada com anlodipino. Considerar trocar por atorvastatina, pravastatina ou rosuvastatina (sem essa interação).',
     'fda', 'FDA Drug Safety Communication 2011-06-08', 0.97);

-- Outras estatinas com anlodipino (mais seguras, registradas pra contexto)
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('anlodipino', 'atorvastatina', 'minor',
     'CYP3A4 weak inhibition',
     'Anlodipino inibe CYP3A4; aumento mínimo da exposição à atorvastatina.',
     'Sem ajuste necessário em doses convencionais. Monitorar mialgia.',
     'lexicomp', 0.8);

-- =====================================================
-- 3. Outras interações relevantes do anlodipino
-- =====================================================
-- Anlodipino + β-bloq: bloqueio cardíaco (efeito somado bradicardia)
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('anlodipino', 'betabloqueador_cardiosseletivo', 'minor',
     'Additive negative inotropy',
     'Anlodipino + β-bloq cardiosseletivo: efeito anti-hipertensivo somado, inotropismo negativo somado.',
     'Combinação aceita em hipertensão refratária. Monitorar PA + edema.',
     'lexicomp', 0.85);

-- =====================================================
-- 4. Vital constraints — anlodipino + PA baixa
-- =====================================================
INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('ccb_dihidropiridinico', 'bp_systolic', 'lt', 110,
     'warning_strong',
     'PA <110 + BCCa di-hidropiridínico (anlodipino, nifedipino): hipotensão sintomática, queda, IRA.',
     'Adiar dose. Reavaliar PA. Considerar redução.',
     'manual');

-- =====================================================
-- 5. Fall risk — BCCa
-- =====================================================
INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('ccb_dihidropiridinico', 1,
     'BCCa di-hidropiridínico: hipotensão postural + tontura — risco queda em idoso');

-- =====================================================
-- 6. Renal adjustment
-- =====================================================
INSERT INTO aia_health_drug_renal_adjustments
    (principle_active, clcr_min, clcr_max, action, rationale, source)
VALUES
    ('anlodipino', 0, 999, 'no_adjustment',
     'Anlodipino: sem ajuste renal (metabolismo hepático).', 'manual');

-- =====================================================
-- 7. Anticholinergic burden
-- =====================================================
INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes) VALUES
    ('anlodipino', 0, NULL),
    ('nifedipino', 0, NULL),
    ('felodipino', 0, NULL),
    ('lercanidipino', 0, NULL)
ON CONFLICT (principle_active) DO NOTHING;

-- =====================================================
-- 8. Beers — nifedipino IR (não-prolongada) deve ser evitado em idoso
-- =====================================================
-- Atualizamos nifedipino genérico pra alertar Beers; quando vier
-- distinção IR vs ER, refinaremos.
UPDATE aia_health_drug_dose_limits
SET beers_avoid = TRUE,
    beers_rationale = 'Nifedipino de liberação imediata: hipotensão súbita e isquemia em idoso. Beers 2023 — Strong avoid. Preferir liberação prolongada ou outro BCCa.'
WHERE principle_active = 'nifedipino';

COMMIT;
