-- ConnectaIACare — Autenticação + perfis + sessões
-- Data: 2026-04-24
--
-- Contexto:
--   Até agora a plataforma operava stateless (phone do cuidador como
--   identidade implícita). Com Murilo testando e parceiros recebendo acesso
--   ao CRM web, precisamos de auth real para:
--     - rastreabilidade por usuário em aia_health_audit_chain.actor
--     - LGPD Art. 11 (controle de acesso a dados sensíveis)
--     - escopo de parceiro (pacientes visíveis só pra leitura)
--     - obrigatoriedade pré-piloto com SPA Tecnosenior
--
-- Esta migration cria as fundações para:
--   • Bloco A (auth): users + sessions + JWT
--   • Bloco B (gestão): users CRUD + avatar
--   • Bloco C (perfis customizáveis): aia_health_profiles + permissions chain
--   • Bloco D (recovery / 2FA): colunas mfa_*, password_reset_*, metadata JSONB
--     (tabelas/endpoints específicos virão em migration futura)
--
-- Roles iniciais (estendíveis via aia_health_profiles):
--   super_admin    — Alexandre, acesso total cross-tenant
--   admin_tenant   — admin da clínica/SPA
--   medico         — médico (CRM obrigatório)
--   enfermeiro     — enfermagem (COREN obrigatório)
--   cuidador_pro   — cuidador profissional cadastrado no CRM
--   familia        — familiar do paciente (escopo: paciente vinculado)
--   parceiro       — parceiro externo (escopo restrito por allowed_patient_ids)

BEGIN;

-- =====================================================
-- aia_health_profiles — perfis customizáveis (Bloco C)
-- =====================================================
-- Permite que admin_tenant crie perfis com permissions específicas,
-- por exemplo "supervisor_noturno" com leitura de care_events + escrita
-- limitada. Quando vazio, sistema usa fallback ROLE_PERMISSIONS no código.
CREATE TABLE IF NOT EXISTS aia_health_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    permissions JSONB NOT NULL DEFAULT '[]'::JSONB,  -- ex: ["patients:read", "events:write"]
    config JSONB NOT NULL DEFAULT '{}'::JSONB,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_tenant_slug
    ON aia_health_profiles(tenant_id, slug);

-- =====================================================
-- aia_health_users — usuários autenticáveis
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN (
        'super_admin', 'admin_tenant', 'medico', 'enfermeiro',
        'cuidador_pro', 'familia', 'parceiro'
    )),
    -- Override explícito de permissions (Bloco C: precedência mais alta).
    -- Se vazio, cai no profile_id; se profile vazio, no fallback do role.
    permissions JSONB NOT NULL DEFAULT '[]'::JSONB,
    profile_id UUID REFERENCES aia_health_profiles(id) ON DELETE SET NULL,

    -- Avatar (Bloco B). Salvo como data:image/...;base64,... ou URL externa.
    avatar_url TEXT,
    phone TEXT,

    -- Documentos profissionais (opcionais por role)
    crm_register TEXT,            -- ex: "12345/RS"
    coren_register TEXT,          -- ex: "RS-987654"

    -- Vínculos opcionais
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE SET NULL,

    -- Escopo restrito (parceiros: lista explícita de pacientes visíveis)
    allowed_patient_ids JSONB DEFAULT '[]'::JSONB,
    partner_org TEXT,             -- ex: "Tecnosenior"

    -- Flags / 2FA (Bloco D — colunas reservadas, endpoints futuros)
    active BOOLEAN NOT NULL DEFAULT TRUE,
    password_change_required BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret TEXT,                              -- TOTP secret (cifrar na app antes de gravar)
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,                     -- bloqueio temporário após brute force

    last_login_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_email
    ON aia_health_users(tenant_id, lower(email));
CREATE INDEX IF NOT EXISTS idx_users_role ON aia_health_users(role);
CREATE INDEX IF NOT EXISTS idx_users_active ON aia_health_users(active);
CREATE INDEX IF NOT EXISTS idx_users_profile ON aia_health_users(profile_id);

-- =====================================================
-- aia_health_user_sessions — refresh tokens revogáveis
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_user_sessions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
    refresh_token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token
    ON aia_health_user_sessions(refresh_token_hash)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_user_sessions_user
    ON aia_health_user_sessions(tenant_id, user_id, revoked_at);

-- =====================================================
-- aia_health_password_reset_tokens — Bloco D (estrutura pronta, endpoints depois)
-- =====================================================
CREATE TABLE IF NOT EXISTS aia_health_password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    requested_ip TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pwreset_token_hash
    ON aia_health_password_reset_tokens(token_hash)
    WHERE used_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pwreset_user
    ON aia_health_password_reset_tokens(user_id, created_at DESC);

-- =====================================================
-- Trigger: auto-update updated_at
-- =====================================================
CREATE OR REPLACE FUNCTION aia_health_users_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON aia_health_users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON aia_health_users
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_users_set_updated_at();

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON aia_health_profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON aia_health_profiles
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_users_set_updated_at();

COMMIT;
