-- Migration 008 — Catálogo de Doenças (CID-10 + extensões futuras)
--
-- Fonte oficial: DATASUS CID-10 v2008 (Ministério da Saúde)
-- http://www2.datasus.gov.br/cid10/V2008/cid10.htm
-- Licença: livre (dado público do governo brasileiro)
--
-- Usado em:
--  - Autocomplete na seção de Avaliação do SOAP editor (teleconsulta)
--  - Classificação automática de diagnósticos nas análises clínicas
--  - Busca no prontuário longitudinal
--  - Mapeamento FHIR (Condition.code)

-- pg_trgm: precisa vir ANTES do CREATE TABLE pra gin_trgm_ops funcionar.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS aia_health_disease_catalog (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Taxonomia
    code          TEXT NOT NULL,                -- Ex: "M19" ou "M19.0"
    code_family   TEXT NOT NULL,                -- Ex: "M19" (sem sufixo)
    code_block    TEXT,                         -- Ex: "M15-M19" (grupo)
    code_chapter  TEXT,                         -- Ex: "XIII" (capítulo CID-10)

    description_pt TEXT NOT NULL,               -- Ex: "Outras artroses"
    description_en TEXT,                        -- Opcional
    synonyms       TEXT[] DEFAULT '{}'::TEXT[], -- Termos alternativos populares

    -- Metadata
    system        TEXT NOT NULL DEFAULT 'icd10-datasus',  -- futuro: icd11, snomed
    version       TEXT NOT NULL DEFAULT '2008',
    is_subcategory BOOLEAN NOT NULL DEFAULT FALSE,
    parent_code   TEXT,                         -- FK lógica pro code pai

    -- Flags úteis em geriatria
    is_geriatric_common BOOLEAN DEFAULT FALSE,  -- Pré-flag manual pra acelerar UX

    -- Full-text search (trgm + to_tsvector)
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('portuguese',
            coalesce(description_pt, '') || ' ' ||
            coalesce(array_to_string(synonyms, ' '), '') || ' ' ||
            coalesce(code, '')
        )
    ) STORED,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(system, code)
);

-- Indexes pra busca rápida
CREATE INDEX IF NOT EXISTS idx_disease_code ON aia_health_disease_catalog(code);
CREATE INDEX IF NOT EXISTS idx_disease_family ON aia_health_disease_catalog(code_family);
CREATE INDEX IF NOT EXISTS idx_disease_search ON aia_health_disease_catalog USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_disease_description_trgm
    ON aia_health_disease_catalog USING gin (description_pt gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_disease_geriatric
    ON aia_health_disease_catalog(is_geriatric_common)
    WHERE is_geriatric_common = TRUE;

COMMENT ON TABLE aia_health_disease_catalog IS
'Catálogo de códigos de doenças CID-10 (DATASUS). Extensível pra CID-11 e SNOMED-CT (quando licenciado).';

COMMENT ON COLUMN aia_health_disease_catalog.synonyms IS
'Termos populares que pacientes/cuidadores usam (ex: para "I10" incluir "pressão alta", "hipertensão").';

COMMENT ON COLUMN aia_health_disease_catalog.is_geriatric_common IS
'Flag curada manualmente — doenças frequentes em idosos (>65 anos). Boostam ranking na busca.';
