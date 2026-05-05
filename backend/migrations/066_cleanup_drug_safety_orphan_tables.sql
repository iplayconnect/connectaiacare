-- ====================================================================
-- 066_cleanup_drug_safety_orphan_tables.sql
--
-- Cleanup de tabelas órfãs criadas pela migration 065 (drug-safety MVP)
-- após decisão estratégica de refatorar drug_safety_service como WRAPPER
-- sobre dose_validator + cascade_detector existentes.
--
-- Contexto (sessão 2026-05-05):
--   Migration 065 criou aia_health_drug_catalog, aia_health_beers_flags,
--   aia_health_drug_lookup_gaps com schema redundante. Auditoria revelou
--   que o sistema já tinha estrutura mais sofisticada:
--   - aia_health_drug_dose_limits (151 rows, beers_avoid + age_group)
--   - aia_health_drug_interactions (93 rows, principle_a/b + class_a/b
--     + time_separation_minutes + food_warning)
--   - aia_health_drug_anticholinergic_burden (51 rows, escala ACB)
--   - aia_health_drug_fall_risk (38 rows, STOPP 2023)
--   - aia_health_drug_renal_adjustments (45)
--   - aia_health_drug_hepatic_adjustments (166)
--   - 11 checks integrados em dose_validator.validate()
--
-- Decisão: drop tabelas órfãs vazias (sem FK, sem dados perdidos),
-- refatorar drug_safety_service pra usar pipeline existente.
-- Migration 065 propriamente NÃO é revertida (aia_health_drug_interactions
-- foi preservada via IF NOT EXISTS — não afetou).
-- ====================================================================

BEGIN;

-- Apenas as 3 tabelas que MEU PR criou exclusivamente (validei via
-- query: nenhuma referência a essas em outros lugares do código antes
-- da migration 065).
DROP TABLE IF EXISTS aia_health_drug_lookup_gaps CASCADE;
DROP TABLE IF EXISTS aia_health_beers_flags CASCADE;
DROP TABLE IF EXISTS aia_health_drug_catalog CASCADE;

-- Trigger function órfã da 065
DROP FUNCTION IF EXISTS _touch_drug_catalog();

COMMIT;
