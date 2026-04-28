-- ConnectaIACare — Plantões + phone_type (insight Grok do panel LLM).
--
-- Resolve dois problemas reais:
--
-- 1. Biometria 1:N hoje busca em todos os cuidadores do tenant. Em
--    tenant com 10-15 cuidadores fica impreciso. Limitando ao pool
--    do plantão atual (3-4 vozes) o acerto sobe muito.
--
-- 2. Lares oferecem celular por plantão (compartilhado). Vários
--    cuidadores usam o mesmo número. Biometria fica inútil.
--    Precisamos saber se o número é shared ou personal.
--
-- Aplicável a TODOS os tenants (geriatria, clínica, hospital).

BEGIN;

-- ════════════════════════════════════════════════════════════════════
-- 1. phone_type por cuidador
-- ════════════════════════════════════════════════════════════════════
-- shared  = celular do plantão, vários cuidadores usam (biometria off)
-- personal = WhatsApp pessoal (biometria normal)
-- unknown = ainda não classificado (default seguro: trata como shared)

ALTER TABLE aia_health_caregivers
    ADD COLUMN IF NOT EXISTS phone_type TEXT
        NOT NULL DEFAULT 'unknown'
        CHECK (phone_type IN ('personal', 'shared', 'unknown'));

CREATE INDEX IF NOT EXISTS idx_caregivers_phone_type
    ON aia_health_caregivers(tenant_id, phone_type);


-- ════════════════════════════════════════════════════════════════════
-- 2. Cadastro de plantões (turnos fixos por tenant)
-- ════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS aia_health_shift_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    caregiver_id UUID NOT NULL REFERENCES aia_health_caregivers(id)
        ON DELETE CASCADE,

    -- Nome do plantão (ex: 'morning', 'afternoon', 'night')
    shift_name TEXT NOT NULL,

    -- Janela horária do plantão (TIME, sem fuso — assume timezone do tenant)
    starts_at TIME NOT NULL,
    ends_at TIME NOT NULL,

    -- Dias da semana em que esse cuidador faz esse plantão.
    -- 1=segunda ... 7=domingo (ISO 8601).
    -- Array vazio = todos os dias.
    weekdays INT[] NOT NULL DEFAULT ARRAY[1,2,3,4,5,6,7]::INT[],

    active BOOLEAN NOT NULL DEFAULT TRUE,

    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Mesmo cuidador NÃO pode ter o mesmo plantão duplicado nos mesmos
    -- dias (regra solta — overrides resolvem casos pontuais)
    UNIQUE (caregiver_id, shift_name, starts_at, ends_at)
);

CREATE INDEX IF NOT EXISTS idx_shifts_tenant_active
    ON aia_health_shift_schedules(tenant_id, active)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_shifts_caregiver
    ON aia_health_shift_schedules(caregiver_id);

DROP TRIGGER IF EXISTS trg_shifts_updated ON aia_health_shift_schedules;
CREATE TRIGGER trg_shifts_updated
    BEFORE UPDATE ON aia_health_shift_schedules
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();


-- ════════════════════════════════════════════════════════════════════
-- 3. Override temporário (cobertura de plantão por outro cuidador)
-- ════════════════════════════════════════════════════════════════════
-- Cenário: cuidador da manhã cobre plantão da tarde por 1 dia.
-- A biometria não acha a voz no pool da tarde → fallback pergunta
-- "você é X, Y ou Z?" → cuidador responde "Sou Ana, cobrindo a
-- tarde hoje" → registra override aqui.

CREATE TABLE IF NOT EXISTS aia_health_shift_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    caregiver_id UUID NOT NULL REFERENCES aia_health_caregivers(id)
        ON DELETE CASCADE,
    shift_name TEXT NOT NULL,

    -- Janela de validade do override
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,

    -- Quem registrou (admin manual ou sistema via fallback Sofia)
    created_by TEXT,                 -- 'system' | 'admin' | user_id
    reason TEXT,                     -- 'cobertura_temporaria', 'troca', etc.

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (valid_until > valid_from)
);

CREATE INDEX IF NOT EXISTS idx_overrides_active
    ON aia_health_shift_overrides(tenant_id, valid_from, valid_until);

CREATE INDEX IF NOT EXISTS idx_overrides_caregiver
    ON aia_health_shift_overrides(caregiver_id);


-- ════════════════════════════════════════════════════════════════════
-- 4. VIEW: cuidadores ativos no plantão atual
-- ════════════════════════════════════════════════════════════════════
-- Usada pelo voice_biometrics_service para reduzir pool 1:N.
-- Considera tanto schedule fixo quanto override temporário ativo.

CREATE OR REPLACE VIEW aia_health_active_shift_caregivers AS
SELECT DISTINCT
    s.tenant_id,
    s.shift_name,
    s.caregiver_id,
    c.full_name,
    c.phone,
    c.phone_type,
    'scheduled' AS source
FROM aia_health_shift_schedules s
JOIN aia_health_caregivers c ON c.id = s.caregiver_id
WHERE s.active = TRUE
  AND c.active = TRUE
  AND CURRENT_TIME BETWEEN s.starts_at AND s.ends_at
  AND EXTRACT(ISODOW FROM CURRENT_DATE)::INT = ANY(s.weekdays)

UNION

SELECT DISTINCT
    o.tenant_id,
    o.shift_name,
    o.caregiver_id,
    c.full_name,
    c.phone,
    c.phone_type,
    'override' AS source
FROM aia_health_shift_overrides o
JOIN aia_health_caregivers c ON c.id = o.caregiver_id
WHERE c.active = TRUE
  AND NOW() BETWEEN o.valid_from AND o.valid_until;


-- ════════════════════════════════════════════════════════════════════
-- 5. Helper function: classifica plantão atual a partir da hora
-- ════════════════════════════════════════════════════════════════════
-- Útil quando o cliente envia áudio mas não sabemos o nome do
-- plantão. Dado um tenant_id e a hora atual, retorna o nome do
-- plantão mais provável (que tenha CURRENT_TIME dentro da janela).

CREATE OR REPLACE FUNCTION aia_health_current_shift_name(p_tenant TEXT)
RETURNS TEXT AS $$
DECLARE
    v_shift TEXT;
BEGIN
    SELECT shift_name INTO v_shift
    FROM aia_health_shift_schedules
    WHERE tenant_id = p_tenant
      AND active = TRUE
      AND CURRENT_TIME BETWEEN starts_at AND ends_at
      AND EXTRACT(ISODOW FROM CURRENT_DATE)::INT = ANY(weekdays)
    LIMIT 1;

    RETURN v_shift;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;
