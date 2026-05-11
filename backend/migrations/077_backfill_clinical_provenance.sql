-- =============================================================================
-- 077 — Backfill de provenance em conditions/medications/allergies
-- =============================================================================
--
-- Contexto (Alexandre + Henrique 2026-05-10):
--   Pacientes importados da Tecnosenior têm conditions/medications/allergies
--   como arrays de strings:
--       ["Hipertensão", "Diabetes Mellitus tipo 2"]
--
--   O wizard novo (PR cadastro completo) e a verificação clínica trabalham
--   com objetos contendo provenance:
--       [{"name": "Hipertensão", "source": "imported_tecnosenior", ...}]
--
--   O helper `normalize_clinical_array` já lê AMBOS (lazy migration on read),
--   mas itens em formato string aparecem na UI sem badge de origem — isso
--   confunde a Coordenadora PUC e o Henrique na revisão.
--
-- O que esta migration faz:
--   • Pra cada paciente, examina os 3 campos JSONB.
--   • Se o array contém ao menos 1 elemento string, converte TODOS pra objeto
--     estampando source = 'imported_tecnosenior' (ou 'imported_other' se o
--     paciente não tem tecnosenior_patient_id).
--   • Se o array já é todo de objetos, NÃO toca (idempotente).
--   • Preserva o nome original e adiciona declared_at = NOW(), original_source
--     = source, declared_by_user_id = NULL (origem é importação, não usuário).
--
-- Reversibilidade:
--   Não-destrutiva pra o nome/conteúdo. Pra reverter em emergência,
--   roda na mão: UPDATE ... SET conditions = (SELECT jsonb_agg(item->>'name') ...)
--   mas raramente vai ser necessário porque o helper de leitura já lida
--   com os dois formatos.
--
-- Performance:
--   Pacientes em produção hoje: ~50-200. Migration roda em <1s.
--   Em deploys futuros com volume maior, considerar rodar em batches.
-- =============================================================================

BEGIN;

-- Função helper local — converte um JSONB array que pode ser misto
-- (strings e objetos) num array só de objetos com provenance estampada.
-- Idempotente: items que já são objetos passam intactos.
CREATE OR REPLACE FUNCTION pg_temp.backfill_clinical_array(
    arr JSONB,
    default_source TEXT
) RETURNS JSONB AS $$
DECLARE
    item JSONB;
    result JSONB := '[]'::JSONB;
    obj JSONB;
BEGIN
    IF arr IS NULL OR jsonb_typeof(arr) != 'array' OR jsonb_array_length(arr) = 0 THEN
        RETURN arr;
    END IF;

    FOR item IN SELECT jsonb_array_elements(arr) LOOP
        IF jsonb_typeof(item) = 'string' THEN
            -- String solta → vira objeto com provenance.
            -- `item #>> '{}'` extrai o valor primitivo sem aspas (e
            -- preserva apóstrofos/aspas internas, ao contrário de
            -- trim(both '"') que poderia quebrar conteúdo legítimo).
            obj := jsonb_build_object(
                'name',                    item #>> '{}',
                'source',                  default_source,
                'original_source',         default_source,
                'declared_at',             to_jsonb(NOW()::TEXT),
                'declared_by_user_id',     NULL::TEXT,
                'verified_by_clinician_at', NULL::TEXT,
                'verified_by_user_id',     NULL::TEXT
            );
            result := result || jsonb_build_array(obj);
        ELSIF jsonb_typeof(item) = 'object' THEN
            -- Objeto já existe; só completa source se faltar
            obj := item;
            IF NOT (obj ? 'source') OR obj->>'source' IS NULL THEN
                obj := obj || jsonb_build_object('source', default_source);
            END IF;
            IF NOT (obj ? 'original_source') OR obj->>'original_source' IS NULL THEN
                obj := obj || jsonb_build_object(
                    'original_source', COALESCE(obj->>'source', default_source)
                );
            END IF;
            IF NOT (obj ? 'declared_at') OR obj->>'declared_at' IS NULL THEN
                obj := obj || jsonb_build_object('declared_at', to_jsonb(NOW()::TEXT));
            END IF;
            result := result || jsonb_build_array(obj);
        ELSE
            -- Tipo inesperado (number, bool, null) — descarta
            CONTINUE;
        END IF;
    END LOOP;

    RETURN result;
END;
$$ LANGUAGE plpgsql VOLATILE;


-- Aplica em todos os pacientes
-- ---------------------------------------------------------------------------
-- A condição "WHERE algum campo tem string" filtra rows que precisam atualizar,
-- evitando rewrite de toda tabela.
WITH targets AS (
    SELECT id,
           tecnosenior_patient_id,
           conditions,
           medications,
           allergies
      FROM aia_health_patients
     WHERE
        -- Pelo menos 1 dos 3 campos tem ao menos 1 elemento string
        EXISTS (
            SELECT 1 FROM jsonb_array_elements(COALESCE(conditions, '[]'::JSONB)) e
             WHERE jsonb_typeof(e) = 'string'
        )
        OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(COALESCE(medications, '[]'::JSONB)) e
             WHERE jsonb_typeof(e) = 'string'
        )
        OR EXISTS (
            SELECT 1 FROM jsonb_array_elements(COALESCE(allergies, '[]'::JSONB)) e
             WHERE jsonb_typeof(e) = 'string'
        )
)
UPDATE aia_health_patients p
   SET conditions = pg_temp.backfill_clinical_array(
            p.conditions,
            CASE WHEN p.tecnosenior_patient_id IS NOT NULL
                 THEN 'imported_tecnosenior'
                 ELSE 'imported_other'
            END
       ),
       medications = pg_temp.backfill_clinical_array(
            p.medications,
            CASE WHEN p.tecnosenior_patient_id IS NOT NULL
                 THEN 'imported_tecnosenior'
                 ELSE 'imported_other'
            END
       ),
       allergies = pg_temp.backfill_clinical_array(
            p.allergies,
            CASE WHEN p.tecnosenior_patient_id IS NOT NULL
                 THEN 'imported_tecnosenior'
                 ELSE 'imported_other'
            END
       ),
       updated_at = NOW()
  FROM targets t
 WHERE p.id = t.id;


-- Recalcula registration_completeness pra refletir o novo formato
-- (helper de completude conta items não-vazios; após backfill, seções
-- que tinham strings agora contam como "complete")
-- ---------------------------------------------------------------------------
UPDATE aia_health_patients
   SET registration_completeness = jsonb_build_object(
        'demographics', CASE
            WHEN full_name IS NOT NULL AND birth_date IS NOT NULL THEN 'complete'
            WHEN full_name IS NOT NULL THEN 'partial'
            ELSE 'missing'
        END,
        'conditions', CASE
            WHEN jsonb_array_length(COALESCE(conditions, '[]'::JSONB)) > 0 THEN 'complete'
            ELSE 'missing'
        END,
        'medications', CASE
            WHEN jsonb_array_length(COALESCE(medications, '[]'::JSONB)) > 0 THEN 'complete'
            ELSE 'missing'
        END,
        'allergies', CASE
            WHEN jsonb_array_length(COALESCE(allergies, '[]'::JSONB)) > 0 THEN 'complete'
            ELSE 'missing'
        END,
        'responsibles', CASE
            WHEN responsible IS NOT NULL AND responsible != 'null'::JSONB THEN 'complete'
            ELSE 'missing'
        END,
        'functional_baseline', 'missing',  -- campo dedicado virá depois
        'last_updated_at', to_jsonb(NOW()::TEXT)
   )
 WHERE registration_completeness IS NULL
    OR NOT (registration_completeness ? 'last_updated_at');


-- Sanity check — quantos pacientes ainda têm strings (deve ser 0 após esta migration)
DO $$
DECLARE
    qty INT;
BEGIN
    SELECT COUNT(*) INTO qty
      FROM aia_health_patients p
     WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(p.conditions, '[]'::JSONB)) e
         WHERE jsonb_typeof(e) = 'string'
     )
        OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(p.medications, '[]'::JSONB)) e
         WHERE jsonb_typeof(e) = 'string'
     )
        OR EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(p.allergies, '[]'::JSONB)) e
         WHERE jsonb_typeof(e) = 'string'
     );

    IF qty > 0 THEN
        RAISE WARNING 'Migration 077: % pacientes ainda têm strings em campos clínicos. Investigar.', qty;
    ELSE
        RAISE NOTICE 'Migration 077: backfill clínico concluído — 0 pacientes restantes com formato legado.';
    END IF;
END;
$$;

COMMIT;
