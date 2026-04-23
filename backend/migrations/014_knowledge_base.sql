-- Migration 014 — Knowledge Base vetorizada para Sofia
--
-- Parte da Onda B (ADR-027). Fundação pra:
--   - Agente de objeções (busca argumentos por similaridade)
--   - Respostas contextuais em onboarding / companion
--   - Futuro: agentes especialistas da Onda D (cada um consulta KB)
--   - Futuro: RAG pra teleconsulta (diretrizes clínicas)
--
-- 4 domínios iniciais (campo `domain`):
--   - plans       → detalhes dos 4 planos (Essencial/Família/Premium/+Device)
--   - compliance  → LGPD, CDC, Estatuto do Idoso, cancelamento, reembolso
--   - geriatrics  → condições comuns (Alzheimer, Parkinson, hipertensão, etc)
--   - medications → fármacos frequentes em idosos (interações, horários)
--
-- Embeddings: 768-dim alinhado com embedding_service.py (Gemini ou OpenAI truncado)
-- Extensão: pgvector já habilitada em migration 003

-- ═══════════════════════════════════════════════════════════════════
-- 1. KNOWLEDGE CHUNKS — unidade atomizada de conhecimento
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'sofiacuida_b2c',

    -- Categorização
    domain TEXT NOT NULL CHECK (domain IN (
        'plans', 'compliance', 'geriatrics', 'medications',
        'company', 'pricing_objections', 'general'
    )),
    subdomain TEXT,                        -- 'plano_essencial' | 'lgpd_direitos' | 'alzheimer' | 'losartana'

    -- Conteúdo
    title TEXT NOT NULL,
    content TEXT NOT NULL,                 -- markdown permitido (ser parseado antes de mostrar)
    summary TEXT,                          -- 1-2 linhas pra ranking rápido

    -- Embedding (768 dims, alinhado com embedding_service.py)
    embedding vector(768),

    -- Metadata pra filtros
    keywords TEXT[],                       -- busca exata / boost lexical
    applies_to_plans TEXT[],               -- ex: ['premium', 'premium_device']
    applies_to_roles TEXT[],               -- ex: ['family', 'self', 'caregiver']
    priority INTEGER NOT NULL DEFAULT 50,  -- 0-100 (ordenação quando similaridade empata)
    confidence TEXT NOT NULL DEFAULT 'high' CHECK (confidence IN (
        'high',      -- curado humano, checado
        'medium',    -- gerado por IA revisado por admin
        'low'        -- auto-ingestão, não revisado
    )),

    -- Rastreabilidade / governança
    source TEXT,                           -- URL ou arquivo origem
    source_type TEXT CHECK (source_type IN (
        'internal_curated',                -- nosso time escreveu
        'regulatory',                      -- texto de lei / órgão (LGPD, CFM)
        'clinical_guideline',              -- diretriz médica (SBGG, MS)
        'product_spec',                    -- nosso produto
        'llm_generated',                   -- IA gerou, precisa revisar
        'external_partner'                 -- Tecnosenior, MedMonitor
    )),
    reviewed_by_user_id UUID,
    reviewed_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Versão e lifecycle
    version INTEGER NOT NULL DEFAULT 1,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until TIMESTAMPTZ,               -- null = vigente

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════════
-- 2. Índices
-- ═══════════════════════════════════════════════════════════════════

-- pgvector: IVFFlat é mais barato que HNSW pra ≤10k linhas (nosso caso inicial)
-- Lists=10 é um bom começo pra <1k vetores; aumenta quando crescer.
CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON aia_health_knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE INDEX IF NOT EXISTS idx_kb_tenant_domain
    ON aia_health_knowledge_chunks(tenant_id, domain, active);

CREATE INDEX IF NOT EXISTS idx_kb_subdomain
    ON aia_health_knowledge_chunks(tenant_id, subdomain)
    WHERE subdomain IS NOT NULL;

-- GIN em keywords pra busca lexical complementar (boost)
CREATE INDEX IF NOT EXISTS idx_kb_keywords
    ON aia_health_knowledge_chunks
    USING GIN(keywords);

-- Trigger updated_at
DROP TRIGGER IF EXISTS trg_kb_touch ON aia_health_knowledge_chunks;
CREATE TRIGGER trg_kb_touch
    BEFORE UPDATE ON aia_health_knowledge_chunks
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();


-- ═══════════════════════════════════════════════════════════════════
-- 3. KNOWLEDGE RETRIEVAL LOG — telemetria de uso
-- ═══════════════════════════════════════════════════════════════════
-- Registra qual chunk foi retrieved pra qual pergunta. Base pra:
--   - Melhorar embeddings (quais perguntas não encontram nada?)
--   - Detectar gaps de conteúdo (busca frequente sem match)
--   - Rankear chunks por utilidade real (feedback loop)

CREATE TABLE IF NOT EXISTS aia_health_kb_retrieval_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,

    -- Contexto da busca
    subject_phone TEXT,
    session_id UUID,
    session_context TEXT,                  -- onboarding | companion | care_event

    -- Query
    query_text TEXT NOT NULL,
    query_domain TEXT,                     -- domain filtro aplicado
    query_embedding vector(768),

    -- Resultados
    chunks_returned UUID[],                -- IDs dos chunks retornados (top N)
    top_similarity FLOAT,                  -- score do melhor match
    chunk_used UUID,                       -- se foi de fato incluído no prompt
    fallback_triggered BOOLEAN NOT NULL DEFAULT FALSE,

    -- Feedback (se coletarmos)
    user_satisfied BOOLEAN,                -- opcional, feedback explícito
    retrieval_helpful BOOLEAN,             -- inferido (user não repetiu pergunta?)

    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_log_time
    ON aia_health_kb_retrieval_log(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kb_log_fallback
    ON aia_health_kb_retrieval_log(fallback_triggered, created_at DESC)
    WHERE fallback_triggered = TRUE;


COMMENT ON TABLE aia_health_knowledge_chunks IS
'Knowledge base vetorizada da Sofia. 4 domínios: planos, compliance, geriatria, medicações. Ingestão via seeds/kb_*.md + seeder.';

COMMENT ON TABLE aia_health_kb_retrieval_log IS
'Log de retrievals pra detectar gaps de conteúdo e calibrar ranking.';
