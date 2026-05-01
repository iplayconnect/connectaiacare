-- =====================================================================
-- 060_classification_corpus_review.sql
--
-- Persiste corpus de classificação + reviews humanas (Sprint Henrique).
--
-- Por quê: o corpus_generator.py joga ~240 casos rotulados por LLM em
-- YAML. Antes de virar gold-standard, precisa olho clínico — Henrique
-- (biomed/farma) revisa caso a caso e fixa o expected_event_type. A
-- gente quer que essa revisão fique na plataforma com audit trail
-- (autoria, timestamp), não em planilha externa.
--
-- 2 tabelas:
--   aia_health_classification_corpus_cases    — casos a serem revisados
--   aia_health_classification_corpus_reviews  — decisões de revisor
-- =====================================================================

-- 1. CASOS A REVISAR ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aia_health_classification_corpus_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- code estável vindo do YAML (ex: "cuidado_higiene_001"). Permite
    -- merge idempotente quando reseed.
    case_code TEXT UNIQUE NOT NULL,

    -- Texto do relato como sairia do cuidador (chat ou Whisper).
    transcript TEXT NOT NULL,

    -- O que o LLM sugeriu (ou o que foi semente humana). Mantém histórico
    -- mesmo depois da revisão.
    llm_suggested_event_type TEXT NOT NULL,
    llm_suggested_classification TEXT,  -- routine|attention|urgent|critical
    llm_rationale TEXT,

    -- Pra weighting de métricas (easy/medium/hard)
    difficulty TEXT,

    -- 'seed' (semente humana) | 'llm_generated' (DeepSeek)
    source TEXT NOT NULL DEFAULT 'llm_generated',

    -- Status da revisão (denormalizado pra query rápida do "next case").
    -- 'pending' = ninguém revisou; 'reviewed' = pelo menos 1 review;
    -- 'conflict' = reservado pra futuro multi-reviewer.
    review_status TEXT NOT NULL DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (llm_suggested_event_type IN (
        'relato_geral', 'cuidado_higiene', 'alimentacao_hidratacao',
        'medicacao', 'sinal_vital', 'intercorrencia',
        'sintoma_novo', 'apoio_emocional'
    )),
    CHECK (review_status IN ('pending', 'reviewed', 'conflict')),
    CHECK (source IN ('seed', 'llm_generated'))
);

CREATE INDEX IF NOT EXISTS idx_corpus_cases_review_status
    ON aia_health_classification_corpus_cases(review_status);
CREATE INDEX IF NOT EXISTS idx_corpus_cases_difficulty
    ON aia_health_classification_corpus_cases(difficulty);


-- 2. REVISÕES HUMANAS ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aia_health_classification_corpus_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    case_id UUID NOT NULL REFERENCES
        aia_health_classification_corpus_cases(id) ON DELETE CASCADE,
    reviewer_user_id UUID NOT NULL REFERENCES
        aia_health_users(id) ON DELETE RESTRICT,

    -- Decisão clínica do revisor. Esse é o gold-standard que o
    -- benchmark consome.
    expected_event_type TEXT NOT NULL,
    -- Severidade (opcional — revisor pode discordar do LLM aqui também).
    expected_classification TEXT,

    -- Justificativa clínica curta (livre).
    note TEXT,

    -- Computado: decisão bate com sugestão LLM? Útil pra medir
    -- quanto o LLM erra antes da revisão (~baseline accuracy).
    agrees_with_llm BOOLEAN NOT NULL,

    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Um revisor por caso (versão atual). Se quiser multi-reviewer,
    -- remover esta unique e tratar conflict via review_status.
    UNIQUE (case_id, reviewer_user_id),

    CHECK (expected_event_type IN (
        'relato_geral', 'cuidado_higiene', 'alimentacao_hidratacao',
        'medicacao', 'sinal_vital', 'intercorrencia',
        'sintoma_novo', 'apoio_emocional'
    )),
    CHECK (expected_classification IS NULL OR expected_classification IN (
        'routine', 'attention', 'urgent', 'critical'
    ))
);

CREATE INDEX IF NOT EXISTS idx_corpus_reviews_reviewer
    ON aia_health_classification_corpus_reviews(reviewer_user_id);
CREATE INDEX IF NOT EXISTS idx_corpus_reviews_case
    ON aia_health_classification_corpus_reviews(case_id);


-- 3. TRIGGER — atualiza review_status do case ao inserir review ──────
CREATE OR REPLACE FUNCTION aia_health_corpus_case_mark_reviewed()
RETURNS trigger AS $$
BEGIN
    UPDATE aia_health_classification_corpus_cases
       SET review_status = 'reviewed', updated_at = NOW()
     WHERE id = NEW.case_id
       AND review_status = 'pending';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_corpus_review_marks_case
    ON aia_health_classification_corpus_reviews;
CREATE TRIGGER trg_corpus_review_marks_case
    AFTER INSERT ON aia_health_classification_corpus_reviews
    FOR EACH ROW EXECUTE FUNCTION aia_health_corpus_case_mark_reviewed();


-- 4. ROLE clinical_reviewer ──────────────────────────────────────────
-- Não há tabela `roles` enum — VALID_ROLES é só Python set. Mas se
-- houver permissions table (Bloco C), garante a permission "corpus:review".
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name = 'aia_health_permissions') THEN
        INSERT INTO aia_health_permissions (code, label, description)
        VALUES (
            'corpus:review',
            'Revisar corpus de classificação',
            'Permite votar no expected_event_type de cases do classificador.'
        )
        ON CONFLICT (code) DO NOTHING;
    END IF;
END $$;


COMMENT ON TABLE aia_health_classification_corpus_cases IS
'Casos do corpus de classificação event_type — fonte do gold-standard.';
COMMENT ON TABLE aia_health_classification_corpus_reviews IS
'Revisões humanas dos casos — decide o expected_event_type definitivo.';
