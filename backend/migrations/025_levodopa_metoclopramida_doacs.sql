-- ConnectaIACare — Levodopa/carbidopa + Metoclopramida + DOACs
-- Data: 2026-04-25
--
-- 3 medicamentos prevalentes em geriatria que precisam de cobertura
-- determinística:
--   1. Levodopa/carbidopa (anti-parkinsoniano dopaminérgico)
--   2. Metoclopramida (Beers AVOID — discinesia tardia)
--   3. Rivaroxabana + Apixabana (DOACs — alternativa moderna à varfarina)
--
-- Cada um é mapeado nas dimensões aplicáveis: dose máxima, Beers, classe
-- terapêutica, NTI, interações, contraindicações por condição, ajuste
-- renal, fall risk, anticholinergic burden, vitais.

BEGIN;

-- =====================================================
-- 1. dose_limits — adições
-- =====================================================
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, beers_avoid, beers_rationale,
     source, source_ref, confidence, notes)
VALUES
    -- LEVODOPA (geralmente em combinação com carbidopa ou benserazida)
    ('levodopa', 'oral', 800, 'mg', 'antiparkinsoniano_dopaminergico',
     FALSE, NULL,
     'anvisa', 'Bulário ANVISA — Sinemet/Prolopa: 300-800mg/dia divididos. Doses até 2g/dia em Parkinson avançado individualizadas.',
     0.9,
     'Idoso: iniciar 100mg 3×/dia. Hipotensão postural + alucinações + freezing/dyskinesias.'),

    -- METOCLOPRAMIDA (Beers AVOID — discinesia tardia)
    ('metoclopramida', 'oral', 30, 'mg', 'procinetico_d2',
     TRUE,
     'Beers 2023: antagonista dopaminérgico — risco discinesia tardia (frequentemente IRREVERSÍVEL em idoso), parkinsonismo, distonia, sedação. FDA limita a uso ≤5 dias.',
     'beers_2023', 'Beers 2023 — Strong avoid > 12 sem',
     0.97,
     'Doses ≤5 dias. Reduzir 50% se ClCr <40.'),

    -- RIVAROXABANA (DOAC anti-Xa)
    ('rivaroxabana', 'oral', 20, 'mg', 'anticoagulante_doac',
     FALSE, NULL,
     'anvisa', 'Bulário Xarelto: FA não-valvar 20mg 1×/dia (15mg se ClCr 15-50). TVP/EP tratamento 30mg/dia primeiros 21d, depois 20mg.',
     0.95,
     'Tomar com alimento (absorção). Reduzir pra 15mg/dia se ClCr 15-50.'),

    -- APIXABANA (DOAC anti-Xa)
    ('apixabana', 'oral', 10, 'mg', 'anticoagulante_doac',
     FALSE, NULL,
     'anvisa', 'Bulário Eliquis: FA 5mg 2×/dia. Reduzir pra 2.5mg 2× se ≥2 dos 3: idade ≥80, peso ≤60kg, Cr ≥1.5 mg/dL.',
     0.95,
     'Mais seguro que varfarina em idoso. Sem necessidade INR.')
ON CONFLICT (principle_active, route, age_group_min) DO NOTHING;

-- =====================================================
-- 2. drug_aliases (marcas brasileiras)
-- =====================================================
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type, notes) VALUES
    -- Levodopa
    ('Prolopa', 'levodopa', 'brand', 'Levodopa + benserazida'),
    ('Sinemet', 'levodopa', 'brand', 'Levodopa + carbidopa'),
    ('Cronomet', 'levodopa', 'brand', 'Levodopa + carbidopa LP'),
    ('Sifrol', 'levodopa', 'misspelling', 'Atenção: Sifrol é pramipexol, não levodopa — confirmar'),
    ('Stalevo', 'levodopa', 'brand', 'Levodopa + carbidopa + entacapona'),
    ('L-Dopa', 'levodopa', 'synonym', NULL),
    ('Levodopa carbidopa', 'levodopa', 'synonym', NULL),

    -- Metoclopramida
    ('Plasil', 'metoclopramida', 'brand', NULL),
    ('Eucil', 'metoclopramida', 'brand', NULL),
    ('Metoclopra', 'metoclopramida', 'misspelling', NULL),

    -- Rivaroxabana
    ('Xarelto', 'rivaroxabana', 'brand', NULL),
    ('Rivaroxaban', 'rivaroxabana', 'synonym', 'Grafia em inglês'),

    -- Apixabana
    ('Eliquis', 'apixabana', 'brand', NULL),
    ('Apixaban', 'apixabana', 'synonym', 'Grafia em inglês')
ON CONFLICT (lower(alias)) DO NOTHING;

-- =====================================================
-- 3. drug_interactions (pares novos)
-- =====================================================

-- ── LEVODOPA + ANTAGONISTAS DOPAMINÉRGICOS = bloqueio do efeito ──
-- Metoclopramida e antipsicóticos típicos bloqueiam D2, anulando levodopa.
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('levodopa', 'metoclopramida', 'major',
     'Dopamine D2 antagonism → levodopa effect blocked',
     'Metoclopramida bloqueia D2 — anula efeito antiparkinsoniano da levodopa + risco síndrome extrapiramidal somada.',
     'NÃO associar. Trocar metoclopramida por ondansetrona (5HT3) ou domperidona (não cruza BHE).',
     'lexicomp', 0.97);

INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('levodopa', 'procinetico_d2', 'major',
     'Dopamine D2 antagonism',
     'Procinético D2-antagonista anula efeito da levodopa.',
     'Não associar. Trocar antiemético/procinético.',
     'lexicomp', 0.95);

-- ── METOCLOPRAMIDA + OPIOIDE / BZD = sedação somada ──
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('metoclopramida', 'opioide', 'moderate',
     'Additive sedation + extrapyramidal',
     'Metoclopramida + opioide: sedação somada + risco SEP potencializado.',
     'Avaliar real necessidade. Doses mínimas.',
     'lexicomp', 0.85),
    ('metoclopramida', 'bzd', 'moderate',
     'Additive sedation',
     'Metoclopramida + BZD em idoso: sedação somada + risco SEP.',
     'Evitar combinação em idoso.',
     'lexicomp', 0.85);

-- ── DOACs + ANTIAGREGANTE / AINE = SANGRAMENTO ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('acido acetilsalicilico', 'rivaroxabana', 'major',
     'Bleeding risk',
     'AAS + rivaroxabana: risco hemorrágico maior. Use somente se SCA recente ou stent.',
     'Reavaliar real indicação dupla. Se inevitável, IBP profilático e duração curta.',
     'beers_2023', 0.95),
    ('acido acetilsalicilico', 'apixabana', 'major',
     'Bleeding risk',
     'AAS + apixabana: risco hemorrágico maior.',
     'Avaliar dupla terapia em SCA/stent. IBP profilático.',
     'beers_2023', 0.95),
    ('clopidogrel', 'rivaroxabana', 'major',
     'Bleeding risk',
     'Clopidogrel + rivaroxabana: sangramento aumentado.',
     'Reavaliar dupla. Se necessária pós-stent: duração curta + IBP.',
     'beers_2023', 0.95),
    ('clopidogrel', 'apixabana', 'major',
     'Bleeding risk',
     'Clopidogrel + apixabana: sangramento aumentado.',
     'Reavaliar dupla.',
     'beers_2023', 0.95),
    -- DOAC + Varfarina = CONTRAINDICATED
    ('rivaroxabana', 'varfarina', 'contraindicated',
     'Excessive anticoagulation',
     'Varfarina + DOAC simultâneos: anticoagulação excessiva, risco hemorrágico extremo.',
     'NÃO associar. Pra transição varfarina→DOAC: parar varfarina, monitorar INR e iniciar DOAC quando INR <2.',
     'lexicomp', 0.99),
    ('apixabana', 'varfarina', 'contraindicated',
     'Excessive anticoagulation',
     'Varfarina + DOAC simultâneos: NÃO associar.',
     'Mesma regra de transição que rivaroxabana.',
     'lexicomp', 0.99),
    -- DOAC + DOAC duplicidade
    ('apixabana', 'rivaroxabana', 'contraindicated',
     'Duplicate anticoagulation',
     'Dois DOACs simultâneos: anticoagulação excessiva.',
     'Suspender um.',
     'manual', 0.99);

-- DOAC + AINE/SSRI/corticoide = sangramento (via classe)
INSERT INTO aia_health_drug_interactions
    (principle_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('rivaroxabana', 'analgesico_aine', 'major',
     'GI bleeding',
     'AINE + rivaroxabana: risco sangramento GI.',
     'Não associar. Paracetamol pra dor.',
     'beers_2023', 0.95),
    ('apixabana', 'analgesico_aine', 'major',
     'GI bleeding',
     'AINE + apixabana: risco sangramento GI.',
     'Não associar. Paracetamol pra dor.',
     'beers_2023', 0.95),
    ('rivaroxabana', 'ssri', 'moderate',
     'GI bleeding',
     'SSRI + DOAC: risco GI moderado.',
     'IBP profilático se uso prolongado.',
     'beers_2023', 0.85),
    ('apixabana', 'ssri', 'moderate',
     'GI bleeding',
     'SSRI + DOAC: risco GI.',
     'IBP profilático.',
     'beers_2023', 0.85),
    ('rivaroxabana', 'corticoide', 'moderate',
     'GI bleeding',
     'Corticoide + DOAC: risco úlcera/sangra.',
     'IBP profilático obrigatório se uso prolongado.',
     'lexicomp', 0.85),
    ('apixabana', 'corticoide', 'moderate',
     'GI bleeding',
     'Corticoide + DOAC: risco GI.',
     'IBP profilático.',
     'lexicomp', 0.85);

-- =====================================================
-- 4. condition_contraindications
-- =====================================================

-- METOCLOPRAMIDA × Parkinson (CONTRAIND), demência (warning)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_principle_active,
     severity, rationale, recommendation, source, confidence) VALUES
    ('parkinson', 'G20', 'metoclopramida', 'contraindicated',
     'Metoclopramida bloqueia D2 — agrava parkinsonismo, anula L-dopa.',
     'NÃO usar. Trocar por ondansetrona ou domperidona.',
     'beers_2023', 0.99);

INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_principle_active,
     severity, rationale, recommendation, source, confidence) VALUES
    ('demencia', 'metoclopramida', 'warning',
     'Metoclopramida em demência: risco delirium + SEP.',
     'Evitar uso prolongado. Doses mínimas + ≤5 dias.',
     'beers_2023', 0.9);

-- LEVODOPA × Glaucoma ângulo fechado / psicose
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_principle_active,
     severity, rationale, recommendation, source, confidence) VALUES
    ('glaucoma', 'levodopa', 'warning',
     'Levodopa pode aumentar PIO em glaucoma de ângulo fechado.',
     'Avaliar tipo de glaucoma. Em ângulo fechado, evitar.',
     'manual', 0.85);

-- DOAC × sangramento GI / DRC severa
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class,
     severity, rationale, recommendation, source, confidence) VALUES
    ('sangramento_gi', 'anticoagulante_doac', 'caution',
     'DOAC em sangramento GI prévio: avaliar risco/benefício.',
     'Discutir multidisciplinar. IBP profilático.',
     'manual', 0.85),
    ('doenca renal cronica', 'anticoagulante_doac', 'caution',
     'DOACs em DRC: ajuste de dose obrigatório por ClCr.',
     'Apixabana mais segura em DRC moderada. Rivaroxabana <30 reduz; <15 evitar.',
     'kdigo', 0.92);

-- =====================================================
-- 5. drug_renal_adjustments
-- =====================================================
INSERT INTO aia_health_drug_renal_adjustments
    (principle_active, clcr_min, clcr_max, action, rationale, source) VALUES
    -- Metoclopramida
    ('metoclopramida', 0, 40, 'reduce_50pct',
     'ClCr <40: reduzir dose 50% (excreção renal).',
     'lexicomp'),
    ('metoclopramida', 40, 999, 'no_adjustment',
     'ClCr ≥40: dose padrão.', 'lexicomp'),

    -- Rivaroxabana
    ('rivaroxabana', 0, 15, 'avoid',
     'ClCr <15: contraindicado (acúmulo).',
     'kdigo'),
    ('rivaroxabana', 15, 50, 'reduce_50pct',
     'ClCr 15-50 em FA: reduzir pra 15mg/dia.',
     'kdigo'),
    ('rivaroxabana', 50, 999, 'no_adjustment',
     'ClCr ≥50: dose padrão 20mg/dia.',
     'kdigo'),

    -- Apixabana
    ('apixabana', 0, 15, 'avoid',
     'ClCr <15: contraindicado salvo dialisado em uso muito específico.',
     'kdigo'),
    ('apixabana', 15, 30, 'reduce_50pct',
     'ClCr 15-30: 2.5mg 2× (FA).',
     'kdigo'),
    ('apixabana', 30, 999, 'no_adjustment',
     'Critérios de redução: idade ≥80 OU peso ≤60kg OU Cr ≥1.5. Se ≥2 → 2.5mg 2×.',
     'manual'),

    -- Levodopa
    ('levodopa', 0, 30, 'reduce_50pct',
     'ClCr <30: reduzir dose 50% pelo aumento risco confusão/alucinação.',
     'manual'),
    ('levodopa', 30, 999, 'no_adjustment', 'Sem ajuste.', 'manual')
ON CONFLICT DO NOTHING;

-- =====================================================
-- 6. drug_vital_constraints
-- =====================================================
INSERT INTO aia_health_drug_vital_constraints
    (principle_active, vital_field, operator, threshold,
     severity, rationale, recommendation, source) VALUES
    ('levodopa', 'bp_systolic', 'lt', 100,
     'warning_strong',
     'PA <100 + levodopa: hipotensão postural (efeito comum).',
     'Adiar dose. Avaliar volemia. Ajustar dose se persistir.', 'manual'),
    ('metoclopramida', 'oxygen_saturation', 'lt', 92,
     'warning',
     'SatO2 <92% + metoclopramida: sedação somada.',
     'Reavaliar necessidade.', 'manual');

-- =====================================================
-- 7. drug_fall_risk
-- =====================================================
INSERT INTO aia_health_drug_fall_risk
    (principle_active, fall_risk_score, rationale) VALUES
    ('levodopa', 2,
     'Hipotensão postural + freezing + discinesias — risco queda alto'),
    ('metoclopramida', 2,
     'Sedação + parkinsonismo iatrogênico + hipotensão — risco queda');

INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale) VALUES
    ('anticoagulante_doac', 1,
     'DOAC: sangra após queda — não aumenta risco da queda em si mas eleva consequências');

-- =====================================================
-- 8. anticholinergic_burden
-- =====================================================
INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes) VALUES
    ('levodopa', 0, NULL),
    ('metoclopramida', 1, 'Efeito anticolinérgico leve + central'),
    ('rivaroxabana', 0, NULL),
    ('apixabana', 0, NULL)
ON CONFLICT (principle_active) DO NOTHING;

COMMIT;
