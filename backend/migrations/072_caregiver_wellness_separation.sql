-- =============================================================================
-- 072 — Separação cuidador↔paciente: wellness events fora do prontuário
-- =============================================================================
--
-- Decisão arquitetural (Alexandre 2026-05-09):
--
-- 1. Relatos com event_type='apoio_emocional' NÃO devem ser registrados no
--    prontuário do paciente (aia_health_care_events). Eles são sobre o
--    CUIDADOR, não sobre o paciente. Misturar polui PHI clínico, gera
--    confusão LGPD, e enche CareNote do TotalCare com info irrelevante.
--
-- 2. Esses casos viram aia_health_caregiver_wellness_events e são roteados
--    pro GESTOR responsável da unidade (admin_tenant do tenant), não pro
--    plantão clínico nem responsável do paciente.
--
-- 3. Corpus Review (validação humana de classificação): a fila padrão
--    serve só event_types clínicos. Casos apoio_emocional ficam em
--    track='caregiver_wellness' — futura aba pra reviewer dedicado.
--
-- Migração idempotente.
-- =============================================================================


-- 1. Filtro de track na Corpus Review
ALTER TABLE aia_health_classification_corpus_cases
    ADD COLUMN IF NOT EXISTS review_track TEXT
        NOT NULL DEFAULT 'clinical'
        CHECK (review_track IN ('clinical', 'caregiver_wellness'));

-- Backfill: todos os apoio_emocional vão pro track de wellness
UPDATE aia_health_classification_corpus_cases
   SET review_track = 'caregiver_wellness'
 WHERE llm_suggested_event_type = 'apoio_emocional'
   AND review_track = 'clinical';

CREATE INDEX IF NOT EXISTS idx_corpus_cases_track_status
    ON aia_health_classification_corpus_cases(review_track, review_status);

COMMENT ON COLUMN aia_health_classification_corpus_cases.review_track IS
    'Track de revisão: clinical (Henrique/médico/farma valida classificação ' ||
    'clínica) | caregiver_wellness (gestor de unidade valida casos de ' ||
    'apoio_emocional/burnout do cuidador). Default clinical.';


-- 2. Tabela de eventos de bem-estar do cuidador (separada do prontuário)
CREATE TABLE IF NOT EXISTS aia_health_caregiver_wellness_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL REFERENCES aia_health_tenants(id) ON DELETE RESTRICT,
    -- Cuidador identificado (NULL se Sofia não conseguiu mapear voz/phone)
    caregiver_id UUID REFERENCES aia_health_caregivers(id) ON DELETE SET NULL,
    caregiver_phone TEXT NOT NULL,
    -- Texto bruto do relato (transcript do áudio ou texto enviado)
    raw_text TEXT NOT NULL,
    -- Resumo curto pra UI/notificação
    summary TEXT,
    -- Severidade — mesma escala do clínico mas com semântica de wellness:
    --   routine    = desabafo simples, log silencioso
    --   attention  = exaustão moderada, vale acolher
    --   urgent     = burnout severo / risco operacional iminente
    --   critical   = ideação de auto-extermínio / crise grave
    severity TEXT NOT NULL DEFAULT 'routine'
        CHECK (severity IN ('routine', 'attention', 'urgent', 'critical')),
    -- Origem do canal (whatsapp/voice/web)
    source_channel TEXT NOT NULL DEFAULT 'whatsapp',
    -- Vínculo com o report original (audit trail) — sem cascata de delete
    -- pra preservar histórico mesmo se o report sumir.
    source_report_id UUID,
    -- Status do tratamento pelo gestor
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved', 'escalated')),
    -- Quem o sistema notificou inicialmente
    notified_managers TEXT[],         -- array de user_ids notificados
    notified_at TIMESTAMPTZ,
    -- Quem reconheceu / quando
    acknowledged_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    acknowledged_at TIMESTAMPTZ,
    -- Resolução
    resolution_summary TEXT,
    resolved_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aia_wellness_tenant_status
    ON aia_health_caregiver_wellness_events(tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_aia_wellness_caregiver_recent
    ON aia_health_caregiver_wellness_events(caregiver_id, created_at DESC)
    WHERE caregiver_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_aia_wellness_unresolved
    ON aia_health_caregiver_wellness_events(tenant_id, severity, created_at DESC)
    WHERE status IN ('open', 'acknowledged');


COMMENT ON TABLE aia_health_caregiver_wellness_events IS
    'Eventos de bem-estar/exaustão de cuidadores. SEPARADO de ' ||
    'aia_health_care_events (prontuário do paciente) por design — ' ||
    'cuidador relatando burnout NÃO é PHI clínico do paciente.';

COMMENT ON COLUMN aia_health_caregiver_wellness_events.tenant_id IS
    'Tenant da UNIDADE/EMPREGADOR do cuidador (lar de idosos, ILPI, etc.). ' ||
    'Gestor responsável é resolvido via admin_tenant role desse tenant.';


-- 3. Trigger updated_at
CREATE OR REPLACE FUNCTION _aia_wellness_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_aia_wellness_updated
    ON aia_health_caregiver_wellness_events;
CREATE TRIGGER trg_aia_wellness_updated
    BEFORE UPDATE ON aia_health_caregiver_wellness_events
    FOR EACH ROW EXECUTE FUNCTION _aia_wellness_touch();
