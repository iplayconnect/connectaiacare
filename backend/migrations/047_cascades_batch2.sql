-- ConnectaIACare — Cascatas adicionais batch 2 (revisão Henrique).
--
-- Cascatas aprovadas pelo Henrique no checklist clínico:
-- - Opioide → constipação → laxante (separada da cascata anticolinérgica)
-- - IMAO + alimentos ricos em tirosina → crise hipertensiva (alerta orientativo)
--
-- Auto_generated com flag review_status='auto_pending' pra revisão clínica.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- ADD: flags auto_generated + review_status em aia_health_drug_cascades
-- (similar ao que já tem em outras tabelas do motor)
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_drug_cascades
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));


-- ════════════════════════════════════════════════════════════════
-- 1. Opioide → constipação → laxante crônico
-- ════════════════════════════════════════════════════════════════
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_classes, drug_c_principles, drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, source_ref, confidence,
    auto_generated, review_status
) VALUES (
    'Opioide → constipação → laxante crônico',
    'moderate',
    ARRAY['opioide'],
    ARRAY['lactulose', 'bisacodil', 'picossulfato_sodio', 'sene', 'macrogol', 'oleo_mineral'],
    ARRAY['laxante'],
    'a_and_c',
    'Constipação induzida por opioide (OIC — Opioid-Induced Constipation)',
    'Opioides ativam receptores μ intestinais → reduzem motilidade + aumentam '
    'tônus de esfíncteres. Constipação afeta 40-90% dos pacientes em uso '
    'crônico. Diferente da constipação anticolinérgica, é mecanismo distinto '
    'e pode coexistir. Médico frequentemente prescreve laxante crônico '
    'reativamente, sem orientação preventiva ou consideração de antagonista '
    'opioide periférico.',
    'PROFILAXIA: prescrever laxante junto ao opioide desde início + '
    'hidratação + fibras. Em uso crônico + constipação refratária, '
    'considerar antagonista opioide periférico (metilnaltrexona, naloxegol). '
    'Avaliar se a indicação do opioide ainda existe.',
    'Pra dor moderada: tramadol (menor OIC que morfina) ou paracetamol+codeina. '
    'Em dor crônica não-oncológica, considerar gabapentina/duloxetina '
    'pra dor neuropática ou fisioterapia + AINE em surtos.',
    'rochon_bmj_2017', 'STOPP D9 + Beers 2023', 0.90,
    TRUE, 'auto_pending'
) ON CONFLICT (name) DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- 2. IMAO + alimentos ricos em tirosina → crise hipertensiva
--    NOTA: cascata informacional/orientativa — não scaneia dieta real
--    do paciente, apenas alerta quando há prescrição de IMAO.
-- ════════════════════════════════════════════════════════════════
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles, drug_a_classes,
    drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    exclusion_conditions,
    source, source_ref, confidence,
    auto_generated, review_status
) VALUES (
    'IMAO + alimentos ricos em tirosina (alerta dietético)',
    'major',
    ARRAY['selegilina', 'tranilcipromina', 'fenelzina', 'isocarboxazida',
          'moclobemida', 'rasagilina'],
    ARRAY['imao_a', 'imao_b', 'imao_nao_seletivo'],
    -- C aqui é "anti-hipertensivo de resgate" — médico pode prescrever
    -- pra controlar crise sem identificar a causa real (IMAO + tirosina)
    ARRAY['ieca', 'ara', 'betabloqueador_cardiosseletivo',
          'betabloqueador_nao_seletivo', 'ccb_dihidropiridinico'],
    'a_and_c',
    'Crise hipertensiva por interação IMAO + alimentos ricos em tirosina '
    '(queijos curados, embutidos, vinho fermentado, fava). Alerta orientativo: '
    'paciente em uso de IMAO + episódio agudo de HAS deve investigar dieta',
    'IMAOs (especialmente IMAO-A não-seletivos como tranilcipromina, fenelzina) '
    'inibem o catabolismo de tirosina dietética. Tirosina em quantidade alta '
    'circula livre, causando liberação maciça de noradrenalina endógena → '
    'crise hipertensiva (pico PA 180-200/120 em minutos). IMAO-B (selegilina, '
    'rasagilina) em doses baixas (≤10mg/dia) tem risco menor por seletividade. '
    'Médico desconhecendo a interação prescreve anti-hipertensivo de resgate '
    'sem orientar restrição dietética — paciente continua expondo-se.',
    'EDUCAÇÃO DIETÉTICA prioritária: restrição de queijos curados (parmesão, '
    'gorgonzola, brie), embutidos curados (salame, presunto cru), vinho '
    'fermentado, fava, peixes em conserva, soja fermentada. Alerta médico '
    'em prescrição de IMAO. Em IMAO-B baixa dose (selegilina ≤10mg), risco '
    'é baixo mas educação ainda recomendada.',
    'Pra depressão refratária: avaliar trocar IMAO por modulador serotonérgico '
    'novo (vortioxetina) ou ketamina supervisionada. Para Parkinson: '
    'rasagilina é mais seletiva IMAO-B que selegilina.',
    NULL,
    'manual', 'AGS Beers 2023 + Bula ANVISA + UpToDate', 0.85,
    TRUE, 'auto_pending'
) ON CONFLICT (name) DO NOTHING;


COMMIT;
