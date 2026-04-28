-- ConnectaIACare — Schema para auto-populate em fase POC.
--
-- Decisão Opção B (validada pelo CEO): auto-populate Tier Verde + Tier Amarelo
-- com flag explícita pra revisão clínica posterior. Sofia adiciona disclaimer
-- reforçado nas saídas que vêm de regras auto-geradas.
--
-- Tier Verde (auto + sem flag): nome, aliases, classe, dose adulto, forma, indicação
-- Tier Amarelo (auto + flag): dose geriátrica, Beers, ACB conservador,
--                              ajuste renal/hepático básico
-- Tier Vermelho (NUNCA auto): interações específicas, contraindicações por
--                              condição CIDX, cascatas, score cumulativo

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- Flags por linha em aia_health_drug_dose_limits
-- ════════════════════════════════════════════════════════════════
ALTER TABLE aia_health_drug_dose_limits
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved')),
    ADD COLUMN IF NOT EXISTS source_auto TEXT,
    ADD COLUMN IF NOT EXISTS auto_review_notes TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;

COMMENT ON COLUMN aia_health_drug_dose_limits.review_status IS
    'verified = curado por humano (default histórico) | '
    'auto_pending = auto-gerado, requer revisão clínica | '
    'auto_approved = auto-gerado mas validado por curador sênior';

-- aia_health_condition_contraindications (onde mora Beers/AVOID por condição)
ALTER TABLE aia_health_condition_contraindications
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));

ALTER TABLE aia_health_drug_anticholinergic_burden
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));

ALTER TABLE aia_health_drug_fall_risk
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));

ALTER TABLE aia_health_drug_renal_adjustments
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));

ALTER TABLE aia_health_drug_hepatic_adjustments
    ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS review_status TEXT
        NOT NULL DEFAULT 'verified'
        CHECK (review_status IN ('verified', 'auto_pending', 'auto_approved'));


-- ════════════════════════════════════════════════════════════════
-- Índices úteis pra fila de revisão
-- ════════════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_dose_limits_auto_pending
    ON aia_health_drug_dose_limits(principle_active)
    WHERE review_status = 'auto_pending';

CREATE INDEX IF NOT EXISTS idx_contraindications_auto_pending
    ON aia_health_condition_contraindications(condition_term)
    WHERE review_status = 'auto_pending';


-- ════════════════════════════════════════════════════════════════
-- View consolidada: cobertura RENAME com breakdown auto vs verified
-- DROP antes do CREATE pra permitir mudança de nome de colunas
-- (PostgreSQL não permite renomear colunas via CREATE OR REPLACE)
-- ════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS aia_health_rename_coverage_summary;

CREATE VIEW aia_health_rename_coverage_summary AS
SELECT
    r.componente,
    r.geriatric_relevance,
    COUNT(DISTINCT r.principle_active) AS total_rename,
    COUNT(DISTINCT r.principle_active) FILTER (WHERE r.motor_coverage = 'covered') AS covered_total,
    COUNT(DISTINCT r.principle_active) FILTER (
        WHERE r.motor_coverage = 'covered'
          AND COALESCE(d.review_status, 'verified') = 'verified'
    ) AS covered_verified,
    COUNT(DISTINCT r.principle_active) FILTER (
        WHERE r.motor_coverage = 'covered'
          AND d.review_status = 'auto_pending'
    ) AS covered_auto_pending,
    COUNT(DISTINCT r.principle_active) FILTER (WHERE r.motor_coverage = 'in_progress') AS in_progress,
    COUNT(DISTINCT r.principle_active) FILTER (WHERE r.motor_coverage = 'pending') AS pending,
    ROUND(
        100.0 * COUNT(DISTINCT r.principle_active) FILTER (WHERE r.motor_coverage = 'covered')
        / NULLIF(COUNT(DISTINCT r.principle_active), 0), 1
    ) AS pct_covered
FROM aia_health_rename_drugs r
LEFT JOIN aia_health_drug_dose_limits d ON d.principle_active = r.principle_active
WHERE r.edicao = '2024'
GROUP BY r.componente, r.geriatric_relevance
ORDER BY r.componente,
    CASE r.geriatric_relevance
        WHEN 'high' THEN 1
        WHEN 'medium' THEN 2
        WHEN 'low' THEN 3
        WHEN 'excluded' THEN 4
    END;


COMMIT;
