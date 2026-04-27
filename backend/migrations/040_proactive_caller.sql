-- ConnectaIACare — Proactive Caller (Sofia decide dinamicamente quando ligar).
--
-- Complementa proactive_scheduler.py (WhatsApp via cron) e checkin_scheduler
-- (dentro de care_event ativo). Aqui o disparo é por SCORE clínico, não por
-- expressão temporal: avalia risk_score + adesão + eventos abertos + janela
-- horária do paciente, e decide se vale ligar AGORA.
--
-- Toda decisão (will_call OU skip) é registrada em
-- aia_health_proactive_call_decisions — auditável e analisável.

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- 1. Preferências de chamada por paciente
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS sofia_proactive_calls_enabled BOOLEAN
        NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS preferred_call_window_start TIME
        NOT NULL DEFAULT '08:00:00',
    ADD COLUMN IF NOT EXISTS preferred_call_window_end TIME
        NOT NULL DEFAULT '21:00:00',
    ADD COLUMN IF NOT EXISTS min_hours_between_calls INTEGER
        NOT NULL DEFAULT 4,
    ADD COLUMN IF NOT EXISTS do_not_disturb_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proactive_call_phone TEXT,
    ADD COLUMN IF NOT EXISTS proactive_scenario_code TEXT,
    ADD COLUMN IF NOT EXISTS proactive_call_timezone TEXT
        NOT NULL DEFAULT 'America/Sao_Paulo';

COMMENT ON COLUMN aia_health_patients.sofia_proactive_calls_enabled IS
    'Master switch — paciente opta por receber chamadas dinâmicas (LGPD opt-in).';
COMMENT ON COLUMN aia_health_patients.preferred_call_window_start IS
    'Hora local mais cedo aceitável (default 08:00) — antes disso, skip silencioso.';
COMMENT ON COLUMN aia_health_patients.preferred_call_window_end IS
    'Hora local mais tarde aceitável (default 21:00) — depois disso, skip silencioso.';
COMMENT ON COLUMN aia_health_patients.min_hours_between_calls IS
    'Intervalo mínimo entre ligações Sofia (default 4h) — evita spam.';
COMMENT ON COLUMN aia_health_patients.do_not_disturb_until IS
    'Pausa temporária — paciente pediu pra não ligar até essa data.';
COMMENT ON COLUMN aia_health_patients.proactive_call_phone IS
    'Override do telefone usado pelo proactive_caller (E.164 sem +). '
    'Se NULL, falls back pra responsible JSON.';
COMMENT ON COLUMN aia_health_patients.proactive_scenario_code IS
    'Override do scenario_code usado pelo proactive_caller. '
    'Se NULL, usa default do tenant.';


-- ════════════════════════════════════════════════════════════════
-- 2. Log de decisões — TODA avaliação fica registrada
-- ════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_proactive_call_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id)
        ON DELETE CASCADE,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- decisão
    decision TEXT NOT NULL CHECK (decision IN (
        'will_call',                  -- score >= threshold, vai disparar
        'skip_disabled',              -- patient.sofia_proactive_calls_enabled = false
        'skip_dnd',                   -- do_not_disturb_until > now
        'skip_outside_window',        -- fora de preferred_call_window
        'skip_too_soon',              -- ligou recentemente (< min_hours)
        'skip_low_score',             -- score < threshold
        'skip_no_phone',              -- não tem telefone discável
        'skip_no_scenario',           -- nenhum scenario_code resolvível
        'skip_circuit_open',          -- safety circuit breaker fechou tenant
        'failed_dispatch'             -- chamou voice-call-service e deu erro
    )),

    trigger_score INTEGER NOT NULL DEFAULT 0,

    -- breakdown explicativo: { risk_level, missed_doses_24h, open_urgent_events,
    --                          hours_since_last_call, scenario_code, phone, ... }
    breakdown JSONB NOT NULL DEFAULT '{}',

    -- se will_call: ID retornado pelo voice-call-service
    call_id TEXT,
    -- se failed_dispatch: motivo
    error TEXT,

    -- pra trace: trigger_score breakdown registrado mesmo em skip
    -- ajuda a calibrar threshold
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_proactive_decisions_tenant_recent
    ON aia_health_proactive_call_decisions(tenant_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_proactive_decisions_patient_recent
    ON aia_health_proactive_call_decisions(patient_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_proactive_decisions_will_call
    ON aia_health_proactive_call_decisions(tenant_id, evaluated_at DESC)
    WHERE decision = 'will_call';


-- ════════════════════════════════════════════════════════════════
-- 3. Default scenario_code por tenant (em tenant_config.guardrail_settings
--    seria misturar conceitos — vai em proactive_caller_settings dedicado)
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_tenant_config
    ADD COLUMN IF NOT EXISTS proactive_caller_settings JSONB
        NOT NULL DEFAULT '{
            "default_scenario_code": "paciente_checkin_matinal",
            "trigger_threshold": 50,
            "tick_interval_seconds": 300
        }'::jsonb;

COMMENT ON COLUMN aia_health_tenant_config.proactive_caller_settings IS
    'Config do worker: default_scenario_code (qual cenário usar), '
    'trigger_threshold (score mínimo pra disparar), tick_interval_seconds.';


COMMIT;
