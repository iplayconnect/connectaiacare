-- =============================================================================
-- 079 — Drop CHECK constraint antigo de expected_event_type
-- =============================================================================
--
-- Bug reportado em prod 2026-05-15 por Henrique durante revisão corpus:
--
--   API 500: {"detail":"new row for relation
--   \"aia_health_classification_corpus_reviews\" violates check constraint
--   \"aia_health_classification_corpus_revi_expected_event_type_check\"
--   DETAIL: Failing row contains (8ce8ae11-477f...)"}
--
-- Causa: a migration 073 (corpus_event_types_expansion) ADICIONOU um novo
-- CHECK constraint com os 11 tipos (incluindo avaliacao_funcional,
-- evolucao_clinica, evento_adverso_medicamentoso), mas NÃO dropou o
-- antigo. Resultado: tabela tem 2 constraints simultâneos:
--
--   • aia_health_classification_corpus_revi_expected_event_type_check
--     (antigo, 8 tipos — falta os 3 novos)
--   • aia_health_classification_corpus_reviews_expected_event_type_ch
--     (novo, 11 tipos — completo)
--
-- Postgres aplica AMBOS, então qualquer insert com os 3 tipos novos falha
-- no constraint antigo. Esta migration dropa o constraint antigo.
--
-- Por que dropar e não substituir: o constraint novo (com 11 tipos)
-- já está OK e nomeado canonicamente. Manter os dois é redundância
-- pura — só remover o antigo basta.
--
-- Idempotente: usa DROP CONSTRAINT IF EXISTS.
-- =============================================================================

BEGIN;

ALTER TABLE aia_health_classification_corpus_reviews
    DROP CONSTRAINT IF EXISTS aia_health_classification_corpus_revi_expected_event_type_check;

-- Sanity: confirma que o constraint novo (completo, 11 tipos) continua existindo
DO $$
DECLARE
    qty INT;
BEGIN
    SELECT COUNT(*) INTO qty
      FROM pg_constraint
     WHERE conname = 'aia_health_classification_corpus_reviews_expected_event_type_ch'
       AND conrelid = 'aia_health_classification_corpus_reviews'::regclass;

    IF qty = 0 THEN
        RAISE WARNING 'Migration 079: constraint NOVO esperado nao foi encontrado. Investigar antes de prosseguir.';
    ELSE
        RAISE NOTICE 'Migration 079: constraint antigo removido. Constraint novo (11 tipos) preservado.';
    END IF;
END;
$$;

COMMIT;
