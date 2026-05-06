-- ═══════════════════════════════════════════════════════════════════
-- 069 — Funil comercial UNIFICADO em aia_health_plans
--      + Reposicionamento agressivo do catálogo B2C (decisão Alex+Milene)
--
-- A migration 068 (mergeada via PR #137) falhou em prod porque
-- aia_health_plans JÁ EXISTIA — criada por migration #011 b2c
-- subscriptions com schema diferente + 3 rows seed do tenant
-- sofiacuida_b2c (Essencial/Premium/Premium+Device).
--
-- Esta migration UNIFICA tudo numa só tabela com:
--   1) Coluna `scope` discriminadora ('subscription_b2c' | 'commercial_sales')
--   2) Colunas comerciais aditivas (target_persona, max_patients, etc.)
--   3) tenant_id passa a NULLABLE (planos comerciais sem tenant)
--   4) Backfill rows existentes
--   5) Reposicionamento agressivo:
--      - Essencial: R$49,90 → R$39,90 + 2 ligações VoIP/dia
--      - NOVO: Família R$69,90 (2 idosos, 2 ligações totais)
--      - Premium: mantém R$149,90 (com 3 ligações/dia + Central 24h)
--      - Premium+Device: DESATIVADO (sem hardware nessa fase do projeto)
--   6) Adiciona ILPI Starter + Hospital Geriatria (B2B sob consulta)
--
-- Regra de negócio (vai pro prompt Sofia comercial):
--   - Sofia NUNCA fecha venda autônoma
--   - Sempre agenda demo (schedule_demo_with_calendar) ou
--     callback (schedule_callback_call) pra time humano fechar
--   - B2B: Sofia NUNCA menciona preço — só agenda
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ═════════════ 1) Expansão de aia_health_plans ════════════════════

ALTER TABLE aia_health_plans
    ALTER COLUMN tenant_id DROP NOT NULL;

ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS scope text NOT NULL DEFAULT 'subscription_b2c'
        CHECK (scope IN ('subscription_b2c', 'commercial_sales'));

ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS target_persona text;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS target_segment text;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS price_monthly_cents int;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS price_setup_cents int NOT NULL DEFAULT 0;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS max_patients int;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS max_caregivers int;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS max_messages_month int;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS max_voice_minutes_month int;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS daily_calls_count int NOT NULL DEFAULT 0;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS pitch_short text;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS pitch_full text;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS differentials jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS public boolean NOT NULL DEFAULT TRUE;
ALTER TABLE aia_health_plans
    ADD COLUMN IF NOT EXISTS requires_demo_to_close boolean NOT NULL DEFAULT FALSE;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'aia_health_plans_target_persona_check'
    ) THEN
        ALTER TABLE aia_health_plans
            ADD CONSTRAINT aia_health_plans_target_persona_check
            CHECK (target_persona IS NULL OR target_persona IN (
                'individual', 'familia', 'ilpi', 'clinica', 'hospital', 'parceiro'
            ));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_plans_scope_target
    ON aia_health_plans(scope, target_persona) WHERE active = TRUE;

COMMENT ON COLUMN aia_health_plans.scope IS
    'subscription_b2c: paciente/família assina via /planos. '
    'commercial_sales: time vende, Sofia recomenda mas NÃO fecha.';
COMMENT ON COLUMN aia_health_plans.daily_calls_count IS
    'Quantidade de ligações automáticas Sofia VoIP por dia. '
    '0=sem; 2=Essencial/Família (manhã+noite); 3=Premium (manhã+meio+noite).';
COMMENT ON COLUMN aia_health_plans.requires_demo_to_close IS
    'Se TRUE, Sofia comercial NUNCA fecha venda — sempre agenda demo/call. '
    'B2B sempre TRUE (ILPI/Hospital). B2C self-service mantém FALSE pra '
    'permitir checkout direto na landing.';


-- ═════════════ 2) Reposicionamento dos planos B2C existentes ══════

-- 2.1 — Sofia Cuida Essencial: R$49,90 → R$39,90 + 2 ligações/dia + drug safety
UPDATE aia_health_plans SET
    scope = 'subscription_b2c',
    target_persona = 'familia',
    target_segment = 'familiar',
    price_cents = 3990,
    price_monthly_cents = 3990,
    max_patients = 1,
    max_beneficiaries = 1,
    daily_calls_count = 2,
    public = TRUE,
    pitch_short = 'Drug Safety + WhatsApp 24/7 + 2 ligações diárias da Sofia pra 1 idoso.',
    pitch_full = 'Plano de entrada agressivo. Sofia conversa com seu idoso 2 vezes por dia: '
                 'pela manhã pergunta como dormiu/como se sente, à noite pergunta como foi o dia. '
                 'INCLUI Drug Safety completo (cruzamento de medicamentos contra Beers/STOPP/'
                 'interações — 142 drugs no nosso knowledge graph). Lembra horários de medicação, '
                 'escala pra família se identificar problema. NÃO inclui voice biomarkers '
                 '(análise de sinais de regressão por voz) — esse é do Família+.',
    differentials = '["pharmacovigilance_full","whatsapp","ligacoes_diarias_voip","lembrete_meds","escalacao_familia"]'::jsonb,
    tagline = 'Drug Safety + WhatsApp + 2 ligações diárias',
    features = '["Sofia no WhatsApp 24/7","2 ligações diárias da Sofia VoIP (manhã + noite)","Drug Safety completo (Beers, interações, dose limits)","Lembretes de medicação","Escalação automática pra família","Relatório semanal pra família","Até 3 contatos de emergência"]'::jsonb
WHERE sku = 'essencial';

-- 2.2 — Sofia Cuida Premium: mantém R$149,90 mas reforça pitch
UPDATE aia_health_plans SET
    scope = 'subscription_b2c',
    target_persona = 'familia',
    target_segment = 'familiar',
    price_monthly_cents = 14990,
    max_patients = COALESCE(max_patients, 2),
    daily_calls_count = 3,
    public = TRUE,
    pitch_short = '3 ligações diárias + Central 24h humana + teleconsulta mensal pra até 2 idosos.',
    pitch_full = 'Plano completo. Sofia conversa 3x ao dia (manhã, meio-dia, noite). Drug safety '
                 'completo (142 drugs, Beers/STOPP). Análise de voz por biomarcadores (detecta '
                 'sinais de regressão). Central 24h humana entra quando Sofia escala. '
                 'Teleconsulta com geriatra inclusa por mês. Vídeo ConnectaLive.',
    differentials = '["pharmacovigilance_full","voice_biomarkers","central_24h","teleconsulta","video","ligacoes_3x_dia"]'::jsonb
WHERE sku = 'premium';

-- 2.3 — Sofia Cuida Premium + Dispositivo: DESATIVADO
UPDATE aia_health_plans SET
    active = FALSE,
    public = FALSE,
    scope = 'subscription_b2c',
    target_persona = 'familia'
WHERE sku = 'premium_device';


-- ═════════════ 3) NOVO plano: Família R$69,90 ══════════════════════

INSERT INTO aia_health_plans (
    tenant_id, sku, name, scope, target_persona, target_segment,
    price_cents, price_monthly_cents, price_setup_cents, currency, billing_period,
    max_beneficiaries, max_patients, max_caregivers,
    max_messages_month, max_voice_minutes_month, daily_calls_count,
    features, max_emergency_contacts,
    trial_days, trial_requires_card, pix_allows_trial,
    required_verification, display_order, active, public,
    requires_demo_to_close,
    tagline, pitch_short, pitch_full, differentials
) VALUES (
    'sofiacuida_b2c', 'familia', 'Sofia Cuida Família',
    'subscription_b2c', 'familia', 'familiar',
    6990, 6990, 0, 'BRL', 'monthly',
    2, 2, 4, 1500, 180, 2,
    '["Sofia no WhatsApp 24/7","2 ligações diárias da Sofia VoIP (configurável: idoso 1, idoso 2 ou cuidador)","Drug Safety completo (142 medicamentos, Beers/STOPP)","Análise de voz por biomarcadores (sinais de regressão)","Lembretes de medicação personalizados","Escalação automática pra família","Relatório semanal pra família","Até 5 contatos de emergência"]'::jsonb,
    5, 0, FALSE, FALSE, 'cpf_whatsapp', 20, TRUE, TRUE,
    FALSE,
    'Para casais ou 2 idosos da família — drug safety + voz biomarcadores',
    'Plano de entrada pra cuidar de 2 idosos (esposa+marido, pai+mãe). 2 ligações diárias da Sofia (configurável). Drug Safety completo cruzando medicamentos. Análise de voz biomarcadores.',
    'Filho/cuidador contrata 1 plano pros 2 pais. Sofia liga 2x ao dia (manhã e noite) — configura se ligações vão pros idosos diretos, pro cuidador, ou alterna entre eles. INCLUI drug safety completo (cruzamento de medicamentos contra Beers/STOPP/interações) e análise de voz por biomarcadores (sinais de regressão cognitiva ou física). Sem Central 24h humana — esse é o salto pro Premium.',
    '["pharmacovigilance_full","voice_biomarkers","ligacoes_diarias_voip","2_idosos","cruzamento_medicamentos"]'::jsonb
) ON CONFLICT (sku) DO UPDATE SET
    name = EXCLUDED.name,
    scope = EXCLUDED.scope,
    target_persona = EXCLUDED.target_persona,
    price_monthly_cents = EXCLUDED.price_monthly_cents,
    daily_calls_count = EXCLUDED.daily_calls_count,
    features = EXCLUDED.features,
    pitch_short = EXCLUDED.pitch_short,
    pitch_full = EXCLUDED.pitch_full,
    differentials = EXCLUDED.differentials,
    active = TRUE,
    updated_at = NOW();


-- ═════════════ 4) Planos B2B (commercial_sales — sob consulta) ══════

INSERT INTO aia_health_plans (
    tenant_id, sku, name, scope, target_persona, target_segment,
    price_cents, price_monthly_cents, price_setup_cents, currency, billing_period,
    max_beneficiaries, max_patients, max_caregivers,
    max_messages_month, max_voice_minutes_month, daily_calls_count,
    features, max_emergency_contacts,
    trial_days, trial_requires_card, pix_allows_trial,
    required_verification, display_order, active, public,
    requires_demo_to_close,
    pitch_short, pitch_full, differentials
) VALUES
-- ILPI Starter (até 30 leitos) — sob consulta
(NULL, 'b2b_ilpi_starter_30leitos', 'ILPI Starter (até 30 leitos)',
 'commercial_sales', 'ilpi', 'pequeno_porte',
 0, NULL, 0, 'BRL', 'monthly',
 NULL, 30, 20, 5000, 600, 0,
 '["Sofia multi-cuidador WhatsApp","Sofia voz e VoIP","Drug Safety completo","Análise de voz biomarcadores","Central 24h humana","Relatórios clínicos","Gestão de turnos","Integração opcional com Tecnosenior/HL7"]'::jsonb,
 NULL, 0, FALSE, FALSE, 'cpf_whatsapp', 200, TRUE, TRUE,
 TRUE,
 'Sofia coordenando comunicação entre cuidadores e equipe clínica.',
 'Solução pra ILPI até 30 leitos. Sofia recebe relatos via WhatsApp/voz, valida medicações contra Beers/STOPP/interações, escala intercorrências pra equipe clínica via Central 24h. Análise de voz por biomarcadores em todos os idosos. Gestão de turnos integrada. Preço sob consulta — agendamento de demo obrigatório.',
 '["pharmacovigilance","multi_caregiver","central_24h","relatorios_clinicos","voice_biomarkers","gestao_turnos"]'::jsonb),

-- Hospital Geriatria — enterprise (não público)
(NULL, 'b2b_hospital_geriatria', 'Hospital Geriatria',
 'commercial_sales', 'hospital', 'medio_porte',
 0, NULL, 0, 'BRL', 'monthly',
 NULL, NULL, NULL, NULL, NULL, 0,
 '["Plantão médico integrado","Escalonamento clínico","Doctor dashboard","Emergency escalation","HL7/FHIR integration","Audit LGPD completo","Drug Safety + voice biomarkers"]'::jsonb,
 NULL, 0, FALSE, FALSE, 'cpf_whatsapp', 300, TRUE, FALSE,
 TRUE,
 'Sofia integrada ao plantão hospitalar com escalonamento clínico.',
 'Plano enterprise pra hospital com ala/setor geriátrico. Sofia integrada ao plantão médico, escalonamento clínico via handoff_clinical, dashboard pra equipe médica, integração HL7/FHIR sob consulta, auditoria LGPD completa. Sob consulta — não público no site, agendamento via time enterprise.',
 '["pharmacovigilance","escalation_clinical","hl7_fhir","compliance_lgpd","plantao_24h"]'::jsonb)
ON CONFLICT (sku) DO UPDATE SET
    name = EXCLUDED.name,
    scope = EXCLUDED.scope,
    target_persona = EXCLUDED.target_persona,
    pitch_short = EXCLUDED.pitch_short,
    pitch_full = EXCLUDED.pitch_full,
    differentials = EXCLUDED.differentials,
    requires_demo_to_close = EXCLUDED.requires_demo_to_close,
    updated_at = NOW();


-- ═════════════ 5) Tabelas lead_* (drop+recreate idempotente) ═══════

DROP TABLE IF EXISTS aia_health_lead_activities CASCADE;
DROP TABLE IF EXISTS aia_health_lead_proposals CASCADE;
DROP TABLE IF EXISTS aia_health_lead_calls CASCADE;
DROP TABLE IF EXISTS aia_health_lead_demos CASCADE;


CREATE TABLE aia_health_lead_demos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,
    scheduled_by_user_id UUID REFERENCES aia_health_users(id),
    scheduled_by_actor text NOT NULL DEFAULT 'sofia',
    assigned_to_user_id UUID REFERENCES aia_health_users(id),
    scheduled_at timestamptz NOT NULL,
    duration_minutes int NOT NULL DEFAULT 30,
    timezone text NOT NULL DEFAULT 'America/Sao_Paulo',
    meeting_url text,
    meeting_provider text,
    plan_focus_id UUID REFERENCES aia_health_plans(id),
    notes text,
    status text NOT NULL DEFAULT 'scheduled',
    confirmed_at timestamptz,
    completed_at timestamptz,
    completed_outcome text,
    completed_summary text,
    reminder_sent_at timestamptz,
    follow_up_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CHECK (status IN ('scheduled', 'confirmed', 'completed', 'no_show', 'cancelled')),
    CHECK (scheduled_by_actor IN ('sofia', 'human', 'self_service')),
    CHECK (meeting_provider IS NULL OR meeting_provider IN ('zoom', 'meet', 'connectalive', 'in_person', 'phone'))
);

CREATE INDEX idx_lead_demos_lead ON aia_health_lead_demos(lead_id, scheduled_at DESC);
CREATE INDEX idx_lead_demos_assigned ON aia_health_lead_demos(assigned_to_user_id, status, scheduled_at)
    WHERE status IN ('scheduled', 'confirmed');
CREATE INDEX idx_lead_demos_upcoming ON aia_health_lead_demos(scheduled_at)
    WHERE status IN ('scheduled', 'confirmed');


CREATE TABLE aia_health_lead_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,
    direction text NOT NULL,
    called_by_actor text NOT NULL,
    called_by_user_id UUID REFERENCES aia_health_users(id),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    duration_seconds int,
    call_type text NOT NULL DEFAULT 'follow_up',
    transcript text,
    summary text,
    outcome text,
    sentiment text,
    next_action text,
    next_action_at timestamptz,
    recording_url text,
    recording_consent boolean NOT NULL DEFAULT FALSE,
    sofia_session_id UUID REFERENCES aia_health_sofia_sessions(id),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CHECK (direction IN ('inbound', 'outbound')),
    CHECK (called_by_actor IN ('sofia_voip', 'sofia_voice', 'human', 'auto_dialer')),
    CHECK (call_type IN ('discovery', 'follow_up', 'callback', 'proposal', 'closing', 'support', 'qualification')),
    CHECK (outcome IS NULL OR outcome IN ('connected', 'voicemail', 'no_answer', 'busy', 'rejected', 'failed')),
    CHECK (sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE INDEX idx_lead_calls_lead ON aia_health_lead_calls(lead_id, started_at DESC);
CREATE INDEX idx_lead_calls_next_action ON aia_health_lead_calls(next_action_at)
    WHERE next_action_at IS NOT NULL;


CREATE TABLE aia_health_lead_proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES aia_health_plans(id),
    sent_by_user_id UUID REFERENCES aia_health_users(id),
    sent_by_actor text NOT NULL DEFAULT 'human',
    custom_price_monthly_cents int,
    custom_price_setup_cents int,
    custom_features jsonb,
    discount_percent numeric(4,1),
    valid_until date NOT NULL,
    proposal_url text,
    proposal_html text,
    sent_via text,
    status text NOT NULL DEFAULT 'sent',
    sent_at timestamptz NOT NULL DEFAULT NOW(),
    viewed_at timestamptz,
    decided_at timestamptz,
    decision_reason text,
    converted_to_tenant_id text REFERENCES aia_health_tenants(id),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    CHECK (status IN ('sent', 'viewed', 'accepted', 'rejected', 'expired', 'withdrawn')),
    CHECK (sent_via IS NULL OR sent_via IN ('email', 'whatsapp', 'in_demo', 'voice_call'))
);

CREATE INDEX idx_lead_proposals_lead ON aia_health_lead_proposals(lead_id, sent_at DESC);
CREATE INDEX idx_lead_proposals_status ON aia_health_lead_proposals(status, valid_until)
    WHERE status IN ('sent', 'viewed');


CREATE TABLE aia_health_lead_activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,
    activity_type text NOT NULL,
    actor_type text NOT NULL,
    actor_user_id UUID REFERENCES aia_health_users(id),
    actor_name text,
    summary text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    related_demo_id UUID REFERENCES aia_health_lead_demos(id) ON DELETE SET NULL,
    related_call_id UUID REFERENCES aia_health_lead_calls(id) ON DELETE SET NULL,
    related_proposal_id UUID REFERENCES aia_health_lead_proposals(id) ON DELETE SET NULL,
    importance text NOT NULL DEFAULT 'normal',
    occurred_at timestamptz NOT NULL DEFAULT NOW(),
    created_at timestamptz NOT NULL DEFAULT NOW(),
    CHECK (actor_type IN ('sofia', 'human', 'system', 'lead')),
    CHECK (importance IN ('minor', 'normal', 'important', 'critical'))
);

CREATE INDEX idx_lead_activities_lead_time ON aia_health_lead_activities(lead_id, occurred_at DESC);
CREATE INDEX idx_lead_activities_type ON aia_health_lead_activities(activity_type, occurred_at DESC);


-- ═════════════ Triggers updated_at ═════════════════════════════════

CREATE OR REPLACE FUNCTION aia_health_set_updated_at()
RETURNS trigger AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_lead_demos_updated') THEN
        CREATE TRIGGER trg_lead_demos_updated BEFORE UPDATE ON aia_health_lead_demos
            FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_lead_proposals_updated') THEN
        CREATE TRIGGER trg_lead_proposals_updated BEFORE UPDATE ON aia_health_lead_proposals
            FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();
    END IF;
END $$;


-- ═════════════ Trigger: lead status change → activity ══════════════

CREATE OR REPLACE FUNCTION aia_health_log_lead_status_activity()
RETURNS trigger AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO aia_health_lead_activities (
            lead_id, activity_type, actor_type, actor_name,
            summary, details, importance
        ) VALUES (
            NEW.id, 'status_changed', 'system', 'system_trigger',
            FORMAT('Status: %s → %s', OLD.status, NEW.status),
            jsonb_build_object('from', OLD.status, 'to', NEW.status),
            CASE WHEN NEW.status IN ('converted', 'lost') THEN 'important'
                 ELSE 'normal' END
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_leads_status_activity') THEN
        CREATE TRIGGER trg_leads_status_activity
            AFTER UPDATE ON aia_health_leads
            FOR EACH ROW EXECUTE FUNCTION aia_health_log_lead_status_activity();
    END IF;
END $$;


COMMIT;
