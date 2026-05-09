-- =============================================================================
-- 075 — Bases curadas: CID-10 geriátrico + medicamento→classe + condição×med
-- =============================================================================
--
-- Decisão Alexandre+Henrique 2026-05-09: 3 bases curadas que servem o
-- wizard de cadastro. Versionadas + auditáveis pra revisão acadêmica
-- (Coordenadora do curso de Farmácia da PUC potencialmente vai validar):
--
--   1. aia_health_cid10_curated      — ~150 CIDs comuns em geriatria
--      (autocomplete da tela de condições)
--   2. aia_health_medication_class_dictionary — ~80 medicamentos comuns
--      mapeados pra classe terapêutica (suporta cross-validation)
--   3. aia_health_disease_medication_expectations — 8 pares iniciais
--      condição → classe esperada (motor de soft prompt)
--
-- Cada entry tem ciclo de revisão: draft → under_review → approved.
-- Permite exportar pra revisão offline da Coordenadora.
--
-- Migration cria as tabelas vazias. Seeds vão em arquivo separado de
-- import (popular_curated_bases.sql ou via script Python).
-- =============================================================================


-- 1. CID-10 curado (subset geriátrico)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aia_health_cid10_curated (
    code TEXT PRIMARY KEY,                  -- ex: 'I10', 'E11.9', 'F03'
    -- Nomes
    description_pt TEXT NOT NULL,           -- nome técnico oficial
    description_layman TEXT,                -- nome popular ("pressão alta")
    description_en TEXT,                    -- pra FHIR/internacional
    -- Categoria geriátrica
    category TEXT NOT NULL CHECK (category IN (
        'cardiovascular', 'respiratorio', 'endocrino_metabolico',
        'neurologico', 'psiquiatrico', 'osteomuscular',
        'infeccioso', 'oncologico', 'urinario', 'digestivo',
        'sensorial', 'cuidados_paliativos', 'outro'
    )),
    -- Ciclo de revisão
    review_status TEXT NOT NULL DEFAULT 'draft' CHECK (review_status IN (
        'draft', 'under_review', 'approved'
    )),
    reviewed_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    -- Versionamento
    version INT NOT NULL DEFAULT 1,
    -- Audit
    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Search support
    search_text TEXT GENERATED ALWAYS AS (
        lower(code || ' ' || description_pt ||
              COALESCE(' ' || description_layman, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_aia_cid10_search
    ON aia_health_cid10_curated USING gin(search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_aia_cid10_category
    ON aia_health_cid10_curated(category);
CREATE INDEX IF NOT EXISTS idx_aia_cid10_approved
    ON aia_health_cid10_curated(review_status)
    WHERE review_status = 'approved';

COMMENT ON TABLE aia_health_cid10_curated IS
    'Subset curado de CID-10 PT-BR pra autocomplete de condições no ' ||
    'cadastro de paciente. ~150 entries focados em geriatria, incluindo ' ||
    'crônicas + infecciosas comuns em idoso (Henrique 2026-05-09). ' ||
    'Versionado e revisável academicamente.';

-- pg_trgm extension pra fuzzy search (provavelmente já habilitado, mas idempotente)
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- 2. Medicamento → classe terapêutica
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aia_health_medication_class_dictionary (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- Nome canônico (princípio ativo)
    active_ingredient TEXT NOT NULL,        -- "Losartana"
    -- Nomes comerciais comuns (pra match em texto livre)
    brand_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Match patterns (substrings case-insensitive pra detectar em texto livre)
    -- ex: ["losartana", "losartan"] casa "Losartana 50mg" e "tomei o Losartan"
    match_patterns TEXT[] NOT NULL,
    -- Classes terapêuticas (algumas drogas têm múltiplas — ex: AAS é antiagregante E AINE)
    therapeutic_classes TEXT[] NOT NULL,
    -- Indicações principais (pra UI explicar)
    main_indications TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Nota livre clínica
    notes TEXT,
    -- Ciclo de revisão
    review_status TEXT NOT NULL DEFAULT 'draft' CHECK (review_status IN (
        'draft', 'under_review', 'approved'
    )),
    reviewed_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    -- Versionamento
    version INT NOT NULL DEFAULT 1,
    -- Audit
    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Constraint: active_ingredient único por versão aprovada
    UNIQUE (active_ingredient)
);

CREATE INDEX IF NOT EXISTS idx_aia_med_class_patterns
    ON aia_health_medication_class_dictionary USING GIN(match_patterns);
CREATE INDEX IF NOT EXISTS idx_aia_med_class_therapeutic
    ON aia_health_medication_class_dictionary USING GIN(therapeutic_classes);
CREATE INDEX IF NOT EXISTS idx_aia_med_class_approved
    ON aia_health_medication_class_dictionary(review_status)
    WHERE review_status = 'approved';

COMMENT ON TABLE aia_health_medication_class_dictionary IS
    'Mapping medicamento (texto livre do paciente) → classe terapêutica. ' ||
    'Suporta cross-validation: paciente diz "tomo Losartana 50" → ' ||
    'casamos com active_ingredient=Losartana → therapeutic_classes=[anti_hipertensivo,BRA]. ' ||
    'Henrique 2026-05-09: ~80 medicamentos comuns em geriatria, baseline ' ||
    'curado por Claude → revisado por Henrique → revisado pela Coord. PUC.';


-- 3. Expectativas condição × medicamento (motor de soft prompt)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS aia_health_disease_medication_expectations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- A condição declarada
    condition_label TEXT NOT NULL,          -- "Hipertensão Arterial Sistêmica (HAS)"
    -- CID-10 associado (FK pra base curada)
    cid10_code TEXT REFERENCES aia_health_cid10_curated(code) ON DELETE SET NULL,
    -- Match patterns no texto livre da condição (caso paciente escreveu manual)
    condition_match_patterns TEXT[] NOT NULL,
    -- Classes terapêuticas esperadas (any-match — basta 1 da lista pra "ok")
    expected_therapeutic_classes TEXT[] NOT NULL,
    -- Severidade do prompt se não houver nenhuma da classe listada
    prompt_severity TEXT NOT NULL DEFAULT 'medium' CHECK (prompt_severity IN (
        'low',      -- info ('opcional listar')
        'medium',   -- warning ('recomendado listar')
        'high',     -- alerta forte ('importante esclarecer')
        'critical'  -- bloqueio mole ('risco grave de não tratar')
    )),
    -- Mensagem mostrada ao usuário
    prompt_message TEXT NOT NULL,
    -- Opções padrão de resposta (JSON: lista de {value, label})
    response_options JSONB NOT NULL DEFAULT
        '[
            {"value": "forgot_to_list", "label": "Esqueci de listar — adicionar agora"},
            {"value": "non_pharmacological", "label": "Em tratamento não-medicamentoso (dieta/atividade)"},
            {"value": "medical_indication", "label": "Médico orientou suspender / não tomar agora"},
            {"value": "skip", "label": "Pular sem responder"}
        ]'::jsonb,
    -- Justificativa clínica (visível ao reviewer)
    clinical_rationale TEXT,
    -- Ciclo de revisão
    review_status TEXT NOT NULL DEFAULT 'draft' CHECK (review_status IN (
        'draft', 'under_review', 'approved'
    )),
    reviewed_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    -- Versionamento
    version INT NOT NULL DEFAULT 1,
    -- Audit
    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Active flag pra desativar regra sem deletar (preserva histórico)
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_aia_dm_expect_active
    ON aia_health_disease_medication_expectations(active, review_status)
    WHERE active = TRUE AND review_status = 'approved';
CREATE INDEX IF NOT EXISTS idx_aia_dm_expect_patterns
    ON aia_health_disease_medication_expectations USING GIN(condition_match_patterns);

COMMENT ON TABLE aia_health_disease_medication_expectations IS
    'Regras curadas: dada uma condição declarada, qual classe terapêutica ' ||
    'esperamos ver listada nas medicações? Se não houver match, dispara ' ||
    'soft prompt no wizard. Henrique 2026-05-09: 8 condições baseline ' ||
    '(HAS, DM, IC, FA, Hipotireoidismo, DPOC, Asma, DAC). Expansível.';


-- 4. Trigger updated_at compartilhado
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _aia_curated_touch_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cid10_updated ON aia_health_cid10_curated;
CREATE TRIGGER trg_cid10_updated
    BEFORE UPDATE ON aia_health_cid10_curated
    FOR EACH ROW EXECUTE FUNCTION _aia_curated_touch_updated();

DROP TRIGGER IF EXISTS trg_medclass_updated ON aia_health_medication_class_dictionary;
CREATE TRIGGER trg_medclass_updated
    BEFORE UPDATE ON aia_health_medication_class_dictionary
    FOR EACH ROW EXECUTE FUNCTION _aia_curated_touch_updated();

DROP TRIGGER IF EXISTS trg_dmexpect_updated ON aia_health_disease_medication_expectations;
CREATE TRIGGER trg_dmexpect_updated
    BEFORE UPDATE ON aia_health_disease_medication_expectations
    FOR EACH ROW EXECUTE FUNCTION _aia_curated_touch_updated();
