-- Estende CHECKs de aia_health_sofia_sessions pra incluir personas e channels
-- novos usados pela voice-call-service e cenários de ligação.
--
-- Aplicado em produção via ALTER ad-hoc primeiro (ver 2026-04-26 incident);
-- esta migration garante que deploys futuros já tenham os valores corretos.

BEGIN;

-- persona: + 'comercial', 'sofia_proativa'
ALTER TABLE aia_health_sofia_sessions
    DROP CONSTRAINT IF EXISTS aia_health_sofia_sessions_persona_check;
ALTER TABLE aia_health_sofia_sessions
    ADD CONSTRAINT aia_health_sofia_sessions_persona_check
    CHECK (persona = ANY (ARRAY[
        'cuidador_pro', 'familia', 'medico', 'enfermeiro',
        'admin_tenant', 'super_admin', 'paciente_b2c', 'parceiro',
        'anonymous',
        'comercial', 'sofia_proativa'
    ]));

-- channel: + 'voice_call' (já adicionado em hotfix anterior — idempotente)
ALTER TABLE aia_health_sofia_sessions
    DROP CONSTRAINT IF EXISTS aia_health_sofia_sessions_channel_check;
ALTER TABLE aia_health_sofia_sessions
    ADD CONSTRAINT aia_health_sofia_sessions_channel_check
    CHECK (channel = ANY (ARRAY['web', 'whatsapp', 'voice', 'voice_call', 'api']));

COMMIT;
