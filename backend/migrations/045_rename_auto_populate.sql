-- ConnectaIACare — Auto-populate Tier Verde + Tier Amarelo pros 30 gaps
-- prioritários do RENAME 2024.
--
-- ESCOPO:
-- - Tier Verde: nome canônico, classe terapêutica, dose máxima adulto,
--   forma farmacêutica, indicação SUS, flag in_rename
-- - Tier Amarelo: Beers AVOID/CAUTION em condição (via condition_contraindications),
--   ACB Score (Boustani), Fall Risk Score (por classe terapêutica)
-- - Tier Vermelho NÃO incluído: interações pareadas específicas,
--   contraindicações por condição clínica detalhadas, ajuste renal/hepático
--   por faixa, cascatas — ficam pra curador sênior.
--
-- DISCLAIMER OPERACIONAL:
-- Toda saída clínica vinda destas linhas terá disclaimer reforçado da
-- Sofia: "Esta informação foi gerada automaticamente e está em revisão
-- clínica — confirme com seu médico ou farmacêutico."
--
-- FONTE DOS DADOS:
-- RENAME 2024 (Portaria GM/MS Nº 4.876) + ANVISA Bulário Eletrônico +
-- AGS Beers 2023 + Boustani Anticholinergic Burden Scale + STOPP 2023
-- (fall risk).

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- DOSE LIMITS — Tier Verde (auto + flag review_status='auto_pending')
-- ════════════════════════════════════════════════════════════════

-- DIURÉTICOS
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('hidroclorotiazida', 'oral', 50, 'mg', 'diuretico_tiazidico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('furosemida', 'oral', 600, 'mg', 'diuretico_alca', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('espironolactona', 'oral', 400, 'mg', 'diuretico_poupador_potassio', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('indapamida', 'oral', 5, 'mg', 'diuretico_tiazidico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- BCCa NÃO-DHP
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('verapamil', 'oral', 480, 'mg', 'ccb_nao_dihidropiridinico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('diltiazem', 'oral', 360, 'mg', 'ccb_nao_dihidropiridinico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- INIBIDORES DE COLINESTERASE + MEMANTINA (demência)
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('donepezila', 'oral', 23, 'mg', 'inibidor_colinesterase', 65, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('rivastigmina', 'oral', 12, 'mg', 'inibidor_colinesterase', 65, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('galantamina', 'oral', 24, 'mg', 'inibidor_colinesterase', 65, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('memantina', 'oral', 20, 'mg', 'demencia_nmda', 65, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- CORTICOIDES SISTÊMICOS
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('prednisona', 'oral', 80, 'mg', 'corticoide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('prednisolona', 'oral', 80, 'mg', 'corticoide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('dexametasona', 'oral', 40, 'mg', 'corticoide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('hidrocortisona', 'oral', 400, 'mg', 'corticoide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ANTICONVULSIVANTES / DOR NEUROPÁTICA
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('carbamazepina', 'oral', 1200, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('valproato_sodico', 'oral', 3000, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('fenitoina', 'oral', 600, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('gabapentina', 'oral', 3600, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- BRONCODILATADORES INALATÓRIOS
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('salbutamol', 'inalatoria', 1600, 'mcg', 'beta2_agonista_curta', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('formoterol', 'inalatoria', 24, 'mcg', 'beta2_agonista_longa_laba', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('budesonida', 'inalatoria', 1600, 'mcg', 'corticoide_inalatorio', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('ipratropio', 'inalatoria', 240, 'mcg', 'anticolinergico_curta_sama', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('tiotropio', 'inalatoria', 18, 'mcg', 'anticolinergico_longa_lama', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ANTIDEPRESSIVOS TRICÍCLICOS
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('amitriptilina', 'oral', 150, 'mg', 'antidepressivo_triciclico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('nortriptilina', 'oral', 150, 'mg', 'antidepressivo_triciclico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- INSULINAS (placeholder conservador — schema dose por kg/glicemia)
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('insulina_nph', 'subcutanea', 200, 'UI', 'insulina_basal', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose deve ser calculada por kg/glicemia. Dose máxima é placeholder conservador.'),
('insulina_regular', 'subcutanea', 200, 'UI', 'insulina_rapida', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose deve ser calculada por kg/glicemia.')
ON CONFLICT DO NOTHING;

-- OUTROS ESSENCIAIS GERIATRIA
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('biperideno', 'oral', 16, 'mg', 'anticolinergico_antiparkinsoniano', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('acido_folico', 'oral', 5, 'mg', 'vitamina', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('sulfato_ferroso', 'oral', 200, 'mg', 'mineral_ferro', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- BEERS / Contraindicações por condição (via aia_health_condition_contraindications)
-- Tier Amarelo — auto + flag review_status='auto_pending'
-- ════════════════════════════════════════════════════════════════

-- Antidepressivos tricíclicos — Beers AVOID em ≥65 (anticolinérgico forte)
INSERT INTO aia_health_condition_contraindications (
    condition_term, condition_icd10,
    affected_principle_active, affected_therapeutic_class,
    severity, rationale, recommendation, source, source_ref, confidence,
    auto_generated, review_status
) VALUES
('idoso ≥65', NULL, 'amitriptilina', NULL,
 'contraindicated',
 'Anticolinérgico forte (ACB 3); Beers 2023 AVOID em ≥65 — risco confusão, queda, retenção urinária',
 'Substituir por nortriptilina (menos anticolinérgico) ou ISRS pra depressão',
 'beers_2023', 'AGS Beers 2023', 0.85,
 TRUE, 'auto_pending'),
('demência', 'F00-F03', 'biperideno', NULL,
 'contraindicated',
 'Anticolinérgico forte; Beers 2023 AVOID em demência por agravar declínio cognitivo',
 'Reavaliar necessidade do biperideno; considerar ajuste do antipsicótico que causou parkinsonismo',
 'beers_2023', 'AGS Beers 2023', 0.85,
 TRUE, 'auto_pending'),
('insuficiência cardíaca sistólica', 'I50', 'verapamil', NULL,
 'contraindicated',
 'Inotrópico negativo; AVOID em ICFEr — risco de descompensação cardíaca',
 'Em ICFEr usar betabloqueador + IECA/BRA. Verapamil só em IC de FE preservada',
 'beers_2023', 'AGS Beers 2023', 0.90,
 TRUE, 'auto_pending'),
('insuficiência cardíaca sistólica', 'I50', 'diltiazem', NULL,
 'contraindicated',
 'Inotrópico negativo; AVOID em ICFEr',
 'Em ICFEr usar betabloqueador + IECA/BRA',
 'beers_2023', 'AGS Beers 2023', 0.90,
 TRUE, 'auto_pending'),
('idoso ≥65', NULL, 'fenitoina', NULL,
 'caution',
 'Janela terapêutica estreita; Beers 2023 Caution em ≥65 — risco neurotoxicidade',
 'Considerar gabapentina ou lamotrigina como alternativa',
 'beers_2023', 'AGS Beers 2023', 0.80,
 TRUE, 'auto_pending'),
('IRC com ClCr<30', 'N18', 'espironolactona', NULL,
 'caution',
 'Risco hipercalemia, especialmente combinado com IECA/BRA',
 'Monitor K+ rigoroso; reduzir dose se ClCr<30; AVOID se ClCr<10',
 'kdigo', 'KDIGO 2024', 0.85,
 TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- ACB SCORE (escala Boustani) — Tier Amarelo
-- Coluna: burden_score (não acb_score como tentei antes)
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes, source,
     auto_generated, review_status)
VALUES
('amitriptilina', 3, 'Tricíclico — alto efeito anticolinérgico (Boustani 2008)', 'acb_scale',
 TRUE, 'auto_pending'),
('nortriptilina', 1, 'Tricíclico — preferida vs amitriptilina (menor anticolinérgico)', 'acb_scale',
 TRUE, 'auto_pending'),
('biperideno', 3, 'Anticolinérgico antiparkinsoniano — alto efeito central', 'acb_scale',
 TRUE, 'auto_pending'),
('ipratropio', 1, 'Anticolinérgico inalatório — biodisponibilidade sistêmica baixa mas conta no cumulativo', 'acb_scale',
 TRUE, 'auto_pending'),
('tiotropio', 1, 'Anticolinérgico longa ação — biodisponibilidade sistêmica baixa mas conta', 'acb_scale',
 TRUE, 'auto_pending'),
('fenitoina', 1, 'Efeito anticolinérgico discreto', 'acb_scale',
 TRUE, 'auto_pending'),
('carbamazepina', 1, 'Efeito anticolinérgico discreto', 'acb_scale',
 TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- FALL RISK SCORE — por classe terapêutica
-- Schema: principle_active OR therapeutic_class
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale, source,
     auto_generated, review_status)
VALUES
('diuretico_tiazidico', 1,
 'Hipotensão postural · hipocalemia · poliúria',
 'stopp_2023', TRUE, 'auto_pending'),
('diuretico_alca', 2,
 'Hipotensão postural · poliúria intensa · hipocalemia',
 'stopp_2023', TRUE, 'auto_pending'),
('diuretico_poupador_potassio', 1,
 'Hipotensão postural moderada',
 'stopp_2023', TRUE, 'auto_pending'),
('ccb_nao_dihidropiridinico', 1,
 'Bradicardia · hipotensão',
 'stopp_2023', TRUE, 'auto_pending'),
('inibidor_colinesterase', 1,
 'Bradicardia · síncope vasovagal',
 'stopp_2023', TRUE, 'auto_pending'),
('antidepressivo_triciclico', 2,
 'Hipotensão postural · sedação · efeito anticolinérgico',
 'stopp_2023', TRUE, 'auto_pending'),
('anticonvulsivante', 1,
 'Sedação · ataxia · alteração do equilíbrio',
 'stopp_2023', TRUE, 'auto_pending'),
('insulina_basal', 1,
 'Hipoglicemia → confusão e queda',
 'stopp_2023', TRUE, 'auto_pending'),
('insulina_rapida', 1,
 'Hipoglicemia pós-prandial',
 'stopp_2023', TRUE, 'auto_pending'),
('corticoide', 1,
 'Miopatia proximal · osteoporose (fratura se cair)',
 'stopp_2023', TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- Atualiza tracker: fármacos que receberam auto-populate viram
-- 'in_progress' (codificação técnica feita, aguardando review clínico)
-- ════════════════════════════════════════════════════════════════
UPDATE aia_health_rename_drugs
SET motor_coverage = 'in_progress',
    last_reviewed_at = NOW(),
    last_reviewed_by = 'auto_populate_v1',
    notes_curador = 'Tier Verde (dose, classe, RENAME meta) + Tier Amarelo '
                    '(Beers, ACB, fall risk conservador) auto-gerados. '
                    'Tier Vermelho (interações, contraindicações específicas, '
                    'cascatas, ajuste renal/hepático detalhado) ficam pra '
                    'curador clínico sênior.'
WHERE motor_coverage = 'pending'
  AND principle_active IN (
    'hidroclorotiazida', 'furosemida', 'espironolactona',
    'insulina_nph', 'insulina_regular',
    'prednisona', 'prednisolona', 'dexametasona', 'hidrocortisona',
    'verapamil', 'diltiazem',
    'donepezila', 'rivastigmina', 'galantamina', 'memantina',
    'carbamazepina', 'valproato_sodico', 'fenitoina', 'gabapentina',
    'salbutamol', 'formoterol', 'budesonida', 'ipratropio', 'tiotropio',
    'amitriptilina', 'nortriptilina',
    'biperideno',
    'acido_folico', 'sulfato_ferroso'
  );


COMMIT;
