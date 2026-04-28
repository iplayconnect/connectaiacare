-- ConnectaIACare — Auto-populate batch 2: ~35 fármacos priorizados pelo
-- Henrique Bordin no checklist clínico de revisão.
--
-- Inclusão baseada em ⭐ (alta prioridade) na resposta do Henrique:
-- cardiovasculares (BRAs, betabloq cardiosseletivos, nitratos, antiarrítmicos),
-- antidiabéticos (insulinas, DPP-4, acarbose, antitireoidiano),
-- SNC (anticonvulsivantes, dor neuropática),
-- pneumo (LABAs, ICS, combinações fixas),
-- corticoide (metilprednisolona),
-- opioides + AINEs seletivos,
-- antialérgicos não-sedativos,
-- ósseo + vitaminas + procinéticos.
--
-- Tier Verde + Tier Amarelo (review_status='auto_pending').
-- Disclaimer reforçado da Sofia avisa "em revisão clínica".

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- DOSE LIMITS — Batch 2 (Henrique ⭐ priorizados)
-- ════════════════════════════════════════════════════════════════

-- ── Cardiovasculares adicionais ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('bisoprolol', 'oral', 20, 'mg', 'betabloqueador_cardiosseletivo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('nebivolol', 'oral', 40, 'mg', 'betabloqueador_cardiosseletivo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('olmesartana', 'oral', 40, 'mg', 'ara', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('telmisartana', 'oral', 80, 'mg', 'ara', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('valsartana', 'oral', 320, 'mg', 'ara', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('mononitrato_isossorbida', 'oral', 240, 'mg', 'nitrato', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('dinitrato_isossorbida', 'oral', 160, 'mg', 'nitrato', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('amiodarona', 'oral', 600, 'mg', 'antiarritmico_classe_iii', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('digoxina', 'oral', 0.25, 'mg', 'glicosideo_cardiaco', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── Antidiabéticos / endócrino adicionais ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('insulina_glargina', 'subcutanea', 200, 'UI', 'insulina_basal_longa', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose por kg/glicemia. Placeholder conservador.'),
('insulina_lispro', 'subcutanea', 200, 'UI', 'insulina_rapida_analoga', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose pré-prandial por carbohidrato.'),
('insulina_asparte', 'subcutanea', 200, 'UI', 'insulina_rapida_analoga', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose pré-prandial por carbohidrato.'),
('insulina_glulisina', 'subcutanea', 200, 'UI', 'insulina_rapida_analoga', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Schema customizado: dose pré-prandial por carbohidrato.'),
('sitagliptina', 'oral', 100, 'mg', 'dpp4_inibidor', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('acarbose', 'oral', 300, 'mg', 'inibidor_alfa_glicosidase', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('metimazol', 'oral', 60, 'mg', 'antitireoidiano', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── SNC: anticonvulsivantes / dor neuropática adicionais ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('pregabalina', 'oral', 600, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Múltiplo uso: epilepsia, dor neuropática, ansiedade generalizada'),
('lamotrigina', 'oral', 400, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Múltiplo uso: epilepsia, transtorno bipolar (estabilizador humor)'),
('topiramato', 'oral', 400, 'mg', 'anticonvulsivante', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Múltiplo uso: epilepsia, profilaxia enxaqueca, dor neuropática')
ON CONFLICT DO NOTHING;

-- ── Pneumo: LABAs adicionais + ICS + combinações fixas ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('salmeterol', 'inalatoria', 100, 'mcg', 'beta2_agonista_longa_laba', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('fluticasona', 'inalatoria', 1000, 'mcg', 'corticoide_inalatorio', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('beclometasona', 'inalatoria', 2000, 'mcg', 'corticoide_inalatorio', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('formoterol+budesonida', 'inalatoria', 24, 'mcg', 'broncodilatador_combinado_laba_ics', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('salmeterol+fluticasona', 'inalatoria', 100, 'mcg', 'broncodilatador_combinado_laba_ics', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── Corticoide adicional ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('metilprednisolona', 'oral', 60, 'mg', 'corticoide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── Opioides + AINEs seletivos ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('tramadol', 'oral', 400, 'mg', 'opioide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Cuidado: pode reduzir limiar convulsivo; risco de síndrome serotoninérgica com SSRI'),
('codeina', 'oral', 240, 'mg', 'opioide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Frequente em associação com paracetamol'),
('morfina', 'oral', 200, 'mg', 'opioide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Dose oral; em uso EV/SC dose menor. Em idoso titular cuidadosamente.'),
('oxicodona', 'oral', 80, 'mg', 'opioide', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('nimesulida', 'oral', 400, 'mg', 'aine_seletivo_cox2_parcial', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Hepatotoxicidade — ANVISA limita uso a 15 dias'),
('meloxicam', 'oral', 15, 'mg', 'aine_seletivo_cox2_parcial', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── Antialérgicos H1 ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto)
VALUES
('loratadina', 'oral', 10, 'mg', 'antihistaminico_h1_nao_sedativo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('desloratadina', 'oral', 5, 'mg', 'antihistaminico_h1_nao_sedativo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('fexofenadina', 'oral', 360, 'mg', 'antihistaminico_h1_nao_sedativo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('difenidramina', 'oral', 300, 'mg', 'antihistaminico_h1_sedativo', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto')
ON CONFLICT DO NOTHING;

-- ── Ósseo + Vitaminas + Procinéticos ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, age_group_min, source,
     auto_generated, review_status, source_auto, auto_review_notes)
VALUES
('risedronato', 'oral', 35, 'mg', 'bifosfonato', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Posologia comum: 35mg/semana. Dose máxima é semanal, não diária.'),
('denosumabe', 'subcutanea', 60, 'mg', 'inibidor_rankl', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Posologia: 60mg SC a cada 6 meses. Não é dose diária.'),
('cianocobalamina', 'oral', 1000, 'mcg', 'vitamina_b12', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('bromoprida', 'oral', 30, 'mg', 'procinetico_d2', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto'),
('domperidona', 'oral', 30, 'mg', 'procinetico_d2_periferico', 18, 'anvisa',
 TRUE, 'auto_pending', 'rename_2024_auto',
 'Cuidado QT longo — ANVISA recomenda ECG basal em idoso')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- BEERS / Contraindicações por condição (Tier Amarelo)
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_condition_contraindications (
    condition_term, condition_icd10,
    affected_principle_active, affected_therapeutic_class,
    severity, rationale, recommendation, source, source_ref, confidence,
    auto_generated, review_status
) VALUES
-- Difenidramina — Beers AVOID em ≥65 (anticolinérgico forte)
('idoso ≥65', NULL, 'difenidramina', NULL,
 'contraindicated',
 'Anticolinérgico forte (ACB 3); Beers 2023 AVOID em ≥65 — risco confusão, queda, retenção urinária, glaucoma',
 'Substituir por antihistamínico não-sedativo (loratadina, desloratadina, fexofenadina)',
 'beers_2023', 'AGS Beers 2023', 0.90,
 TRUE, 'auto_pending'),
-- Tramadol — Caution: limiar convulsivo
('história de epilepsia', 'G40', 'tramadol', NULL,
 'caution',
 'Reduz limiar convulsivo; cuidado em pacientes com epilepsia ou risco aumentado',
 'Considerar opioide alternativo (codeína, morfina baixa dose) em paciente com epilepsia',
 'manual', 'Bula ANVISA', 0.85,
 TRUE, 'auto_pending'),
-- Tramadol + SSRI — Caution: síndrome serotoninérgica
('uso de SSRI', NULL, 'tramadol', NULL,
 'caution',
 'Risco síndrome serotoninérgica quando associado a SSRI (sertralina, fluoxetina, escitalopram, paroxetina, citalopram)',
 'Monitorar sinais (febre, agitação, tremor, hiperreflexia). Considerar alternativa opioide',
 'manual', 'Lexicomp', 0.90,
 TRUE, 'auto_pending'),
-- Amiodarona — múltiplas contraindicações
('idoso ≥65', NULL, 'amiodarona', NULL,
 'caution',
 'Toxicidade pulmonar, hepática, tireoidiana, neurológica em uso prolongado. Beers 2023 Caution em ≥65',
 'Monitorar TSH, função hepática (TGO/TGP), avaliação pulmonar a cada 6 meses',
 'beers_2023', 'AGS Beers 2023', 0.90,
 TRUE, 'auto_pending'),
-- Digoxina — Caution dose alta + ajuste renal
('idoso ≥65', NULL, 'digoxina', NULL,
 'caution',
 'Beers 2023 Caution: dose >0.125mg/dia em ≥65 raramente justificada. Janela terapêutica estreita.',
 'Manter dose ≤0.125mg/dia em idoso. Ajuste renal obrigatório (ClCr<50 reduzir 50%)',
 'beers_2023', 'AGS Beers 2023', 0.95,
 TRUE, 'auto_pending'),
-- Morfina — IRC reduzir
('IRC com ClCr<30', 'N18', 'morfina', NULL,
 'caution',
 'Acúmulo de metabólitos ativos (M3G, M6G) → neurotoxicidade, mioclonia',
 'Reduzir dose 50% se ClCr<30; preferir oxicodona ou fentanil em IRC severa',
 'kdigo', 'KDIGO 2024', 0.85,
 TRUE, 'auto_pending'),
-- Nimesulida — hepatotoxicidade
('hepatopatia', 'K70-K77', 'nimesulida', NULL,
 'contraindicated',
 'Hepatotoxicidade documentada; ANVISA restringe uso a 15 dias. Black box em alguns países.',
 'AVOID em qualquer hepatopatia. Alternativa: paracetamol, dipirona ou meloxicam (com cuidado)',
 'anvisa', 'Bula ANVISA', 0.95,
 TRUE, 'auto_pending'),
-- Domperidona — QT longo
('history of QT longo', 'I49.8', 'domperidona', NULL,
 'contraindicated',
 'Prolonga intervalo QT; risco arritmia ventricular. ANVISA recomenda ECG basal em idoso',
 'AVOID em paciente com history of QT longo, arritmia, ou uso concomitante de outros prolongadores QT',
 'anvisa', 'Bula ANVISA', 0.90,
 TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- ACB SCORE — Boustani escala oficial (Tier Amarelo)
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_anticholinergic_burden
    (principle_active, burden_score, notes, source,
     auto_generated, review_status)
VALUES
('difenidramina', 3, 'Antihistaminico H1 sedativo — alto efeito anticolinérgico (Boustani 2008)', 'acb_scale',
 TRUE, 'auto_pending'),
('tramadol', 1, 'Opioide com efeito anticolinérgico discreto (Boustani 2008)', 'acb_scale',
 TRUE, 'auto_pending'),
('codeina', 1, 'Opioide com efeito anticolinérgico discreto', 'acb_scale',
 TRUE, 'auto_pending'),
('topiramato', 1, 'Anticonvulsivante — efeito anticolinérgico discreto', 'acb_scale',
 TRUE, 'auto_pending'),
('pregabalina', 0, 'Anticonvulsivante sem efeito anticolinérgico documentado', 'acb_scale',
 TRUE, 'auto_pending'),
('lamotrigina', 0, 'Anticonvulsivante sem efeito anticolinérgico', 'acb_scale',
 TRUE, 'auto_pending'),
('loratadina', 0, 'Antihistaminico H1 não-sedativo — sem efeito anticolinérgico relevante', 'acb_scale',
 TRUE, 'auto_pending'),
('desloratadina', 0, 'Antihistaminico H1 não-sedativo', 'acb_scale',
 TRUE, 'auto_pending'),
('fexofenadina', 0, 'Antihistaminico H1 não-sedativo — sem passagem hematoencefálica', 'acb_scale',
 TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- FALL RISK SCORE — por classe terapêutica nova
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_drug_fall_risk
    (therapeutic_class, fall_risk_score, rationale, source,
     auto_generated, review_status)
VALUES
('nitrato', 2, 'Hipotensão postural · cefaleia · síncope vasovagal',
 'stopp_2023', TRUE, 'auto_pending'),
('antiarritmico_classe_iii', 1, 'Bradicardia · hipotensão · neuropatia periférica em uso prolongado',
 'stopp_2023', TRUE, 'auto_pending'),
('glicosideo_cardiaco', 1, 'Toxicidade digitálica → confusão · bradicardia · arritmia',
 'stopp_2023', TRUE, 'auto_pending'),
('opioide', 2, 'Sedação · hipotensão · confusão (especialmente em idoso)',
 'stopp_2023', TRUE, 'auto_pending'),
('aine_seletivo_cox2_parcial', 1, 'Tontura · risco renal · risco gastrointestinal',
 'stopp_2023', TRUE, 'auto_pending'),
('antihistaminico_h1_sedativo', 2, 'Sedação · efeito anticolinérgico · confusão em idoso',
 'stopp_2023', TRUE, 'auto_pending'),
('inibidor_alfa_glicosidase', 0, 'Sem aumento direto de risco de queda',
 'stopp_2023', TRUE, 'auto_pending'),
('dpp4_inibidor', 0, 'Risco hipoglicemia muito baixo (sem aumento direto de queda)',
 'stopp_2023', TRUE, 'auto_pending'),
('insulina_basal_longa', 1, 'Hipoglicemia (menor risco que NPH em uso noturno)',
 'stopp_2023', TRUE, 'auto_pending'),
('insulina_rapida_analoga', 1, 'Hipoglicemia pós-prandial',
 'stopp_2023', TRUE, 'auto_pending')
ON CONFLICT DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- Atualiza tracker: adiciona novos fármacos do batch 2 ao tracker
-- e marca como 'in_progress' (codificação técnica feita)
-- ════════════════════════════════════════════════════════════════

INSERT INTO aia_health_rename_drugs
    (principle_active, componente, edicao, formas_disponiveis,
     grupo_terapeutico, populacao_alvo, indicacao_sus,
     geriatric_relevance, motor_coverage, notes_curador)
VALUES
-- Cardio
('bisoprolol', 'basico', '2024', ARRAY['comprimido'],
 'Betabloqueador cardiosseletivo', ARRAY['adulto', 'idoso'],
 'IC, HAS, angina', 'high', 'in_progress',
 'Aprovado pelo Henrique. Auto-populate Tier Verde + Amarelo.'),
('nebivolol', 'basico', '2024', ARRAY['comprimido'],
 'Betabloqueador cardiosseletivo', ARRAY['adulto', 'idoso'],
 'HAS · IC com FE preservada', 'high', 'in_progress',
 'Aprovado pelo Henrique. Auto-populate Tier Verde + Amarelo.'),
('olmesartana', 'basico', '2024', ARRAY['comprimido'],
 'Bloqueador receptor angiotensina (BRA)', ARRAY['adulto', 'idoso'],
 'HAS', 'high', 'in_progress', 'Auto-populate.'),
('telmisartana', 'basico', '2024', ARRAY['comprimido'],
 'Bloqueador receptor angiotensina (BRA)', ARRAY['adulto', 'idoso'],
 'HAS · profilaxia CV', 'high', 'in_progress', 'Auto-populate.'),
('valsartana', 'basico', '2024', ARRAY['comprimido'],
 'Bloqueador receptor angiotensina (BRA)', ARRAY['adulto', 'idoso'],
 'HAS · IC', 'high', 'in_progress', 'Auto-populate.'),
('mononitrato_isossorbida', 'basico', '2024', ARRAY['comprimido'],
 'Nitrato', ARRAY['adulto', 'idoso'],
 'Angina estável · IC', 'high', 'in_progress', 'Auto-populate.'),
('dinitrato_isossorbida', 'basico', '2024', ARRAY['comprimido', 'sublingual'],
 'Nitrato', ARRAY['adulto', 'idoso'],
 'Angina aguda (sublingual) · profilaxia', 'high', 'in_progress', 'Auto-populate.'),
('amiodarona', 'basico', '2024', ARRAY['comprimido', 'injetavel'],
 'Antiarrítmico classe III', ARRAY['adulto', 'idoso'],
 'FA · taquiarritmias ventriculares', 'high', 'in_progress',
 'Toxicidade pulmonar/hepática/tireoidiana — monitor obrigatório'),
('digoxina', 'basico', '2024', ARRAY['comprimido'],
 'Glicosídeo cardíaco', ARRAY['adulto', 'idoso'],
 'IC · controle FA', 'high', 'in_progress',
 'Janela estreita; ajuste renal; Beers Caution dose >0.125mg'),

-- Endócrino
('insulina_glargina', 'basico', '2024', ARRAY['injetavel'],
 'Insulina basal longa ação', ARRAY['adulto', 'idoso'],
 'DM1, DM2', 'high', 'in_progress', 'Auto-populate.'),
('insulina_lispro', 'basico', '2024', ARRAY['injetavel'],
 'Insulina rápida análoga', ARRAY['adulto', 'idoso'],
 'DM1, DM2 pós-prandial', 'high', 'in_progress', 'Auto-populate.'),
('insulina_asparte', 'basico', '2024', ARRAY['injetavel'],
 'Insulina rápida análoga', ARRAY['adulto', 'idoso'],
 'DM1, DM2 pós-prandial', 'high', 'in_progress', 'Auto-populate.'),
('insulina_glulisina', 'basico', '2024', ARRAY['injetavel'],
 'Insulina rápida análoga', ARRAY['adulto', 'idoso'],
 'DM1, DM2 pós-prandial', 'high', 'in_progress', 'Auto-populate.'),
('sitagliptina', 'basico', '2024', ARRAY['comprimido'],
 'Inibidor DPP-4', ARRAY['adulto', 'idoso'],
 'DM2 — boa segurança em idoso (baixo risco hipoglicemia)', 'high', 'in_progress',
 'Auto-populate.'),
('acarbose', 'basico', '2024', ARRAY['comprimido'],
 'Inibidor alfa-glicosidase', ARRAY['adulto', 'idoso'],
 'DM2 pós-prandial', 'medium', 'in_progress', 'Auto-populate.'),
('metimazol', 'basico', '2024', ARRAY['comprimido'],
 'Antitireoidiano', ARRAY['adulto', 'idoso'],
 'Hipertireoidismo', 'medium', 'in_progress', 'Auto-populate.'),

-- SNC
('pregabalina', 'basico', '2024', ARRAY['cápsula'],
 'Anticonvulsivante / dor neuropática', ARRAY['adulto', 'idoso'],
 'Epilepsia · dor neuropática · ansiedade generalizada', 'high', 'in_progress',
 'Múltiplo uso. Ajuste renal obrigatório.'),
('lamotrigina', 'basico', '2024', ARRAY['comprimido'],
 'Anticonvulsivante', ARRAY['adulto', 'idoso'],
 'Epilepsia · transtorno bipolar', 'high', 'in_progress', 'Auto-populate.'),
('topiramato', 'basico', '2024', ARRAY['comprimido'],
 'Anticonvulsivante', ARRAY['adulto', 'idoso'],
 'Epilepsia · profilaxia enxaqueca · dor neuropática', 'high', 'in_progress',
 'Auto-populate.'),

-- Pneumo
('salmeterol', 'basico', '2024', ARRAY['inalador'],
 'Beta-2 agonista longa ação (LABA)', ARRAY['adulto', 'idoso'],
 'Asma, DPOC manutenção', 'high', 'in_progress', 'Auto-populate.'),
('fluticasona', 'basico', '2024', ARRAY['inalador', 'spray nasal'],
 'Corticoide inalatório (ICS)', ARRAY['adulto', 'idoso'],
 'Asma, DPOC, rinite alérgica', 'high', 'in_progress', 'Auto-populate.'),
('beclometasona', 'basico', '2024', ARRAY['inalador'],
 'Corticoide inalatório (ICS)', ARRAY['adulto', 'idoso'],
 'Asma, DPOC', 'high', 'in_progress', 'Auto-populate.'),
('formoterol+budesonida', 'basico', '2024', ARRAY['inalador'],
 'Combinação fixa LABA+ICS', ARRAY['adulto', 'idoso'],
 'Asma, DPOC manutenção', 'high', 'in_progress', 'Auto-populate.'),
('salmeterol+fluticasona', 'basico', '2024', ARRAY['inalador'],
 'Combinação fixa LABA+ICS', ARRAY['adulto', 'idoso'],
 'Asma, DPOC manutenção', 'high', 'in_progress', 'Auto-populate.'),

-- Corticoide
('metilprednisolona', 'basico', '2024', ARRAY['comprimido', 'injetavel'],
 'Glicocorticoide', ARRAY['adulto', 'idoso'],
 'Inflamação, autoimune, exacerbação aguda', 'high', 'in_progress',
 'Auto-populate.'),

-- Opioides + AINEs
('tramadol', 'basico', '2024', ARRAY['comprimido', 'cápsula', 'gotas'],
 'Opioide analgésico', ARRAY['adulto', 'idoso'],
 'Dor moderada a intensa', 'high', 'in_progress',
 'Risco síndrome serotoninérgica com SSRI; reduz limiar convulsivo'),
('codeina', 'basico', '2024', ARRAY['comprimido'],
 'Opioide analgésico', ARRAY['adulto', 'idoso'],
 'Dor leve-moderada · antitussígeno', 'high', 'in_progress', 'Auto-populate.'),
('morfina', 'basico', '2024', ARRAY['comprimido', 'injetavel', 'oral'],
 'Opioide forte', ARRAY['adulto', 'idoso'],
 'Dor severa · cuidado paliativo', 'high', 'in_progress',
 'IRC: reduzir dose 50% se ClCr<30'),
('oxicodona', 'basico', '2024', ARRAY['comprimido liberação prolongada'],
 'Opioide forte', ARRAY['adulto', 'idoso'],
 'Dor severa crônica', 'high', 'in_progress', 'Auto-populate.'),
('nimesulida', 'basico', '2024', ARRAY['comprimido', 'gotas'],
 'AINE seletivo COX-2 parcial', ARRAY['adulto', 'idoso'],
 'Dor inflamatória aguda', 'medium', 'in_progress',
 'ANVISA limita uso a 15 dias por hepatotoxicidade'),
('meloxicam', 'basico', '2024', ARRAY['comprimido', 'injetavel'],
 'AINE seletivo COX-2 parcial', ARRAY['adulto', 'idoso'],
 'Dor inflamatória crônica', 'medium', 'in_progress', 'Auto-populate.'),

-- Antialérgicos
('loratadina', 'basico', '2024', ARRAY['comprimido', 'xarope'],
 'Antihistaminico H1 não-sedativo', ARRAY['adulto', 'idoso'],
 'Rinite alérgica · urticária', 'medium', 'in_progress', 'Auto-populate.'),
('desloratadina', 'basico', '2024', ARRAY['comprimido'],
 'Antihistaminico H1 não-sedativo', ARRAY['adulto', 'idoso'],
 'Rinite alérgica · urticária', 'medium', 'in_progress', 'Auto-populate.'),
('fexofenadina', 'basico', '2024', ARRAY['comprimido'],
 'Antihistaminico H1 não-sedativo', ARRAY['adulto', 'idoso'],
 'Rinite alérgica · urticária', 'medium', 'in_progress', 'Auto-populate.'),
('difenidramina', 'basico', '2024', ARRAY['comprimido', 'xarope'],
 'Antihistaminico H1 sedativo', ARRAY['adulto', 'idoso'],
 'Rinite · cinetose · sedação', 'medium', 'in_progress',
 'Beers AVOID em ≥65 — anticolinérgico forte'),

-- Ósseo + Vitaminas + Procinéticos
('risedronato', 'basico', '2024', ARRAY['comprimido'],
 'Bifosfonato', ARRAY['adulto', 'idoso'],
 'Osteoporose pós-menopausa · masculina', 'high', 'in_progress',
 'Posologia semanal (35mg/sem)'),
('denosumabe', 'especializado', '2024', ARRAY['injetavel'],
 'Inibidor RANKL', ARRAY['idoso'],
 'Osteoporose grave', 'high', 'in_progress',
 'Componente Especializado · 60mg SC a cada 6 meses'),
('cianocobalamina', 'basico', '2024', ARRAY['comprimido', 'injetavel'],
 'Vitamina B12', ARRAY['adulto', 'idoso'],
 'Anemia megaloblástica · neuropatia · suplementação em idoso com IBP crônico',
 'high', 'in_progress',
 'Cascata IBP→déficit B12 já mapeada'),
('bromoprida', 'basico', '2024', ARRAY['comprimido', 'gotas'],
 'Procinético D2', ARRAY['adulto', 'idoso'],
 'Náusea, refluxo · pré-procedimento', 'medium', 'in_progress',
 'Risco extrapiramidal; uso prolongado AVOID'),
('domperidona', 'basico', '2024', ARRAY['comprimido', 'suspensão'],
 'Procinético D2 periférico', ARRAY['adulto', 'idoso'],
 'Náusea · refluxo · gastroparesia', 'medium', 'in_progress',
 'QT longo — ECG basal em idoso')
ON CONFLICT (principle_active, edicao) DO NOTHING;


COMMIT;
