-- Migration 015 — Handshake Web → WhatsApp (Onda B)
--
-- Adiciona campo `metadata` JSONB em aia_health_onboarding_sessions pra
-- armazenar UTMs, referrer, user agent, IP do lead capturado via web.
--
-- Também adiciona índices úteis pra analítica de funil B2C.

-- ═══════════════════════════════════════════════════════════════════
-- 1. Campo metadata (UTM / origem / tracking)
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE aia_health_onboarding_sessions
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::JSONB;

COMMENT ON COLUMN aia_health_onboarding_sessions.metadata IS
'Metadata de origem do lead: UTM params, referrer, IP, user agent. Usado pra funil de conversão e ROI de tráfego pago.';


-- ═══════════════════════════════════════════════════════════════════
-- 2. Índices pra analítica de funil
-- ═══════════════════════════════════════════════════════════════════

-- Origin (web_onboarding | whatsapp_direct | email_campaign | ...)
CREATE INDEX IF NOT EXISTS idx_onboarding_origin
    ON aia_health_onboarding_sessions((metadata->>'origin'))
    WHERE metadata IS NOT NULL;

-- UTM source (google | facebook | direct | email)
CREATE INDEX IF NOT EXISTS idx_onboarding_utm_source
    ON aia_health_onboarding_sessions((metadata->>'utm_source'))
    WHERE metadata->>'utm_source' IS NOT NULL;

-- UTM campaign (b2c_abril | retarget_semana_1 | ...)
CREATE INDEX IF NOT EXISTS idx_onboarding_utm_campaign
    ON aia_health_onboarding_sessions((metadata->>'utm_campaign'))
    WHERE metadata->>'utm_campaign' IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════════
-- 3. View de funil (agregação pronta)
-- ═══════════════════════════════════════════════════════════════════

CREATE OR REPLACE VIEW v_onboarding_funnel AS
SELECT
    COALESCE(metadata->>'origin', 'whatsapp_direct') AS origin,
    metadata->>'utm_source' AS utm_source,
    metadata->>'utm_campaign' AS utm_campaign,
    state,
    COUNT(*) AS n,
    COUNT(*) FILTER (WHERE completed_at IS NOT NULL) AS completed,
    COUNT(*) FILTER (WHERE abandoned_at IS NOT NULL) AS abandoned,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE completed_at IS NOT NULL) / NULLIF(COUNT(*), 0),
        2
    ) AS conversion_rate_pct
FROM aia_health_onboarding_sessions
GROUP BY
    metadata->>'origin',
    metadata->>'utm_source',
    metadata->>'utm_campaign',
    state;

COMMENT ON VIEW v_onboarding_funnel IS
'Funil de conversão por origem/campanha. Base pra dashboard de ROI de tráfego pago.';
