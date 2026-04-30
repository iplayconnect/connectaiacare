-- ═══════════════════════════════════════════════════════════════════
-- 059 — Tabela mãe aia_health_tenants
--
-- Atualmente tenant_id (text) está espalhado em 59 tabelas mas não
-- há tabela mestre. aia_health_tenant_config tem CONFIG por tenant
-- mas não a IDENTIDADE (nome, branding, status, IA persona).
--
-- Essa migration cria a tabela mãe e seeda os tenants existentes.
-- Não força FK ainda em todas as tabelas filhas (pode quebrar prod).
-- FK adicionada só em tenant_config (mais isolada).
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_tenants (
    id text PRIMARY KEY,                -- slug, ex: 'connectaiacare_demo', 'tecnosenior'
    name text NOT NULL,                  -- 'ConnectaIACare Demo', 'Tecnosenior — Vidafone'

    -- Identidade da IA per tenant
    ai_name text NOT NULL DEFAULT 'Sofia',           -- 'Sofia', 'Emília', etc
    ai_voice text NOT NULL DEFAULT 'ara',            -- voz Grok pra TTS
    ai_kickoff_phrase text,                          -- saudação custom (override do default)

    -- Branding
    logo_url text,
    primary_color text,                              -- hex ex: '#31E1FF'
    accent_color text,

    -- Canais (números/IDs)
    whatsapp_phone text,                             -- número WhatsApp da IA
    whatsapp_evolution_instance text,                -- nome da instância no Evolution
    voice_did text,                                  -- número SIP DID inbound (ex: 5130624363)
    voice_sip_provider text,                         -- 'flux' | 'nvoip' | etc

    -- Integrações externas habilitadas (Tecnosenior, MedMonitor, ConnectaLive)
    integrations_enabled jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- Status
    active boolean NOT NULL DEFAULT TRUE,
    suspended boolean NOT NULL DEFAULT FALSE,
    suspended_reason text,
    suspended_at timestamptz,

    -- Auditoria
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW(),
    created_by_user_id uuid,

    -- Metadata livre
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_tenants_active
    ON aia_health_tenants(active) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_tenants_whatsapp
    ON aia_health_tenants(whatsapp_phone) WHERE whatsapp_phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tenants_voice_did
    ON aia_health_tenants(voice_did) WHERE voice_did IS NOT NULL;

COMMENT ON TABLE aia_health_tenants IS
    'Tabela mãe de tenants. Cada tenant é um cliente da plataforma '
    '(ILPI, clínica, B2C familiar, parceiro tipo Tecnosenior). '
    'Contém identidade da IA (Sofia/Emília), canais, branding e status.';

-- Trigger pra updated_at automático
CREATE TRIGGER trg_tenants_updated
    BEFORE UPDATE ON aia_health_tenants
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_set_updated_at();

-- Seed: tenant principal já em uso
INSERT INTO aia_health_tenants (
    id, name, ai_name, ai_voice,
    voice_did, voice_sip_provider,
    integrations_enabled, active
) VALUES (
    'connectaiacare_demo',
    'ConnectaIACare — Demo / Casa de Geriatria',
    'Sofia',
    'ara',
    '5130624363',
    'flux',
    '{"tecnosenior": true, "medmonitor": false, "connectalive": false}'::jsonb,
    TRUE
) ON CONFLICT (id) DO NOTHING;

-- Seed: tenant Tecnosenior (preparação pra Emília)
INSERT INTO aia_health_tenants (
    id, name, ai_name, ai_voice,
    integrations_enabled, active
) VALUES (
    'tecnosenior',
    'Tecnosenior — Vidafone',
    'Emília',
    'ara',
    '{"tecnosenior": true}'::jsonb,
    FALSE  -- inativo até multi-tenant rollout completar
) ON CONFLICT (id) DO NOTHING;

-- FK em tenant_config (com ON DELETE RESTRICT pra não perder config
-- acidentalmente; tenant inativo pode ficar suspended em vez de
-- deletado).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_tenant_config_tenant'
    ) THEN
        ALTER TABLE aia_health_tenant_config
            ADD CONSTRAINT fk_tenant_config_tenant
            FOREIGN KEY (tenant_id) REFERENCES aia_health_tenants(id)
            ON DELETE RESTRICT;
    END IF;
END $$;
