-- ═══════════════════════════════════════════════════════════════════
-- 068 — Fluxo comercial completo (planos + demos + calls + propostas
--       + timeline)
--
-- Phase D Comercial — fundação do funil que Sofia (Whats + Voz + VoIP)
-- vai operar. Tabela aia_health_leads (migration 061) já tem o "card"
-- do lead com status. Faltava o que está AO REDOR do card:
--   - aia_health_plans                 → catálogo Sofia consulta pra apresentar
--   - aia_health_lead_demos            → demos agendadas (data/hora/responsável/sala)
--   - aia_health_lead_calls            → ligações registradas (Sofia VoIP, retornos)
--   - aia_health_lead_proposals        → propostas enviadas (valor, plano, validade)
--   - aia_health_lead_activities       → timeline agregada (kanban detail page)
--
-- Tudo aditivo, FKs com ON DELETE CASCADE pra apagar lead → apaga toda
-- atividade dele. RLS via tenant_id ainda não — leads são pré-tenant
-- (vão pra `converted_to_tenant_id` só quando convertem). Painel admin
-- (super_admin / admin_tenant) lê tudo.
-- ═══════════════════════════════════════════════════════════════════

BEGIN;

-- ═════════════ 1) Catálogo de planos vendáveis ═════════════════════

CREATE TABLE IF NOT EXISTS aia_health_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku TEXT NOT NULL UNIQUE,                    -- 'b2c_individual_basic', 'b2b_ilpi_pro_50leitos'
    name TEXT NOT NULL,                          -- 'Plano Individual Básico', 'ILPI Pro 50 Leitos'
    target_persona TEXT NOT NULL,                -- 'individual'|'familia'|'ilpi'|'clinica'|'hospital'
    target_segment TEXT,                         -- 'pequeno_porte'|'medio_porte'|'grande_porte'|'familiar'

    -- Pricing
    price_monthly_cents INT,                     -- preço mensal em centavos (NULL = sob consulta)
    price_setup_cents INT NOT NULL DEFAULT 0,    -- taxa de setup
    currency TEXT NOT NULL DEFAULT 'BRL',
    billing_period TEXT NOT NULL DEFAULT 'monthly', -- monthly|annual|one_time

    -- Capacidade
    max_patients INT,                            -- NULL = ilimitado
    max_caregivers INT,
    max_messages_month INT,                      -- limite mensagens Sofia
    max_voice_minutes_month INT,                 -- limite minutos voz/voip

    -- Features (jsonb pra flexibilidade)
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Ex: {"sofia_whatsapp": true, "sofia_voice": true, "sofia_voip": true,
    --      "drug_safety_review": true, "tecnosenior_integration": false,
    --      "central_24h_human": true, "connectalive_video": false}

    -- Sales pitch (Sofia consulta pra apresentar)
    pitch_short TEXT,                            -- 1-2 frases pra Sofia falar
    pitch_full TEXT,                             -- detalhamento pra propostas
    differentials JSONB NOT NULL DEFAULT '[]'::jsonb, -- ['drug_safety','24x7','...']

    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,
    public BOOLEAN NOT NULL DEFAULT TRUE,        -- aparece no site? (false = só vendido pelo time)

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (target_persona IN (
        'individual', 'familia', 'ilpi', 'clinica', 'hospital', 'parceiro'
    )),
    CHECK (billing_period IN ('monthly', 'annual', 'one_time'))
);

CREATE INDEX IF NOT EXISTS idx_plans_active_target
    ON aia_health_plans(active, target_persona) WHERE active = TRUE;

COMMENT ON TABLE aia_health_plans IS
    'Catálogo de planos vendáveis. Sofia consulta via tool query_plans '
    'pra apresentar opções aos leads. Frontend admin /comercial/planos '
    'edita. Quando um lead converte, conversion linka pro plan.id.';


-- ═════════════ 2) Demos agendadas ══════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_lead_demos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,

    -- Quem
    scheduled_by_user_id UUID REFERENCES aia_health_users(id), -- super_admin/admin que agendou
    scheduled_by_actor TEXT NOT NULL DEFAULT 'sofia',   -- 'sofia'|'human'|'self_service'
    assigned_to_user_id UUID REFERENCES aia_health_users(id),  -- quem vai conduzir a demo

    -- Quando + onde
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INT NOT NULL DEFAULT 30,
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    meeting_url TEXT,                            -- Zoom/Meet/ConnectaLive
    meeting_provider TEXT,                       -- 'zoom'|'meet'|'connectalive'|'in_person'

    -- Conteúdo
    plan_focus_id UUID REFERENCES aia_health_plans(id), -- plano que vamos demonstrar
    notes TEXT,                                  -- "Lead quer ver drug safety + integração Tecnosenior"

    -- Status
    status TEXT NOT NULL DEFAULT 'scheduled',    -- scheduled|confirmed|completed|no_show|cancelled
    confirmed_at TIMESTAMPTZ,                    -- lead confirmou (clicou no link?)
    completed_at TIMESTAMPTZ,
    completed_outcome TEXT,                      -- 'interested'|'follow_up'|'not_interested'|'converted'
    completed_summary TEXT,                      -- resumo pós-demo (humano preenche)

    -- Reminder/follow-up
    reminder_sent_at TIMESTAMPTZ,
    follow_up_at TIMESTAMPTZ,                    -- quando dar follow-up (next_action)

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN (
        'scheduled', 'confirmed', 'completed', 'no_show', 'cancelled'
    )),
    CHECK (scheduled_by_actor IN ('sofia', 'human', 'self_service')),
    CHECK (meeting_provider IN ('zoom', 'meet', 'connectalive', 'in_person', 'phone'))
);

CREATE INDEX IF NOT EXISTS idx_lead_demos_lead
    ON aia_health_lead_demos(lead_id, scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_demos_assigned
    ON aia_health_lead_demos(assigned_to_user_id, status, scheduled_at)
    WHERE status IN ('scheduled', 'confirmed');
CREATE INDEX IF NOT EXISTS idx_lead_demos_upcoming
    ON aia_health_lead_demos(scheduled_at)
    WHERE status IN ('scheduled', 'confirmed');

COMMENT ON TABLE aia_health_lead_demos IS
    'Demos agendadas pra leads. Sofia agenda via schedule_demo_with_calendar '
    'tool. Time comercial vê na agenda /comercial/demos. Após demo, '
    'humano preenche outcome + summary pra mover lead pro próximo estágio.';


-- ═════════════ 3) Calls (ligações) registradas ═════════════════════

CREATE TABLE IF NOT EXISTS aia_health_lead_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,

    -- Quem ligou pra quem
    direction TEXT NOT NULL,                     -- inbound|outbound (lead ligou? Sofia/comercial ligou pro lead?)
    called_by_actor TEXT NOT NULL,               -- 'sofia_voip'|'sofia_voice'|'human'|'auto_dialer'
    called_by_user_id UUID REFERENCES aia_health_users(id), -- se human

    -- Quando + duração
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    duration_seconds INT,

    -- Conteúdo
    call_type TEXT NOT NULL DEFAULT 'follow_up', -- discovery|follow_up|callback|proposal|closing|support
    transcript TEXT,                             -- transcrição (se via Sofia VoIP/Voz)
    summary TEXT,                                -- resumo (LLM ou humano)
    outcome TEXT,                                -- 'connected'|'voicemail'|'no_answer'|'busy'|'rejected'
    sentiment TEXT,                              -- 'positive'|'neutral'|'negative' (auto-detectado)
    next_action TEXT,                            -- 'schedule_demo'|'send_proposal'|'follow_up'|'closed_won'|'closed_lost'
    next_action_at TIMESTAMPTZ,

    -- Recording
    recording_url TEXT,                          -- audio gravado (LGPD: opt-in!)
    recording_consent BOOLEAN NOT NULL DEFAULT FALSE,

    -- Linkagem com sessão Sofia (se Sofia VoIP)
    sofia_session_id UUID REFERENCES aia_health_sofia_sessions(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (direction IN ('inbound', 'outbound')),
    CHECK (called_by_actor IN (
        'sofia_voip', 'sofia_voice', 'human', 'auto_dialer'
    )),
    CHECK (call_type IN (
        'discovery', 'follow_up', 'callback', 'proposal', 'closing',
        'support', 'qualification'
    )),
    CHECK (outcome IS NULL OR outcome IN (
        'connected', 'voicemail', 'no_answer', 'busy', 'rejected', 'failed'
    )),
    CHECK (sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE INDEX IF NOT EXISTS idx_lead_calls_lead
    ON aia_health_lead_calls(lead_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_calls_next_action
    ON aia_health_lead_calls(next_action_at)
    WHERE next_action_at IS NOT NULL;

COMMENT ON TABLE aia_health_lead_calls IS
    'Ligações registradas (Sofia VoIP/Voz inbound, comercial humano '
    'outbound, callbacks agendados). Sofia VoIP popula automaticamente '
    'quando recebe ligação de phone que bate com lead. Tool '
    'register_lead_call deixa Sofia salvar resumo pós-call.';


-- ═════════════ 4) Propostas enviadas ═══════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_lead_proposals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES aia_health_plans(id),

    -- Quem
    sent_by_user_id UUID REFERENCES aia_health_users(id),
    sent_by_actor TEXT NOT NULL DEFAULT 'human', -- 'sofia'|'human'

    -- Conteúdo da proposta
    custom_price_monthly_cents INT,              -- override do plano (negociação)
    custom_price_setup_cents INT,
    custom_features JSONB,                       -- features adicionais negociadas
    discount_percent NUMERIC(4,1),               -- desconto %
    valid_until DATE NOT NULL,                   -- validade da proposta

    -- Documento
    proposal_url TEXT,                           -- PDF ou link público
    proposal_html TEXT,                          -- HTML inline (pra preview/email)
    sent_via TEXT,                               -- 'email'|'whatsapp'|'in_demo'

    -- Status
    status TEXT NOT NULL DEFAULT 'sent',         -- sent|viewed|accepted|rejected|expired|withdrawn
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    viewed_at TIMESTAMPTZ,                       -- track abertura (pixel/link click)
    decided_at TIMESTAMPTZ,
    decision_reason TEXT,

    -- Conversão
    converted_to_tenant_id TEXT REFERENCES aia_health_tenants(id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN (
        'sent', 'viewed', 'accepted', 'rejected', 'expired', 'withdrawn'
    )),
    CHECK (sent_via IS NULL OR sent_via IN ('email', 'whatsapp', 'in_demo', 'voice_call'))
);

CREATE INDEX IF NOT EXISTS idx_lead_proposals_lead
    ON aia_health_lead_proposals(lead_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_proposals_status
    ON aia_health_lead_proposals(status, valid_until)
    WHERE status IN ('sent', 'viewed');

COMMENT ON TABLE aia_health_lead_proposals IS
    'Propostas comerciais enviadas. Sofia pode gerar via tool send_proposal. '
    'Time humano também envia via UI /comercial/leads/<id>/proposta. '
    'Quando aceita, lead.status=converted + lead.converted_to_tenant_id '
    'preenchido (idealmente cria novo tenant ILPI/clínica).';


-- ═════════════ 5) Timeline de atividades ═══════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_lead_activities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES aia_health_leads(id) ON DELETE CASCADE,

    -- Tipo
    activity_type TEXT NOT NULL,
    -- 'lead_created' | 'message_received' | 'message_sent' |
    -- 'call_made' | 'call_received' | 'demo_scheduled' |
    -- 'demo_completed' | 'proposal_sent' | 'proposal_accepted' |
    -- 'proposal_rejected' | 'note_added' | 'status_changed' |
    -- 'qualification_updated' | 'converted' | 'lost' | 'reassigned'

    -- Quem
    actor_type TEXT NOT NULL,                    -- 'sofia'|'human'|'system'|'lead' (próprio lead)
    actor_user_id UUID REFERENCES aia_health_users(id),
    actor_name TEXT,                             -- nome free-form (caso sofia: "Sofia (WhatsApp)")

    -- Conteúdo
    summary TEXT NOT NULL,                       -- 1 linha pra timeline
    details JSONB NOT NULL DEFAULT '{}'::jsonb,  -- payload completo

    -- Linkagem com row específica (opcional)
    related_demo_id UUID REFERENCES aia_health_lead_demos(id) ON DELETE SET NULL,
    related_call_id UUID REFERENCES aia_health_lead_calls(id) ON DELETE SET NULL,
    related_proposal_id UUID REFERENCES aia_health_lead_proposals(id) ON DELETE SET NULL,

    -- Importance pra UI (filtros)
    importance TEXT NOT NULL DEFAULT 'normal',   -- minor|normal|important|critical

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (actor_type IN ('sofia', 'human', 'system', 'lead')),
    CHECK (importance IN ('minor', 'normal', 'important', 'critical'))
);

CREATE INDEX IF NOT EXISTS idx_lead_activities_lead_time
    ON aia_health_lead_activities(lead_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_lead_activities_type
    ON aia_health_lead_activities(activity_type, occurred_at DESC);

COMMENT ON TABLE aia_health_lead_activities IS
    'Timeline cross-table de tudo que rolou com 1 lead. UI detail page '
    '(/comercial/leads/<id>) renderiza isso linearmente. Sofia popula via '
    'register_lead_activity tool quando faz algo relevante (mandou msg, '
    'chamou tool, etc). Triggers internos populam automaticamente quando '
    'lead muda de status, demo agendada, proposta enviada.';


-- ═════════════ Triggers pra updated_at ═════════════════════════════

CREATE OR REPLACE FUNCTION aia_health_set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_plans_updated') THEN
        CREATE TRIGGER trg_plans_updated BEFORE UPDATE ON aia_health_plans
            FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();
    END IF;
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

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_leads_status_activity') THEN
        CREATE TRIGGER trg_leads_status_activity
            AFTER UPDATE ON aia_health_leads
            FOR EACH ROW
            EXECUTE FUNCTION aia_health_log_lead_status_activity();
    END IF;
END $$;


-- ═════════════ Seed: 4 planos iniciais (Sofia precisa de algo
--                pra apresentar dia 1) ═════════════════════════════

INSERT INTO aia_health_plans (
    sku, name, target_persona, target_segment,
    price_monthly_cents, price_setup_cents, currency, billing_period,
    max_patients, max_caregivers, max_messages_month, max_voice_minutes_month,
    features, pitch_short, pitch_full, differentials, active, public
) VALUES
-- B2C Individual (paciente sozinho ou família)
(
    'b2c_individual_basic',
    'Individual Básico',
    'individual', 'familiar',
    9900, 0, 'BRL', 'monthly',  -- R$99/mês
    1, 2, 500, 60,
    '{"sofia_whatsapp": true, "sofia_voice": false, "sofia_voip": false, '
    '"drug_safety_review": true, "central_24h_human": false}'::jsonb,
    'Sofia no WhatsApp 24/7 com checagem farmacológica pra 1 idoso.',
    'Plano voltado pra família que cuida de 1 idoso em casa. Sofia '
    'atende dúvidas sobre medicação, lembra horários, alerta a família '
    'se detectar problema farmacológico (Beers, interação). Não inclui '
    'Central 24h humana.',
    '["pharmacovigilance","whatsapp","lembrete_meds"]'::jsonb,
    TRUE, TRUE
),
-- B2C Premium
(
    'b2c_individual_premium',
    'Individual Premium',
    'individual', 'familiar',
    24900, 0, 'BRL', 'monthly',  -- R$249/mês
    1, 4, 2000, 240,
    '{"sofia_whatsapp": true, "sofia_voice": true, "sofia_voip": true, '
    '"drug_safety_review": true, "central_24h_human": true, '
    '"connectalive_video": true, "weekly_report": true}'::jsonb,
    'Tudo do Básico + Sofia por voz, ligação 24/7 e Central humana.',
    'Plano completo pra quem quer presença total. Sofia atende WhatsApp, '
    'voz e telefone. Cuidador pode ligar a qualquer hora. Central 24h '
    'humana entra quando Sofia escala. Relatório semanal pra família.',
    '["pharmacovigilance","whatsapp","voice","voip","central_24h","video"]'::jsonb,
    TRUE, TRUE
),
-- B2B ILPI Pequena
(
    'b2b_ilpi_starter_30leitos',
    'ILPI Starter (até 30 leitos)',
    'ilpi', 'pequeno_porte',
    NULL, 200000, 'BRL', 'monthly',  -- preço sob consulta + R$2k setup
    30, 20, 5000, 600,
    '{"sofia_whatsapp": true, "sofia_voice": true, "sofia_voip": true, '
    '"drug_safety_review": true, "central_24h_human": true, '
    '"tecnosenior_integration": false, "connectalive_video": true, '
    '"shift_management": true, "weekly_report": true}'::jsonb,
    'Sofia coordenando comunicação entre cuidadores e equipe clínica.',
    'Solução completa pra ILPI até 30 leitos. Sofia recebe relatos dos '
    'cuidadores via WhatsApp/voz, valida medicações contra Beers/STOPP, '
    'escala intercorrências pra equipe clínica via Central 24h. '
    'Integração opcional com sistemas de prontuário sob consulta.',
    '["pharmacovigilance","multi_caregiver","central_24h","relatorios_clinicos"]'::jsonb,
    TRUE, TRUE
),
-- B2B Hospital
(
    'b2b_hospital_geriatria',
    'Hospital Geriatria',
    'hospital', 'medio_porte',
    NULL, 500000, 'BRL', 'monthly',  -- preço sob consulta + R$5k setup
    NULL, NULL, NULL, NULL,
    '{"sofia_whatsapp": true, "sofia_voice": true, "sofia_voip": true, '
    '"drug_safety_review": true, "central_24h_human": true, '
    '"medical_handoff": true, "doctor_dashboard": true, '
    '"emergency_escalation": true, "shift_management": true, '
    '"hl7_fhir_integration": true, "audit_lgpd_complete": true}'::jsonb,
    'Sofia integrada ao plantão hospitalar com escalonamento clínico.',
    'Plano enterprise pra hospital com ala/setor geriátrico. Sofia '
    'integrada com plantão médico, escalonamento clínico via handoff_clinical, '
    'dashboard pra equipe médica, integração HL7/FHIR sob consulta, '
    'auditoria LGPD completa.',
    '["pharmacovigilance","escalation_clinical","hl7_fhir","compliance_lgpd"]'::jsonb,
    TRUE, FALSE   -- enterprise: não público no site
)
ON CONFLICT (sku) DO NOTHING;


COMMIT;
