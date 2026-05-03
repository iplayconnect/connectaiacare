-- ====================================================================
-- 064_handoff_outcome_fields.sql
--
-- Phase A · PR A4 — FinalizationModal polido.
--
-- Adiciona 3 colunas em aia_health_human_handoff_queue pra capturar
-- o desfecho estruturado quando operador marca handoff como resolvido:
--
--   outcome_category  — categoria do desfecho (radio no modal)
--   outcome_tags      — tags multi-select (issues comuns, BR-friendly)
--   outcome_rating    — auto-avaliação 1-5 do operador (pra coaching)
--
-- Categorias e tags são validadas no app (whitelist em
-- admin_handoff_routes.py); colunas são TEXT/TEXT[] pra permitir
-- extensão sem migration.
--
-- Idempotente.
-- ====================================================================

ALTER TABLE aia_health_human_handoff_queue
    ADD COLUMN IF NOT EXISTS outcome_category TEXT,
    ADD COLUMN IF NOT EXISTS outcome_tags TEXT[],
    ADD COLUMN IF NOT EXISTS outcome_rating SMALLINT;

-- CHECK constraint pra rating no intervalo válido 1-5 (NULL permitido).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'aia_health_handoff_outcome_rating_range'
    ) THEN
        ALTER TABLE aia_health_human_handoff_queue
            ADD CONSTRAINT aia_health_handoff_outcome_rating_range
            CHECK (
                outcome_rating IS NULL
                OR (outcome_rating BETWEEN 1 AND 5)
            );
    END IF;
END $$;

-- Index pra dashboards futuros (Fase C — métricas operador):
-- "qual a distribuição de outcome_category nos últimos 30 dias?"
CREATE INDEX IF NOT EXISTS idx_handoff_outcome_resolved
    ON aia_health_human_handoff_queue(outcome_category, resolved_at DESC)
    WHERE status = 'resolved';

-- Index GIN pra tag analytics ("quantos handoffs tiveram tag
-- 'urgencia_real' nas últimas semanas?").
CREATE INDEX IF NOT EXISTS idx_handoff_outcome_tags_gin
    ON aia_health_human_handoff_queue
    USING GIN (outcome_tags)
    WHERE status = 'resolved' AND outcome_tags IS NOT NULL;
