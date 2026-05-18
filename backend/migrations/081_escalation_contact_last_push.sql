-- =============================================================================
-- 081 — Última atividade de push P1 por contato de escalação
-- =============================================================================
--
-- Contexto (Alexandre 2026-05-17): UI da pagina de contatos não
-- mostra quando o plantonista recebeu push pela última vez. Sem isso,
-- impossivel saber se o contato está vivo (recebendo notificações).
--
-- Adiciona colunas materializadas:
--   - last_p1_received_at TIMESTAMPTZ — último push P1 enviado
--   - last_p1_handoff_id UUID — pra navegar até o handoff
--   - total_p1_received INT — contador total
--
-- Mantido como materializado (vs computar via JOIN com audit_log)
-- porque:
--   1. Audit log cresce indefinidamente — query agregada fica lenta
--   2. UI exibe lista de contatos (10-50 rows) com último push;
--      pre-computado é O(1) por row
--   3. Atualização é via UPDATE simples no momento de cada push
--      (idempotente; idempotente se o mesmo handoff disparar 2x).
--
-- O update fica em sofia_tools.py dentro do bloco que envia
-- p1_admin_escalation_push (proximo commit).
-- =============================================================================

BEGIN;

ALTER TABLE aia_health_tenant_escalation_contacts
    ADD COLUMN IF NOT EXISTS last_p1_received_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_p1_handoff_id UUID,
    ADD COLUMN IF NOT EXISTS total_p1_received INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN aia_health_tenant_escalation_contacts.last_p1_received_at IS
    'Quando esse contato recebeu o último push P1. Atualizado pelo '
    'tool escalate_to_human_clinical em sofia_tools.py. NULL = nunca '
    'recebeu (recém cadastrado ou inativo). UI mostra "Última push: '
    '2h atrás" — sinal de vida do contato.';

COMMENT ON COLUMN aia_health_tenant_escalation_contacts.last_p1_handoff_id IS
    'FK soft pro último handoff que disparou push pra esse contato. '
    'Permite navegar direto do dashboard pro caso (sem JOIN).';

COMMENT ON COLUMN aia_health_tenant_escalation_contacts.total_p1_received IS
    'Contador acumulado de P1s recebidos. Métrica simples de carga '
    'distribuída entre plantonistas.';

-- Index pra dashboard "contatos sem push recente"
CREATE INDEX IF NOT EXISTS idx_escalation_last_p1
    ON aia_health_tenant_escalation_contacts(tenant_id, last_p1_received_at DESC)
    WHERE active = TRUE;

-- Backfill (best-effort) pra contatos existentes baseado no audit_log
-- Pra cada contato ativo, busca o último p1_admin_escalation_push
-- com phone do contato no payload e popula last_p1_received_at.
-- Sem JOIN (audit_log não tem FK direto); usa subquery por phone.
UPDATE aia_health_tenant_escalation_contacts c
   SET last_p1_received_at = sub.last_sent,
       total_p1_received = sub.total
  FROM (
    SELECT
      payload->>'phone_redacted' AS phone_redacted_anchor,
      COUNT(*) AS total,
      MAX(created_at) AS last_sent
    FROM aia_health_audit_log
    WHERE action = 'outbound_sent'
      AND payload->>'reason' = 'p1_admin_escalation_push'
      AND created_at >= NOW() - INTERVAL '90 days'
    GROUP BY payload->>'phone_redacted'
  ) sub
 WHERE
   -- Match por phone redacted: payload tem "55519****4144";
   -- contato tem phone full "5551998774144". Comparamos sufixo.
   sub.phone_redacted_anchor IS NOT NULL
   AND sub.phone_redacted_anchor LIKE '%' || RIGHT(c.phone, 4);

COMMIT;
