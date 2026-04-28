-- ConnectaIACare — RENAME 2024 como base oficial de cobertura.
--
-- RENAME = Relação Nacional de Medicamentos Essenciais (Ministério da
-- Saúde / CONITEC). Define os medicamentos disponíveis no SUS.
--
-- Decisão estratégica: o motor adota RENAME 2024 como base oficial de
-- cobertura. Cada fármaco no motor tem flag declarada de pertencimento
-- à lista + componente correspondente (Básico/Estratégico/Especializado).
--
-- Meta: cobertura 100% do RENAME 2024 Componente Básico relevante para
-- adultos/idosos (~150 princípios ativos, vs 48 atuais).

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Estende aia_health_drug_dose_limits com flags RENAME
--    (essa é a tabela canônica que enumera princípios ativos do motor)
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_drug_dose_limits
    ADD COLUMN IF NOT EXISTS in_rename BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS rename_componente TEXT
        CHECK (rename_componente IS NULL OR rename_componente IN (
            'basico', 'estrategico', 'especializado'
        )),
    -- Edição/ano da RENAME (preparação pra atualizações futuras: 2024, 2026...)
    ADD COLUMN IF NOT EXISTS rename_edicao TEXT,
    -- Notas específicas RENAME (forma farmacêutica disponível no SUS,
    -- restrições de uso, etc)
    ADD COLUMN IF NOT EXISTS rename_notes TEXT;

COMMENT ON COLUMN aia_health_drug_dose_limits.in_rename IS
    'TRUE se o princípio ativo está em RENAME 2024 (qualquer componente).';
COMMENT ON COLUMN aia_health_drug_dose_limits.rename_componente IS
    'basico = atenção primária | estrategico = HIV/TB/notificação compulsória | '
    'especializado = alto custo/raras';
COMMENT ON COLUMN aia_health_drug_dose_limits.rename_edicao IS
    'Edição RENAME (ex: "2024", "2026"). Permite tracking de mudanças entre edições.';


-- ════════════════════════════════════════════════════════════════
-- 2. Tabela RENAME canônica — fonte da verdade do que está em RENAME
--    Pode ter fármacos AINDA NÃO COBERTOS pelo motor (gap explícito)
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_rename_drugs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Princípio ativo canônico (mesmo formato de aia_health_drug_dose_limits)
    principle_active TEXT NOT NULL,
    componente TEXT NOT NULL CHECK (componente IN (
        'basico', 'estrategico', 'especializado'
    )),
    edicao TEXT NOT NULL DEFAULT '2024',
    -- Forma farmacêutica disponível no SUS (comprimido, solução oral,
    -- injetável, etc) — pode ter múltiplas formas por princípio
    formas_disponiveis TEXT[] NOT NULL DEFAULT '{}',
    -- Subgrupo farmacológico/terapêutico conforme RENAME
    grupo_terapeutico TEXT,
    -- Faixa etária / população alvo (adulto, pediatria, gestante, idoso)
    populacao_alvo TEXT[],
    -- Indicação primária no SUS
    indicacao_sus TEXT,
    -- Notas (restrições de uso, condições especiais, etc)
    notes TEXT,
    -- Relevância pra cuidado geriátrico (high/medium/low/excluded)
    geriatric_relevance TEXT NOT NULL DEFAULT 'medium' CHECK (
        geriatric_relevance IN ('high', 'medium', 'low', 'excluded')
    ),
    -- Status de cobertura pelo motor
    motor_coverage TEXT NOT NULL DEFAULT 'pending' CHECK (
        motor_coverage IN ('covered', 'pending', 'in_progress', 'not_applicable')
    ),
    -- Auditoria
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reviewed_at TIMESTAMPTZ,
    last_reviewed_by TEXT,
    notes_curador TEXT,
    UNIQUE (principle_active, edicao)
);

CREATE INDEX IF NOT EXISTS idx_rename_drugs_componente
    ON aia_health_rename_drugs(componente, geriatric_relevance);
CREATE INDEX IF NOT EXISTS idx_rename_drugs_coverage
    ON aia_health_rename_drugs(motor_coverage)
    WHERE motor_coverage IN ('pending', 'in_progress');


-- ════════════════════════════════════════════════════════════════
-- 3. Marca os 48 princípios ativos atuais como in_rename onde aplicável
--    (curadoria preliminar baseada em conhecimento público de RENAME 2024)
-- ════════════════════════════════════════════════════════════════
UPDATE aia_health_drug_dose_limits
SET in_rename = TRUE,
    rename_componente = 'basico',
    rename_edicao = '2024'
WHERE principle_active IN (
    -- Anti-hipertensivos (RENAME Componente Básico)
    'losartana', 'enalapril', 'anlodipino', 'propranolol',
    'atenolol', 'metoprolol', 'carvedilol',
    -- Antidiabéticos
    'metformina', 'glibenclamida', 'gliclazida',
    -- Antiplaquetários/Anticoagulantes (alguns)
    'acido acetilsalicilico', 'clopidogrel', 'varfarina',
    -- Estatinas
    'sinvastatina', 'atorvastatina',
    -- IBPs
    'omeprazol',
    -- Antidepressivos
    'fluoxetina', 'sertralina',
    -- Hipnóticos/ansiolíticos
    'clonazepam', 'diazepam',
    -- Antipsicóticos
    'haloperidol', 'risperidona',
    -- Antiparkinsoniano
    'levodopa+carbidopa',
    -- Antieméticos
    'metoclopramida', 'ondansetrona',
    -- Antibióticos
    'amoxicilina', 'amoxicilina+clavulanato', 'azitromicina',
    'ciprofloxacino', 'sulfa+trimetoprima',
    -- Outros
    'paracetamol', 'dipirona', 'ibuprofeno',
    'alendronato', 'levotiroxina', 'carbonato de cálcio'
);

-- Marca os que NÃO estão em RENAME (DOACs novos, antipsicóticos atípicos
-- não-RENAME, etc) explicitamente como FALSE (já é default mas explicita)
UPDATE aia_health_drug_dose_limits
SET in_rename = FALSE,
    rename_componente = NULL,
    rename_notes = 'Não consta em RENAME 2024 — adoção via prática privada'
WHERE principle_active IN (
    'rivaroxabana', 'apixabana', 'dabigatrana',  -- DOACs (em RENAME 2024 Especializado parcial)
    'rosuvastatina',                              -- estatina mais nova
    'empagliflozina', 'dapagliflozina',          -- SGLT2
    'pantoprazol', 'esomeprazol',                -- IBPs alternativos
    'escitalopram', 'mirtazapina',               -- antidepressivos novos
    'alprazolam', 'zolpidem',                     -- hipnóticos não-RENAME
    'quetiapina', 'olanzapina',                   -- atípicos
    'pramipexol', 'ropinirol',                    -- antiparkinsonianos novos
    'naproxeno', 'diclofenaco'                    -- AINEs alternativos
);


-- ════════════════════════════════════════════════════════════════
-- 4. Seed inicial da tabela aia_health_rename_drugs com gaps prioritários
--    (fármacos em RENAME 2024 que AINDA NÃO estão no motor — alvo do sprint)
-- ════════════════════════════════════════════════════════════════
INSERT INTO aia_health_rename_drugs
    (principle_active, componente, edicao, formas_disponiveis,
     grupo_terapeutico, populacao_alvo, indicacao_sus,
     geriatric_relevance, motor_coverage, notes)
VALUES
    -- Diuréticos
    ('hidroclorotiazida', 'basico', '2024', ARRAY['comprimido'],
     'Diurético tiazídico', ARRAY['adulto', 'idoso'],
     'Hipertensão, edema', 'high', 'pending',
     'Geriatria: cuidado com hiponatremia, hiperuricemia, hipocalemia'),
    ('furosemida', 'basico', '2024', ARRAY['comprimido', 'injetável'],
     'Diurético de alça', ARRAY['adulto', 'idoso'],
     'IC descompensada, edema, IRC', 'high', 'pending',
     'Geriatria: ototoxicidade em alta dose, hipocalemia, depleção de volume'),
    ('espironolactona', 'basico', '2024', ARRAY['comprimido'],
     'Diurético poupador de potássio', ARRAY['adulto', 'idoso'],
     'IC, hiperaldosteronismo, ascite cirrótica', 'high', 'pending',
     'Geriatria: monitorar K+ rigoroso, especialmente com IECA/BRA'),

    -- Insulinas
    ('insulina_nph', 'basico', '2024', ARRAY['injetável'],
     'Insulina basal', ARRAY['adulto', 'idoso'],
     'DM1, DM2', 'high', 'pending',
     'Schema diferente das demais — dose baseada em peso/glicemia, não fixa'),
    ('insulina_regular', 'basico', '2024', ARRAY['injetável'],
     'Insulina rápida', ARRAY['adulto', 'idoso'],
     'DM1, DM2 com hiperglicemia pós-prandial', 'high', 'pending',
     'Risco hipoglicemia em idoso — uso cuidadoso'),

    -- Corticoides sistêmicos
    ('prednisona', 'basico', '2024', ARRAY['comprimido'],
     'Glicocorticoide', ARRAY['adulto', 'idoso'],
     'Inflamação, autoimune, exacerbação DPOC/asma', 'high', 'pending',
     'Cascata: prednisona → hiperglicemia → antidiabético (já mapeada)'),
    ('prednisolona', 'basico', '2024', ARRAY['comprimido', 'solução oral'],
     'Glicocorticoide', ARRAY['adulto', 'idoso', 'pediatria'],
     'Inflamação, autoimune', 'high', 'pending', NULL),
    ('dexametasona', 'basico', '2024',
     ARRAY['comprimido', 'injetável', 'colírio', 'creme'],
     'Glicocorticoide potente', ARRAY['adulto', 'idoso'],
     'Inflamação severa, edema cerebral, antiemético oncológico',
     'high', 'pending', NULL),
    ('hidrocortisona', 'basico', '2024', ARRAY['injetável', 'creme'],
     'Glicocorticoide', ARRAY['adulto', 'idoso'],
     'Insuficiência adrenal, choque', 'medium', 'pending', NULL),

    -- BCCa não-DHP
    ('verapamil', 'basico', '2024', ARRAY['comprimido'],
     'BCCa não-dihidropiridínico', ARRAY['adulto', 'idoso'],
     'HAS, FA, taquicardia supraventricular', 'high', 'pending',
     'Geriatria: bradicardia, constipação. Contraind. em IC sistólica'),
    ('diltiazem', 'basico', '2024', ARRAY['comprimido'],
     'BCCa não-dihidropiridínico', ARRAY['adulto', 'idoso'],
     'HAS, FA, angina', 'high', 'pending',
     'Geriatria: similar verapamil mas menos constipante'),

    -- Inibidores de colinesterase + memantina (demência)
    ('donepezila', 'especializado', '2024', ARRAY['comprimido'],
     'Inibidor colinesterase', ARRAY['idoso'],
     'Demência Alzheimer leve a moderada', 'high', 'pending',
     'Componente Especializado RENAME — alto custo. Cascata: bradicardia'),
    ('rivastigmina', 'especializado', '2024',
     ARRAY['cápsula', 'adesivo transdérmico'],
     'Inibidor colinesterase', ARRAY['idoso'],
     'Demência Alzheimer, Parkinson com demência', 'high', 'pending', NULL),
    ('galantamina', 'especializado', '2024', ARRAY['comprimido'],
     'Inibidor colinesterase', ARRAY['idoso'],
     'Demência Alzheimer leve a moderada', 'high', 'pending', NULL),
    ('memantina', 'especializado', '2024', ARRAY['comprimido'],
     'Antagonista NMDA', ARRAY['idoso'],
     'Demência Alzheimer moderada a grave', 'high', 'pending',
     'Ajuste renal obrigatório — ClCr<30 reduzir dose'),

    -- Anticonvulsivantes / dor neuropática
    ('carbamazepina', 'basico', '2024', ARRAY['comprimido', 'suspensão'],
     'Anticonvulsivante', ARRAY['adulto', 'idoso'],
     'Epilepsia, neuralgia trigeminal', 'high', 'pending',
     'Geriatria: hiponatremia, indução enzimática (interações)'),
    ('valproato_sodico', 'basico', '2024',
     ARRAY['comprimido', 'cápsula', 'xarope'],
     'Anticonvulsivante', ARRAY['adulto', 'idoso'],
     'Epilepsia, transtorno bipolar, profilaxia enxaqueca',
     'medium', 'pending',
     'Hepatotoxicidade, plaquetopenia. Ajuste hepático obrigatório'),
    ('fenitoina', 'basico', '2024', ARRAY['comprimido', 'injetável'],
     'Anticonvulsivante', ARRAY['adulto', 'idoso'],
     'Epilepsia', 'medium', 'pending',
     'Janela terapêutica estreita, muitas interações, hiperplasia gengival'),
    ('gabapentina', 'basico', '2024', ARRAY['cápsula', 'comprimido'],
     'Anticonvulsivante / dor neuropática', ARRAY['adulto', 'idoso'],
     'Epilepsia, dor neuropática, neuralgia pós-herpética',
     'high', 'pending',
     'Ajuste renal obrigatório. Sedação em idoso'),

    -- Broncodilatadores
    ('salbutamol', 'basico', '2024',
     ARRAY['aerosol', 'solução para nebulização'],
     'Beta-2 agonista curta ação', ARRAY['adulto', 'idoso', 'pediatria'],
     'Asma, DPOC — alívio agudo', 'high', 'pending',
     'Cuidado com tremor, taquicardia em idoso'),
    ('formoterol', 'basico', '2024', ARRAY['inalador'],
     'Beta-2 agonista longa ação (LABA)', ARRAY['adulto', 'idoso'],
     'Asma, DPOC — manutenção', 'high', 'pending',
     'Sempre associado com ICS em asma'),
    ('budesonida', 'basico', '2024', ARRAY['inalador', 'nebulização'],
     'Corticoide inalatório (ICS)', ARRAY['adulto', 'idoso', 'pediatria'],
     'Asma, DPOC — controle', 'high', 'pending',
     'Risco candidíase oral, monitorar enxaguar boca após uso'),
    ('ipratropio', 'basico', '2024', ARRAY['nebulização', 'aerosol'],
     'Anticolinérgico curta ação (SAMA)', ARRAY['adulto', 'idoso'],
     'DPOC, asma resistente', 'high', 'pending',
     'Anticolinérgico — soma ao ACB Score'),
    ('tiotropio', 'basico', '2024', ARRAY['inalador'],
     'Anticolinérgico longa ação (LAMA)', ARRAY['adulto', 'idoso'],
     'DPOC manutenção', 'high', 'pending',
     'Anticolinérgico longa ação — ACB Score elevado em idoso'),

    -- Antidepressivos clássicos
    ('amitriptilina', 'basico', '2024', ARRAY['comprimido'],
     'Antidepressivo tricíclico', ARRAY['adulto'],
     'Depressão, dor neuropática', 'medium', 'pending',
     'Beers AVOID em ≥65 — anticolinérgico forte. Considerar nortriptilina'),
    ('nortriptilina', 'basico', '2024', ARRAY['comprimido'],
     'Antidepressivo tricíclico', ARRAY['adulto', 'idoso'],
     'Depressão, dor neuropática', 'high', 'pending',
     'Preferida vs amitriptilina em idoso (menor anticolinérgico)'),

    -- Outros essenciais geriatria
    ('biperideno', 'basico', '2024', ARRAY['comprimido'],
     'Anticolinérgico', ARRAY['adulto', 'idoso'],
     'Parkinsonismo iatrogênico', 'medium', 'pending',
     'Anticolinérgico — Beers AVOID em demência. ACB Score 3'),
    ('metildopa', 'basico', '2024', ARRAY['comprimido'],
     'Anti-hipertensivo central', ARRAY['adulto', 'gestante'],
     'HAS, especialmente gestação', 'low', 'pending',
     'Pouco usado em geriatria — uso histórico'),
    ('acido_folico', 'basico', '2024', ARRAY['comprimido'],
     'Suplemento vitamínico', ARRAY['adulto', 'idoso', 'gestante'],
     'Anemia megaloblástica, profilaxia', 'medium', 'pending', NULL),
    ('sulfato_ferroso', 'basico', '2024', ARRAY['comprimido', 'solução'],
     'Suplemento mineral', ARRAY['adulto', 'idoso', 'gestante'],
     'Anemia ferropriva', 'high', 'pending',
     'Cascata: IBP crônico → má absorção ferro → suplementação')

ON CONFLICT (principle_active, edicao) DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- 5. View útil pra dashboard de cobertura
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW aia_health_rename_coverage_summary AS
SELECT
    componente,
    geriatric_relevance,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE motor_coverage = 'covered') AS covered,
    COUNT(*) FILTER (WHERE motor_coverage = 'in_progress') AS in_progress,
    COUNT(*) FILTER (WHERE motor_coverage = 'pending') AS pending,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE motor_coverage = 'covered') /
        NULLIF(COUNT(*), 0), 1
    ) AS pct_covered
FROM aia_health_rename_drugs
WHERE edicao = '2024'
GROUP BY componente, geriatric_relevance
ORDER BY componente,
    CASE geriatric_relevance
        WHEN 'high' THEN 1
        WHEN 'medium' THEN 2
        WHEN 'low' THEN 3
        WHEN 'excluded' THEN 4
    END;

COMMENT ON VIEW aia_health_rename_coverage_summary IS
    'Resumo de cobertura RENAME 2024 por componente e relevância geriátrica.';


COMMIT;
