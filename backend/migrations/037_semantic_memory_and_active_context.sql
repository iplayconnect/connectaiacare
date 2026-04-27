-- ConnectaIACare — Memória semântica + Active Context cross-channel.
--
-- 1. embedding vector(768) em aia_health_sofia_messages (pgvector)
--    + HNSW index pra recall_semantic ("você lembra quando falamos de X?")
-- 2. aia_health_sofia_active_context — UNLOGGED table com TTL 45min,
--    cross-channel: chat texto + voz browser + ligação compartilham
--    contexto da conversa em andamento.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Embedding column + HNSW index (recall semântico)
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_sofia_messages
    ADD COLUMN IF NOT EXISTS embedding vector(768),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

-- HNSW (Hierarchical Navigable Small World): mais rápido em recall do
-- que IVFFlat pra <1M vetores. Cosine similarity (vector_cosine_ops).
CREATE INDEX IF NOT EXISTS idx_sofia_messages_embedding
    ON aia_health_sofia_messages USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- Index pra encontrar messages sem embedding (worker batch processa)
CREATE INDEX IF NOT EXISTS idx_sofia_messages_pending_embed
    ON aia_health_sofia_messages(created_at)
    WHERE embedding IS NULL AND content IS NOT NULL;


-- ════════════════════════════════════════════════════════════════
-- 2. Active Context — buffer cross-channel (45min TTL)
-- ════════════════════════════════════════════════════════════════
-- UNLOGGED: sem WAL → zero overhead pra dado ephemeral. Se PG cair,
-- dado some — não importa (active context é descartável).
CREATE UNLOGGED TABLE IF NOT EXISTS aia_health_sofia_active_context (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id UUID,
    patient_id UUID,
    -- chave de agrupamento: (user_id) ou (patient_id) ou (phone)
    -- normalmente user_id pra profissionais; patient_id+phone pra pacientes B2C
    context_key TEXT NOT NULL,
    -- canal de origem
    channel TEXT NOT NULL,
    -- conteúdo (~500 chars max — só pra dar visão rápida do que tava acontecendo)
    role TEXT NOT NULL,        -- user|assistant|tool|system
    content TEXT,
    tool_name TEXT,
    -- expiração automática
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_active_context_lookup
    ON aia_health_sofia_active_context(context_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_active_context_expiry
    ON aia_health_sofia_active_context(expires_at);


-- ════════════════════════════════════════════════════════════════
-- 3. Cleanup function (chamada por cron leve)
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION cleanup_expired_active_context()
RETURNS INTEGER AS $$
DECLARE
    deleted INTEGER;
BEGIN
    DELETE FROM aia_health_sofia_active_context
    WHERE expires_at < NOW() - INTERVAL '1 minute';
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$ LANGUAGE plpgsql;


COMMIT;
