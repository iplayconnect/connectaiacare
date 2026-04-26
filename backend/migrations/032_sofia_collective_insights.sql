-- ConnectaIACare — Memória coletiva Sofia (cross-tenant, anonimizada).
--
-- Diferente de aia_health_sofia_user_memory (per-user, com PII), esta
-- camada agrega padrões clínicos de TODAS as interações Sofia↔Profissional,
-- com PII removida, formando uma base de conhecimento que enriquece a Sofia
-- pra todos os usuários.
--
-- Pipeline (cron diário):
--   1. Coleta mensagens das últimas 24h
--   2. Anonimiza (regex + LLM): remove nomes, UUIDs, telefones, emails, CRMs
--   3. Extrai insights agrupados (LLM): "padrão clínico", "dúvida feature", etc.
--   4. Insere em raw_insights — staging
--   5. Reagrupa por tema; quando freq ≥ MIN_FREQUENCY (default 3), promove
--      pra aia_health_knowledge_chunks com domain='collective_insight'
--      (Sofia já consome via query_clinical_guidelines).
--
-- LGPD: não armazena dados crus aqui. Todos os textos são anonimizados.
-- Audit em aia_health_audit_chain.

BEGIN;

-- =====================================================
-- 1. Raw insights (staging) — antes de promover pra knowledge_chunks
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_sofia_collective_insights_raw (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Origem (rastreabilidade — agregada, sem PII)
    source_tenant_id TEXT,                  -- pode ser NULL (cross-tenant)
    source_session_count INTEGER NOT NULL DEFAULT 1,  -- quantas sessões contribuíram
    source_message_window_start TIMESTAMPTZ,
    source_message_window_end TIMESTAMPTZ,

    -- Tipo do insight pra ranking/agrupamento
    insight_type TEXT NOT NULL CHECK (insight_type IN (
        'clinical_question',     -- pergunta recorrente sobre fármaco/condição
        'prescribing_pattern',   -- padrão de prescrição observado
        'feature_doubt',         -- dúvida sobre feature da plataforma
        'knowledge_gap',         -- pergunta que Sofia não soube responder
        'workflow_friction',     -- ponto de fricção repetido
        'other'
    )),

    -- Conteúdo anonimizado (já saneado)
    title TEXT NOT NULL,                   -- "Interação levodopa + metoclopramida"
    summary TEXT NOT NULL,                 -- 1-2 linhas
    detail TEXT,                           -- markdown, mais profundo
    keywords TEXT[],                       -- pra agrupar similares
    therapeutic_classes TEXT[],            -- ex: ['antiparkinsoniano', 'antiemetico']
    conditions TEXT[],                     -- ex: ['parkinson', 'demencia']

    -- Frequência observada (incrementa quando insights similares aparecem)
    frequency INTEGER NOT NULL DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Promoção (quando frequency >= threshold, vira knowledge_chunk)
    promoted BOOLEAN NOT NULL DEFAULT FALSE,
    promoted_chunk_id UUID,                -- FK pra aia_health_knowledge_chunks
    promoted_at TIMESTAMPTZ,

    -- Modelo que extraiu (rastreabilidade)
    extractor_model TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collective_raw_type_freq
    ON aia_health_sofia_collective_insights_raw(insight_type, frequency DESC, promoted);

-- Index pra agrupar por keyword (quando o extrator reporta um insight novo,
-- procuramos similar nas keywords pra agregar frequência em vez de duplicar)
CREATE INDEX IF NOT EXISTS idx_collective_raw_keywords
    ON aia_health_sofia_collective_insights_raw USING GIN(keywords);

-- Trigger updated_at
CREATE OR REPLACE FUNCTION _touch_collective_raw()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_collective_raw ON aia_health_sofia_collective_insights_raw;
CREATE TRIGGER trg_touch_collective_raw
    BEFORE UPDATE ON aia_health_sofia_collective_insights_raw
    FOR EACH ROW EXECUTE FUNCTION _touch_collective_raw();


-- =====================================================
-- 2. Estende knowledge_chunks pra aceitar o domain novo
-- =====================================================
-- domain CHECK precisa incluir 'collective_insight'. Recriamos o check.
ALTER TABLE aia_health_knowledge_chunks
    DROP CONSTRAINT IF EXISTS aia_health_knowledge_chunks_domain_check;

ALTER TABLE aia_health_knowledge_chunks
    ADD CONSTRAINT aia_health_knowledge_chunks_domain_check
    CHECK (domain IN (
        'plans', 'compliance', 'geriatrics', 'medications',
        'company', 'pricing_objections', 'general',
        'collective_insight'   -- ← novo
    ));

-- source_type também precisa incluir 'collective_aggregate'
ALTER TABLE aia_health_knowledge_chunks
    DROP CONSTRAINT IF EXISTS aia_health_knowledge_chunks_source_type_check;

ALTER TABLE aia_health_knowledge_chunks
    ADD CONSTRAINT aia_health_knowledge_chunks_source_type_check
    CHECK (source_type IN (
        'internal_curated', 'regulatory', 'clinical_guideline',
        'product_spec', 'llm_generated', 'external_partner',
        'collective_aggregate'  -- ← novo
    ));


-- =====================================================
-- 3. Cursor de quando o cron rodou pela última vez
--    (evita reprocessar mensagens)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_sofia_collective_cursor (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_window_end TIMESTAMPTZ,
    last_run_messages_processed INTEGER,
    last_run_insights_extracted INTEGER,
    last_run_insights_promoted INTEGER,
    last_run_duration_ms INTEGER
);

INSERT INTO aia_health_sofia_collective_cursor (id, last_run_at, last_message_window_end)
VALUES (1, NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days')
ON CONFLICT (id) DO NOTHING;

COMMIT;
