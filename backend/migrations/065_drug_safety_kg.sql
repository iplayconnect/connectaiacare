-- ====================================================================
-- 065_drug_safety_kg.sql
--
-- Knowledge Graph farmacológico — MVP open-source pra cruzamento de
-- medicamentos + flags Beers Criteria 2023 em geriatria.
--
-- Estrutura em 3 tabelas (knowledge graph como triplas + atributos):
--   1. aia_health_drug_catalog       → nodos (drugs)
--   2. aia_health_beers_flags        → atributos clínicos (Beers 2023)
--   3. aia_health_drug_interactions  → arestas (drug ↔ drug)
--
-- Fontes (todas open access / public domain):
--   - Beers Criteria 2023 (American Geriatrics Society)
--     https://doi.org/10.1111/jgs.18372
--   - Bulário Anvisa (https://consultas.anvisa.gov.br/#/bulario/)
--   - DrugBank Open Data subset
--   - DDInter database (open access, doi:10.1093/nar/gkab880)
--
-- ⚠️  AVISO CLÍNICO IMPORTANTE:
-- Este é dataset MVP curado parcialmente. Cobertura ~30 drugs prioritários
-- pra geriatria. NÃO usar pra decisão clínica antes de revisão por
-- profissional habilitado (ver coluna requires_clinical_review).
-- Referência canônica permanece bula oficial + parecer médico.
--
-- Idempotente.
-- ====================================================================

BEGIN;

-- ─── 1. CATÁLOGO DE DRUGS (nodos do KG) ─────────────────────────
CREATE TABLE IF NOT EXISTS aia_health_drug_catalog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Identificadores cross-reference
    rxnorm_cui TEXT,                     -- ID RxNorm (NIH/NLM EUA) pra mapping internacional
    atc_code TEXT,                       -- WHO Anatomical Therapeutic Chemical code
    -- Nomes
    generic_name TEXT NOT NULL,          -- Nome genérico (ex: "Atenolol", "Diazepam")
    generic_name_normalized TEXT NOT NULL, -- lowercase + sem acentos pra busca
    brand_names TEXT[] NOT NULL DEFAULT '{}', -- nomes comerciais BR (ex: ['Atenol', 'Tenoblock'])
    -- Classificação
    therapeutic_class TEXT,              -- ex: "betabloqueador cardiosseletivo"
    pharmacologic_class TEXT,            -- mecanismo (ex: "beta-1 selective adrenergic blocker")
    -- LGPD / consent (psicotrópicos exigem cuidado extra)
    is_psychotropic BOOLEAN NOT NULL DEFAULT FALSE,
    is_controlled BOOLEAN NOT NULL DEFAULT FALSE, -- portaria 344 SVS BR
    -- Metadata
    source TEXT NOT NULL CHECK (source IN (
        'beers_2023', 'anvisa', 'drugbank_open', 'manual_curation', 'ddinter'
    )),
    source_ref TEXT,                     -- ex: "Beers 2023, Table 2, p.2055"
    requires_clinical_review BOOLEAN NOT NULL DEFAULT TRUE, -- MVP: tudo TRUE até Henrique revisar
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(generic_name_normalized)
);

CREATE INDEX IF NOT EXISTS idx_drug_catalog_generic
    ON aia_health_drug_catalog (generic_name_normalized);
CREATE INDEX IF NOT EXISTS idx_drug_catalog_brand_gin
    ON aia_health_drug_catalog USING GIN (brand_names);
CREATE INDEX IF NOT EXISTS idx_drug_catalog_rxnorm
    ON aia_health_drug_catalog (rxnorm_cui)
    WHERE rxnorm_cui IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drug_catalog_psychotropic
    ON aia_health_drug_catalog (is_psychotropic)
    WHERE is_psychotropic = TRUE;

-- ─── 2. BEERS CRITERIA 2023 FLAGS ───────────────────────────────
-- "Drugs to avoid" ou "use with caution" em idosos ≥65 anos.
-- Cada flag tem categoria, racional clínico, severidade e força de
-- recomendação. Permite múltiplas flags por drug (ex: avoid AND
-- caution-with-condition).
CREATE TABLE IF NOT EXISTS aia_health_beers_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drug_id UUID NOT NULL REFERENCES aia_health_drug_catalog(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN (
        'avoid_in_elderly',          -- Tabela 2 Beers: evitar em ≥65
        'avoid_with_condition',      -- Tabela 3: evitar com comorbidade X
        'use_with_caution',          -- Tabela 4: usar com cautela
        'avoid_certain_combinations',-- Tabela 5: evitar combinações
        'reduced_dose_in_renal'      -- Tabela 6: reduzir dose se ClCr baixo
    )),
    severity TEXT NOT NULL CHECK (severity IN ('high', 'moderate', 'low')),
    evidence_quality TEXT CHECK (evidence_quality IN ('high', 'moderate', 'low')),
    recommendation_strength TEXT CHECK (recommendation_strength IN ('strong', 'weak')),
    rationale TEXT NOT NULL,             -- Por que está flagged (ex: "alto risco anticolinérgico")
    clinical_consequences TEXT,          -- O que pode acontecer (ex: "delirium, queda")
    conditions TEXT[] NOT NULL DEFAULT '{}', -- Comorbidades que pioram (ex: 'CKD', 'dementia', 'falls_history')
    alternatives TEXT,                   -- Sugestões clínicas (ex: "considerar lorazepam dose menor")
    source_ref TEXT NOT NULL,            -- ex: "Beers 2023, Table 2, p.2055, ref [4]"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_beers_drug ON aia_health_beers_flags (drug_id);
CREATE INDEX IF NOT EXISTS idx_beers_severity ON aia_health_beers_flags (severity);
CREATE INDEX IF NOT EXISTS idx_beers_conditions_gin
    ON aia_health_beers_flags USING GIN (conditions);

-- ─── 3. DRUG-DRUG INTERACTIONS (arestas do KG) ──────────────────
-- Direção convencional: sempre drug_a_id < drug_b_id (lexicograficamente UUID)
-- pra evitar duplicar (A↔B == B↔A). Service.check_interactions()
-- canonicaliza antes de query.
CREATE TABLE IF NOT EXISTS aia_health_drug_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drug_a_id UUID NOT NULL REFERENCES aia_health_drug_catalog(id) ON DELETE CASCADE,
    drug_b_id UUID NOT NULL REFERENCES aia_health_drug_catalog(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK (severity IN (
        'contraindicated',  -- Não usar juntos jamais
        'major',            -- Risco alto, evitar/monitorar intensamente
        'moderate',         -- Cautela, monitorar
        'minor'             -- Awareness, sem mudança rotineira
    )),
    mechanism_type TEXT CHECK (mechanism_type IN (
        'pharmacodynamic',  -- somam/antagonizam efeito
        'pharmacokinetic',  -- absorção/metabolismo (CYP) afetado
        'mixed'
    )),
    description TEXT NOT NULL,           -- Descrição clínica (ex: "potencializa hipotensão postural")
    clinical_management TEXT,            -- O que fazer (ex: "monitorar PA semanalmente")
    onset TEXT CHECK (onset IN ('rapid', 'delayed', 'unknown')),
    documentation TEXT CHECK (documentation IN (
        'established',  -- comprovado em estudos
        'probable',     -- altamente sugerido
        'theoretical'   -- baseado em mecanismo
    )),
    source TEXT NOT NULL CHECK (source IN (
        'ddinter', 'drugbank_open', 'beers_2023', 'manual_curation', 'anvisa'
    )),
    source_ref TEXT,
    requires_clinical_review BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Garantir ordem canônica drug_a_id < drug_b_id
    CHECK (drug_a_id < drug_b_id),
    UNIQUE(drug_a_id, drug_b_id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_drug_a ON aia_health_drug_interactions (drug_a_id);
CREATE INDEX IF NOT EXISTS idx_interactions_drug_b ON aia_health_drug_interactions (drug_b_id);
CREATE INDEX IF NOT EXISTS idx_interactions_severity ON aia_health_drug_interactions (severity);

-- ─── Trigger: updated_at ────────────────────────────────────────
CREATE OR REPLACE FUNCTION _touch_drug_catalog() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_drug_catalog ON aia_health_drug_catalog;
CREATE TRIGGER trg_touch_drug_catalog
    BEFORE UPDATE ON aia_health_drug_catalog
    FOR EACH ROW EXECUTE FUNCTION _touch_drug_catalog();

-- ─── Tabela de gaps (audit log de drugs perguntados mas ausentes) ──
-- Quando Sofia recebe relato com drug não cadastrado, registra aqui pra
-- priorizar curadoria. Sem dado clínico — só nome e contagem.
CREATE TABLE IF NOT EXISTS aia_health_drug_lookup_gaps (
    id BIGSERIAL PRIMARY KEY,
    raw_drug_mention TEXT NOT NULL,      -- texto cru do relato
    normalized_query TEXT NOT NULL,      -- lowercase + sem acentos
    tenant_id TEXT,
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(normalized_query, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_drug_gaps_count
    ON aia_health_drug_lookup_gaps (occurrences DESC);

COMMIT;
