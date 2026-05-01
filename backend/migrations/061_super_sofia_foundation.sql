-- =====================================================================
-- 061_super_sofia_foundation.sql
--
-- Phase A da arquitetura Super Sofia (ver
-- docs/SUPER_SOFIA_PLATFORM_ARCHITECTURE.md).
--
-- Migrations base pra suportar:
--   • Multi-tenant routing por phone (IdentityResolver)
--   • Lead funnel B2B/B2C
--   • Handoff queue pra Central 24h
--   • Phone history (idoso troca chip, cuidador troca emprego)
--   • Tenant policies (rate limit, quota, scopes)
--   • LLM cost tracking por tenant
--   • Audit log imutável (append-only via trigger)
--   • Tenant central pra leads anônimos (connectaiacare_central)
--   • Extensões em aia_health_sofia_sessions (multi-canal coherent,
--     sub_agent identity, handoff_id link)
--
-- Idempotente: re-rodável sem efeito colateral. Phase A não muda
-- comportamento de produção — só prepara o terreno.
-- =====================================================================


-- 1. PHONE HISTORY ──────────────────────────────────────────────────
-- Permite continuidade quando idoso/cuidador/familiar troca número.
-- IdentityResolver consulta isso DEPOIS de tentativa em users/
-- caregivers/patients vigentes.

CREATE TABLE IF NOT EXISTS aia_health_user_phone_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES aia_health_users(id) ON DELETE CASCADE,
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE CASCADE,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    phone TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Pelo menos 1 dos 3 FKs precisa estar setado
    CHECK (
        (user_id IS NOT NULL)::int +
        (caregiver_id IS NOT NULL)::int +
        (patient_id IS NOT NULL)::int >= 1
    )
);

CREATE INDEX IF NOT EXISTS idx_phone_history_phone_active
    ON aia_health_user_phone_history(phone) WHERE active;
CREATE INDEX IF NOT EXISTS idx_phone_history_user
    ON aia_health_user_phone_history(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_phone_history_caregiver
    ON aia_health_user_phone_history(caregiver_id) WHERE caregiver_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_phone_history_patient
    ON aia_health_user_phone_history(patient_id) WHERE patient_id IS NOT NULL;

COMMENT ON TABLE aia_health_user_phone_history IS
'Histórico de phones de users/caregivers/patients. IdentityResolver consulta como fallback quando phone atual não casa em registro vigente.';


-- 2. LEAD FUNNEL ────────────────────────────────────────────────────
-- Captura B2B/B2C de phones anônimos com intent comercial/suporte.
-- Tools capture_lead, qualify_lead_score, schedule_demo escrevem aqui.

CREATE TABLE IF NOT EXISTS aia_health_leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    organization TEXT,
    role_self_declared TEXT,    -- 'gestor_ilpi'|'medico'|'familiar'|'parceiro'|'outro'
    intent TEXT NOT NULL,        -- output do intent_classifier
    confidence NUMERIC(3,2),
    source_channel TEXT NOT NULL DEFAULT 'whatsapp',
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,  -- utm, referrer, primeira msg
    status TEXT NOT NULL DEFAULT 'new',
    qualification_score INT,     -- 0-100 (heurística)
    qualified_at TIMESTAMPTZ,
    qualified_by_user_id UUID REFERENCES aia_health_users(id),
    demo_scheduled_at TIMESTAMPTZ,
    demo_link TEXT,
    converted_to_tenant_id TEXT REFERENCES aia_health_tenants(id),
    converted_at TIMESTAMPTZ,
    lost_reason TEXT,
    notes JSONB NOT NULL DEFAULT '[]'::jsonb,  -- array de {at, by, text}
    last_contact_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN (
        'new', 'qualified', 'demo_scheduled',
        'in_demo', 'proposal_sent', 'converted', 'lost'
    )),
    CHECK (source_channel IN ('whatsapp', 'voice_call', 'web', 'email', 'api'))
);

CREATE INDEX IF NOT EXISTS idx_leads_status_created
    ON aia_health_leads(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leads_phone
    ON aia_health_leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_intent
    ON aia_health_leads(intent);

COMMENT ON TABLE aia_health_leads IS
'Funil de leads B2B/B2C capturados via tool capture_lead. Status segue máquina de estados new→qualified→demo_scheduled→in_demo→proposal_sent→converted|lost.';


-- 3. HUMAN HANDOFF QUEUE ────────────────────────────────────────────
-- Quando Sofia decide passar pra humano (Central 24h ou tenant
-- attendant). Notification dispara mensagem WhatsApp pro Central
-- 5551997354484 + UI fila de claim em /admin/system/operations/handoff.

CREATE TABLE IF NOT EXISTS aia_health_human_handoff_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID NOT NULL,
    phone TEXT NOT NULL,
    tenant_id TEXT REFERENCES aia_health_tenants(id),  -- null = lead/anônimo
    channel TEXT NOT NULL DEFAULT 'whatsapp',
    reason TEXT NOT NULL,                 -- ex: 'lead_high_value', 'clinical_uncertainty', 'user_requested'
    context_summary TEXT NOT NULL,        -- Sofia resume com LLM antes de salvar
    conversation_log JSONB NOT NULL,      -- últimos N turnos como array {at,role,content}
    triggered_by TEXT NOT NULL DEFAULT 'sofia',  -- 'sofia'|'user'|'admin'|'guardrail'
    priority TEXT NOT NULL DEFAULT 'P3',  -- P1 <5min, P2 <30min, P3 <2h
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_to_user_id UUID REFERENCES aia_health_users(id),
    notified_central_at TIMESTAMPTZ,      -- quando avisamos Central 24h
    central_message_id TEXT,              -- ID do msg WhatsApp pro Central
    claimed_at TIMESTAMPTZ,
    claimed_by_user_id UUID REFERENCES aia_health_users(id),
    resolved_at TIMESTAMPTZ,
    resolved_by_user_id UUID REFERENCES aia_health_users(id),
    resolution_summary TEXT,
    sla_target_seconds INT,               -- calculado pelo priority
    sla_breached_at TIMESTAMPTZ,          -- preenchido se passou SLA
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (priority IN ('P1', 'P2', 'P3')),
    CHECK (status IN ('pending', 'claimed', 'resolved', 'expired'))
);

CREATE INDEX IF NOT EXISTS idx_handoff_status_priority
    ON aia_health_human_handoff_queue(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_handoff_phone
    ON aia_health_human_handoff_queue(phone);
CREATE INDEX IF NOT EXISTS idx_handoff_trace
    ON aia_health_human_handoff_queue(trace_id);
CREATE INDEX IF NOT EXISTS idx_handoff_tenant
    ON aia_health_human_handoff_queue(tenant_id) WHERE tenant_id IS NOT NULL;

COMMENT ON TABLE aia_health_human_handoff_queue IS
'Fila de pedidos de atendimento humano. Quando claimed, Sofia para de responder no phone até resolved.';


-- 4. TENANT POLICIES ────────────────────────────────────────────────
-- Rate limit, quota, scopes, quiet hours por tenant.

CREATE TABLE IF NOT EXISTS aia_health_tenant_policies (
    tenant_id TEXT PRIMARY KEY REFERENCES aia_health_tenants(id) ON DELETE CASCADE,
    -- Quotas
    monthly_msg_quota INT,
    monthly_voice_minutes_quota INT,
    monthly_llm_tokens_quota_input BIGINT,
    monthly_llm_tokens_quota_output BIGINT,
    -- Rate limits
    rate_limit_msgs_per_phone_per_hour INT NOT NULL DEFAULT 30,
    rate_limit_msgs_per_phone_per_day INT NOT NULL DEFAULT 200,
    -- Quiet hours (default 22h-7h, sem outbound info|attention)
    quiet_hours_start TIME NOT NULL DEFAULT '22:00',
    quiet_hours_end TIME NOT NULL DEFAULT '07:00',
    quiet_hours_severity_floor TEXT NOT NULL DEFAULT 'urgent',  -- só urgent|critical bypass
    -- Scopes
    active_profiles TEXT[] NOT NULL DEFAULT ARRAY[
        'super_admin','admin_tenant','medico','enfermeiro',
        'cuidador_pro','familia','paciente_b2c'
    ],
    enabled_tools TEXT[],   -- null = padrão por profile
    disabled_tools TEXT[],  -- override negativo
    -- White-label
    white_label_approved BOOLEAN NOT NULL DEFAULT FALSE,
    -- Custom config (extensão livre por tenant)
    custom_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (quiet_hours_severity_floor IN ('attention','urgent','critical'))
);

COMMENT ON TABLE aia_health_tenant_policies IS
'Policies por tenant: rate limit, quotas, quiet hours, scope de tools, flag de white-label.';


-- 5. LLM COST LOG ───────────────────────────────────────────────────
-- Cost tracking obrigatório desde Phase A (target 10k msgs/dia em
-- 6 meses → custo ~$600/mês LLM, sem dashboard fica cego).

CREATE TABLE IF NOT EXISTS aia_health_llm_cost_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT REFERENCES aia_health_tenants(id),
    trace_id UUID,
    session_id UUID,
    provider TEXT NOT NULL,        -- 'anthropic'|'deepseek'|'gemini'|'xai'|'openai'
    model TEXT NOT NULL,
    task TEXT NOT NULL,            -- 'intent_classifier'|'clinical_judge'|...
    profile TEXT,                  -- profile do user que disparou (pra atribuição)
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    estimated_cost_usd NUMERIC(10,6) NOT NULL,
    duration_ms INT,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    fallback_from_provider TEXT,
    error_class TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_cost_tenant_created
    ON aia_health_llm_cost_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_cost_task
    ON aia_health_llm_cost_log(task, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_cost_trace
    ON aia_health_llm_cost_log(trace_id) WHERE trace_id IS NOT NULL;

COMMENT ON TABLE aia_health_llm_cost_log IS
'Custo por chamada LLM. Dashboard cross-tenant em /admin/system/health/cost lê isso. Particionar mensalmente quando >10M rows.';


-- 6. SOFIA SESSIONS · extensões pra multi-canal coherent ────────────

ALTER TABLE aia_health_sofia_sessions
    ADD COLUMN IF NOT EXISTS active_channels TEXT[] NOT NULL DEFAULT ARRAY['whatsapp']::TEXT[],
    ADD COLUMN IF NOT EXISTS sub_agent TEXT,
    ADD COLUMN IF NOT EXISTS handoff_id UUID REFERENCES aia_health_human_handoff_queue(id),
    ADD COLUMN IF NOT EXISTS context_continuation_window_minutes INT NOT NULL DEFAULT 45,
    ADD COLUMN IF NOT EXISTS trace_ids UUID[] NOT NULL DEFAULT ARRAY[]::UUID[];

COMMENT ON COLUMN aia_health_sofia_sessions.active_channels IS
'Canais que esta sessão atendeu. Sofia voice + chat WhatsApp do mesmo phone em <45min compartilham session (append channel).';

COMMENT ON COLUMN aia_health_sofia_sessions.sub_agent IS
'Sub-agente ativo: clinical|caregiver|family|patient_b2c|partner|admin|commercial|support|onboarding_b2c|onboarding_b2b';

COMMENT ON COLUMN aia_health_sofia_sessions.handoff_id IS
'Se preenchido, sessão está em handoff humano. Sofia silencia até resolução.';


-- 7. AUDIT LOG IMUTÁVEL ─────────────────────────────────────────────
-- Append-only via trigger. UPDATE/DELETE recusados (exceto
-- DROP TABLE em migrations futuras explicitamente).

CREATE TABLE IF NOT EXISTS aia_health_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT,
    trace_id UUID,
    session_id UUID,
    action TEXT NOT NULL,           -- 'inbound_received'|'tool_called'|'handoff_initiated'|...
    actor TEXT,                     -- user_id | 'sofia' | 'system'
    actor_role TEXT,
    resource_type TEXT,             -- 'session'|'tool'|'lead'|'patient'|'message'
    resource_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_created
    ON aia_health_audit_log(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_trace
    ON aia_health_audit_log(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_action_created
    ON aia_health_audit_log(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor
    ON aia_health_audit_log(actor) WHERE actor IS NOT NULL;

-- Trigger imutabilidade: recusa UPDATE e DELETE
CREATE OR REPLACE FUNCTION aia_health_audit_log_immutable()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'aia_health_audit_log is append-only — % rejected (id=%, action=%)',
        TG_OP, OLD.id, OLD.action
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON aia_health_audit_log;
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE ON aia_health_audit_log
    FOR EACH ROW EXECUTE FUNCTION aia_health_audit_log_immutable();

DROP TRIGGER IF EXISTS trg_audit_no_delete ON aia_health_audit_log;
CREATE TRIGGER trg_audit_no_delete
    BEFORE DELETE ON aia_health_audit_log
    FOR EACH ROW EXECUTE FUNCTION aia_health_audit_log_immutable();

COMMENT ON TABLE aia_health_audit_log IS
'Append-only. Triggers recusam UPDATE/DELETE. Particionar mensalmente quando >10M rows. LGPD: retention policy 5 anos com purge programado em job futuro.';


-- 8. TENANT CENTRAL (ponto único de entrada pra phones não-resolvidos) ─
-- Decisão Alexandre 2026-05-01 (Leitura A — simplificação radical):
--
-- TODO phone não-identificado pelo IdentityResolver cai aqui. Super
-- Sofia faz intent_classifier dentro do central e ramifica:
--   • interesse_servico (B2C) → onboarding sofiacuida_b2c sub-agente
--   • interesse_servico (B2B) → fluxo comercial → capture_lead
--   • agendar_demo            → schedule_demo
--   • suporte_cliente         → escalate_to_human (Central 24h)
--   • clínico                 → pergunta tenant (caso ambíguo) ou cuidador-relato
--   • spam/abuso              → silencia + audit log
--
-- sofiacuida_b2c continua existindo como tenant — abriga ASSINANTES
-- B2C JÁ CONVERTIDOS (assinatura ativa). Não recebe mais entrada
-- direta de phone novo via webhook.
--
-- connectaiacare_demo continua sendo tenant clínico com pacientes
-- reais (cuidadores de hospital piloto, etc.).

INSERT INTO aia_health_tenants (
    id, name, ai_name, ai_voice, active, suspended,
    integrations_enabled, metadata
) VALUES (
    'connectaiacare_central',
    'ConnectaIA Care Central',
    'Sofia',
    'ara',
    TRUE, FALSE,
    '{}'::jsonb,
    jsonb_build_object(
        'purpose', 'central_unified_entry',
        'description', 'Ponto único de entrada pra todo phone não-identificado pelo IdentityResolver. Super Sofia classifica intent e ramifica pra B2C/B2B/suporte/clínico.',
        'central_phone', '5551997354484',
        'created_in_migration', '061_super_sofia_foundation'
    )
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    metadata = EXCLUDED.metadata,
    updated_at = NOW();

-- Policy default pro tenant central
INSERT INTO aia_health_tenant_policies (
    tenant_id,
    rate_limit_msgs_per_phone_per_hour,
    rate_limit_msgs_per_phone_per_day,
    active_profiles,
    custom_config
) VALUES (
    'connectaiacare_central',
    20,   -- mais restritivo (anti-spam de lead)
    100,
    ARRAY['anonymous'],  -- só anônimo entra; sub-agentes ramificam
    jsonb_build_object(
        'central_handoff_phone', '5551997354484',
        'lead_email_capture_after_n_turns', 5,
        'unified_entry', true
    )
)
ON CONFLICT (tenant_id) DO UPDATE SET
    custom_config = EXCLUDED.custom_config,
    updated_at = NOW();


-- 9. TRIGGER updated_at em policies ─────────────────────────────────

CREATE OR REPLACE FUNCTION aia_health_touch_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenant_policies_updated_at
    ON aia_health_tenant_policies;
CREATE TRIGGER trg_tenant_policies_updated_at
    BEFORE UPDATE ON aia_health_tenant_policies
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_leads_updated_at ON aia_health_leads;
CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON aia_health_leads
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();
