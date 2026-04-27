-- ConnectaIACare — Cascatas de prescrição (dimensão 13 do motor).
--
-- Cascata = paciente recebe droga A que causa efeito adverso, e médico
-- prescreve droga C pra TRATAR esse efeito em vez de suspender A.
-- Paciente termina com 2 (ou 3) drogas onde 1 era suficiente — risco
-- aumentado, custo aumentado, polifarmácia evitável.
--
-- Padrões cobertos hoje:
--   a_and_c   — paciente tem A + C (ex AINE + anti-hipertensivo)
--   a_b_and_c — paciente tem A + B + C (ex Triple Whammy: AINE+IECA+diurético)
--
-- Curadoria Fase 1: 8 cascatas mais relevantes em geriatria brasileira.
-- Fontes: Beers 2023, STOPP/START v2, prescribing cascades (Rochon et al
-- BMJ 2017), Lexicomp.
--
-- Class names usadas alinhadas com aia_health_drug_dose_limits.therapeutic_class
-- (ex 'analgesico_aine', 'ieca', 'ara' — em PT-BR, não 'nsaid'/'ace_inhibitor').

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Tabela
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_drug_cascades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    severity TEXT NOT NULL CHECK (severity IN (
        'contraindicated', 'major', 'moderate', 'minor'
    )),

    -- Drug A: ofensor primário (causa o efeito adverso)
    drug_a_principles TEXT[] NOT NULL DEFAULT '{}',
    drug_a_classes TEXT[] NOT NULL DEFAULT '{}',

    -- Drug B: cofator do triplo (NULL/vazio se a_and_c)
    drug_b_principles TEXT[] NOT NULL DEFAULT '{}',
    drug_b_classes TEXT[] NOT NULL DEFAULT '{}',

    -- Drug C: o "tratamento da cascata" (que provavelmente não devia)
    drug_c_principles TEXT[] NOT NULL DEFAULT '{}',
    drug_c_classes TEXT[] NOT NULL DEFAULT '{}',

    match_pattern TEXT NOT NULL CHECK (match_pattern IN (
        'a_and_c', 'a_b_and_c'
    )),

    adverse_effect TEXT NOT NULL,
    cascade_explanation TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    alternative TEXT,

    -- Schema: { "icd_codes": ["E10", "E11"], "rationale": "..." }
    exclusion_conditions JSONB,

    source TEXT NOT NULL CHECK (source IN (
        'beers_2023', 'stopp_start_v2', 'rochon_bmj_2017',
        'lexicomp', 'manual'
    )),
    source_ref TEXT,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (
        cardinality(drug_a_principles) > 0 OR cardinality(drug_a_classes) > 0
    ),
    CHECK (
        cardinality(drug_c_principles) > 0 OR cardinality(drug_c_classes) > 0
    ),
    CHECK (
        match_pattern = 'a_and_c' OR
        (cardinality(drug_b_principles) > 0 OR cardinality(drug_b_classes) > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_drug_cascades_active
    ON aia_health_drug_cascades(severity, name) WHERE active = TRUE;


-- ════════════════════════════════════════════════════════════════
-- 2. Seeds — 8 cascatas críticas
--    Class names alinhadas com produção (PT-BR underscore_case).
-- ════════════════════════════════════════════════════════════════

-- 2.1 Triple Whammy — AINE + IECA/BRA + Diurético = IRA aguda
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_classes, drug_b_classes, drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, source_ref, confidence
) VALUES (
    'Triple Whammy (AINE + IECA/BRA + Diurético)',
    'major',
    ARRAY['analgesico_aine'],
    ARRAY['ieca', 'ara'],
    ARRAY['diuretico_tiazidico', 'diuretico_alca'],
    'a_b_and_c',
    'Lesão renal aguda — risco 31% aumentado vs uso isolado',
    'AINE inibe prostaglandinas que mantêm fluxo sanguíneo renal. '
    'IECA/BRA reduz pressão de filtração glomerular. Diurético depleta '
    'volume. Os três juntos = colapso renal funcional, especialmente em '
    'idoso com função renal limítrofe.',
    'EVITAR a combinação. Se imprescindível: monitorar creatinina + '
    'eletrólitos a cada 7-14 dias nas primeiras 4 semanas. Em idoso '
    '≥75 anos com TFG <60, considerar contraindicada.',
    'Substituir AINE por paracetamol até 3g/dia (ajustando hepático). '
    'Para dor neuropática, considerar duloxetina ou gabapentina.',
    'rochon_bmj_2017', 'BMJ 2017;359:j5251 + STOPP K2',
    0.92
) ON CONFLICT (name) DO NOTHING;


-- 2.2 AINE → HAS tratada com anti-hipertensivo
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_classes, drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, confidence
) VALUES (
    'HAS induzida por AINE',
    'moderate',
    ARRAY['analgesico_aine'],
    ARRAY['ieca', 'ara', 'betabloqueador_cardiosseletivo',
          'betabloqueador_nao_seletivo', 'ccb_dihidropiridinico',
          'diuretico_tiazidico'],
    'a_and_c',
    'Hipertensão por inibição renal de prostaglandinas + retenção sódica',
    'AINE eleva PA em 5-10 mmHg em uso crônico (3-5 dias). Médico '
    'frequentemente atribui à HAS essencial e prescreve anti-hipertensivo. '
    'Paciente fica em polifarmácia evitável + risco renal/cardiovascular '
    'aumentado.',
    'Avaliar TEMPORALIDADE: HAS pré-existia ao AINE? Se diagnóstico de '
    'HAS é posterior ao AINE: tentar suspender AINE e medir PA por '
    '2 semanas antes de iniciar anti-hipertensivo.',
    'Paracetamol pra dor; fisioterapia pra dor crônica.',
    'rochon_bmj_2017', 0.88
) ON CONFLICT (name) DO NOTHING;


-- 2.3 BCCa di-hidropiridínico → edema tratado com diurético
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles, drug_a_classes,
    drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, confidence
) VALUES (
    'Edema por BCCa-DHP tratado com diurético',
    'moderate',
    ARRAY['anlodipino', 'nifedipino', 'felodipino', 'lercanidipino'],
    ARRAY['ccb_dihidropiridinico'],
    ARRAY['diuretico_tiazidico', 'diuretico_alca'],
    'a_and_c',
    'Edema periférico bilateral por vasodilatação arteriolar (NÃO-volumétrico)',
    'Anlodipino/nifedipino causam edema periférico em 8-15% dos pacientes '
    '(dose-dependente). Edema é por vasodilatação, NÃO por retenção '
    'hídrica. Diurético é INEFICAZ pra esse tipo de edema e ainda causa '
    'hipovolemia/hipocalemia.',
    'Reduzir dose do BCCa-DHP. Se persistir, trocar por BCCa não-DHP '
    '(verapamil/diltiazem) ou IECA/BRA. NÃO adicionar diurético.',
    'Verapamil 80-240 mg/dia ou diltiazem (cuidado com bradicardia). '
    'Se IC, IECA é melhor escolha que BCCa.',
    'rochon_bmj_2017', 0.90
) ON CONFLICT (name) DO NOTHING;


-- 2.4 Antipsicótico → parkinsonismo iatrogênico tratado com antiparkinsoniano
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_classes, drug_a_principles,
    drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    exclusion_conditions,
    source, confidence
) VALUES (
    'Antipsicótico + antiparkinsoniano (paradoxal)',
    'major',
    ARRAY['antipsicotico_atipico'],
    ARRAY['haloperidol', 'risperidona', 'olanzapina', 'quetiapina',
          'clozapina', 'aripiprazol', 'ziprasidona'],
    ARRAY['antiparkinsoniano_dopaminergico', 'antiparkinsoniano_agonista_d2'],
    'a_and_c',
    'Parkinsonismo medicamentoso (extrapiramidalismo) — Beers AVOID em demência',
    'Antipsicóticos bloqueiam receptor D2 — mesmo mecanismo que causa '
    'sintomas parkinsonianos. Antiparkinsonianos (levodopa, pramipexol) '
    'fazem o oposto. Combinar é PARADOXAL: trata-se o efeito adverso '
    'da droga A com droga C que faz exatamente o oposto. Risco: '
    'descompensação psiquiátrica + sintomas extrapiramidais persistentes.',
    'PARAR ou trocar o antipsicótico. Em paciente com demência + '
    'sintomas psicóticos, preferir quetiapina ou clozapina (menor '
    'antagonismo D2). Em idoso sem indicação clara: deprescrição.',
    'Quetiapina 12,5-50 mg/dia ou clozapina (em paciente jovem com '
    'esquizofrenia refratária). Avaliar se uso é mesmo necessário '
    '(Beers 2023 AVOID em demência por aumentar mortalidade e AVC).',
    '{"icd_codes": ["G20", "G21"], "rationale": "Paciente com Doença de Parkinson real ou parkinsonismo prévio (não-iatrogênico) — antiparkinsoniano é necessário independente do antipsicótico."}'::jsonb,
    'beers_2023', 0.93
) ON CONFLICT (name) DO NOTHING;


-- 2.5 Metoclopramida → discinesia tardia
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles, drug_a_classes,
    drug_c_classes, drug_c_principles,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, confidence
) VALUES (
    'Metoclopramida → discinesia tardia',
    'major',
    ARRAY['metoclopramida'],
    ARRAY['procinetico_d2'],
    ARRAY['antipsicotico_atipico', 'bzd'],
    ARRAY['clonazepam', 'diazepam'],
    'a_and_c',
    'Discinesia tardia (movimentos involuntários da face/língua) — Beers AVOID',
    'Metoclopramida é antagonista D2 + uso prolongado (>3 meses) causa '
    'discinesia tardia em 1-15% dos idosos. Movimento involuntário pode '
    'persistir MESES após suspensão. Médico frequentemente prescreve '
    'benzodiazepínico ou antipsicótico pra "controlar tremor", agravando '
    'risco de queda + sedação.',
    'SUSPENDER metoclopramida IMEDIATAMENTE. Discinesia pode regredir '
    'mas pode também ser permanente. NÃO prescrever benzo/antipsicótico '
    'sem avaliação neurológica especializada.',
    'Pra náusea: ondansetrona, dimenidrinato (curto prazo) ou domperidona '
    '(<10 dias). Reavaliação geriátrica imediata.',
    'beers_2023', 0.95
) ON CONFLICT (name) DO NOTHING;


-- 2.6 IBP crônico → suplementos B12/Cálcio
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles, drug_a_classes,
    drug_c_principles, drug_c_classes,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, confidence
) VALUES (
    'IBP crônico + suplementos B12/Cálcio',
    'minor',
    ARRAY['omeprazol', 'pantoprazol', 'esomeprazol', 'lansoprazol'],
    ARRAY['ipp'],
    ARRAY['cianocobalamina', 'carbonato de cálcio', 'citrato de cálcio'],
    ARRAY['suplemento_calcio'],
    'a_and_c',
    'Redução de absorção de B12 e cálcio (acidez gástrica reduzida)',
    'IBP suprime acidez gástrica → reduz absorção de B12 (precisa pH '
    'ácido) e de Ca++ (forma ionizada). Médico prescreve suplemento sem '
    'reavaliar duração do IBP. Em uso >2 anos, IBP correlaciona com '
    'fratura de quadril, demência (controversa), pneumonia e infecção '
    'por C. difficile.',
    'REAVALIAR INDICAÇÃO do IBP: ainda há refluxo? Há esofagite '
    'erosiva ativa? Se uso é "preventivo gastrointestinal" sem '
    'indicação clara: deprescrever. Se é necessário, dosar B12 sérica '
    'e cálcio iônico antes de suplementar.',
    'Ranitidina/famotidina (H2 bloqueadores) têm menos impacto absortivo. '
    'Considerar dose mínima eficaz do IBP + retirada gradual.',
    'stopp_start_v2', 0.80
) ON CONFLICT (name) DO NOTHING;


-- 2.7 Anticolinérgico → constipação tratada com laxante crônico
-- Match por principles (sem class 'anticolinergico' na taxonomia atual)
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles,
    drug_c_principles,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    source, confidence
) VALUES (
    'Anticolinérgico + laxante crônico',
    'moderate',
    ARRAY['amitriptilina', 'oxibutinina', 'paroxetina', 'prometazina',
          'difenidramina', 'imipramina', 'clomipramina', 'tolterodina'],
    ARRAY['lactulose', 'bisacodil', 'óleo mineral', 'picossulfato de sódio',
          'macrogol', 'sene'],
    'a_and_c',
    'Constipação por bloqueio muscarínico intestinal (ACB Score elevado)',
    'Anticolinérgicos reduzem motilidade intestinal — constipação afeta '
    '60-80% dos pacientes em uso crônico. Paciente reclama, médico '
    'prescreve laxante crônico. Carga anticolinérgica (ACB Score) também '
    'causa retenção urinária, confusão, queda, glaucoma — laxante mascara '
    'só um sintoma da síndrome.',
    'REDUZIR carga anticolinérgica. Trocar amitriptilina por nortriptilina '
    '(menor ACB), oxibutinina por mirabegrona, prometazina por '
    'difenidramina apenas pontual. Calcular ACB Score do paciente — '
    '≥3 = alto risco cognitivo.',
    'Pra dor neuropática: gabapentina/duloxetina. Pra sono: higiene '
    'do sono + melatonina. Pra urge urinária: mirabegrona.',
    'beers_2023', 0.85
) ON CONFLICT (name) DO NOTHING;


-- 2.8 Glicocorticoide → hiperglicemia tratada com antidiabético
INSERT INTO aia_health_drug_cascades (
    name, severity,
    drug_a_principles, drug_a_classes,
    drug_c_classes, drug_c_principles,
    match_pattern, adverse_effect,
    cascade_explanation, recommendation, alternative,
    exclusion_conditions,
    source, confidence
) VALUES (
    'Hiperglicemia por corticoide + antidiabético novo',
    'moderate',
    ARRAY['prednisona', 'prednisolona', 'dexametasona', 'hidrocortisona'],
    ARRAY['corticoide'],
    ARRAY['biguanida', 'sulfonilureia'],
    ARRAY['metformina', 'glibenclamida', 'gliclazida', 'insulina',
          'empagliflozina', 'dapagliflozina', 'sitagliptina'],
    'a_and_c',
    'Hiperglicemia induzida por corticoide (efeito de dose proporcional)',
    'Glicocorticoide eleva glicemia em jejum/pós-prandial via '
    'gliconeogênese hepática + resistência periférica. Em uso curto '
    '(<14 dias) frequentemente é transitória. Em uso crônico, '
    'antidiabético é necessário — mas avaliar se a indicação do '
    'corticoide ainda existe e se a dose pode ser reduzida.',
    'AVALIAR DURAÇÃO do corticoide: <2 semanas → monitorar glicemia, '
    'sem antidiabético na maioria. >2 semanas → ajustar dose corticoide '
    'ao mínimo eficaz e introduzir antidiabético (preferir metformina '
    'se função renal adequada).',
    'Reduzir dose do corticoide ao mínimo eficaz; alternativas '
    '(esteroide-sparing) dependem da indicação primária.',
    '{"icd_codes": ["E10", "E11", "E13", "E14"], "rationale": "Paciente já era diabético pré-corticoide — antidiabético é tratamento crônico, não cascata."}'::jsonb,
    'rochon_bmj_2017', 0.85
) ON CONFLICT (name) DO NOTHING;


COMMIT;
