-- =============================================================================
-- 071 — Tecnosenior CareNotes V2: cache de mídia + tabela de fotos
-- =============================================================================
--
-- Suporte aos novos endpoints do TotalCare V2:
--   POST /agent/care-notes/{id}/audio/                   (1 áudio por nota, write-once)
--   POST /agent/care-notes/{note_id}/addendums/{aid}/audio/ (1 áudio por addendum)
--   POST /agent/care-notes/{id}/photos/                  (sem limite, opcionalmente atrelada a addendum)
--
-- Política de fronteira (decidida 2026-05-07):
--   • Enviamos artefatos finais (CareNote pronta, áudio bruto, foto, closed_reason)
--   • NÃO expomos a inteligência da Sofia (orquestração, classificação, biometria,
--     drug safety) como API pra Tecnosenior consumir.
--   • Mídia vai pro S3 deles (conforme V2). Trade-off conhecido — discussão em
--     andamento com Murilo.
--
-- Migração idempotente. Rodar múltiplas vezes não quebra nada.
-- =============================================================================

-- 1. Cache de URL pós-upload (audio na CareNote principal)
ALTER TABLE aia_health_tecnosenior_sync
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_url TEXT,
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_uploaded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_upload_error TEXT,
    ADD COLUMN IF NOT EXISTS closed_reason_sent TEXT;
    -- closed_reason_sent: o que efetivamente mandamos no fechamento
    -- (audit, pode diferir do care_events.closed_reason se sanitizamos)

COMMENT ON COLUMN aia_health_tecnosenior_sync.tecnosenior_audio_url IS
    'URL pré-assinada S3 retornada pelo TotalCare. Expira ~1h. Não usar pra ' ||
    'reproduzir; sempre fazer GET na CareNote pra URL fresca.';

-- 2. Cache de URL pós-upload (audio em addendums)
ALTER TABLE aia_health_tecnosenior_addendums
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_url TEXT,
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_uploaded_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tecnosenior_audio_upload_error TEXT;

-- 3. Fotos (1 row por foto enviada)
CREATE TABLE IF NOT EXISTS aia_health_tecnosenior_photos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    care_event_id UUID NOT NULL REFERENCES aia_health_care_events(id) ON DELETE CASCADE,
    tecnosenior_carenote_id INT NOT NULL,
    tecnosenior_addendum_id INT,           -- NULL se foto pertence só à nota
    tecnosenior_photo_id INT NOT NULL,     -- ID retornado pelo TotalCare
    local_image_path TEXT,                 -- caminho do nosso storage local
    remote_image_url TEXT,                 -- presigned URL S3 (efêmera, ~1h)
    content_type TEXT,                     -- image/jpeg | image/png | etc.
    size_bytes INT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    upload_error TEXT,                     -- se falhou; null se ok
    UNIQUE(tecnosenior_photo_id)
);

CREATE INDEX IF NOT EXISTS idx_aia_tec_photos_care_event
    ON aia_health_tecnosenior_photos(care_event_id);
CREATE INDEX IF NOT EXISTS idx_aia_tec_photos_carenote
    ON aia_health_tecnosenior_photos(tecnosenior_carenote_id);
CREATE INDEX IF NOT EXISTS idx_aia_tec_photos_addendum
    ON aia_health_tecnosenior_photos(tecnosenior_addendum_id)
    WHERE tecnosenior_addendum_id IS NOT NULL;

COMMENT ON TABLE aia_health_tecnosenior_photos IS
    'Auditoria de fotos enviadas pro TotalCare (V2). 1 row por foto. ' ||
    'remote_image_url é presigned e expira — sempre fazer GET fresco se precisar.';
