-- ConnectaIACare — Decisões B2C/individual (estrutura de licença +
-- forma de tratamento + cap de mensagens).
--
-- Detalhes em docs/decisoes_b2c_individual.md.
--
-- O schema persiste as decisões no banco. Enforcement de quota fica
-- pra próximo sprint — campos preparam o terreno.

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. preferred_form_of_address por paciente
-- ════════════════════════════════════════════════════════════════════
-- Como Sofia se dirige ao paciente:
--   first_name        → "Maria"
--   formal            → "Dona Maria" / "Sr. José" (default conservador)
--   full_first_name   → "Dona Maria Helena"
--   nickname          → "Mariazinha" (apelido carinhoso)

ALTER TABLE aia_health_patients
    ADD COLUMN IF NOT EXISTS preferred_form_of_address TEXT
        DEFAULT 'formal'
        CHECK (preferred_form_of_address IN (
            'first_name', 'formal', 'full_first_name', 'nickname'
        ));

COMMENT ON COLUMN aia_health_patients.preferred_form_of_address IS
'Como Sofia chama o paciente em interações diretas. Definido no '
'onboarding ("Você prefere Maria ou Dona Maria?"). Default formal '
'pra errar pelo respeito quando paciente não respondeu.';


-- ════════════════════════════════════════════════════════════════════
-- 2. licensing_model + quota por tenant
-- ════════════════════════════════════════════════════════════════════
-- licensing_model é INDEPENDENTE de tenant_type:
--   tenant_type     afeta operação (plantão, biometria, fluxo)
--   licensing_model afeta cobrança e cap de uso
--
-- Combinações típicas:
--   ILPI/clinica/hospital    → b2b_organization
--   B2C (família cuidando)   → b2c_family
--   individual (idoso solo)  → individual

ALTER TABLE aia_health_tenant_config
    ADD COLUMN IF NOT EXISTS licensing_model TEXT
        NOT NULL DEFAULT 'b2b_organization'
        CHECK (licensing_model IN (
            'b2b_organization', 'b2c_family', 'individual'
        )),
    ADD COLUMN IF NOT EXISTS message_quota_monthly INT,
    ADD COLUMN IF NOT EXISTS quota_warning_threshold_pct INT
        NOT NULL DEFAULT 80
        CHECK (quota_warning_threshold_pct BETWEEN 1 AND 99);

COMMENT ON COLUMN aia_health_tenant_config.message_quota_monthly IS
'Cap mensal de mensagens. NULL = ilimitado. Aviso aos N% (default 80) '
'+ throttle suave acima de 100% (não corta, fica mais devagar). '
'Keywords críticas SEMPRE passam mesmo com quota zerada.';


-- ════════════════════════════════════════════════════════════════════
-- 3. Contador mensal de uso por tenant
-- ════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_message_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    period_year INT NOT NULL,
    period_month INT NOT NULL,
    message_count INT NOT NULL DEFAULT 0,
    audio_count INT NOT NULL DEFAULT 0,
    text_count INT NOT NULL DEFAULT 0,
    last_warning_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, period_year, period_month),
    CHECK (period_month BETWEEN 1 AND 12),
    CHECK (period_year >= 2024)
);

CREATE INDEX IF NOT EXISTS idx_message_usage_tenant_period
    ON aia_health_message_usage(tenant_id, period_year, period_month);

DROP TRIGGER IF EXISTS trg_message_usage_updated
    ON aia_health_message_usage;
CREATE TRIGGER trg_message_usage_updated
    BEFORE UPDATE ON aia_health_message_usage
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- ════════════════════════════════════════════════════════════════════
-- 4. Audit de override de emergência
-- ════════════════════════════════════════════════════════════════════
-- Quando keyword crítica dispara processing acima da quota, gravamos
-- aqui pra futuro audit (e pra negociar com cliente que reclamar
-- "por que minha quota encheu?" — porque foi emergência real).

CREATE TABLE IF NOT EXISTS aia_health_quota_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    keyword_matched TEXT,
    report_id UUID REFERENCES aia_health_reports(id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quota_overrides_tenant_date
    ON aia_health_quota_overrides(tenant_id, triggered_at DESC);


-- ════════════════════════════════════════════════════════════════════
-- 5. Helper function: incrementa contador (usado pelo pipeline)
-- ════════════════════════════════════════════════════════════════════
-- UPSERT atômico que mantém o contador mensal sem necessidade de
-- aplicação resolver race condition.

CREATE OR REPLACE FUNCTION aia_health_increment_message_usage(
    p_tenant TEXT,
    p_kind TEXT  -- 'audio' | 'text'
)
RETURNS INT AS $$
DECLARE
    v_now TIMESTAMPTZ := NOW();
    v_year INT := EXTRACT(YEAR FROM v_now)::INT;
    v_month INT := EXTRACT(MONTH FROM v_now)::INT;
    v_new_count INT;
BEGIN
    INSERT INTO aia_health_message_usage (
        tenant_id, period_year, period_month,
        message_count, audio_count, text_count
    ) VALUES (
        p_tenant, v_year, v_month,
        1,
        CASE WHEN p_kind = 'audio' THEN 1 ELSE 0 END,
        CASE WHEN p_kind = 'text' THEN 1 ELSE 0 END
    )
    ON CONFLICT (tenant_id, period_year, period_month) DO UPDATE SET
        message_count = aia_health_message_usage.message_count + 1,
        audio_count = aia_health_message_usage.audio_count
            + (CASE WHEN p_kind = 'audio' THEN 1 ELSE 0 END),
        text_count = aia_health_message_usage.text_count
            + (CASE WHEN p_kind = 'text' THEN 1 ELSE 0 END)
    RETURNING message_count INTO v_new_count;

    RETURN v_new_count;
END;
$$ LANGUAGE plpgsql;


-- ════════════════════════════════════════════════════════════════════
-- 6. VIEW: status de quota por tenant (mês corrente)
-- ════════════════════════════════════════════════════════════════════
-- Painel admin lê isso pra mostrar "70/100 mensagens este mês"

CREATE OR REPLACE VIEW aia_health_current_month_usage AS
SELECT
    t.tenant_id,
    t.licensing_model,
    t.message_quota_monthly,
    t.quota_warning_threshold_pct,
    COALESCE(u.message_count, 0) AS message_count,
    COALESCE(u.audio_count, 0) AS audio_count,
    COALESCE(u.text_count, 0) AS text_count,
    CASE
        WHEN t.message_quota_monthly IS NULL THEN NULL
        ELSE ROUND(
            (COALESCE(u.message_count, 0)::NUMERIC * 100.0)
            / NULLIF(t.message_quota_monthly, 0),
            1
        )
    END AS quota_used_pct,
    u.last_warning_sent_at
FROM aia_health_tenant_config t
LEFT JOIN aia_health_message_usage u
    ON u.tenant_id = t.tenant_id
   AND u.period_year = EXTRACT(YEAR FROM NOW())::INT
   AND u.period_month = EXTRACT(MONTH FROM NOW())::INT;


COMMIT;
