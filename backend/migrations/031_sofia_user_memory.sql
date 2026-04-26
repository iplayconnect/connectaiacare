-- ConnectaIACare — Memória persistente Sofia ↔ Usuário (cross-session).
--
-- Por que? aia_health_sofia_messages só guarda histórico DENTRO da sessão
-- ativa (SESSION_INACTIVE_HOURS=1). Após 1h sem uso, nova sessão = perda
-- total de contexto. Sofia "esquecia" o usuário.
--
-- Solução: tabela 1-pra-1 com aia_health_users com summary textual + fatos
-- estruturados (key_facts JSONB). Sofia carrega ao iniciar sessão; atualiza
-- a cada N mensagens via LLM (Gemini 3 Flash).
--
-- LGPD: opt-in via flag sofia_memory_enabled em aia_health_users.
--   - Profissionais (medico/enfermeiro/admin/super_admin/parceiro) = TRUE
--   - cuidador_pro/familia = TRUE (consentimento já no onboarding)
--   - paciente_b2c = FALSE até consentimento explícito (UI próxima fase)

BEGIN;

-- =====================================================
-- 1. Flag opt-in em aia_health_users
-- =====================================================
ALTER TABLE aia_health_users
    ADD COLUMN IF NOT EXISTS sofia_memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS sofia_memory_consented_at TIMESTAMPTZ;

-- Default depende do role (paciente_b2c precisa consentir antes)
-- Como não temos role 'paciente_b2c' em aia_health_users (paciente B2C
-- usa fluxo separado em aia_health_patients), todos os roles atuais
-- ficam TRUE. Quando o paciente_b2c entrar como user, deixará de DEFAULT
-- vir TRUE — implementação UI cuida disso.

-- =====================================================
-- 2. Tabela de memória cross-session
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_sofia_user_memory (
    user_id UUID PRIMARY KEY REFERENCES aia_health_users(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,

    -- Resumo narrativo dos últimos N períodos (gerado por LLM).
    -- Mantido em ~500-800 caracteres pra não inflar prompt.
    summary TEXT,

    -- Fatos estruturados extraídos por LLM. Schema flexível, evolui sem
    -- migration. Exemplos:
    --   {"role_context": "médica geriatria, atende 30 pacientes/semana",
    --    "preferences": ["respostas curtas", "cita Beers sempre"],
    --    "ongoing_topics": ["caso paciente Maria — dose levodopa"],
    --    "key_patients": ["uuid-paciente-1", "uuid-paciente-2"],
    --    "concerns": ["polifarmácia em demência"]}
    key_facts JSONB NOT NULL DEFAULT '{}'::JSONB,

    -- Quantidade de mensagens já incorporadas. Usamos pra decidir
    -- quando re-summarizar (cada N novas mensagens).
    messages_at_last_summary INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER NOT NULL DEFAULT 0,

    -- Modelo usado pra gerar o resumo (rastreabilidade)
    summary_model TEXT,

    last_summarized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sofia_user_memory_tenant
    ON aia_health_sofia_user_memory(tenant_id, last_summarized_at DESC);

-- Trigger pra atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION _touch_sofia_user_memory()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_sofia_user_memory ON aia_health_sofia_user_memory;
CREATE TRIGGER trg_touch_sofia_user_memory
    BEFORE UPDATE ON aia_health_sofia_user_memory
    FOR EACH ROW EXECUTE FUNCTION _touch_sofia_user_memory();

COMMIT;
