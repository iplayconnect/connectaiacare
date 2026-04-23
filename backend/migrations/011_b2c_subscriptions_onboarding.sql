-- Migration 011 — B2C Subscriptions + Onboarding via WhatsApp + Payments
--
-- ADR-026: Onboarding completo via WhatsApp Sofia. Zero app, zero portal.
-- Idoso/familiar conversam com Sofia, que coleta dados, confirma identidade,
-- gera link de pagamento (ou QR PIX), ativa assinatura.
--
-- Regras de negócio críticas:
--   - Trial 7 dias (CDC Art. 49 — direito de arrependimento)
--   - TRIAL disponível APENAS com cartão recorrente
--   - PIX é pagamento imediato (sem trial — assina pagando)
--   - Payer ≠ Beneficiary (filho paga, mãe é o idoso monitorado)

-- ═══════════════════════════════════════════════════════════════════
-- 1. Plans (catálogo de preços)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_plans (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL DEFAULT 'sofiacuida_b2c',

    sku           TEXT NOT NULL,                -- 'essencial' | 'familia' | 'premium' | 'premium_device'
    name          TEXT NOT NULL,                -- 'Sofia Cuida Essencial'
    tagline       TEXT,                         -- 'Monitoramento 24h via WhatsApp'

    -- Preço (armazenado em centavos pra evitar float drama)
    price_cents   INTEGER NOT NULL,             -- 4990 = R$ 49,90
    currency      TEXT NOT NULL DEFAULT 'BRL',
    billing_period TEXT NOT NULL DEFAULT 'monthly' CHECK (billing_period IN ('monthly', 'yearly')),

    -- Benefícios (pra renderizar na UI + Sofia apresentar)
    features      JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Capacidades
    max_beneficiaries INTEGER NOT NULL DEFAULT 1,    -- seat-based: família pode ter 2 idosos
    max_emergency_contacts INTEGER NOT NULL DEFAULT 3,
    includes_teleconsulta BOOLEAN DEFAULT FALSE,
    teleconsulta_per_month INTEGER DEFAULT 0,
    includes_atente_24h BOOLEAN DEFAULT FALSE,       -- central humana
    includes_medication_reminders BOOLEAN DEFAULT TRUE,
    includes_voice_biomarkers BOOLEAN DEFAULT FALSE,
    includes_community_network BOOLEAN DEFAULT FALSE,
    includes_device BOOLEAN DEFAULT FALSE,            -- pulseira/relógio SOS

    -- Trial policy
    trial_days           INTEGER NOT NULL DEFAULT 7,  -- CDC Art. 49
    trial_requires_card  BOOLEAN NOT NULL DEFAULT TRUE,
    pix_allows_trial     BOOLEAN NOT NULL DEFAULT FALSE,  -- PIX = assina pagando

    -- Verificação exigida (ADR-025 anti-fraude)
    required_verification TEXT NOT NULL DEFAULT 'cpf_whatsapp' CHECK (required_verification IN (
        'cpf_sms', 'cpf_whatsapp', 'doc_photo', 'selfie_doc_match'
    )),

    display_order INTEGER NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(tenant_id, sku)
);


-- ═══════════════════════════════════════════════════════════════════
-- 2. Subscriptions (assinatura ativa)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_subscriptions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL DEFAULT 'sofiacuida_b2c',
    human_id      INTEGER NOT NULL DEFAULT nextval('aia_health_subscriptions_human_seq'),

    plan_sku      TEXT NOT NULL,                -- FK lógica em aia_health_plans.sku

    -- Quem paga ≠ quem é o beneficiário (idoso)
    payer_subject_type TEXT NOT NULL CHECK (payer_subject_type IN (
        'patient_self', 'family_member', 'caregiver_pro'
    )),
    payer_subject_id   UUID NOT NULL,
    payer_phone        TEXT NOT NULL,           -- WhatsApp do pagante
    payer_cpf_hash     TEXT,                    -- hash do CPF (LGPD)
    payer_name         TEXT NOT NULL,
    payer_email        TEXT,

    -- Beneficiários (pode ter N idosos monitorados)
    beneficiary_patient_ids UUID[] NOT NULL,

    -- Estado
    status        TEXT NOT NULL DEFAULT 'trialing' CHECK (status IN (
        'trialing',            -- em período de teste (7 dias)
        'active',              -- pagando e ativo
        'past_due',            -- cobrança falhou
        'cancelled',           -- cancelou
        'ended',               -- chegou ao fim sem renovar
        'suspended'            -- admin suspendeu
    )),
    payment_method TEXT NOT NULL CHECK (payment_method IN (
        'credit_card', 'pix_recurring', 'pix_monthly', 'boleto', 'payroll'
    )),

    -- Datas
    trial_started_at TIMESTAMPTZ,
    trial_ends_at    TIMESTAMPTZ,
    activated_at     TIMESTAMPTZ,               -- primeiro pagamento confirmado
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    next_billing_at      TIMESTAMPTZ,
    cancelled_at         TIMESTAMPTZ,
    cancellation_reason  TEXT,

    -- Integração PSP (Asaas, MP, etc)
    psp_provider    TEXT,                       -- 'asaas' | 'mercadopago' | 'pagseguro'
    psp_customer_id TEXT,                       -- customer no PSP
    psp_subscription_id TEXT,                   -- recorrência no PSP
    psp_metadata    JSONB,

    -- Origem (attribution)
    referral_code_used TEXT,
    onboarding_session_id UUID,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE SEQUENCE IF NOT EXISTS aia_health_subscriptions_human_seq START 10001;

CREATE INDEX IF NOT EXISTS idx_subscriptions_payer_phone
    ON aia_health_subscriptions(payer_phone);
CREATE INDEX IF NOT EXISTS idx_subscriptions_active
    ON aia_health_subscriptions(status, next_billing_at)
    WHERE status IN ('trialing', 'active', 'past_due');
CREATE INDEX IF NOT EXISTS idx_subscriptions_beneficiaries
    ON aia_health_subscriptions USING gin(beneficiary_patient_ids);


-- ═══════════════════════════════════════════════════════════════════
-- 3. Onboarding Sessions (state machine da Sofia)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_onboarding_sessions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL DEFAULT 'sofiacuida_b2c',

    phone         TEXT NOT NULL,                -- WhatsApp do pagante/iniciante
    channel       TEXT NOT NULL DEFAULT 'whatsapp',

    -- State machine da conversa
    state         TEXT NOT NULL DEFAULT 'greeting' CHECK (state IN (
        'greeting',                -- "Olá! Pra quem você quer cuidar?"
        'role_selection',          -- "Pra você? Pra ente querido?"
        'collect_payer_name',      -- nome do pagante
        'collect_payer_cpf',       -- CPF pra validação
        'collect_beneficiary',     -- nome do idoso + idade
        'collect_conditions',      -- condições conhecidas
        'collect_medications',     -- medicações (foto ou texto)
        'collect_contacts',        -- contatos de emergência
        'collect_address',         -- CEP + endereço
        'plan_selection',          -- escolhe plano
        'payment_method',          -- cartão ou PIX
        'payment_pending',         -- link enviado, aguardando pagamento
        'consent_lgpd',            -- aceita termos
        'active',                  -- concluído
        'abandoned',               -- ficou parado mais de 48h
        'rejected'                 -- falha CPF/documento
    )),

    -- Dados coletados até agora (incrementais)
    collected_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Exemplo: {
    --   "payer": {"name": "João Silva", "cpf_hash": "...", "email": "..."},
    --   "beneficiary": {"name": "Maria Silva", "age": 82, "conditions": [...]},
    --   "contacts": [{"name": "...", "phone": "..."}, ...],
    --   "plan": "familia",
    --   "payment_method": "credit_card",
    --   "payment_link": "...",
    -- }

    -- Validações anti-fraude
    cpf_verified_at         TIMESTAMPTZ,
    document_photo_verified_at TIMESTAMPTZ,
    consent_signed_at       TIMESTAMPTZ,
    consent_version         TEXT,
    consent_audio_hash      TEXT,                -- opcional — áudio de consent

    -- Estado final
    completed_at  TIMESTAMPTZ,
    subscription_id UUID,                        -- FK pra subscriptions quando ativar
    abandoned_at  TIMESTAMPTZ,
    abandon_reason TEXT,

    -- Telemetria
    message_count     INTEGER NOT NULL DEFAULT 0,
    last_message_at   TIMESTAMPTZ,
    session_duration_seconds INTEGER,
    funnel_step_times JSONB,                    -- {"greeting": 2s, "role_selection": 45s, ...}

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uniq_active_onboarding UNIQUE (phone, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_onboarding_state_idle
    ON aia_health_onboarding_sessions(state, last_message_at)
    WHERE state NOT IN ('active', 'abandoned', 'rejected');


-- ═══════════════════════════════════════════════════════════════════
-- 4. Payment Intents + Transactions (log de cobranças)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_payment_intents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL DEFAULT 'sofiacuida_b2c',

    subscription_id UUID REFERENCES aia_health_subscriptions(id) ON DELETE SET NULL,
    onboarding_session_id UUID REFERENCES aia_health_onboarding_sessions(id) ON DELETE SET NULL,

    -- Valor
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'BRL',
    description   TEXT,                        -- "Sofia Cuida Familia - abril/2026"

    -- Método
    method        TEXT NOT NULL CHECK (method IN (
        'credit_card', 'pix', 'boleto'
    )),

    -- Integração PSP
    psp_provider  TEXT NOT NULL,               -- 'asaas' | 'mercadopago' | ...
    psp_intent_id TEXT,                        -- id no PSP
    psp_checkout_url TEXT,                     -- link que Sofia envia
    psp_qr_code   TEXT,                        -- PIX QR code (base64)
    psp_copy_paste TEXT,                       -- PIX copia-cola

    -- Estado
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',                  -- aguardando paciente pagar
        'processing',               -- PSP está processando
        'succeeded',                -- pago
        'failed',                   -- falhou
        'cancelled',                -- cancelado pelo user
        'refunded',                 -- reembolsado
        'expired'                   -- link expirou sem pagamento
    )),
    failure_reason TEXT,

    -- Datas
    expires_at    TIMESTAMPTZ,
    paid_at       TIMESTAMPTZ,
    refunded_at   TIMESTAMPTZ,

    -- Webhooks
    last_webhook_at TIMESTAMPTZ,
    webhook_events  JSONB DEFAULT '[]'::jsonb,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payment_intent_subscription
    ON aia_health_payment_intents(subscription_id);
CREATE INDEX IF NOT EXISTS idx_payment_intent_pending
    ON aia_health_payment_intents(status, expires_at)
    WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS idx_payment_intent_psp_id
    ON aia_health_payment_intents(psp_provider, psp_intent_id);


-- ═══════════════════════════════════════════════════════════════════
-- 5. Triggers de updated_at
-- ═══════════════════════════════════════════════════════════════════

DROP TRIGGER IF EXISTS trg_plans_touch ON aia_health_plans;
CREATE TRIGGER trg_plans_touch
    BEFORE UPDATE ON aia_health_plans
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_subscriptions_touch ON aia_health_subscriptions;
CREATE TRIGGER trg_subscriptions_touch
    BEFORE UPDATE ON aia_health_subscriptions
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_onboarding_touch ON aia_health_onboarding_sessions;
CREATE TRIGGER trg_onboarding_touch
    BEFORE UPDATE ON aia_health_onboarding_sessions
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_payment_intent_touch ON aia_health_payment_intents;
CREATE TRIGGER trg_payment_intent_touch
    BEFORE UPDATE ON aia_health_payment_intents
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();


-- ═══════════════════════════════════════════════════════════════════
-- 6. Seed de planos (Sofia Cuida B2C)
-- ═══════════════════════════════════════════════════════════════════

INSERT INTO aia_health_plans
    (sku, name, tagline, price_cents, features,
     max_beneficiaries, max_emergency_contacts, includes_medication_reminders,
     trial_days, trial_requires_card, pix_allows_trial,
     display_order)
VALUES
    (
        'essencial', 'Sofia Cuida Essencial',
        'Monitoramento via WhatsApp com IA — 24h',
        4990,  -- R$ 49,90
        '[
            "Check-in diário por WhatsApp",
            "Até 3 contatos de emergência",
            "Lembretes de medicação inteligentes",
            "Escalação automática pra família",
            "Relatório semanal pra família",
            "Busca de preços de medicamentos"
        ]'::jsonb,
        1, 3, TRUE,
        7, TRUE, FALSE,
        10
    ),
    (
        'familia', 'Sofia Cuida Família',
        'Tudo do Essencial + monitoramento estendido + rede comunitária',
        8990,  -- R$ 89,90
        '[
            "Tudo do Essencial",
            "Grupo familiar — até 5 contatos",
            "Sofia Voz (ligações proativas)",
            "Rede comunitária de socorro por raio",
            "Relatório diário detalhado",
            "Biomarkers de voz (relatório mensal)",
            "Suporte prioritário"
        ]'::jsonb,
        2, 5, TRUE,
        7, TRUE, FALSE,
        20
    ),
    (
        'premium', 'Sofia Cuida Premium',
        'Teleconsulta mensal + central humana Atente 24h',
        14990,  -- R$ 149,90
        '[
            "Tudo do Família",
            "1 teleconsulta com geriatra incluída por mês",
            "Central Atente 24h (humana)",
            "Motor de medicamentos completo (5 camadas)",
            "Integração com plano de saúde",
            "Ajuste automático de horários de medicação"
        ]'::jsonb,
        2, 7, TRUE,
        7, TRUE, FALSE,
        30
    ),
    (
        'premium_device', 'Sofia Cuida Premium + Dispositivo',
        'Tudo do Premium + pulseira SOS com detecção de queda',
        19990,  -- R$ 199,90
        '[
            "Tudo do Premium",
            "Pulseira SOS Tecnosenior inclusa",
            "Detecção automática de queda",
            "Monitoramento contínuo de sinais vitais",
            "Instalação domiciliar incluída"
        ]'::jsonb,
        1, 7, TRUE,
        7, TRUE, FALSE,
        40
    )
ON CONFLICT (tenant_id, sku) DO UPDATE SET
    name = EXCLUDED.name,
    tagline = EXCLUDED.tagline,
    price_cents = EXCLUDED.price_cents,
    features = EXCLUDED.features,
    updated_at = now();

UPDATE aia_health_plans SET includes_atente_24h = TRUE, includes_community_network = TRUE
    WHERE sku IN ('premium', 'premium_device');
UPDATE aia_health_plans SET includes_community_network = TRUE, includes_voice_biomarkers = TRUE
    WHERE sku = 'familia';
UPDATE aia_health_plans SET includes_device = TRUE WHERE sku = 'premium_device';
UPDATE aia_health_plans SET teleconsulta_per_month = 1 WHERE sku IN ('premium', 'premium_device');


COMMENT ON TABLE aia_health_plans IS
'Catálogo de planos B2C Sofia Cuida. Preços em centavos. Trial 7 dias (CDC Art. 49) apenas com cartão.';

COMMENT ON TABLE aia_health_subscriptions IS
'Assinatura ativa. Payer pode ser diferente do beneficiário (filho paga pra mãe).';

COMMENT ON TABLE aia_health_onboarding_sessions IS
'State machine da Sofia conduzindo onboarding conversacional via WhatsApp.';

COMMENT ON TABLE aia_health_payment_intents IS
'Cobranças (1a fatura trial-end, mensalidades recorrentes, upgrade emergencial).';
