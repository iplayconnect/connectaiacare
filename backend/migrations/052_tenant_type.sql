-- ConnectaIACare — Tenant type (ILPI / clínica / hospital / B2C / individual).
--
-- Plataforma atende quatro modelos de cliente, e Sofia precisa
-- comportar-se diferente em cada:
--
--   ILPI       — lar de idosos, plantões obrigatórios, cuidadores
--                profissionais, multi-paciente.
--   clinica    — clínica geriátrica, plantões fixos, atendimento
--                ambulatorial.
--   hospital   — internação, plantões 12x36, alta rotatividade.
--   B2C        — paciente em casa com cuidador particular ou familiar.
--                Plantão opcional (geralmente sem). 1-2 pacientes.
--   individual — paciente que assina sozinho (Sofia direto pra ele).
--                Sem cuidador formal. B2C puro.
--
-- A flag afeta:
--  * shift_resolver — em B2C/individual, plantão vazio é esperado
--    (não warning) e biometria cai pra 1:N pequeno (1-2 pessoas) ou
--    1:1 direto.
--  * pipeline — em individual, "cuidador" pode ser o próprio paciente
--    (persona detectada pela biometria).
--  * Sofia tone — ILPI usa linguagem técnica, B2C usa linguagem mais
--    acolhedora.

BEGIN;

ALTER TABLE aia_health_tenant_config
    ADD COLUMN IF NOT EXISTS tenant_type TEXT
        NOT NULL DEFAULT 'ILPI'
        CHECK (tenant_type IN (
            'ILPI', 'clinica', 'hospital', 'B2C', 'individual'
        ));

COMMENT ON COLUMN aia_health_tenant_config.tenant_type IS
'Modelo de cliente. Afeta comportamento do shift_resolver, pipeline '
'e tom da Sofia. ILPI/clinica/hospital exigem plantão; B2C/individual '
'tornam plantão opcional.';

CREATE INDEX IF NOT EXISTS idx_tenant_config_type
    ON aia_health_tenant_config(tenant_type);

COMMIT;
