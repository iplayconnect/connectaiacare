-- ConnectaIACare — Extensões F1: classe terapêutica, NTI, alergia mapping
-- Data: 2026-04-25
--
-- Habilita 4 cruzamentos novos no dose_validator:
--   1. Alergia → bloqueia/avisa por princípio ativo + cross-reactivity
--   2. Duplicidade terapêutica → 2 medicamentos da mesma classe ativos
--   3. Polifarmácia → > 5 schedules ativos (Beers)
--   4. Janela terapêutica estreita (NTI) → exige TDM/INR
--
-- Não criamos tabelas novas: estendemos drug_dose_limits e adicionamos
-- mapeamento de alergias.

BEGIN;

-- =====================================================
-- aia_health_drug_dose_limits — colunas novas
-- =====================================================
ALTER TABLE aia_health_drug_dose_limits
    ADD COLUMN IF NOT EXISTS therapeutic_class TEXT,
    ADD COLUMN IF NOT EXISTS narrow_therapeutic_index BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS nti_monitoring TEXT;        -- "INR alvo 2-3", "nível sérico digoxina", etc

CREATE INDEX IF NOT EXISTS idx_dose_limits_therapeutic_class
    ON aia_health_drug_dose_limits(therapeutic_class)
    WHERE therapeutic_class IS NOT NULL AND active = TRUE;

CREATE INDEX IF NOT EXISTS idx_dose_limits_nti
    ON aia_health_drug_dose_limits(principle_active)
    WHERE narrow_therapeutic_index = TRUE;

-- =====================================================
-- Update seed: classes terapêuticas + NTI flags
-- =====================================================
-- Classes seguem padrão: <grupo>_<subgrupo>
-- analgesico_paracetamol, analgesico_dipirona, analgesico_aine,
-- opioide, bzd, ieca, ara, betabloqueador, diuretico_tiazidico,
-- diuretico_alca, antiagregante, anticoagulante, estatina,
-- biguanida, sulfonilureia, ssri, anticolinesterasico,
-- ipp, hormonio_tireoide, corticoide, demencia_nmda

UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'analgesico_paracetamol' WHERE principle_active = 'paracetamol';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'analgesico_dipirona'    WHERE principle_active = 'dipirona';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'antiagregante'          WHERE principle_active = 'acido acetilsalicilico';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'analgesico_aine'        WHERE principle_active IN ('ibuprofeno','naproxeno','diclofenaco','cetoprofeno');

UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'opioide'                WHERE principle_active IN ('tramadol','codeina');

UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'bzd'                    WHERE principle_active IN ('alprazolam','diazepam','clonazepam','lorazepam');
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'hipnotico_z'            WHERE principle_active = 'zolpidem';

-- Cardio
UPDATE aia_health_drug_dose_limits
    SET therapeutic_class = 'glicosideo_cardiaco',
        narrow_therapeutic_index = TRUE,
        nti_monitoring = 'Nível sérico digoxina alvo 0.5-0.9 ng/mL em idoso. Suspender se sintomas de toxicidade.'
    WHERE principle_active = 'digoxina';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'ara'                    WHERE principle_active = 'losartana';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'ieca'                   WHERE principle_active IN ('enalapril','captopril');
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'betabloqueador'         WHERE principle_active IN ('atenolol','metoprolol');
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'diuretico_alca'         WHERE principle_active = 'furosemida';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'diuretico_tiazidico'    WHERE principle_active = 'hidroclorotiazida';
UPDATE aia_health_drug_dose_limits
    SET therapeutic_class = 'anticoagulante_avk',
        narrow_therapeutic_index = TRUE,
        nti_monitoring = 'INR alvo 2.0-3.0 (FA não valvar) ou 2.5-3.5 (válvula mecânica). Monitorar a cada 4 sem em estável.'
    WHERE principle_active = 'varfarina';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'antiagregante'          WHERE principle_active = 'clopidogrel';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'estatina'               WHERE principle_active IN ('sinvastatina','atorvastatina');

-- DM2
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'biguanida'              WHERE principle_active = 'metformina';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'sulfonilureia'          WHERE principle_active IN ('glibenclamida','glicazida');

-- Psiq
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'ssri'                   WHERE principle_active IN ('sertralina','fluoxetina','escitalopram');
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'antidepressivo_tetraciclico' WHERE principle_active = 'mirtazapina';

-- Demência
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'anticolinesterasico'    WHERE principle_active IN ('donepezila','rivastigmina');
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'demencia_nmda'          WHERE principle_active = 'memantina';

-- Gastro
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'ipp'                    WHERE principle_active IN ('omeprazol','pantoprazol');

-- Endo
UPDATE aia_health_drug_dose_limits
    SET therapeutic_class = 'hormonio_tireoide',
        narrow_therapeutic_index = TRUE,
        nti_monitoring = 'TSH alvo 1-2.5 mUI/L em idoso (mais elevado pra evitar fibrilação atrial e perda óssea). Reavaliar 6-8 sem.'
    WHERE principle_active = 'levotiroxina';
UPDATE aia_health_drug_dose_limits SET therapeutic_class = 'corticoide'             WHERE principle_active = 'prednisona';

-- =====================================================
-- aia_health_allergy_mappings — alergia → princípios ativos afetados
-- =====================================================
-- Quando paciente tem alergia (ex: "sulfa"), validamos contra esta tabela
-- pra ver quais medicamentos cruzam reatividade.
--
-- severity:
--   block   = anafilaxia documentada / cross-reativo conhecido (sulfa→bactrim)
--   warning = cross-reatividade possível (penicilina→cefalo 1ª geração)
--   info    = sensibilidade leve (lactose→comprimidos com lactose)

CREATE TABLE IF NOT EXISTS aia_health_allergy_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Alergia normalizada (lowercase, sem acentos)
    allergy_term TEXT NOT NULL,
    -- Princípio ativo afetado (normalizado, igual dose_limits)
    -- Nullable: alternativa é affected_therapeutic_class. CHECK abaixo
    -- garante que pelo menos um esteja presente.
    affected_principle_active TEXT,
    -- ou classe (alternativa quando o cruzamento é classe inteira)
    affected_therapeutic_class TEXT,
    severity TEXT NOT NULL CHECK (severity IN ('block', 'warning', 'info')),
    cross_reactivity_pct NUMERIC(4,1),   -- ex: 5-10% pen→cefalo 1g
    rationale TEXT NOT NULL,
    source TEXT NOT NULL,
    source_ref TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (affected_principle_active IS NOT NULL OR affected_therapeutic_class IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_allergy_term
    ON aia_health_allergy_mappings(allergy_term)
    WHERE active = TRUE;

-- Sinônimos comuns de alergias usados pelos cuidadores/pacientes
CREATE TABLE IF NOT EXISTS aia_health_allergy_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alias TEXT NOT NULL,                  -- "sulfa", "AAS", "sulfas"
    canonical_term TEXT NOT NULL,         -- "sulfa", "acido acetilsalicilico"
    notes TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_allergy_aliases_unique
    ON aia_health_allergy_aliases(lower(alias));

-- =====================================================
-- Seed alergia mappings (Fase 1 — top alergias geriátricas)
-- =====================================================

INSERT INTO aia_health_allergy_mappings
    (allergy_term, affected_principle_active, severity, rationale, source)
VALUES
    -- AAS / aspirina
    ('aas', 'acido acetilsalicilico', 'block',
     'Reação prévia ao AAS — não usar mesmo em profilaxia.', 'manual'),
    ('aas', 'ibuprofeno', 'warning',
     'Cross-reatividade entre AAS e outros AINEs (5-15%).', 'beers_2023'),
    ('aas', 'naproxeno', 'warning',
     'Cross-reatividade AINEs.', 'beers_2023'),
    ('aas', 'diclofenaco', 'warning',
     'Cross-reatividade AINEs.', 'beers_2023'),
    ('aas', 'cetoprofeno', 'warning',
     'Cross-reatividade AINEs.', 'beers_2023'),

    ('aine', 'ibuprofeno', 'block', 'Alergia documentada a AINEs.', 'manual'),
    ('aine', 'naproxeno', 'block', 'Alergia documentada a AINEs.', 'manual'),
    ('aine', 'diclofenaco', 'block', 'Alergia documentada a AINEs.', 'manual'),
    ('aine', 'cetoprofeno', 'block', 'Alergia documentada a AINEs.', 'manual'),

    -- Dipirona
    ('dipirona', 'dipirona', 'block',
     'Alergia documentada à dipirona — risco anafilaxia/agranulocitose.', 'manual'),

    -- Paracetamol
    ('paracetamol', 'paracetamol', 'block',
     'Alergia documentada — não usar.', 'manual'),

    -- Tramadol/codeína (opioides)
    ('opioide', 'tramadol', 'block', 'Alergia documentada a opioides.', 'manual'),
    ('opioide', 'codeina', 'block', 'Alergia documentada a opioides.', 'manual'),
    ('codeina', 'codeina', 'block',
     'Alergia codeína — também avaliar tramadol/morfina.', 'manual'),

    -- Estatinas
    ('estatina', 'sinvastatina', 'block', 'Reação muscular/hepática prévia a estatina.', 'manual'),
    ('estatina', 'atorvastatina', 'block', 'Reação muscular/hepática prévia a estatina.', 'manual'),

    -- IECA → tosse seca / angioedema
    ('ieca', 'enalapril', 'block',
     'Tosse persistente ou angioedema com IECA — trocar para ARA (losartana).', 'manual'),
    ('ieca', 'captopril', 'block',
     'Tosse persistente ou angioedema com IECA — trocar para ARA.', 'manual');

-- Mapeamentos por classe (mais eficiente quando alergia é genérica)
INSERT INTO aia_health_allergy_mappings
    (allergy_term, affected_principle_active, affected_therapeutic_class, severity, rationale, source)
VALUES
    ('sulfa', NULL, 'diuretico_tiazidico', 'warning',
     'Sulfa: HCTZ tem grupo sulfonamida — risco cross em pacientes com alergia a sulfas.',
     'beers_2023'),
    ('sulfa', NULL, 'diuretico_alca', 'info',
     'Furosemida tem grupo sulfonamida — risco menor que tiazídico mas monitorar.',
     'manual'),
    ('sulfa', NULL, 'sulfonilureia', 'warning',
     'Glibenclamida/glicazida têm grupo sulfa — risco cross.', 'manual');

-- Aliases comuns
INSERT INTO aia_health_allergy_aliases (alias, canonical_term, notes) VALUES
    ('aspirina', 'aas', 'sinonimo'),
    ('acido acetilsalicilico', 'aas', 'principio ativo do AAS'),
    ('sulfas', 'sulfa', 'plural'),
    ('sulfonamida', 'sulfa', 'forma quimica'),
    ('aines', 'aine', 'plural'),
    ('antinflamatorio', 'aine', NULL),
    ('antinflamatorios', 'aine', NULL),
    ('opioides', 'opioide', NULL),
    ('opiacios', 'opioide', NULL),
    ('estatinas', 'estatina', NULL),
    ('iecas', 'ieca', NULL),
    ('inibidor da ECA', 'ieca', NULL)
ON CONFLICT (lower(alias)) DO NOTHING;

COMMIT;
