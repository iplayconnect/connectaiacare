-- ═══════════════════════════════════════════════════════════════════
-- 057 — Classification cascade audit (Tier 1 → 2 → Judge)
--
-- Registra cada decisão do cascade de classificação event_type.
-- Permite:
--   * Audit clínica (defesa: "3 modelos independentes decidiram X")
--   * Análise de qualidade (quando T1 diverge de T2, quando juiz é
--     acionado, taxa de notificações)
--   * Revisão de tenant config (qual modelo escolhe melhor pra qual
--     classe — reaprende ao longo do tempo)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_classification_cascade (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id text NOT NULL DEFAULT 'connectaiacare_demo',

    -- Contexto
    report_id uuid,
    care_event_id uuid,
    patient_id uuid,
    transcript_excerpt text,  -- só primeiros 500 chars (resto fica no report)

    -- ─── Tier 1 (sempre executa) ───
    t1_model text NOT NULL,
    t1_event_type text,
    t1_classification text,
    t1_rationale text,
    t1_elapsed_ms integer,
    t1_error text,

    -- ─── Tier 2 (revalida quando T1 = urgent/critical OU falha) ───
    t2_triggered boolean NOT NULL DEFAULT FALSE,
    t2_trigger_reason text,  -- 'urgent', 'critical', 'classification_failed'
    t2_model text,
    t2_event_type text,
    t2_classification text,
    t2_rationale text,
    t2_elapsed_ms integer,
    t2_error text,
    t2_agreement boolean,  -- T1 vs T2: mesma classe + mesma severity

    -- ─── Tier 3 Judge (quando T1 ≠ T2) ───
    t3_triggered boolean NOT NULL DEFAULT FALSE,
    t3_trigger_reason text,  -- 'event_type_disagreement', 'severity_disagreement', 'both'
    t3_model text,
    t3_event_type text,
    t3_classification text,
    t3_rationale text,  -- chain-of-thought da decisão
    t3_elapsed_ms integer,
    t3_error text,

    -- ─── Decisão final ───
    final_event_type text NOT NULL,
    final_classification text NOT NULL,
    final_decided_by text NOT NULL CHECK (final_decided_by IN (
        'tier1',
        'tier2_agreement',
        'tier3_judge',
        'human_queue',
        'fallback_default'
    )),

    -- ─── Notificação ao responsável (sempre que T3 acionado) ───
    responsible_notified boolean NOT NULL DEFAULT FALSE,
    responsible_notified_at timestamptz,
    responsible_phone text,
    responsible_notification_channel text,  -- 'whatsapp', 'sms', 'voice'
    responsible_notification_error text,

    -- ─── Fila de revisão humana (quando review_strategy = clinical_team) ───
    human_queue_id uuid,

    -- Métricas agregadas
    total_elapsed_ms integer,
    total_cost_usd numeric(10, 6),  -- soma dos custos T1+T2+T3 (ref. estimada)

    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cascade_tenant_created
    ON aia_health_classification_cascade(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cascade_care_event
    ON aia_health_classification_cascade(care_event_id)
    WHERE care_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cascade_t3_triggered
    ON aia_health_classification_cascade(tenant_id, created_at DESC)
    WHERE t3_triggered = TRUE;
CREATE INDEX IF NOT EXISTS idx_cascade_disagreement
    ON aia_health_classification_cascade(tenant_id, created_at DESC)
    WHERE t2_agreement = FALSE;

COMMENT ON TABLE aia_health_classification_cascade IS
    'Audit completo de cada classificação event_type via cascade T1→T2→T3. '
    'Defesa clínica + análise de qualidade + reaprendizado.';
COMMENT ON COLUMN aia_health_classification_cascade.t3_rationale IS
    'Chain-of-thought do juiz (Claude Haiku) explicando por que escolheu '
    'esta classe sobre as alternativas de T1 e T2. Auditável.';

-- ═══════════════════════════════════════════════════════════════════
-- Estende tenant_config com review_strategy
-- ═══════════════════════════════════════════════════════════════════

-- Default = ambiente sem médico (B2C ou ILPI pequena), Claude Haiku
-- decide via juiz e notifica responsável quando T3 aciona.
-- Para clínicas/hospitais, mudar pra 'clinical_team' que envia pra fila
-- humana ao invés de juiz LLM.
ALTER TABLE aia_health_tenant_config
    ADD COLUMN IF NOT EXISTS review_strategy jsonb NOT NULL DEFAULT '{
        "mode": "no_clinical_team",
        "judge_model": "anthropic/claude-3-5-haiku-20241022",
        "notify_responsible_on_judge": true,
        "notify_responsible_on_critical": true,
        "responsible_notification_channel": "whatsapp"
    }'::jsonb;

COMMENT ON COLUMN aia_health_tenant_config.review_strategy IS
    'Estratégia de revisão clínica conforme tipo de cliente. '
    'mode: no_clinical_team (B2C/ILPI sem médico, juiz LLM decide) | '
    'clinical_team (clínica/hospital, fila humana decide) | '
    'hybrid_partner (parceiro tipo Tecnosenior decide via webhook).';
