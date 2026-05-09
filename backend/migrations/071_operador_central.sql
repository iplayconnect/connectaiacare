-- =============================================================================
-- 071 — Operador Central (ATENT 24/7) — role + estado + audit
-- =============================================================================
--
-- Decisão (Alexandre 2026-05-08): operadores da ATENT precisam de painel
-- próprio dentro da plataforma, não só receber WhatsApp como humano.
-- Eles fazem:
--   • Receber handoffs (clínicos e comerciais) na fila
--   • Pegar (claim) handoff e conduzir atendimento
--   • Consultar histórico completo do paciente (leitura privilegiada)
--   • Trocar mensagens via WhatsApp através da plataforma (audit completo)
--   • Escalar pra médico de plantão quando preciso
--   • Resolver/transferir handoff
--
-- Estado em camadas:
--   1. Role 'operador_central' (validado em VALID_ROLES no app — sem
--      constraint no DB pra manter compatibilidade)
--   2. aia_health_operator_states (1 row por user, snapshot de online/shift)
--   3. aia_health_operator_shifts (audit de plantões)
--   4. aia_health_operator_actions (audit fino de cada ação)
--
-- Estende handoff_queue:
--   • handoff_type ganha 'operator' como valor válido (genérico, fila
--     onde operador 24/7 entra primeiro antes de escalar)
--
-- Migração idempotente.
-- =============================================================================

-- 1. Estado atual do operador (denormalizado pra dashboard rápido)
CREATE TABLE IF NOT EXISTS aia_health_operator_states (
    user_id UUID PRIMARY KEY REFERENCES aia_health_users(id) ON DELETE CASCADE,
    is_online BOOLEAN NOT NULL DEFAULT FALSE,
    last_heartbeat_at TIMESTAMPTZ,
    -- Reference pro shift atualmente em curso (NULL = sem plantão ativo)
    current_shift_id UUID,
    -- Handoff que está atendendo agora (NULL = idle)
    current_handoff_id UUID REFERENCES aia_health_human_handoff_queue(id) ON DELETE SET NULL,
    handoffs_handled_today INT NOT NULL DEFAULT 0,
    notes TEXT,                  -- nota livre admin (ex: "operador noturno")
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aia_op_states_online
    ON aia_health_operator_states(is_online, last_heartbeat_at DESC)
    WHERE is_online = TRUE;


-- 2. Audit de plantões — 1 row por turno completo
CREATE TABLE IF NOT EXISTS aia_health_operator_shifts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    handoffs_handled INT NOT NULL DEFAULT 0,
    -- Auto-end se sem heartbeat por > N min (ver job de limpeza)
    auto_ended BOOLEAN NOT NULL DEFAULT FALSE,
    auto_end_reason TEXT,
    duration_seconds INT GENERATED ALWAYS AS (
        CASE WHEN ended_at IS NOT NULL
             THEN EXTRACT(EPOCH FROM (ended_at - started_at))::INT
             ELSE NULL END
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_aia_op_shifts_user_started
    ON aia_health_operator_shifts(user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_aia_op_shifts_active
    ON aia_health_operator_shifts(user_id)
    WHERE ended_at IS NULL;


-- 3. Audit de ações fino — 1 row por ação relevante
CREATE TABLE IF NOT EXISTS aia_health_operator_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operator_user_id UUID NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
    handoff_id UUID REFERENCES aia_health_human_handoff_queue(id) ON DELETE SET NULL,
    patient_id UUID REFERENCES aia_health_patients(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    -- Tipos:
    --   'shift_start' | 'shift_end' | 'go_online' | 'go_offline'
    --   'claim_handoff' | 'release_handoff' | 'resolve_handoff' | 'transfer_handoff'
    --   'message_sent' | 'note_added'
    --   'escalate_clinical' | 'view_patient_context'
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aia_op_actions_operator_recent
    ON aia_health_operator_actions(operator_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aia_op_actions_handoff
    ON aia_health_operator_actions(handoff_id, created_at)
    WHERE handoff_id IS NOT NULL;


-- 4. Estende handoff_type pra incluir 'operator' (sem quebrar rows existentes)
DO $$
BEGIN
    -- Drop e recria a constraint com o valor adicional
    IF EXISTS (
        SELECT 1 FROM information_schema.constraint_column_usage
        WHERE table_name = 'aia_health_human_handoff_queue'
          AND constraint_name LIKE '%handoff_type%'
    ) THEN
        ALTER TABLE aia_health_human_handoff_queue
            DROP CONSTRAINT IF EXISTS aia_health_human_handoff_queue_handoff_type_check;
    END IF;
    ALTER TABLE aia_health_human_handoff_queue
        ADD CONSTRAINT aia_health_human_handoff_queue_handoff_type_check
        CHECK (handoff_type IN ('commercial', 'clinical', 'support', 'operator'));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;


-- 5. Triggers updated_at
CREATE OR REPLACE FUNCTION _aia_op_states_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_aia_op_states_updated
    ON aia_health_operator_states;
CREATE TRIGGER trg_aia_op_states_updated
    BEFORE UPDATE ON aia_health_operator_states
    FOR EACH ROW EXECUTE FUNCTION _aia_op_states_touch();


COMMENT ON TABLE aia_health_operator_states IS
    'Estado em-tempo-real dos operadores ATENT 24/7. is_online + ' ||
    'last_heartbeat_at definem disponibilidade pra atribuição de fila.';

COMMENT ON TABLE aia_health_operator_shifts IS
    'Histórico de plantões. Útil pra remuneração, métricas SLA e ' ||
    'compliance LGPD (quem acessou que paciente em qual turno).';

COMMENT ON TABLE aia_health_operator_actions IS
    'Audit fino. Toda ação relevante do operador no painel central ' ||
    'fica registrada — abre query, manda mensagem, escala, resolve. ' ||
    'Equivale ao audit_log mas focado no fluxo operacional 24/7.';
