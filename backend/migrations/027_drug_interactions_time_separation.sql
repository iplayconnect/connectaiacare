-- ConnectaIACare — Interações resolvíveis por espaçamento de horário
-- Data: 2026-04-25
--
-- Adiciona suporte a interações de ABSORÇÃO/QUELAÇÃO que podem ser
-- mitigadas separando os horários das tomadas. Diferente das interações
-- farmacodinâmicas (sangramento, depressão respiratória) que persistem
-- independente do horário.
--
-- Mecânica:
--   • aia_health_drug_interactions ganha 3 colunas:
--     - time_separation_minutes (NULL = sistêmica; N = pode mitigar com N min)
--     - separation_strategy ('a_first', 'b_first', 'any')
--     - food_warning (texto: instrução adicional sobre alimento/jejum)
--   • Validator compara times_of_day dos schedules e:
--     - Se diff >= time_separation_minutes → silencia (resolvido por espaçamento)
--     - Se diff < threshold → emite warning específico com sugestão de horário

BEGIN;

-- =====================================================
-- 1. ALTER aia_health_drug_interactions
-- =====================================================
ALTER TABLE aia_health_drug_interactions
    ADD COLUMN IF NOT EXISTS time_separation_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS separation_strategy TEXT
        CHECK (separation_strategy IS NULL OR separation_strategy IN
            ('a_first', 'b_first', 'any')),
    ADD COLUMN IF NOT EXISTS food_warning TEXT;

CREATE INDEX IF NOT EXISTS idx_drug_interactions_separation
    ON aia_health_drug_interactions(time_separation_minutes)
    WHERE active = TRUE AND time_separation_minutes IS NOT NULL;

-- =====================================================
-- 2. Adicionar princípios ativos novos pra cobrir os pares
-- =====================================================
INSERT INTO aia_health_drug_dose_limits
    (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
     therapeutic_class, source, source_ref, confidence, notes) VALUES

    -- Bifosfonato (osteoporose)
    ('alendronato', 'oral', 70, 'mg', 'bifosfonato', 'anvisa',
     'Bulário Fosamax: 70mg 1×/sem (osteoporose) ou 10mg/dia.',
     0.95, 'Tomar em jejum com água, ficar de pé 30-60min.'),

    -- Sulfato ferroso
    ('sulfato ferroso', 'oral', 600, 'mg', 'suplemento_ferro', 'anvisa',
     'Bulário: 200-600mg/dia divididos. Cada cp 40mg ferro elementar.',
     0.9, 'Absorção melhor em jejum + vitamina C; pior com chá/café/leite/cálcio.'),

    -- Cálcio (suplemento, comum em idoso)
    ('carbonato de calcio', 'oral', 1500, 'mg', 'suplemento_calcio', 'anvisa',
     'Suplementação cálcio elementar 500-1500mg/dia (osteoporose).',
     0.9, 'Tomar com refeição (carbonato exige acidez gástrica).'),

    -- Quinolonas (antibióticos)
    ('ciprofloxacino', 'oral', 1500, 'mg', 'quinolona', 'anvisa',
     'Bulário: 250-750mg 12/12h.', 0.95, 'Beers: avoid em idoso > 7d (tendinopatia).'),

    ('levofloxacino', 'oral', 750, 'mg', 'quinolona', 'anvisa',
     'Bulário: 250-750mg/dia 1×.', 0.95, 'Mesma observação Beers que cipro.'),

    -- Domperidona (procinético sem efeitos centrais — alternativa à metoclopramida)
    ('domperidona', 'oral', 30, 'mg', 'procinetico_d2_periferico', 'anvisa',
     'Bulário Motilium: 10mg 3×/dia antes das refeições.',
     0.9, 'Diferente de metoclopramida: não cruza BHE → não causa SEP. ANVISA limita uso curto pelo risco prolongamento QT.'),

    -- Antiácidos comuns
    ('hidroxido de aluminio', 'oral', 3600, 'mg', 'antiacido', 'anvisa',
     'Bulário: 600mg 4-6×/dia.', 0.85, 'Quela cátions metálicos no TGI.'),
    ('hidroxido de magnesio', 'oral', 4800, 'mg', 'antiacido', 'anvisa',
     'Bulário: 400-800mg 4-6×/dia.', 0.85, NULL)
ON CONFLICT (principle_active, route, age_group_min) DO NOTHING;

-- Aliases brasileiros
INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type) VALUES
    -- Bifosfonato
    ('Fosamax', 'alendronato', 'brand'),
    ('Endronax', 'alendronato', 'brand'),
    ('Osteoform', 'alendronato', 'brand'),
    ('Acido alendronico', 'alendronato', 'synonym'),

    -- Ferro
    ('Iberol', 'sulfato ferroso', 'brand'),
    ('Combiron', 'sulfato ferroso', 'brand'),
    ('Hemax', 'sulfato ferroso', 'brand'),
    ('Sulfato Ferroso', 'sulfato ferroso', 'synonym'),

    -- Cálcio
    ('Caltrate', 'carbonato de calcio', 'brand'),
    ('Os-Cal', 'carbonato de calcio', 'brand'),
    ('Calcio +D', 'carbonato de calcio', 'brand'),

    -- Quinolonas
    ('Cipro', 'ciprofloxacino', 'brand'),
    ('Ciproxin', 'ciprofloxacino', 'brand'),
    ('Floxacin', 'ciprofloxacino', 'brand'),
    ('Tavanic', 'levofloxacino', 'brand'),
    ('Levaquin', 'levofloxacino', 'brand'),

    -- Domperidona
    ('Motilium', 'domperidona', 'brand'),
    ('Peridona', 'domperidona', 'brand'),

    -- Antiácidos
    ('Maalox', 'hidroxido de aluminio', 'brand'),
    ('Mylanta', 'hidroxido de aluminio', 'brand'),
    ('Estomazil', 'hidroxido de aluminio', 'brand'),
    ('Leite de Magnesia', 'hidroxido de magnesio', 'brand')
ON CONFLICT (lower(alias)) DO NOTHING;

-- =====================================================
-- 3. INTERAÇÕES DE ABSORÇÃO/QUELAÇÃO (resolvíveis por espaçamento)
-- =====================================================

-- ── LEVOTIROXINA: absorção crítica em jejum, quelada por cátions ──
-- Levotiroxina ↔ cálcio
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('carbonato de calcio', 'levotiroxina', 'moderate',
     'Chelation in GI tract',
     'Cálcio quela levotiroxina no TGI, reduzindo absorção em até 30-40%.',
     'Tomar levotiroxina em jejum (>30min antes do café) e cálcio pelo menos 4h depois.',
     'lexicomp', 0.95,
     240, 'b_first',
     'Levotiroxina exige jejum estrito de 30min antes do desjejum. Cálcio só após o desjejum.');

-- Levotiroxina ↔ ferro
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('levotiroxina', 'sulfato ferroso', 'moderate',
     'Chelation in GI tract',
     'Ferro quela levotiroxina no TGI; absorção da L-T4 cai significativamente.',
     'Tomar levotiroxina em jejum + ferro pelo menos 4h depois.',
     'lexicomp', 0.95,
     240, 'a_first',
     'Levotiroxina jejum estrito. Ferro pode ser na refeição do almoço.');

-- Levotiroxina ↔ IBP
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('levotiroxina', 'omeprazol', 'moderate',
     'Reduced absorption (gastric acid)',
     'IBP reduz acidez gástrica e prejudica dissolução da levotiroxina; pode reduzir efeito da L-T4 em 20-30%.',
     'Manter horários separados: L-T4 ao acordar em jejum; IBP antes do café (≥4h depois).',
     'stockleys', 0.85,
     240, 'a_first',
     NULL),
    ('levotiroxina', 'pantoprazol', 'moderate',
     'Reduced absorption (gastric acid)',
     'Mesmo efeito dos IBPs sobre L-T4.',
     'Espaçar ≥4h.',
     'stockleys', 0.85,
     240, 'a_first',
     NULL);

-- ── BIFOSFONATO: absorção crítica em jejum ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('alendronato', 'carbonato de calcio', 'major',
     'Chelation → drastic absorption loss',
     'Cálcio quela alendronato; absorção do bifosfonato cai >90% se tomados juntos. Sem efeito antiosteoporótico.',
     'Alendronato em jejum ESTRITO 30min antes do desjejum (água apenas). Cálcio ≥2h depois ou junto com refeição posterior.',
     'lexicomp', 0.97,
     120, 'a_first',
     'Alendronato exige jejum estrito 30min de pé. Cálcio só após esse intervalo.'),
    ('alendronato', 'sulfato ferroso', 'major',
     'Chelation in GI tract',
     'Ferro quela alendronato — perda de absorção.',
     'Alendronato em jejum, ferro ≥2h depois.',
     'lexicomp', 0.95,
     120, 'a_first',
     NULL);

-- ── QUINOLONAS: queladas por cátions polivalentes ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('ciprofloxacino', 'carbonato de calcio', 'major',
     'Chelation → reduced absorption',
     'Cálcio quela ciprofloxacino; absorção cai em até 50%, pode comprometer eficácia antibiótica.',
     'Ciprofloxacino 2h antes ou ≥6h depois do cálcio.',
     'lexicomp', 0.97,
     360, 'any',
     NULL),
    ('ciprofloxacino', 'sulfato ferroso', 'major',
     'Chelation → reduced absorption',
     'Ferro quela ciprofloxacino; perda de absorção significativa.',
     'Ciprofloxacino 2h antes ou ≥6h depois do ferro.',
     'lexicomp', 0.97,
     360, 'any',
     NULL),
    ('ciprofloxacino', 'hidroxido de aluminio', 'major',
     'Chelation by Al',
     'Antiácido com alumínio quela ciprofloxacino fortemente.',
     'Espaçar ≥6h.',
     'lexicomp', 0.95,
     360, 'any',
     NULL),
    ('ciprofloxacino', 'hidroxido de magnesio', 'major',
     'Chelation by Mg',
     'Antiácido com magnésio quela ciprofloxacino.',
     'Espaçar ≥6h.',
     'lexicomp', 0.95,
     360, 'any',
     NULL),
    ('carbonato de calcio', 'levofloxacino', 'major',
     'Chelation → reduced absorption',
     'Mesmo mecanismo cipro/cálcio.',
     'Espaçar ≥6h.',
     'lexicomp', 0.97,
     360, 'any',
     NULL),
    ('levofloxacino', 'sulfato ferroso', 'major',
     'Chelation → reduced absorption',
     'Mesmo mecanismo de cipro+ferro.',
     'Espaçar ≥6h.',
     'lexicomp', 0.97,
     360, 'any',
     NULL);

-- ── FERRO: absorção pior com IBP/antiácido ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('omeprazol', 'sulfato ferroso', 'moderate',
     'Reduced iron absorption (low gastric acid)',
     'IBP reduz acidez e prejudica a redução de ferro férrico (Fe³⁺) a ferroso (Fe²⁺), absorvível. Reposição pode falhar.',
     'Tomar ferro 1h antes do desjejum (ou seja, antes do IBP) ou ≥2h após.',
     'stockleys', 0.85,
     120, 'b_first',
     'Ferro absorve melhor em jejum; vitamina C melhora absorção. Evitar com café/chá/leite.'),
    ('hidroxido de aluminio', 'sulfato ferroso', 'moderate',
     'Reduced iron absorption',
     'Antiácido reduz absorção do ferro.',
     'Espaçar ≥2h.',
     'lexicomp', 0.85,
     120, 'b_first',
     NULL);

-- ── LEVODOPA: queladas por ferro; competição com proteínas ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('levodopa', 'sulfato ferroso', 'moderate',
     'Chelation → reduced levodopa absorption',
     'Ferro quela levodopa, reduzindo absorção e flutuando o controle motor.',
     'Levodopa 30min antes da refeição; ferro pelo menos 2h depois (ou em outra refeição).',
     'lexicomp', 0.85,
     120, 'a_first',
     'Levodopa também sofre com refeições proteicas (competição transporte aminoácidos) — preferir tomar 30min antes da refeição.');

-- ── DOMPERIDONA: requer ácido gástrico (não junto com IBP/antiácido) ──
INSERT INTO aia_health_drug_interactions
    (principle_a, principle_b, severity, mechanism, clinical_effect,
     recommendation, source, confidence,
     time_separation_minutes, separation_strategy, food_warning)
VALUES
    ('domperidona', 'omeprazol', 'minor',
     'Reduced absorption (low gastric acid)',
     'Domperidona absorve melhor em meio ácido; IBP pode reduzir biodisponibilidade.',
     'Tomar domperidona 30min antes da refeição. IBP no início ou após o desjejum.',
     'stockleys', 0.7,
     30, 'a_first',
     'Domperidona é antiemético procinético — sempre 30min antes da refeição.');

-- ── DUPLICIDADE QUINOLONAS ──
INSERT INTO aia_health_drug_interactions
    (class_a, class_b, severity, mechanism, clinical_effect, recommendation, source, confidence)
VALUES
    ('quinolona', 'quinolona', 'major',
     'Duplicate class',
     'Duas quinolonas simultâneas: efeitos adversos somados (tendinopatia, QT, neuropatia).',
     'Suspender uma.',
     'manual', 0.95);

COMMIT;
