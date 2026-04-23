-- Migration 010 — Medication Schedules + Events + Imports
--
-- Motor de lembretes de medicação B2C + B2B.
--
-- 3 tabelas:
--   1. aia_health_medication_schedules — definição (o que, quando, como)
--   2. aia_health_medication_events     — execução (cada dose prevista, estado)
--   3. aia_health_medication_imports    — fotos/áudios em análise (OCR)
--
-- Fontes de dados:
--   - Prescrições de teleconsulta (populate automático no sign)
--   - Onboarding multimodal (foto da caixa/receita/bula via Claude Vision)
--   - Entrada manual do cuidador
--   - Import de sistemas externos (TotalCare/MedMonitor)

-- ═══════════════════════════════════════════════════════════════════
-- 1. SCHEDULES — o que tomar e quando
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_medication_schedules (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL,
    patient_id    UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,

    -- Identificação do medicamento
    medication_name TEXT NOT NULL,                 -- "Levodopa+Carbidopa"
    medication_name_normalized TEXT,               -- "levodopa carbidopa" (lower + trgm)
    anvisa_code   TEXT,                            -- futuro: catálogo ANVISA
    dose          TEXT NOT NULL,                   -- "250/25mg" ou "1/2 comprimido"
    dose_form     TEXT,                            -- comprimido | cápsula | gotas | ml | spray
    route         TEXT DEFAULT 'oral',             -- oral | sublingual | tópica | injetável

    -- Posologia (flexível, suporta casos reais)
    schedule_type TEXT NOT NULL CHECK (schedule_type IN (
        'fixed_daily',      -- todos os dias nos mesmos horários
        'fixed_weekly',     -- só em dias específicos da semana (ex: Alendronato seg)
        'fixed_monthly',    -- dia do mês (ex: Depo injetável)
        'cycle',            -- N dias consecutivos (antibiótico 7 dias)
        'prn',              -- se necessário — não gera lembrete, só registro
        'custom'            -- escape hatch (cron ou lógica customizada)
    )),
    times_of_day  TIME[],                          -- [07:00, 11:00, 15:00, 19:00]
    days_of_week  INTEGER[],                       -- [1,3,5] = seg/qua/sex (ISO: 1=seg..7=dom)
    day_of_month  INTEGER,                         -- 1..31 (fixed_monthly)
    cycle_length_days INTEGER,                     -- 7 (antibiótico)

    -- Janela e tolerância
    reminder_advance_min INTEGER NOT NULL DEFAULT 10,
    tolerance_minutes    INTEGER NOT NULL DEFAULT 60,
    min_hours_between_doses NUMERIC(4,1) DEFAULT 4.0,  -- intervalo mínimo (Levodopa=4h)

    -- Condições especiais
    with_food     TEXT CHECK (with_food IN ('with', 'without', 'either')) DEFAULT 'either',
    special_instructions TEXT,                     -- "em jejum, 30min antes do café"
    warnings      TEXT[],                          -- ["não combinar com leite", "cuidado com vitamina K"]

    -- Origem (rastreabilidade + audit clínico)
    source_type   TEXT NOT NULL CHECK (source_type IN (
        'prescription',            -- receita de teleconsulta (source_id = prescription_item_id)
        'patient_self_report',     -- idoso declarou no onboarding
        'family_report',           -- familiar informou
        'caregiver_pro',           -- cuidador profissional
        'ocr_image',               -- extraído de foto (source_id = medication_imports.id)
        'ocr_audio',               -- extraído de áudio
        'imported_totalcare',      -- sync com MedMonitor
        'manual_admin'
    )),
    source_id     TEXT,                            -- UUID ou string contextual
    source_confidence NUMERIC(3,2) DEFAULT 1.00,   -- 0.00-1.00 (importante pra OCR)

    added_by_type TEXT,                            -- 'patient' | 'family' | 'caregiver' | 'doctor'
    added_by_id   UUID,

    -- Verificação (dupla confirmação em casos de OCR ou auto-declaração)
    verification_status TEXT NOT NULL DEFAULT 'confirmed' CHECK (verification_status IN (
        'confirmed',        -- ok, pode lembrar
        'needs_review',     -- OCR incerto OU conflito entre fontes
        'conflicting',      -- paciente disse X, familiar disse Y
        'superseded'        -- substituído por nova prescrição
    )),
    verified_by_type TEXT,
    verified_by_id   UUID,
    verified_at      TIMESTAMPTZ,
    conflict_notes   TEXT,

    -- Canal preferido (herda do plano, pode ser override)
    preferred_channels TEXT[] DEFAULT ARRAY['whatsapp'],  -- whatsapp, voice_call, push

    -- Ciclo de vida
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    starts_at     DATE NOT NULL DEFAULT CURRENT_DATE,
    ends_at       DATE,                            -- NULL = indefinido (uso contínuo)
    paused_until  TIMESTAMPTZ,                     -- pausa temporária (internação)
    pause_reason  TEXT,
    deactivated_at TIMESTAMPTZ,
    deactivation_reason TEXT,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medication_sched_patient_active
    ON aia_health_medication_schedules(patient_id, active)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_medication_sched_tenant
    ON aia_health_medication_schedules(tenant_id);

CREATE INDEX IF NOT EXISTS idx_medication_sched_review
    ON aia_health_medication_schedules(verification_status)
    WHERE verification_status IN ('needs_review', 'conflicting');

CREATE INDEX IF NOT EXISTS idx_medication_sched_name_trgm
    ON aia_health_medication_schedules USING gin (medication_name_normalized gin_trgm_ops);


-- ═══════════════════════════════════════════════════════════════════
-- 2. EVENTS — cada dose prevista + execução
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_medication_events (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    schedule_id   UUID NOT NULL REFERENCES aia_health_medication_schedules(id) ON DELETE CASCADE,
    patient_id    UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,
    tenant_id     TEXT NOT NULL,

    -- Momento
    scheduled_at      TIMESTAMPTZ NOT NULL,        -- horário calculado da dose
    reminder_sent_at  TIMESTAMPTZ,                 -- quando o lembrete foi enviado
    confirmed_at      TIMESTAMPTZ,                 -- quando confirmou tomada
    confirmed_by      TEXT CHECK (confirmed_by IN (
        'patient', 'caregiver', 'family', 'auto_assumed', 'dispenser_device'
    )),

    -- Estado
    status        TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN (
        'scheduled',      -- futuro, ainda não enviou lembrete
        'reminder_sent',  -- lembrete enviado, aguardando confirmação
        'taken',          -- confirmado
        'missed',         -- passou da janela sem confirmação
        'skipped',        -- explicitamente pulado com motivo
        'refused',        -- paciente recusou (registra)
        'paused',         -- medicação em pausa
        'cancelled'       -- cancelada (mudança de schedule)
    )),

    -- Dose executada (pode diferir da prescrita)
    actual_dose_taken TEXT,                        -- "1 comprimido" | "1/2 comprimido"
    notes         TEXT,                            -- "teve azia, recusou"

    -- Comunicação
    reminder_channel TEXT,
    reminder_external_ref TEXT,                    -- id mensagem Evolution
    response_external_ref TEXT,                    -- id mensagem de confirmação inbound

    -- Retries
    retry_count   INTEGER NOT NULL DEFAULT 0,
    escalated_at  TIMESTAMPTZ,                     -- escalou pra familiar após missed
    escalation_target TEXT,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medication_event_schedule
    ON aia_health_medication_events(schedule_id, scheduled_at DESC);

CREATE INDEX IF NOT EXISTS idx_medication_event_patient_date
    ON aia_health_medication_events(patient_id, scheduled_at DESC);

CREATE INDEX IF NOT EXISTS idx_medication_event_pending
    ON aia_health_medication_events(scheduled_at)
    WHERE status IN ('scheduled', 'reminder_sent');

CREATE INDEX IF NOT EXISTS idx_medication_event_ref
    ON aia_health_medication_events(reminder_external_ref)
    WHERE reminder_external_ref IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════
-- 3. IMPORTS — fotos/áudios em análise (Claude Vision / Deepgram)
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_medication_imports (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id     TEXT NOT NULL,
    patient_id    UUID NOT NULL REFERENCES aia_health_patients(id) ON DELETE CASCADE,

    -- Origem do arquivo
    source_type   TEXT NOT NULL CHECK (source_type IN (
        'photo_prescription',   -- receita médica
        'photo_package',        -- caixa do medicamento
        'photo_leaflet',        -- bula
        'photo_pill_organizer', -- organizador de comprimidos
        'audio_description',    -- áudio descrevendo
        'text_description'      -- texto livre
    )),

    -- Arquivo (guardamos como base64 ou URL signed no MinIO/S3 — futuro)
    file_b64      TEXT,                            -- temporário pra demo, mover pra storage depois
    file_url      TEXT,                            -- URL assinada (quando tivermos storage)
    file_mime     TEXT,
    file_size_bytes INTEGER,

    -- Upload
    uploaded_by_type TEXT,                         -- patient | family | caregiver
    uploaded_by_id   UUID,
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_user_agent TEXT,

    -- Análise (Claude Vision / Deepgram + Claude)
    analysis_status TEXT NOT NULL DEFAULT 'pending' CHECK (analysis_status IN (
        'pending', 'analyzing', 'done', 'failed', 'discarded'
    )),
    analyzed_at     TIMESTAMPTZ,
    model_used      TEXT,                          -- claude-sonnet-4-vision
    raw_extraction  JSONB,                         -- o que o LLM extraiu cru
    parsed_medications JSONB,                      -- lista normalizada (pronta pra virar schedules)
    needs_more_info TEXT,                          -- "foto está borrada, pode tirar de novo?"
    error_message   TEXT,

    -- Confirmação do usuário (dupla conferência)
    confirmation_status TEXT NOT NULL DEFAULT 'awaiting' CHECK (confirmation_status IN (
        'awaiting',        -- análise feita, aguardando usuário confirmar
        'confirmed',       -- usuário confirmou tudo
        'partially_confirmed',
        'rejected',        -- análise errada, descartada
        'superseded'       -- refeita com outra imagem
    )),
    confirmed_at    TIMESTAMPTZ,
    confirmed_by    TEXT,
    user_corrections JSONB,                        -- o que o usuário mudou vs o extraído

    -- Schedules criados a partir desse import (rastreabilidade)
    created_schedule_ids UUID[],

    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_medication_import_patient
    ON aia_health_medication_imports(patient_id, uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_medication_import_pending
    ON aia_health_medication_imports(analysis_status)
    WHERE analysis_status IN ('pending', 'analyzing');


-- ═══════════════════════════════════════════════════════════════════
-- 4. Trigger de normalização + updated_at
-- ═══════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION aia_health_medication_schedule_normalize()
RETURNS trigger AS $$
BEGIN
    NEW.medication_name_normalized := lower(unaccent(coalesce(NEW.medication_name, '')));
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_medication_sched_normalize ON aia_health_medication_schedules;
CREATE TRIGGER trg_medication_sched_normalize
    BEFORE INSERT OR UPDATE OF medication_name
    ON aia_health_medication_schedules
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_medication_schedule_normalize();


CREATE OR REPLACE FUNCTION aia_health_touch_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_medication_event_touch ON aia_health_medication_events;
CREATE TRIGGER trg_medication_event_touch
    BEFORE UPDATE ON aia_health_medication_events
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_medication_import_touch ON aia_health_medication_imports;
CREATE TRIGGER trg_medication_import_touch
    BEFORE UPDATE ON aia_health_medication_imports
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_touch_updated_at();


COMMENT ON TABLE aia_health_medication_schedules IS
'Definição do que o paciente toma: medicação, dose, horários, origem. Fonte única pro scheduler de lembretes.';

COMMENT ON TABLE aia_health_medication_events IS
'Execução: cada dose prevista vira um event. Status + confirmação permitem calcular adesão real.';

COMMENT ON TABLE aia_health_medication_imports IS
'Fotos de receita/bula/caixa + áudios de descrição enviados pelo usuário. Claude Vision extrai e popula schedules após confirmação.';
