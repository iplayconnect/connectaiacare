-- =============================================================================
-- 073 — 3 novas categorias clínicas + invalidação de reviews wellness
-- =============================================================================
--
-- Decisões clínicas (Henrique 2026-05-09):
--
-- 1. INVALIDAR só as reviews de apoio_emocional já feitas. As clínicas
--    permanecem (Henrique fez essas com olhar crítico). Wellness sai
--    do track de Henrique de qualquer jeito (ver migration 072), então
--    invalidar = limpar revisões antigas pra serem refeitas pelo
--    reviewer correto (gestora/coordenador).
--
-- 2. ADICIONAR 3 novas categorias clínicas ao enum:
--    • avaliacao_funcional — ABVD/AIVD, mobilidade, autonomia
--      (paciente que tava deambulando para de andar; perda de
--      capacidade pra atividades básicas/instrumentais)
--    • evolucao_clinica — melhora/piora desde último plantão
--      (atualização de status sem evento agudo novo)
--    • evento_adverso_medicamentoso — separa de medicacao genérico
--      (paciente reagiu mal ao remédio: efeito colateral, alergia,
--      interação)
--
-- 3. Estende CHECK constraint em 2 lugares:
--    • aia_health_classification_corpus_cases.llm_suggested_event_type
--    • aia_health_classification_corpus_reviews.expected_event_type
--
-- Migração idempotente.
-- =============================================================================


-- 1. INVALIDAR reviews de apoio_emocional ────────────────────────────
--
-- Estratégia: deletar as rows de aia_health_classification_corpus_reviews
-- que apontam pra cases com llm_suggested_event_type='apoio_emocional'.
-- Volta o review_status do case pra 'pending' (será revisto pelo reviewer
-- correto no track caregiver_wellness).

DELETE FROM aia_health_classification_corpus_reviews
 WHERE case_id IN (
    SELECT id FROM aia_health_classification_corpus_cases
     WHERE llm_suggested_event_type = 'apoio_emocional'
 );

UPDATE aia_health_classification_corpus_cases
   SET review_status = 'pending', updated_at = NOW()
 WHERE llm_suggested_event_type = 'apoio_emocional'
   AND review_status = 'reviewed';


-- 2. ESTENDER CHECK constraints com as 3 novas categorias ────────────
--
-- Postgres não permite ALTER de CHECK; tem que DROP e recriar.

ALTER TABLE aia_health_classification_corpus_cases
    DROP CONSTRAINT IF EXISTS
        aia_health_classification_corpus_cases_llm_suggested_event_type_check;
ALTER TABLE aia_health_classification_corpus_cases
    ADD CONSTRAINT aia_health_classification_corpus_cases_llm_suggested_event_type_check
    CHECK (llm_suggested_event_type IN (
        'relato_geral', 'cuidado_higiene', 'alimentacao_hidratacao',
        'medicacao', 'sinal_vital', 'intercorrencia',
        'sintoma_novo', 'apoio_emocional',
        'avaliacao_funcional', 'evolucao_clinica',
        'evento_adverso_medicamentoso'
    ));


ALTER TABLE aia_health_classification_corpus_reviews
    DROP CONSTRAINT IF EXISTS
        aia_health_classification_corpus_reviews_expected_event_type_check;
ALTER TABLE aia_health_classification_corpus_reviews
    ADD CONSTRAINT aia_health_classification_corpus_reviews_expected_event_type_check
    CHECK (expected_event_type IN (
        'relato_geral', 'cuidado_higiene', 'alimentacao_hidratacao',
        'medicacao', 'sinal_vital', 'intercorrencia',
        'sintoma_novo', 'apoio_emocional',
        'avaliacao_funcional', 'evolucao_clinica',
        'evento_adverso_medicamentoso'
    ));

COMMENT ON COLUMN aia_health_classification_corpus_cases.llm_suggested_event_type IS
    '11 categorias (Henrique 2026-05-09 expansão): 8 originais + ' ||
    'avaliacao_funcional (ABVD/AIVD), evolucao_clinica (status update), ' ||
    'evento_adverso_medicamentoso (separa de medicacao genérico).';
