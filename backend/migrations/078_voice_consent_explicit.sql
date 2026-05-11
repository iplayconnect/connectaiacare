-- =============================================================================
-- 078 — Consentimento LGPD explícito + log de identificação biométrica
-- =============================================================================
--
-- Contexto (Alexandre 2026-05-10, política WhatsApp inbound):
--
-- 1. LGPD Art. 11 (dado biométrico) exige **consentimento informado, livre
--    e específico**. Hoje guardamos só `action = 'consent_given'` mas não
--    o TEXTO mostrado ao usuário. Sem o texto, em uma auditoria não
--    conseguimos provar O QUE a pessoa aceitou.
--
-- 2. Toda vez que o sistema **identifica** alguém via biometria (cenários
--    2/3.1/3.2/4 do spec), precisa virar log auditável — não só pra LGPD
--    mas pra calibração futura dos thresholds com áudios reais. Hoje o
--    CHECK do `action` não permite `'identity_resolved'`.
--
-- 3. Quando propomos enrollment via WhatsApp (cenário 5), precisamos
--    rastrear o estado da oferta sem proliferar tabela. Vai como
--    metadata.scenario = 'whatsapp_enrollment_offered' com acompanhamento
--    futuro em tabela dedicada (Entrega B).
--
-- O que esta migration faz:
--   • Estende `voice_consent_log.action` pra aceitar `'identity_resolved'`
--   • Adiciona `consent_text TEXT` — o texto exato exibido ao usuário
--   • Adiciona `consent_version TEXT` — ex: 'v1', 'v2-2026-05-10' pra
--     poder evoluir o termo sem perder rastreabilidade do que foi aceito
--   • Adiciona índice para queries "qual versão do termo cada usuário aceitou"
--
-- Reversibilidade: drop dos campos novos é seguro (só auditoria). O CHECK
-- estendido só ADICIONA valores aceitos — nada quebra.
-- =============================================================================

BEGIN;

-- 1. Estende lista de actions
-- ---------------------------------------------------------------------------
-- Postgres não tem ALTER CHECK direto; tem que dropar e recriar.
ALTER TABLE aia_health_voice_consent_log
    DROP CONSTRAINT IF EXISTS aia_health_voice_consent_log_action_check;

ALTER TABLE aia_health_voice_consent_log
    ADD CONSTRAINT aia_health_voice_consent_log_action_check
    CHECK (action IN (
        'consent_given',
        'consent_revoked',
        'data_accessed',
        'data_deleted',
        'enrollment_added',
        'identity_resolved',           -- NOVO: cada decisão biométrica do sistema
        'enrollment_offered',          -- NOVO: Sofia ofereceu enrollment via WhatsApp
        'enrollment_declined'          -- NOVO: usuário recusou a oferta
    ));


-- 2. Texto exato do termo + versão
-- ---------------------------------------------------------------------------
ALTER TABLE aia_health_voice_consent_log
    ADD COLUMN IF NOT EXISTS consent_text TEXT;

ALTER TABLE aia_health_voice_consent_log
    ADD COLUMN IF NOT EXISTS consent_version TEXT;

COMMENT ON COLUMN aia_health_voice_consent_log.consent_text IS
    'Texto EXATO do termo apresentado ao usuário no momento. ' ||
    'Necessário para auditoria LGPD Art. 11 (consentimento informado). ' ||
    'NULL pra ações que não envolvem aceite (data_accessed, identity_resolved).';

COMMENT ON COLUMN aia_health_voice_consent_log.consent_version IS
    'Versão do termo (ex: v1, v2-2026-05-10). Permite rastrear qual ' ||
    'versão cada usuário aceitou ao longo do tempo.';


-- 3. Índice pra auditoria por versão
-- ---------------------------------------------------------------------------
-- Usado em queries do tipo "todos que aceitaram v1 precisam re-aceitar v2"
CREATE INDEX IF NOT EXISTS idx_consent_version
    ON aia_health_voice_consent_log(consent_version)
    WHERE consent_version IS NOT NULL;


-- 4. Índice pra investigação de identidade por phone (cenários 3/4)
-- ---------------------------------------------------------------------------
-- Quando o suporte pergunta "todas as identificações desse telefone na
-- última semana", queremos resposta rápida. Phone vai em metadata.
CREATE INDEX IF NOT EXISTS idx_consent_log_metadata_phone
    ON aia_health_voice_consent_log
    USING GIN ((metadata -> 'phone'))
    WHERE metadata ? 'phone';


-- 5. Sanity: confirma que action novos foram aceitos
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    test_id BIGINT;
BEGIN
    INSERT INTO aia_health_voice_consent_log
        (caregiver_id, tenant_id, action, metadata)
    VALUES
        (NULL, 'connectaiacare_demo', 'identity_resolved',
         '{"test": true, "scenario": "migration_078_smoketest"}'::JSONB)
    RETURNING id INTO test_id;

    -- Limpa o teste
    DELETE FROM aia_health_voice_consent_log WHERE id = test_id;

    RAISE NOTICE 'Migration 078: action ''identity_resolved'' aceito ✓';
END;
$$;

COMMIT;
