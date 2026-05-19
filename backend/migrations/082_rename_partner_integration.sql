-- ConnectaIACare — Renomeia integracao para nomenclatura generica.
--
-- Motivo: orientacao juridica para remover referencia ao nome de
-- parceiro especifico do schema. As tabelas e colunas passam a ser
-- "partner_carenote_*" / "external_partner_*", preparando o terreno
-- para multiplos parceiros integradores no futuro.
--
-- Migration idempotente: usa IF EXISTS em todos os renames; rodar
-- duas vezes nao causa erro.
--
-- Atencao: nao mexe nos DADOS, so na nomenclatura de objetos
-- (tabelas, colunas, indexes, triggers, chaves JSONB de tenants).

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. Renomear tabelas
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE IF EXISTS aia_health_tecnosenior_sync
    RENAME TO aia_health_partner_carenote_sync;

ALTER TABLE IF EXISTS aia_health_tecnosenior_addendums
    RENAME TO aia_health_partner_carenote_addendums;


-- ════════════════════════════════════════════════════════════════════
-- 2. Renomear colunas em aia_health_patients / aia_health_caregivers
-- ════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_patients'
          AND column_name = 'tecnosenior_patient_id'
    ) THEN
        ALTER TABLE aia_health_patients
            RENAME COLUMN tecnosenior_patient_id TO external_partner_patient_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_caregivers'
          AND column_name = 'tecnosenior_caretaker_id'
    ) THEN
        ALTER TABLE aia_health_caregivers
            RENAME COLUMN tecnosenior_caretaker_id TO external_partner_caretaker_id;
    END IF;
END $$;


-- ════════════════════════════════════════════════════════════════════
-- 3. Renomear colunas dentro das tabelas renomeadas
--    (eram tecnosenior_carenote_id, tecnosenior_status, tecnosenior_addendum_id)
-- ════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    -- aia_health_partner_carenote_sync (antiga _tecnosenior_sync)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_partner_carenote_sync'
          AND column_name = 'tecnosenior_carenote_id'
    ) THEN
        ALTER TABLE aia_health_partner_carenote_sync
            RENAME COLUMN tecnosenior_carenote_id TO partner_carenote_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_partner_carenote_sync'
          AND column_name = 'tecnosenior_status'
    ) THEN
        ALTER TABLE aia_health_partner_carenote_sync
            RENAME COLUMN tecnosenior_status TO partner_sync_status;
    END IF;

    -- aia_health_partner_carenote_addendums (antiga _tecnosenior_addendums)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_partner_carenote_addendums'
          AND column_name = 'tecnosenior_carenote_id'
    ) THEN
        ALTER TABLE aia_health_partner_carenote_addendums
            RENAME COLUMN tecnosenior_carenote_id TO partner_carenote_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'aia_health_partner_carenote_addendums'
          AND column_name = 'tecnosenior_addendum_id'
    ) THEN
        ALTER TABLE aia_health_partner_carenote_addendums
            RENAME COLUMN tecnosenior_addendum_id TO partner_addendum_id;
    END IF;
END $$;


-- ════════════════════════════════════════════════════════════════════
-- 4. Renomear indexes
-- ════════════════════════════════════════════════════════════════════

ALTER INDEX IF EXISTS idx_patients_tecnosenior_id
    RENAME TO idx_patients_external_partner_id;

ALTER INDEX IF EXISTS idx_caregivers_tecnosenior_id
    RENAME TO idx_caregivers_external_partner_id;

ALTER INDEX IF EXISTS idx_tecnosenior_sync_pending
    RENAME TO idx_partner_carenote_sync_pending;

ALTER INDEX IF EXISTS idx_tecnosenior_sync_status
    RENAME TO idx_partner_carenote_sync_status;

ALTER INDEX IF EXISTS idx_tecnosenior_add_pending
    RENAME TO idx_partner_carenote_add_pending;

ALTER INDEX IF EXISTS idx_tecnosenior_add_carenote
    RENAME TO idx_partner_carenote_add_carenote;


-- ════════════════════════════════════════════════════════════════════
-- 5. Renomear triggers
-- ════════════════════════════════════════════════════════════════════

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_tecnosenior_sync_updated'
          AND tgrelid = 'aia_health_partner_carenote_sync'::regclass
    ) THEN
        ALTER TRIGGER trg_tecnosenior_sync_updated
            ON aia_health_partner_carenote_sync
            RENAME TO trg_partner_carenote_sync_updated;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_tecnosenior_add_updated'
          AND tgrelid = 'aia_health_partner_carenote_addendums'::regclass
    ) THEN
        ALTER TRIGGER trg_tecnosenior_add_updated
            ON aia_health_partner_carenote_addendums
            RENAME TO trg_partner_carenote_add_updated;
    END IF;
END $$;


-- ════════════════════════════════════════════════════════════════════
-- 6. Renomear chave JSONB em aia_health_tenants.integrations
--    (key 'tecnosenior' -> 'partner_carenote')
-- ════════════════════════════════════════════════════════════════════

UPDATE aia_health_tenants
   SET integrations = (integrations - 'tecnosenior')
                    || jsonb_build_object(
                         'partner_carenote',
                         COALESCE(integrations->'tecnosenior', 'false'::jsonb)
                       )
 WHERE integrations ? 'tecnosenior';


COMMIT;
