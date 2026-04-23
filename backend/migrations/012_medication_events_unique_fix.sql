-- Migration 012 — EMERGÊNCIA: fix loop de duplicatas em medication_events
--
-- Bug detectado em produção (23/04/2026): scheduler proativo materializava
-- events a cada 15s sem UNIQUE constraint, apesar do ON CONFLICT DO NOTHING.
-- Resultado: 3.203 events duplicados do mesmo (schedule_id, scheduled_at)
-- → 688 lembretes WhatsApp enviados ao cuidador.
--
-- Fix:
--   1. Deduplica events existentes (mantém o mais antigo de cada grupo)
--   2. Cria UNIQUE(schedule_id, scheduled_at) pra ON CONFLICT funcionar

BEGIN;

-- 1. Deduplica — mantém o mais antigo por (schedule_id, scheduled_at).
--    Prioridade: se algum foi 'taken'/'refused'/'skipped', mantém esse.
WITH ranked AS (
    SELECT id,
           schedule_id,
           scheduled_at,
           status,
           ROW_NUMBER() OVER (
               PARTITION BY schedule_id, scheduled_at
               ORDER BY
                   CASE status
                       WHEN 'taken'    THEN 0
                       WHEN 'refused'  THEN 1
                       WHEN 'skipped'  THEN 2
                       WHEN 'reminder_sent' THEN 3
                       WHEN 'scheduled' THEN 4
                       ELSE 9
                   END,
                   created_at ASC
           ) AS rn
    FROM aia_health_medication_events
)
DELETE FROM aia_health_medication_events
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- 2. UNIQUE constraint pra impedir recorrência do bug
ALTER TABLE aia_health_medication_events
    ADD CONSTRAINT uniq_medication_event_per_schedule
    UNIQUE (schedule_id, scheduled_at);

COMMIT;
