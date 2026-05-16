-- =============================================================================
-- 080 — Contatos de escalação por tenant (multi-tenant ready)
-- =============================================================================
--
-- Contexto (Alexandre 2026-05-16):
--   Anti-pattern detectada após migration 079 + fix de P1 push:
--   tinhamos `P1_ESCALATION_PHONES` como env var global. Problemas:
--     - Multi-tenant: ILPI A e ILPI B precisam de plantões diferentes
--     - Operacional: trocar plantonista = SSH + edit .env + restart
--     - Audit: sem histórico de quem mudou quando
--     - UI: sem painel pra admin do tenant gerenciar próprio time
--
-- Esta migration cria estrutura parametrizada:
--   • Por tenant
--   • Por prioridade (P1/P2/P3)
--   • Com nome humano + role pra audit
--   • Schedule opcional (fase 2 — permitir turnos por horário/dia)
--   • Ativo/inativo soft (nunca delete por compliance LGPD)
--
-- Fluxo de uso:
--   1. Sofia escala P1 → escalate_to_human_clinical em sofia_tools.py
--   2. Tool chama _escalation_phones_for(tenant_id, urgency='P1')
--   3. Helper query: SELECT phone FROM ... WHERE tenant_id=X AND
--      'P1'=ANY(priorities) AND active=true [AND schedule_matches_now]
--   4. Pra cada phone retornado, publica msg no stream OUTBOUND
--   5. Fallback: se nenhum contato cadastrado, mantém env var
--      P1_ESCALATION_PHONES (compatibilidade durante transição).
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS aia_health_tenant_escalation_contacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Vínculo com tenant (cascata em delete pra não deixar órfão)
    tenant_id TEXT NOT NULL
        REFERENCES aia_health_tenants(id) ON DELETE CASCADE,

    -- Phone E.164 sem '+' (ex: 5551999XXXXXXX) — formato igual ao
    -- usado em outras tabelas (caregivers, users)
    phone TEXT NOT NULL,

    -- Nome humano da pessoa pra audit/dashboard
    contact_name TEXT NOT NULL,

    -- Papel desse contato no plantão (descritivo, não controle de acesso)
    -- Exemplos: 'plantonista_l1', 'plantonista_l2', 'medico_responsavel',
    --           'admin_tenant', 'enfermeiro_chefe', 'gestor_unidade'
    role TEXT NOT NULL,

    -- Quais prioridades esse contato recebe push WhatsApp
    -- ['P1'] = só emergência crítica
    -- ['P1','P2'] = inclui drug_safety high
    -- ['P1','P2','P3'] = todos os handoffs (cuidado com ruído)
    priorities TEXT[] NOT NULL DEFAULT ARRAY['P1']::TEXT[],

    -- Soft delete — manter histórico pra audit/LGPD
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Schedule (fase 2 — por enquanto NULL = 24/7).
    -- schedule_weekdays: ISO day-of-week 1..7 (1=segunda, 7=domingo);
    --   NULL/array vazio = todos os dias
    -- schedule_start/end: hora local America/Sao_Paulo;
    --   ambos NULL = 24/7
    schedule_weekdays INT[],
    schedule_start TIME,
    schedule_end TIME,

    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    deactivated_at TIMESTAMPTZ,
    deactivated_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,

    -- Notas livres (ex: "plantão revezamento mensal", "férias até X")
    notes TEXT,

    -- Unique soft: mesmo phone pode existir 2× pro mesmo tenant SE um
    -- deles estiver inactive (histórico de plantonista anterior).
    -- Active único por (tenant, phone) garantido via index parcial.
    CONSTRAINT chk_priorities_valid CHECK (
        priorities <@ ARRAY['P1','P2','P3']::TEXT[]
        AND array_length(priorities, 1) > 0
    ),
    CONSTRAINT chk_schedule_consistency CHECK (
        (schedule_start IS NULL AND schedule_end IS NULL)
        OR (schedule_start IS NOT NULL AND schedule_end IS NOT NULL)
    )
);

-- Index parcial: 1 só active por (tenant, phone) — permite múltiplos
-- inactives na história (rotação de plantonistas).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_escalation_contact
    ON aia_health_tenant_escalation_contacts(tenant_id, phone)
    WHERE active = TRUE;

-- Index pra query de lookup (mais comum)
CREATE INDEX IF NOT EXISTS idx_escalation_lookup
    ON aia_health_tenant_escalation_contacts(tenant_id, active)
    WHERE active = TRUE;

-- GIN pra query "todos com prioridade P1"
CREATE INDEX IF NOT EXISTS idx_escalation_priorities
    ON aia_health_tenant_escalation_contacts USING GIN(priorities)
    WHERE active = TRUE;

COMMENT ON TABLE aia_health_tenant_escalation_contacts IS
    'Contatos pra escalação humana de handoffs por tenant + prioridade. '
    'Sofia consulta esta tabela ao disparar P1/P2/P3 e envia push '
    'WhatsApp pros phones aqui listados. Substitui env var '
    'P1_ESCALATION_PHONES (que vira fallback durante transição).';

COMMENT ON COLUMN aia_health_tenant_escalation_contacts.priorities IS
    'Lista de prioridades que esse contato recebe. ["P1"] mais comum. '
    '["P1","P2","P3"] gera ruído — usar só pra equipe operacional dedicada.';

COMMENT ON COLUMN aia_health_tenant_escalation_contacts.schedule_weekdays IS
    'ISO weekday 1=segunda..7=domingo. NULL ou vazio = todos os dias. '
    'Combinado com schedule_start/end pra definir turnos.';

COMMIT;
