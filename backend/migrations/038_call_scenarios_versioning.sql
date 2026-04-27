-- ConnectaIACare — Versionamento de prompts dos call_scenarios.
--
-- Hoje admin edita prompt direto e entra em produção (irresponsável em
-- healthcare). Modelo novo: edição vai pra DRAFT, admin testa contra
-- golden dataset, depois PROMOVE pra PUBLISHED.
--
-- Toda edição cria nova versão. Histórico inviolável (audit chain).

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Versões de cada cenário
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_call_scenarios_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scenario_id UUID NOT NULL REFERENCES aia_health_call_scenarios(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    -- snapshot completo da versão
    label TEXT NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    voice TEXT NOT NULL DEFAULT 'ara',
    allowed_tools TEXT[] NOT NULL DEFAULT '{}',
    post_call_actions TEXT[] NOT NULL DEFAULT '{log_audit}',
    pre_call_context_sql TEXT,
    max_duration_seconds INTEGER NOT NULL DEFAULT 600,
    -- estado
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft',          -- em edição
        'testing',        -- rodando contra golden dataset
        'published',      -- ativo em produção
        'archived'        -- substituído por versão mais nova
    )),
    -- promoção
    published_at TIMESTAMPTZ,
    published_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    -- testes
    golden_test_results JSONB,
    -- autoria
    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,

    UNIQUE (scenario_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_scenario_versions_published
    ON aia_health_call_scenarios_versions(scenario_id)
    WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_scenario_versions_drafts
    ON aia_health_call_scenarios_versions(scenario_id, created_at DESC)
    WHERE status IN ('draft', 'testing');


-- ════════════════════════════════════════════════════════════════
-- 2. Golden dataset — conversas-tipo pra validar mudanças
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_call_scenarios_golden_set (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scenario_id UUID NOT NULL REFERENCES aia_health_call_scenarios(id) ON DELETE CASCADE,
    name TEXT NOT NULL,           -- ex "Idoso relata dor torácica"
    user_input TEXT NOT NULL,     -- mensagem que simula o usuário
    expected_behaviors JSONB NOT NULL,  -- { "should_call_tool": "escalate_to_attendant",
                                        --   "expected_severity": "critical",
                                        --   "should_mention_disclaimer": true,
                                        --   "must_NOT_say": ["diagnostico", "prescrevo"] }
    notes TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_golden_set_scenario
    ON aia_health_call_scenarios_golden_set(scenario_id, active);


-- ════════════════════════════════════════════════════════════════
-- 3. Snapshot inicial: cada cenário ativo vira versão 1 published
-- ════════════════════════════════════════════════════════════════
INSERT INTO aia_health_call_scenarios_versions
    (scenario_id, version_number, label, description, system_prompt,
     voice, allowed_tools, post_call_actions, pre_call_context_sql,
     max_duration_seconds, status, published_at, notes)
SELECT
    id, 1, label, description, system_prompt, voice, allowed_tools,
    post_call_actions, pre_call_context_sql, max_duration_seconds,
    'published', NOW(),
    'Snapshot inicial criado pela migration 038 (versionamento)'
FROM aia_health_call_scenarios
WHERE active = TRUE
ON CONFLICT (scenario_id, version_number) DO NOTHING;


-- ════════════════════════════════════════════════════════════════
-- 4. Adiciona current_version_id em scenarios pra apontar pra versão ativa
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_call_scenarios
    ADD COLUMN IF NOT EXISTS current_version_id UUID
        REFERENCES aia_health_call_scenarios_versions(id) ON DELETE SET NULL;

-- Aponta pra versão 1 recém-criada
UPDATE aia_health_call_scenarios sc
SET current_version_id = (
    SELECT id FROM aia_health_call_scenarios_versions
    WHERE scenario_id = sc.id AND version_number = 1
    LIMIT 1
)
WHERE current_version_id IS NULL AND active = TRUE;

COMMIT;
