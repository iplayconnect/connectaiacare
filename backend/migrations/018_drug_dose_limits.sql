-- ConnectaIACare — Cruzamento determinístico: dose acima do limite máximo
-- Data: 2026-04-25
--
-- Objetivo:
--   Validar prescrições/cadastros de medicação contra dose máxima diária
--   recomendada. 3 pontos de validação (cadastro manual, OCR, teleconsulta)
--   chamam dose_validator.validate(schedule, patient).
--
-- Fontes (Fase 1 — curadoria manual com referências sólidas):
--   • Bulário Eletrônico ANVISA (bulas oficiais)
--   • Critérios de Beers 2023 (American Geriatrics Society)
--   • Guia Farmacêutico Clínico SBGG (Sociedade Brasileira de Geriatria)
--   • WHO ATC/DDD (Defined Daily Dose, padrão internacional)
--   • FDA package inserts (referência cruzada)
--
-- Fase 2 (futura): cron mensal ingest dataset_aberto ANVISA + LLM extrai
-- limites das bulas oficiais.

BEGIN;

-- =====================================================
-- aia_health_drug_dose_limits — limite máximo diário
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_drug_dose_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Princípio ativo normalizado (lowercase, sem acento)
    principle_active TEXT NOT NULL,
    -- Via: oral|iv|sc|im|topical|inhalation|sublingual|rectal
    route TEXT NOT NULL DEFAULT 'oral',

    -- Dose máxima diária (em unidade base do medicamento)
    max_daily_dose_value NUMERIC(12,4) NOT NULL,
    max_daily_dose_unit TEXT NOT NULL,         -- mg|g|mcg|ml|ui|gota|comprimido

    -- Faixa etária aplicável (default geriatria 60+)
    age_group_min SMALLINT NOT NULL DEFAULT 60,
    age_group_max SMALLINT,                    -- NULL = sem teto

    -- Aviso Beers — alguns medicamentos não têm "dose máxima" mas
    -- devem ser EVITADOS em idosos. Quando true, qualquer prescrição
    -- gera warning, mesmo se dose < max_daily_dose_value.
    beers_avoid BOOLEAN NOT NULL DEFAULT FALSE,
    beers_rationale TEXT,                      -- por quê evitar

    -- Procedência
    source TEXT NOT NULL CHECK (source IN (
        'anvisa', 'beers_2023', 'sbgg', 'who_atc', 'fda', 'manual'
    )),
    source_ref TEXT,                           -- citação/link
    -- Confiabilidade da entrada (0-1). 1.0 = bula oficial; 0.7 = consenso
    -- clínico; 0.5 = manual sem refprovada
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.85,

    -- Notas (ajuste renal, hepático, frequência etc)
    notes TEXT,

    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dose_limits_principle
    ON aia_health_drug_dose_limits(principle_active, route)
    WHERE active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_dose_limits_unique
    ON aia_health_drug_dose_limits(principle_active, route, age_group_min);

-- =====================================================
-- aia_health_drug_aliases — sinônimos / nome comercial
-- =====================================================
-- Resolução de "Tylenol" → "paracetamol", "Novalgina" → "dipirona", etc.
-- Normalização aplicada antes do lookup de limites.
CREATE TABLE IF NOT EXISTS aia_health_drug_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alias TEXT NOT NULL,                       -- nome como aparece (case insensitive)
    principle_active TEXT NOT NULL,            -- canonical normalizado
    -- Tipo do alias
    alias_type TEXT NOT NULL DEFAULT 'brand'   -- brand|synonym|misspelling
        CHECK (alias_type IN ('brand', 'synonym', 'misspelling')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drug_aliases_unique
    ON aia_health_drug_aliases(lower(alias));

-- =====================================================
-- Seed Fase 1 — top medicamentos geriátricos críticos
-- =====================================================
-- Curadoria com base em Beers 2023 + SBGG + bulas ANVISA. Confidence:
--   1.0  = limite explícito da bula oficial
--   0.85 = consenso clínico (Beers + SBGG)
--   0.7  = inferência de literatura

-- ── ANALGÉSICOS / ANTIPIRÉTICOS ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('paracetamol', 'oral', 3000, 'mg', FALSE, 'sbgg',
     'SBGG 2023: dose máxima 3g/dia em idoso (vs 4g/dia adulto) — risco hepatotoxicidade.',
     0.95, 'Reduzir 50% se hepatopatia ou peso < 50kg'),
    ('dipirona', 'oral', 4000, 'mg', FALSE, 'anvisa',
     'Bulário ANVISA: 500-1000mg até 4×/dia.',
     1.0, 'Risco agranulocitose — vigilância em uso prolongado'),

    -- AAS analgésico (NÃO confundir com profilaxia 100mg)
    ('acido acetilsalicilico', 'oral', 4000, 'mg', FALSE, 'anvisa',
     'AAS analgésico: 500-1000mg até 4×/dia.',
     0.95, 'Para profilaxia cardiovascular usa-se 75-100mg/dia separado'),

    -- AINEs em idoso = Beers AVOID (mas ainda registramos limite caso seja usado)
    ('ibuprofeno', 'oral', 2400, 'mg', TRUE, 'beers_2023',
     'Beers 2023: AINEs evitar em idoso (risco GI, renal, cardiovascular).',
     0.95, 'Evitar uso > 7 dias. Se necessário, ≤ 1200mg/dia'),
    ('naproxeno', 'oral', 1000, 'mg', TRUE, 'beers_2023',
     'Beers 2023: AINEs evitar em idoso.',
     0.95, NULL),
    ('diclofenaco', 'oral', 150, 'mg', TRUE, 'beers_2023',
     'Beers 2023: AINEs evitar em idoso.',
     0.95, NULL),
    ('cetoprofeno', 'oral', 200, 'mg', TRUE, 'beers_2023',
     'Beers 2023: AINEs evitar em idoso.',
     0.9, NULL);

-- ── OPIOIDES ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('tramadol', 'oral', 400, 'mg', FALSE, 'anvisa',
     'Bulário ANVISA: 50-100mg 4-6×/dia, máximo 400mg/dia.',
     0.95, 'Beers: evitar uso prolongado em idoso (risco hiponatremia, queda)'),
    ('codeina', 'oral', 360, 'mg', TRUE, 'beers_2023',
     'Beers 2023: opióide com forte sedação em idoso, evitar.',
     0.9, 'Avaliar oxicodona/morfina em vez');

-- ── BENZODIAZEPÍNICOS — TODOS Beers AVOID ──
-- Não têm "dose máxima" pra idoso pq devem ser evitados. Quando usados,
-- registramos dose teto baixa pra alertar excesso.
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, beers_rationale, source, source_ref, confidence, notes)
VALUES
    ('alprazolam', 'oral', 0.75, 'mg', TRUE,
     'Risco de queda, fratura, declínio cognitivo, dependência. Meia-vida prolongada em idoso.',
     'beers_2023', 'Beers 2023 — Strong recommendation: avoid', 0.98,
     'Se uso inevitável, taper gradual'),
    ('diazepam', 'oral', 5, 'mg', TRUE,
     'Acumulação de metabólitos ativos em idoso. Alto risco queda/sedação.',
     'beers_2023', 'Beers 2023 — Strong avoid', 0.98, NULL),
    ('clonazepam', 'oral', 1, 'mg', TRUE,
     'Risco queda + dependência. Meia-vida longa potencializa em idoso.',
     'beers_2023', 'Beers 2023 — Strong avoid', 0.98, NULL),
    ('lorazepam', 'oral', 2, 'mg', TRUE,
     'Único BZD aceitável em curto prazo se inevitável (sem metabólito ativo).',
     'beers_2023', 'Beers 2023 — Avoid (preferred BZD se necessário)', 0.95,
     'Se essencial, ≤ 1mg/dia'),
    ('zolpidem', 'oral', 5, 'mg', TRUE,
     'Risco queda noturna, comportamento complexo do sono.',
     'beers_2023', 'Beers 2023 — Avoid > 90 dias', 0.95, NULL);

-- ── CARDIOVASCULAR ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('digoxina', 'oral', 0.125, 'mg', FALSE, 'beers_2023',
     'Beers 2023: > 0.125mg/dia em idoso aumenta risco toxicidade sem benefício.',
     0.98, 'Suspender se ClCr < 30. Monitorar nível sérico'),
    ('losartana', 'oral', 100, 'mg', FALSE, 'anvisa',
     'Bulário: 25-100mg 1×/dia.',
     0.95, NULL),
    ('enalapril', 'oral', 40, 'mg', FALSE, 'anvisa',
     'Bulário: dose máxima 40mg/dia (1-2×/dia).',
     0.95, NULL),
    ('captopril', 'oral', 150, 'mg', FALSE, 'anvisa',
     'Bulário: 50mg 3×/dia.',
     0.95, NULL),
    ('atenolol', 'oral', 100, 'mg', FALSE, 'anvisa',
     'Bulário: 50-100mg 1×/dia.',
     0.95, 'Idoso: iniciar 25mg'),
    ('metoprolol', 'oral', 400, 'mg', FALSE, 'anvisa',
     'Bulário: tartarato até 400mg/dia; succinato até 200mg/dia.',
     0.9, 'Especificar formulação na prescrição'),
    ('furosemida', 'oral', 160, 'mg', FALSE, 'anvisa',
     'Bulário: 20-80mg 1-2×/dia, máx 160mg/dia oral.',
     0.95, 'Risco desidratação/hipocalemia em idoso'),
    ('hidroclorotiazida', 'oral', 25, 'mg', FALSE, 'sbgg',
     'SBGG: doses > 25mg sem benefício adicional, mais efeitos colaterais.',
     0.9, 'Risco hiponatremia em idoso'),
    ('varfarina', 'oral', 10, 'mg', FALSE, 'manual',
     'Dose individualizada por INR (alvo 2.0-3.0). Limite teto pra alerta.',
     0.6, 'Sempre ajustar por INR. Considerar DOAC em fibrilação atrial'),
    ('clopidogrel', 'oral', 75, 'mg', FALSE, 'anvisa',
     'Bulário: 75mg 1×/dia.',
     0.95, NULL),
    ('sinvastatina', 'oral', 40, 'mg', FALSE, 'fda',
     'FDA 2011: 80mg/dia retirado do mercado por miopatia. Limite 40mg.',
     1.0, 'Considerar atorvastatina/rosuvastatina'),
    ('atorvastatina', 'oral', 80, 'mg', FALSE, 'anvisa',
     'Bulário: 10-80mg 1×/dia.',
     0.95, NULL);

-- ── ANTIDIABÉTICOS ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('metformina', 'oral', 2550, 'mg', FALSE, 'anvisa',
     'Bulário: 500-2550mg/dia divididos.',
     0.95, 'Suspender se ClCr < 30. Reavaliar 30-45'),
    ('glibenclamida', 'oral', 20, 'mg', TRUE, 'beers_2023',
     'Beers 2023: hipoglicemia prolongada em idoso (meia-vida longa).',
     0.98, 'Preferir glipizida ou DPP-4'),
    ('glicazida', 'oral', 320, 'mg', FALSE, 'anvisa',
     'Bulário: liberação modificada até 120mg; convencional até 320mg.',
     0.9, 'Beers: risco hipoglicemia mais aceitável que glibenclamida');

-- ── PSIQUIATRIA ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('sertralina', 'oral', 200, 'mg', FALSE, 'anvisa',
     'Bulário: 50-200mg/dia.',
     0.95, 'Beers: monitorar hiponatremia em idoso'),
    ('fluoxetina', 'oral', 80, 'mg', FALSE, 'anvisa',
     'Bulário: 20-80mg/dia.',
     0.95, 'Beers: meia-vida longa, evitar uso prolongado em idoso'),
    ('escitalopram', 'oral', 20, 'mg', FALSE, 'fda',
     'FDA: > 20mg/dia em idoso aumenta QT.',
     0.95, 'Citalopram: máx 20mg em idoso (FDA box warning)'),
    ('mirtazapina', 'oral', 45, 'mg', FALSE, 'anvisa',
     'Bulário: 15-45mg 1×/dia à noite.',
     0.95, NULL);

-- ── DEMÊNCIA ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('donepezila', 'oral', 10, 'mg', FALSE, 'anvisa',
     'Bulário: 5-10mg 1×/dia.',
     0.95, NULL),
    ('rivastigmina', 'oral', 12, 'mg', FALSE, 'anvisa',
     'Bulário: oral até 12mg/dia (6mg 2×).',
     0.95, NULL),
    ('memantina', 'oral', 20, 'mg', FALSE, 'anvisa',
     'Bulário: titulação 5→20mg/dia.',
     0.95, NULL);

-- ── GASTRO ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('omeprazol', 'oral', 40, 'mg', FALSE, 'anvisa',
     'Bulário: 20-40mg 1×/dia.',
     0.95, 'Beers: uso > 8 semanas aumenta risco fratura/C.difficile/B12 baixa'),
    ('pantoprazol', 'oral', 40, 'mg', FALSE, 'anvisa',
     'Bulário: 40mg 1×/dia.',
     0.95, 'Mesma observação Beers que omeprazol');

-- ── ENDÓCRINO ──
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     beers_avoid, source, source_ref, confidence, notes)
VALUES
    ('levotiroxina', 'oral', 200, 'mcg', FALSE, 'anvisa',
     'Bulário: dose individualizada por TSH. Teto típico 200mcg/dia.',
     0.7, 'Idoso: iniciar 12.5-25mcg, ajustar TSH alvo 1-2.5'),
    ('prednisona', 'oral', 60, 'mg', FALSE, 'manual',
     'Uso curto: até 60mg/dia. Teto pra alertar uso prolongado > 20mg/dia.',
     0.7, 'Beers: evitar uso prolongado (osteoporose, diabetes, glaucoma)');

-- =====================================================
-- Seed aliases (top brands brasileiros)
-- =====================================================
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type, notes) VALUES
    -- paracetamol
    ('Tylenol', 'paracetamol', 'brand', NULL),
    ('Tylex', 'paracetamol', 'brand', 'Combinação: contém também codeína!'),
    -- dipirona
    ('Novalgina', 'dipirona', 'brand', NULL),
    ('Anador', 'dipirona', 'brand', NULL),
    -- AAS
    ('Aspirina', 'acido acetilsalicilico', 'brand', NULL),
    ('AAS', 'acido acetilsalicilico', 'synonym', NULL),
    ('AAS Infantil', 'acido acetilsalicilico', 'brand', 'Profilaxia 100mg'),
    -- AINEs
    ('Advil', 'ibuprofeno', 'brand', NULL),
    ('Alivium', 'ibuprofeno', 'brand', NULL),
    ('Voltaren', 'diclofenaco', 'brand', NULL),
    ('Cataflam', 'diclofenaco', 'brand', NULL),
    -- Opioides / analgesia forte
    ('Tylex', 'codeina', 'brand', 'Combinação: contém paracetamol+codeína'),
    -- BZDs
    ('Frontal', 'alprazolam', 'brand', NULL),
    ('Apraz', 'alprazolam', 'brand', NULL),
    ('Valium', 'diazepam', 'brand', NULL),
    ('Rivotril', 'clonazepam', 'brand', NULL),
    ('Lorax', 'lorazepam', 'brand', NULL),
    ('Stilnox', 'zolpidem', 'brand', NULL),
    -- Cardiovascular
    ('Atensina', 'losartana', 'brand', NULL),
    ('Cozaar', 'losartana', 'brand', NULL),
    ('Renitec', 'enalapril', 'brand', NULL),
    ('Capoten', 'captopril', 'brand', NULL),
    ('Atenol', 'atenolol', 'brand', NULL),
    ('Selozok', 'metoprolol', 'brand', NULL),
    ('Lasix', 'furosemida', 'brand', NULL),
    ('Marevan', 'varfarina', 'brand', NULL),
    ('Plavix', 'clopidogrel', 'brand', NULL),
    ('Sinvascor', 'sinvastatina', 'brand', NULL),
    ('Lipitor', 'atorvastatina', 'brand', NULL),
    -- Diabetes
    ('Glifage', 'metformina', 'brand', NULL),
    ('Glucoformin', 'metformina', 'brand', NULL),
    ('Daonil', 'glibenclamida', 'brand', NULL),
    ('Diamicron', 'glicazida', 'brand', NULL),
    -- Psiquiatria
    ('Zoloft', 'sertralina', 'brand', NULL),
    ('Prozac', 'fluoxetina', 'brand', NULL),
    ('Lexapro', 'escitalopram', 'brand', NULL),
    ('Remeron', 'mirtazapina', 'brand', NULL),
    -- Demência
    ('Eranz', 'donepezila', 'brand', NULL),
    ('Exelon', 'rivastigmina', 'brand', NULL),
    ('Ebix', 'memantina', 'brand', NULL),
    -- Gastro
    ('Losec', 'omeprazol', 'brand', NULL),
    ('Pantozol', 'pantoprazol', 'brand', NULL),
    -- Endócrino
    ('Puran T4', 'levotiroxina', 'brand', NULL),
    ('Synthroid', 'levotiroxina', 'brand', NULL),
    ('Meticorten', 'prednisona', 'brand', NULL)
ON CONFLICT (lower(alias)) DO NOTHING;

-- =====================================================
-- Trigger updated_at
-- =====================================================
DROP TRIGGER IF EXISTS trg_dose_limits_updated_at ON aia_health_drug_dose_limits;
CREATE TRIGGER trg_dose_limits_updated_at
    BEFORE UPDATE ON aia_health_drug_dose_limits
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_users_set_updated_at();

COMMIT;
