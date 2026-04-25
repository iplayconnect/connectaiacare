-- 028 — Colunas de auditoria/UI para o dose_revalidation_scheduler.
-- Permite à UI mostrar "última revalidação: 2 dias atrás (info)" e ao
-- scheduler escolher quem revalidar primeiro (ORDER BY last_revalidated_at).

ALTER TABLE aia_health_medication_schedules
    ADD COLUMN IF NOT EXISTS last_revalidated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_revalidation_severity TEXT;

CREATE INDEX IF NOT EXISTS idx_med_schedules_last_revalidated
    ON aia_health_medication_schedules(last_revalidated_at NULLS FIRST)
    WHERE active = TRUE;
