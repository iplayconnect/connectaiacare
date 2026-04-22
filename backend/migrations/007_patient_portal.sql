-- Migration 007 — Portal do Paciente
-- Permite que paciente/familiar acesse resumo da teleconsulta + prescrição
-- com preços por 24h via PIN de 6 dígitos enviado no WhatsApp.
--
-- Compliance:
--   CFM 2.314/2022 · acesso controlado a prontuário pelo paciente
--   LGPD Art. 9º     · transparência sobre tratamento
--   LGPD Art. 18     · direito de acesso do titular

CREATE TABLE IF NOT EXISTS aia_health_patient_portal_access (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    teleconsultation_id  UUID NOT NULL REFERENCES aia_health_teleconsultations(id) ON DELETE CASCADE,
    tenant_id            TEXT NOT NULL DEFAULT 'connectaiacare_demo',

    -- PIN de 6 dígitos enviado via WhatsApp (bcrypt hash, nunca armazenado em claro)
    pin_hash             TEXT NOT NULL,

    -- Telefone pra onde o PIN foi enviado (audit)
    recipient_phone      TEXT NOT NULL,

    -- Controle de TTL — 24h default
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at           TIMESTAMPTZ NOT NULL,

    -- Audit de acesso
    first_accessed_at    TIMESTAMPTZ,
    last_accessed_at     TIMESTAMPTZ,
    access_count         INTEGER NOT NULL DEFAULT 0,

    -- Rate limit: bloqueia após N tentativas erradas (default 5)
    failed_attempts      INTEGER NOT NULL DEFAULT 0,
    locked_at            TIMESTAMPTZ,

    -- Revogação
    revoked_at           TIMESTAMPTZ,
    revoked_reason       TEXT,

    -- Cache de busca de preços (expira em 6h, evita bombardear scraper)
    price_cache          JSONB,
    price_cache_at       TIMESTAMPTZ,

    -- Resumo paciente-friendly (gerado por LLM, cacheado)
    patient_summary      JSONB,
    patient_summary_at   TIMESTAMPTZ
);

CREATE INDEX idx_portal_access_tc ON aia_health_patient_portal_access(teleconsultation_id);
CREATE INDEX idx_portal_access_expires ON aia_health_patient_portal_access(expires_at)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_portal_access_tenant ON aia_health_patient_portal_access(tenant_id);

-- Audit log separado de tentativas de acesso (inclui falhas)
CREATE TABLE IF NOT EXISTS aia_health_patient_portal_access_log (
    id                   BIGSERIAL PRIMARY KEY,
    portal_access_id     UUID REFERENCES aia_health_patient_portal_access(id) ON DELETE SET NULL,
    teleconsultation_id  UUID,
    tenant_id            TEXT NOT NULL,
    ip_address           TEXT,
    user_agent           TEXT,
    action               TEXT NOT NULL,  -- 'pin_sent', 'access_granted', 'access_denied', 'locked', 'revoked'
    detail               JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (action IN (
        'pin_sent', 'access_granted', 'access_denied',
        'locked', 'revoked', 'summary_generated',
        'prices_fetched', 'pdf_downloaded'
    ))
);

CREATE INDEX idx_portal_log_tc ON aia_health_patient_portal_access_log(teleconsultation_id);
CREATE INDEX idx_portal_log_created ON aia_health_patient_portal_access_log(created_at DESC);

-- Trigger updated_at (usando função que já existe em 005)
-- Nenhum trigger necessário aqui pois só created_at + campos imutáveis-após-uso.

COMMENT ON TABLE aia_health_patient_portal_access IS
'Acesso público ao resumo de teleconsulta via PIN (24h TTL). LGPD Art. 9º/18.';

COMMENT ON COLUMN aia_health_patient_portal_access.pin_hash IS
'Bcrypt hash do PIN de 6 dígitos. PIN em claro NUNCA é armazenado.';

COMMENT ON COLUMN aia_health_patient_portal_access.price_cache IS
'Cache de busca de preços por 6h (evita rescrape a cada render da página).';
