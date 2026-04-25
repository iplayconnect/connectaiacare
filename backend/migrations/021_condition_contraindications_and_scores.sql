-- ConnectaIACare — F3: contraindicação por condição + scores cumulativos
-- Data: 2026-04-25
--
-- 3 cruzamentos:
--   1. Contraindicação por condição clínica (CID-10) — AINE+DRC, BB+asma,
--      metformina+IR, opioide+DPOC etc.
--   2. Anticholinergic Burden Score — soma de pontos anticolinérgicos.
--      Score ≥3 = risco delirium/queda em idoso (Boustani 2008).
--   3. Fall Risk Score — soma medicamentos que aumentam queda
--      (BZD, opioide, antipsicótico, anti-hipertensivo agressivo).

BEGIN;

-- =====================================================
-- 1. aia_health_condition_contraindications
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_condition_contraindications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- A condição (texto livre normalizado OU CID-10 quando disponível)
    condition_term TEXT NOT NULL,           -- ex: "asma", "dpoc", "doenca renal cronica"
    condition_icd10 TEXT,                    -- ex: "J45", "J44", "N18"

    -- O que contraindicar (principle ou class — espelha allergy_mappings)
    affected_principle_active TEXT,
    affected_therapeutic_class TEXT,

    severity TEXT NOT NULL CHECK (severity IN ('contraindicated', 'warning', 'caution')),
    rationale TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN (
        'beers_2023', 'sbgg', 'anvisa', 'kdigo', 'gold', 'gina', 'manual'
    )),
    source_ref TEXT,
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        affected_principle_active IS NOT NULL
        OR affected_therapeutic_class IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_condition_contra_term
    ON aia_health_condition_contraindications(condition_term)
    WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_condition_contra_icd10
    ON aia_health_condition_contraindications(condition_icd10)
    WHERE active = TRUE AND condition_icd10 IS NOT NULL;

-- Aliases comuns (asma → asma | bronquite asmática)
CREATE TABLE IF NOT EXISTS aia_health_condition_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alias TEXT NOT NULL,
    canonical_term TEXT NOT NULL,
    notes TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_condition_aliases_unique
    ON aia_health_condition_aliases(lower(alias));

-- ── Seed condition_aliases ──
INSERT INTO aia_health_condition_aliases (alias, canonical_term, notes) VALUES
    ('asma bronquica', 'asma', NULL),
    ('asthma', 'asma', NULL),
    ('dpoc', 'dpoc', NULL),
    ('doenca pulmonar obstrutiva cronica', 'dpoc', NULL),
    ('enfisema', 'dpoc', NULL),
    ('bronquite cronica', 'dpoc', NULL),
    ('insuficiencia renal', 'doenca renal cronica', NULL),
    ('drc', 'doenca renal cronica', NULL),
    ('insuficiencia renal cronica', 'doenca renal cronica', NULL),
    ('irc', 'doenca renal cronica', NULL),
    ('insuficiencia cardiaca', 'icc', NULL),
    ('ic', 'icc', NULL),
    ('icc descompensada', 'icc', NULL),
    ('insuficiencia hepatica', 'hepatopatia', NULL),
    ('cirrose', 'hepatopatia', NULL),
    ('hepatite cronica', 'hepatopatia', NULL),
    ('alzheimer', 'demencia', NULL),
    ('doenca de alzheimer', 'demencia', NULL),
    ('demencia mista', 'demencia', NULL),
    ('demencia vascular', 'demencia', NULL),
    ('diabetes', 'diabetes mellitus', NULL),
    ('dm2', 'diabetes mellitus', NULL),
    ('dm tipo 2', 'diabetes mellitus', NULL),
    ('hipertensao', 'hipertensao arterial', NULL),
    ('has', 'hipertensao arterial', NULL),
    ('parkinson', 'parkinson', NULL),
    ('doenca de parkinson', 'parkinson', NULL),
    ('glaucoma de angulo fechado', 'glaucoma', NULL),
    ('hba', 'glaucoma', 'hipertensao do angulo fechado'),
    ('historico de queda', 'historico_queda', NULL),
    ('quedas recorrentes', 'historico_queda', NULL),
    ('hponatremia', 'hiponatremia', NULL),
    ('siadh', 'hiponatremia', NULL),
    ('sangramento gi', 'sangramento_gi', NULL),
    ('ulcera peptica', 'sangramento_gi', NULL),
    ('hemorragia digestiva', 'sangramento_gi', NULL)
ON CONFLICT (lower(alias)) DO NOTHING;

-- ── Seed contraindications (regras curadas) ──

-- Asma / DPOC × β-bloqueador (broncoespasmo)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('asma', 'J45', 'betabloqueador', 'contraindicated',
     'β-bloqueadores não-seletivos podem causar broncoespasmo grave em asma.',
     'Evitar β-bloqueador. Se cardio-indicado, β1-seletivo cardio (atenolol, metoprolol) com ressalva.',
     'gina', 0.95),
    ('dpoc', 'J44', 'betabloqueador', 'caution',
     'β-bloq pode atenuar resposta a β2-agonista e piorar dispneia em DPOC.',
     'Preferir β1-seletivo (atenolol/metoprolol). Monitorar dispneia.',
     'gold', 0.85);

-- DPOC × opioide (depressão respiratória)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('dpoc', 'J44', 'opioide', 'warning',
     'Opióide reduz drive respiratório — risco em DPOC moderado/grave.',
     'Avaliar gasometria. Doses baixas se essencial. Monitorar SatO2.',
     'beers_2023', 0.9),
    ('dpoc', 'J44', 'bzd', 'warning',
     'BZD reduz drive respiratório — risco em DPOC.',
     'Evitar. Se necessário, lorazepam baixa dose curto prazo.',
     'beers_2023', 0.9);

-- DRC × AINE / metformina (insuficiência renal)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('doenca renal cronica', 'N18', 'analgesico_aine', 'contraindicated',
     'AINE em DRC piora função renal e causa retenção hidrossalina.',
     'NÃO usar AINE em DRC estágio 3+ (TFG < 60). Paracetamol é alternativa.',
     'kdigo', 0.97);

INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_principle_active, severity, rationale, recommendation, source, confidence)
VALUES
    ('doenca renal cronica', 'N18', 'metformina', 'caution',
     'Metformina contraindicada se ClCr < 30. Reavaliar entre 30-45 mL/min.',
     'Suspender se ClCr < 30. Reduzir dose 50% se ClCr 30-45.',
     'kdigo', 0.95);

-- DRC × diurético poupador / IECA (hipercalemia)
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('doenca renal cronica', 'N18', 'ieca', 'caution',
     'IECA em DRC: monitorar K+ e creatinina. Suspender se ClCr cai >30%.',
     'Iniciar dose baixa, K+ + creatinina basal e em 1-2 sem.',
     'kdigo', 0.9),
    ('doenca renal cronica', 'N18', 'ara', 'caution',
     'ARA em DRC: monitorar K+ e creatinina.',
     'Mesmo cuidado que IECA.',
     'kdigo', 0.9);

-- ICC × AINE
INSERT INTO aia_health_condition_contraindications
    (condition_term, condition_icd10, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('icc', 'I50', 'analgesico_aine', 'contraindicated',
     'AINE causa retenção hídrica e descompensa IC.',
     'Evitar. Paracetamol pra dor.',
     'beers_2023', 0.97);

-- Demência × BZD / opioide / anticolinérgico (delirium, declínio)
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('demencia', 'bzd', 'contraindicated',
     'BZD em demência aumenta risco de delirium, queda e declínio cognitivo acelerado.',
     'NÃO usar BZD. Manejo não-farmacológico para agitação. Se essencial curto, considerar trazodona.',
     'beers_2023', 0.97),
    ('demencia', 'opioide', 'warning',
     'Opióide em demência: maior risco de delirium e queda.',
     'Doses baixas. Reavaliar a cada 48h.',
     'beers_2023', 0.9),
    ('demencia', 'hipnotico_z', 'contraindicated',
     'Z-drug em demência: risco delirium e queda.',
     'NÃO usar.',
     'beers_2023', 0.95);

-- Histórico de queda × BZD / opioide / Z-drug
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('historico_queda', 'bzd', 'contraindicated',
     'BZD em paciente com queda prévia: risco multiplicado de fratura.',
     'NÃO usar. Avaliar causa da queda primeiro.',
     'beers_2023', 0.97),
    ('historico_queda', 'hipnotico_z', 'contraindicated',
     'Z-drug em paciente com queda prévia: risco aumentado.',
     'NÃO usar.',
     'beers_2023', 0.95),
    ('historico_queda', 'opioide', 'warning',
     'Opióide em paciente com queda prévia.',
     'Doses baixas, monitorar tontura/sedação.',
     'beers_2023', 0.85);

-- Hiponatremia × SSRI / tiazídico
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('hiponatremia', 'ssri', 'warning',
     'SSRI pode causar/agravar hiponatremia (efeito SIADH).',
     'Monitorar Na sérico semanal nas 2 primeiras semanas. Considerar mirtazapina se hipo persistente.',
     'beers_2023', 0.9),
    ('hiponatremia', 'diuretico_tiazidico', 'contraindicated',
     'Tiazídico em hiponatremia agrava o quadro.',
     'Suspender. Considerar diurético de alça.',
     'manual', 0.9);

-- Hepatopatia × paracetamol alta dose / estatina
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_principle_active, severity, rationale, recommendation, source, confidence)
VALUES
    ('hepatopatia', 'paracetamol', 'warning',
     'Paracetamol em hepatopatia: risco hepatotoxicidade.',
     'Limitar a 2g/dia em hepatopatia leve. Evitar em moderada/grave.',
     'manual', 0.9);

INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('hepatopatia', 'estatina', 'warning',
     'Estatina em hepatopatia: risco hepatotoxicidade adicional.',
     'Avaliar TGO/TGP basal. Suspender se aumento >3× LSN.',
     'manual', 0.85);

-- Sangramento GI × AAS / AINE / anticoagulante / SSRI
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('sangramento_gi', 'analgesico_aine', 'contraindicated',
     'AINE em paciente com sangramento GI prévio: alto risco de recorrência.',
     'NÃO usar. Paracetamol pra dor.',
     'beers_2023', 0.97),
    ('sangramento_gi', 'antiagregante', 'contraindicated',
     'Antiagregante em sangramento GI ativo: contraindicado até estabilização + IBP.',
     'Discutir risco/benefício com cardiologia/gastro.',
     'beers_2023', 0.95),
    ('sangramento_gi', 'anticoagulante_avk', 'caution',
     'Anticoagulante em sangramento GI prévio: avaliar risco/benefício.',
     'Discutir multidisciplinar. IBP profilático obrigatório.',
     'manual', 0.85);

-- Glaucoma de ângulo fechado × anticolinérgico
INSERT INTO aia_health_condition_contraindications
    (condition_term, affected_therapeutic_class, severity, rationale, recommendation, source, confidence)
VALUES
    ('glaucoma', 'antidepressivo_tetraciclico', 'warning',
     'Mirtazapina e antidepressivos com efeito anticolinérgico podem precipitar crise glaucoma.',
     'Avaliar tipo de glaucoma. Em ângulo fechado, evitar.',
     'beers_2023', 0.85);

-- Parkinson × antidopaminérgicos (placeholder, sem antipsicóticos no seed)

-- =====================================================
-- 2. Anticholinergic Burden Score
-- =====================================================
-- Pontuação 0-3 por medicamento (Anticholinergic Cognitive Burden Scale - ACB).
-- Soma cumulativa do paciente; ≥3 = risco delirium/queda em idoso.
-- Fonte: Boustani 2008 + atualizações Aging Clinical & Experimental Research.

CREATE TABLE IF NOT EXISTS aia_health_drug_anticholinergic_burden (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    principle_active TEXT NOT NULL UNIQUE,
    burden_score SMALLINT NOT NULL CHECK (burden_score IN (0, 1, 2, 3)),
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'acb_scale',
    active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO aia_health_drug_anticholinergic_burden (principle_active, burden_score, notes) VALUES
    -- Score 1 (efeito leve)
    ('mirtazapina', 1, 'Antidepressivo com efeito leve anticolinérgico'),
    ('tramadol', 1, 'Opióide com efeito anticolinérgico discreto'),
    ('codeina', 1, 'Opióide leve anticolinérgico'),
    ('digoxina', 1, 'Possível efeito cognitivo em idoso'),
    ('furosemida', 1, 'Risco confusão em idoso desidratado'),
    ('hidroclorotiazida', 1, NULL),
    ('atenolol', 1, NULL),
    ('metoprolol', 1, NULL),
    -- Score 2 (moderado) — sem meds Score 2 no seed atual
    -- Score 3 (forte) — sem meds Score 3 no seed atual
    -- (Anticolinérgicos clássicos: difenidramina, oxibutinina,
    -- amitriptilina, clorpromazina = score 3 — adicionar quando entrarem)
    ('paracetamol', 0, NULL),
    ('dipirona', 0, NULL),
    ('losartana', 0, NULL),
    ('enalapril', 0, NULL),
    ('metformina', 0, NULL),
    ('omeprazol', 0, NULL),
    ('sinvastatina', 0, NULL),
    ('atorvastatina', 0, NULL),
    ('levotiroxina', 0, NULL)
ON CONFLICT (principle_active) DO NOTHING;

-- =====================================================
-- 3. Fall Risk Score (medicamentos que aumentam queda)
-- =====================================================
-- Score 0-3 baseado em literatura geriátrica. ≥3 acumulado = alto risco.
-- Fontes: STOPP/START 2023, Beers 2023, OPIUM-trial.

CREATE TABLE IF NOT EXISTS aia_health_drug_fall_risk (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Match por principle OU class
    principle_active TEXT,
    therapeutic_class TEXT,
    fall_risk_score SMALLINT NOT NULL CHECK (fall_risk_score IN (1, 2, 3)),
    rationale TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'stopp_2023',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (principle_active IS NOT NULL OR therapeutic_class IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_fall_risk_principle
    ON aia_health_drug_fall_risk(principle_active)
    WHERE active = TRUE AND principle_active IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fall_risk_class
    ON aia_health_drug_fall_risk(therapeutic_class)
    WHERE active = TRUE AND therapeutic_class IS NOT NULL;

-- Score 3 (alto risco)
INSERT INTO aia_health_drug_fall_risk (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('bzd', 3, 'BZD: sedação + ataxia + hipotensão postural — maior preditor de queda em idoso'),
    ('hipnotico_z', 3, 'Z-drug: sedação noturna, comportamento complexo do sono'),
    ('opioide', 2, 'Sedação + tontura + hipotensão postural');

-- Score 2 (moderado)
INSERT INTO aia_health_drug_fall_risk (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('ssri', 2, 'SSRI aumenta queda em idoso (mecanismo multifatorial)'),
    ('antidepressivo_tetraciclico', 2, 'Mirtazapina: sedação + hipotensão postural');

-- Score 1 (leve, mas conta no acumulado)
INSERT INTO aia_health_drug_fall_risk (therapeutic_class, fall_risk_score, rationale)
VALUES
    ('diuretico_alca', 1, 'Hipotensão postural + tontura'),
    ('diuretico_tiazidico', 1, 'Hipotensão postural'),
    ('ieca', 1, 'Hipotensão de primeira dose'),
    ('ara', 1, 'Hipotensão postural'),
    ('betabloqueador', 1, 'Bradicardia + hipotensão postural');

INSERT INTO aia_health_drug_fall_risk (principle_active, fall_risk_score, rationale)
VALUES
    ('digoxina', 1, 'Bradicardia + tontura por toxicidade');

COMMIT;
