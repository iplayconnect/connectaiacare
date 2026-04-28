-- ConnectaIACare — Integração Tecnosenior (mapping IDs + sync state).
--
-- Schema mínimo pra começar piloto:
-- - Pacientes/cuidadores ganham campo tecnosenior_*_id (INT do lado deles)
-- - Tabela aia_health_tecnosenior_sync mantém estado de envio por
--   care_event (idempotência via UPSERT por care_event_id)
-- - Tabela aia_health_tecnosenior_addendums idem para addendums
--
-- Resposta do Matheus 2026-04-28: lookup por phone já existe; CPF
-- chega amanhã. Auth: Authorization: Api-Key {chave}. Idempotency-Key
-- não suportado (resolvemos via cache local).

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. Mapping de IDs por entidade
-- ════════════════════════════════════════════════════════════════════
-- Nullable porque pacientes/cuidadores podem existir só do nosso lado
-- (ainda não cadastrados no Tecnosenior).

ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS tecnosenior_patient_id INT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_tecnosenior_id
    ON aia_health_patients(tecnosenior_patient_id)
    WHERE tecnosenior_patient_id IS NOT NULL;


ALTER TABLE aia_health_caregivers
    ADD COLUMN IF NOT EXISTS tecnosenior_caretaker_id INT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_caregivers_tecnosenior_id
    ON aia_health_caregivers(tecnosenior_caretaker_id)
    WHERE tecnosenior_caretaker_id IS NOT NULL;


-- ════════════════════════════════════════════════════════════════════
-- 2. Estado de sync da CareNote (1 linha por care_event)
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_tecnosenior_sync (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    care_event_id UUID NOT NULL UNIQUE
        REFERENCES aia_health_care_events(id) ON DELETE CASCADE,

    -- ID retornado pela Tecnosenior na criação
    tecnosenior_carenote_id INT UNIQUE,

    -- Espelho local do estado deles (OPEN | CLOSED)
    tecnosenior_status TEXT
        CHECK (tecnosenior_status IN ('OPEN', 'CLOSED')),
    closed_at_remote TIMESTAMPTZ,

    -- Sincronização
    last_synced_at TIMESTAMPTZ,
    last_sync_attempt_at TIMESTAMPTZ,
    sync_error TEXT,
    retry_count INT NOT NULL DEFAULT 0,

    -- Cache do payload da última tentativa (debug)
    last_request_payload JSONB,
    last_response_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tecnosenior_sync_pending
    ON aia_health_tecnosenior_sync(last_sync_attempt_at NULLS FIRST)
    WHERE sync_error IS NOT NULL OR last_synced_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tecnosenior_sync_status
    ON aia_health_tecnosenior_sync(tecnosenior_status);

DROP TRIGGER IF EXISTS trg_tecnosenior_sync_updated
    ON aia_health_tecnosenior_sync;
CREATE TRIGGER trg_tecnosenior_sync_updated
    BEFORE UPDATE ON aia_health_tecnosenior_sync
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- ════════════════════════════════════════════════════════════════════
-- 3. Estado de sync dos Addendums (N linhas por care_event)
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_tecnosenior_addendums (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    care_event_id UUID NOT NULL
        REFERENCES aia_health_care_events(id) ON DELETE CASCADE,
    report_id UUID
        REFERENCES aia_health_reports(id) ON DELETE SET NULL,

    -- ID da CareNote pai no lado deles
    tecnosenior_carenote_id INT NOT NULL,
    -- ID retornado pela Tecnosenior ao criar o addendum (NULL até post)
    tecnosenior_addendum_id INT UNIQUE,

    content TEXT NOT NULL,
    content_resume TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    closes_note BOOLEAN NOT NULL DEFAULT FALSE,

    last_synced_at TIMESTAMPTZ,
    sync_error TEXT,
    retry_count INT NOT NULL DEFAULT 0,

    last_request_payload JSONB,
    last_response_payload JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Mesmo report não deve ser enviado 2x como addendum
    UNIQUE (care_event_id, report_id)
);

CREATE INDEX IF NOT EXISTS idx_tecnosenior_add_pending
    ON aia_health_tecnosenior_addendums(care_event_id, occurred_at)
    WHERE last_synced_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_tecnosenior_add_carenote
    ON aia_health_tecnosenior_addendums(tecnosenior_carenote_id);

DROP TRIGGER IF EXISTS trg_tecnosenior_add_updated
    ON aia_health_tecnosenior_addendums;
CREATE TRIGGER trg_tecnosenior_add_updated
    BEFORE UPDATE ON aia_health_tecnosenior_addendums
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


COMMIT;
