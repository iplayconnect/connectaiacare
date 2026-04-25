-- ConnectaIACare — Refinamento clínico β-bloqueadores
-- Data: 2026-04-25
--
-- Razão: agrupar todos β-bloq em "betabloqueador" é tecnicamente errado.
-- Propranolol (β-NÃO-seletivo) é CONTRAINDICADO ABSOLUTO em asma.
-- Atenolol/metoprolol (β1-cardiosseletivos) têm risco menor — caution.
-- Refinamento separa as 2 classes e atualiza regras downstream.
--
-- Adiciona também Propranolol e outros β-NÃO-seletivos no catálogo.

BEGIN;

-- =====================================================
-- 1. Adicionar Propranolol + outros β-bloq não-seletivos
-- =====================================================
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, source, source_ref, confidence, notes)
VALUES
    ('propranolol', 'oral', 320, 'mg', 'betabloqueador_nao_seletivo',
     'anvisa',
     'Bulário ANVISA: dose máxima 320mg/dia divididos.',
     0.95,
     'β-NÃO-seletivo: contraindicado em asma. Idoso: iniciar 10mg 2-3×/dia.'),
    ('nadolol', 'oral', 320, 'mg', 'betabloqueador_nao_seletivo',
     'anvisa',
     'Dose máxima 320mg/dia.', 0.9, 'β-NÃO-seletivo'),
    ('sotalol', 'oral', 320, 'mg', 'betabloqueador_nao_seletivo',
     'anvisa',
     'Antiarrítmico classe III + β-NÃO-seletivo.', 0.9,
     'Risco torsades de pointes — monitorar QTc')
ON CONFLICT (principle_active, route, age_group_min) DO NOTHING;

-- Aliases brasileiros
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type) VALUES
    ('Inderal', 'propranolol', 'brand'),
    ('Inderalici', 'propranolol', 'brand'),
    ('Pranolol', 'propranolol', 'brand'),
    ('Propra', 'propranolol', 'misspelling'),
    ('Sotalex', 'sotalol', 'brand')
ON CONFLICT (lower(alias)) DO NOTHING;

-- =====================================================
-- 2. Reclassificar β-bloq cardiosseletivos
-- =====================================================
-- atenolol e metoprolol já estavam como "betabloqueador" — refino pra
-- "betabloqueador_cardiosseletivo" pra deixar a distinção clara nos logs.
UPDATE aia_health_drug_dose_limits
SET therapeutic_class = 'betabloqueador_cardiosseletivo'
WHERE principle_active IN ('atenolol', 'metoprolol')
  AND therapeutic_class = 'betabloqueador';

-- =====================================================
-- 3. Atualizar condition_contraindications
-- =====================================================
-- Remove regra antiga genérica (asma + class "betabloqueador") porque
-- agora as 2 classes são distintas.
DELETE FROM aia_health_condition_contraindications
WHERE condition_term = 'asma'
  AND affected_therapeutic_class = 'betabloqueador';

DELETE FROM aia_health_condition_contraindications
WHERE condition_term = 'dpoc'
  AND affected_therapeutic_class = 'betabloqueador';

-- Insere regras precisas:
-- ASMA + β-NÃO-seletivo = CONTRAINDICAÇÃO ABSOLUTA
-- ASMA + β1-cardiosseletivo = CAUTION (uso com avaliação)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class,
     severity, rationale, recommendation, source, confidence) VALUES
    ('asma', 'J45', 'betabloqueador_nao_seletivo', 'contraindicated',
     'β-bloqueador NÃO-seletivo (propranolol, nadolol, sotalol) bloqueia receptores β2 brônquicos → broncoespasmo grave. Contraindicação ABSOLUTA em asma.',
     'NÃO usar. Se bloqueio β imprescindível (ex: profilaxia enxaqueca), trocar por β1-cardiosseletivo (atenolol, metoprolol) com avaliação pneumológica.',
     'gina', 0.99),
    ('asma', 'J45', 'betabloqueador_cardiosseletivo', 'warning',
     'β1-cardiosseletivos (atenolol, metoprolol) em asma têm risco menor mas podem precipitar broncoespasmo, especialmente em doses altas ou asma instável.',
     'Usar com cautela: dose mínima eficaz, avaliar PFR antes/depois, iniciar com hospital próximo.',
     'gina', 0.9);

-- DPOC: β1-cardiosseletivo é OK em geral; β-não-seletivo evitar
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class,
     severity, rationale, recommendation, source, confidence) VALUES
    ('dpoc', 'J44', 'betabloqueador_nao_seletivo', 'warning',
     'β-NÃO-seletivo em DPOC: pode atenuar resposta a β2-agonista de resgate.',
     'Preferir β1-cardiosseletivo (atenolol, metoprolol).',
     'gold', 0.92),
    ('dpoc', 'J44', 'betabloqueador_cardiosseletivo', 'caution',
     'β1-cardiosseletivos em DPOC são geralmente seguros e podem ter benefício cardiovascular.',
     'Monitorar dispneia. PFR basal recomendada.',
     'gold', 0.85);

-- =====================================================
-- 4. Atualizar drug_interactions (digoxina+β-bloq)
-- =====================================================
-- A regra antiga: principle="digoxina" + class="betabloqueador" → moderate
-- Como mudamos a classe, vou recriar pra cobrir ambas
UPDATE aia_health_drug_interactions
SET class_b = 'betabloqueador_cardiosseletivo'
WHERE principle_a = 'digoxina' AND class_b = 'betabloqueador';

INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('digoxina', 'betabloqueador_nao_seletivo', 'moderate',
     'Bradycardia + AV block',
     'Digoxina + β-bloq não-seletivo: bradicardia + bloqueio AV.',
     'Monitorar FC e ECG. Reduzir dose se FC < 50.',
     'lexicomp', 0.88);

-- =====================================================
-- 5. Atualizar drug_vital_constraints (β-bloq + FC baixa)
-- =====================================================
-- Mesma lógica: regra antiga afetava class="betabloqueador". Atualizo
-- pra cobrir as 2 novas classes
UPDATE aia_health_drug_vital_constraints
SET therapeutic_class = 'betabloqueador_cardiosseletivo'
WHERE therapeutic_class = 'betabloqueador';

INSERT INTO aia_health_drug_vital_constraints
    (therapeutic_class, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('betabloqueador_nao_seletivo', 'heart_rate', 'lt', 55,
     'warning_strong',
     'FC <55 + β-bloq NÃO-seletivo: bradicardia + risco BAV.',
     'Adiar dose. ECG se FC <50 ou sintomática.', 'manual'),
    ('betabloqueador_nao_seletivo', 'bp_systolic', 'lt', 100,
     'warning_strong',
     'PA <100 + β-bloq NÃO-seletivo: hipotensão sintomática.',
     'Adiar dose. Reavaliar.', 'manual');

-- =====================================================
-- 6. Atualizar fall_risk (β-bloq + queda)
-- =====================================================
UPDATE aia_health_drug_fall_risk
SET therapeutic_class = 'betabloqueador_cardiosseletivo'
WHERE therapeutic_class = 'betabloqueador';

INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('betabloqueador_nao_seletivo', 1,
     'Bradicardia + hipotensão postural — risco queda em idoso');

-- =====================================================
-- 7. Atualizar anticholinergic_burden (propranolol)
-- =====================================================
INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes)
VALUES
    ('propranolol', 1, 'β-bloq central pode causar fadiga e leve confusão'),
    ('nadolol', 1, NULL),
    ('sotalol', 1, NULL)
ON CONFLICT (principle_active) DO NOTHING;

COMMIT;
