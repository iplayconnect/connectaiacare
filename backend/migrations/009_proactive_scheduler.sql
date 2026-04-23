-- Migration 009 — Scheduler Proativo B2C
--
-- Fundação do acompanhamento B2C: check-ins diários, lembretes de
-- medicação, relatórios semanais, aniversários, etc.
--
-- Diferente do scheduler de care_events (que dispara APENAS durante
-- um evento ativo), este scheduler opera CONTINUAMENTE independente
-- de evento — o idoso/cuidador é contatado proativamente segundo
-- agenda pessoal.

-- ═══════════════════════════════════════════════════════════════
-- 1. Templates de mensagens
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_schedule_templates (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL,
    code          TEXT NOT NULL,                 -- 'morning_checkin', 'medication_reminder', 'weekly_report'
    name          TEXT NOT NULL,
    channel       TEXT NOT NULL CHECK (channel IN ('whatsapp', 'voice_call', 'email', 'sms')),
    message_body  TEXT NOT NULL,                 -- Pode ter placeholders {{first_name}}, {{date}}, etc
    buttons       JSONB,                         -- Pra botões rápidos de WhatsApp
    is_builtin    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_schedule_templates_tenant
    ON aia_health_schedule_templates(tenant_id);

-- ═══════════════════════════════════════════════════════════════
-- 2. Agendas proativas por assunto (paciente, cuidador, familiar)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_proactive_schedules (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id             TEXT NOT NULL,

    -- Polimorfismo "leve": pode ser patient, caregiver, family_member
    -- (FK não-formalizada; aplicação valida existência)
    subject_type          TEXT NOT NULL CHECK (subject_type IN (
        'patient', 'caregiver', 'family_member'
    )),
    subject_id            UUID NOT NULL,

    -- Template + configurações
    template_code         TEXT NOT NULL,         -- FK lógica em schedule_templates
    channel               TEXT NOT NULL DEFAULT 'whatsapp',

    -- Agendamento no padrão cron clássico (minuto, hora, dia-mês, mês, dia-semana)
    -- Ex: '0 9 * * *'   = todos os dias às 9h
    --     '0 10 * * 1'  = todas as segundas às 10h
    cron_expression       TEXT NOT NULL,
    timezone              TEXT NOT NULL DEFAULT 'America/Sao_Paulo',

    -- Janela tolerância (idoso pode responder sem estresse)
    response_window_min   INTEGER NOT NULL DEFAULT 120,

    -- Learning: padrão personal observado (atualizado pelo sistema)
    observed_response_avg_min  INTEGER,           -- Tempo médio histórico de resposta
    observed_response_p95_min  INTEGER,           -- P95 pra alertas

    -- Retry e escalação
    max_retries           INTEGER NOT NULL DEFAULT 2,
    retry_interval_min    INTEGER NOT NULL DEFAULT 30,
    escalate_after_no_response_min INTEGER NOT NULL DEFAULT 240,  -- 4h

    -- Telemetria
    last_fired_at         TIMESTAMPTZ,
    last_responded_at     TIMESTAMPTZ,
    consecutive_no_response INTEGER NOT NULL DEFAULT 0,
    total_fires           BIGINT NOT NULL DEFAULT 0,
    total_responses       BIGINT NOT NULL DEFAULT 0,

    -- Estado
    active                BOOLEAN NOT NULL DEFAULT TRUE,
    paused_until          TIMESTAMPTZ,           -- Ex: idoso internado, pausar check-ins
    pause_reason          TEXT,

    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_schedules_active
    ON aia_health_proactive_schedules(active, last_fired_at)
    WHERE active = TRUE AND paused_until IS NULL;

CREATE INDEX IF NOT EXISTS idx_proactive_schedules_subject
    ON aia_health_proactive_schedules(subject_type, subject_id);

CREATE INDEX IF NOT EXISTS idx_proactive_schedules_tenant
    ON aia_health_proactive_schedules(tenant_id);


-- ═══════════════════════════════════════════════════════════════
-- 3. Histórico de disparos (telemetria + audit)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_scheduled_fires (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id       UUID NOT NULL REFERENCES aia_health_proactive_schedules(id) ON DELETE CASCADE,
    tenant_id         TEXT NOT NULL,

    -- Quando deveria disparar × quando disparou de fato
    scheduled_for     TIMESTAMPTZ NOT NULL,
    fired_at          TIMESTAMPTZ,

    -- Canal + conteúdo gerado
    channel           TEXT NOT NULL,
    rendered_message  TEXT,
    external_ref      TEXT,                      -- ID da mensagem no Evolution/WhatsApp

    -- Resposta
    responded_at      TIMESTAMPTZ,
    response_text     TEXT,
    response_duration_seconds INTEGER,

    -- Retry
    retry_count       INTEGER NOT NULL DEFAULT 0,

    -- Estado
    status            TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN (
        'scheduled', 'fired', 'responded', 'no_response', 'escalated',
        'skipped', 'failed', 'expired'
    )),
    error_message     TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_fires_schedule
    ON aia_health_scheduled_fires(schedule_id, scheduled_for DESC);

CREATE INDEX IF NOT EXISTS idx_scheduled_fires_pending
    ON aia_health_scheduled_fires(status, scheduled_for)
    WHERE status IN ('scheduled', 'fired');

CREATE INDEX IF NOT EXISTS idx_scheduled_fires_tenant_date
    ON aia_health_scheduled_fires(tenant_id, fired_at DESC);


-- ═══════════════════════════════════════════════════════════════
-- 4. Heartbeat do worker (detecta scheduler parado)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_scheduler_heartbeat (
    worker_id       TEXT PRIMARY KEY,
    last_tick_at    TIMESTAMPTZ NOT NULL,
    schedules_checked BIGINT NOT NULL DEFAULT 0,
    fires_dispatched  BIGINT NOT NULL DEFAULT 0,
    errors_last_tick  INTEGER NOT NULL DEFAULT 0,
    meta              JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Query de monitoramento (alerta se scheduler para):
-- SELECT worker_id, NOW() - last_tick_at AS silent
-- FROM aia_health_scheduler_heartbeat
-- WHERE last_tick_at < NOW() - INTERVAL '5 minutes';


-- ═══════════════════════════════════════════════════════════════
-- 5. Relatórios periódicos já gerados (cache)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_periodic_reports (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL,
    subject_type  TEXT NOT NULL,
    subject_id    UUID NOT NULL,

    report_kind   TEXT NOT NULL CHECK (report_kind IN (
        'weekly_family', 'monthly_medical', 'daily_summary'
    )),

    -- Período coberto
    period_start  TIMESTAMPTZ NOT NULL,
    period_end    TIMESTAMPTZ NOT NULL,

    -- Conteúdo estruturado (JSON) + versão renderizada pra email/WhatsApp
    payload       JSONB NOT NULL,
    rendered_html TEXT,
    rendered_text TEXT,                          -- Versão WhatsApp curta

    -- Status de envio
    sent_at       TIMESTAMPTZ,
    sent_channels TEXT[],                        -- ['whatsapp', 'email']
    recipients    TEXT[],                        -- telefones/emails

    -- Cache TTL
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(subject_type, subject_id, report_kind, period_start)
);

CREATE INDEX IF NOT EXISTS idx_periodic_reports_subject
    ON aia_health_periodic_reports(subject_type, subject_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_periodic_reports_pending_send
    ON aia_health_periodic_reports(sent_at)
    WHERE sent_at IS NULL;


-- ═══════════════════════════════════════════════════════════════
-- 6. Seed de templates built-in
-- ═══════════════════════════════════════════════════════════════

INSERT INTO aia_health_schedule_templates
    (tenant_id, code, name, channel, message_body, buttons, is_builtin)
VALUES
    ('connectaiacare_demo', 'morning_checkin', 'Check-in matinal',
     'whatsapp',
     E'☀️ Bom dia, {{first_name}}! Como a senhora dormiu?\n\nResponda tocando em um dos botões abaixo.',
     '{"quick_replies": [{"id": "well", "text": "Bem 😊"}, {"id": "meh", "text": "Mais ou menos 😐"}, {"id": "bad", "text": "Mal 😟"}, {"id": "help", "text": "Preciso de ajuda 🆘"}]}'::jsonb,
     TRUE),

    ('connectaiacare_demo', 'evening_checkin', 'Check-in noturno',
     'whatsapp',
     E'🌙 Boa noite, {{first_name}}! Como foi o seu dia?\n\nTomou os remédios certinho?',
     '{"quick_replies": [{"id": "all_good", "text": "Tudo bem ✅"}, {"id": "some_issue", "text": "Algo estranho 🤔"}, {"id": "need_help", "text": "Preciso conversar 📞"}]}'::jsonb,
     TRUE),

    ('connectaiacare_demo', 'medication_reminder', 'Lembrete de medicação',
     'whatsapp',
     E'💊 Olá, {{first_name}}! Está na hora de tomar {{medication}}.\n\nLembre-se: {{dose}} · {{schedule_note}}',
     '{"quick_replies": [{"id": "taken", "text": "Já tomei ✅"}, {"id": "later", "text": "Vou tomar agora 👍"}, {"id": "forgot_had", "text": "Já tomei antes ⏱"}]}'::jsonb,
     TRUE),

    ('connectaiacare_demo', 'weekly_family_report', 'Relatório semanal família',
     'whatsapp',
     E'☀️ *Resumo semanal — {{patient_first_name}}*\n({{period_label}})\n\n{{summary_text}}\n\n{{next_event}}\n\nCom carinho, Equipe ConnectaIACare 💙',
     NULL,
     TRUE)
ON CONFLICT (tenant_id, code) DO UPDATE SET
    message_body = EXCLUDED.message_body,
    buttons = EXCLUDED.buttons,
    updated_at = now();


COMMENT ON TABLE aia_health_proactive_schedules IS
'Agendamentos proativos por assunto. Cron-style com timezone + janela tolerância + learning pattern.';

COMMENT ON COLUMN aia_health_proactive_schedules.observed_response_avg_min IS
'Atualizado pelo worker a cada resposta. Usado pra detectar desvio do padrão pessoal (evita falsos alarmes em idoso tranquilo).';

COMMENT ON TABLE aia_health_scheduler_heartbeat IS
'Monitoramento do worker. Alerta devops se last_tick_at > 5 min (scheduler parou).';
