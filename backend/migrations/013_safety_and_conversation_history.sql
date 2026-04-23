-- Migration 013 — Safety Layer + Conversation History
--
-- Parte da Onda A (ADR-027).
--
-- Duas tabelas novas:
--   1. aia_health_conversation_messages — histórico unificado de mensagens
--      user+bot, canal-agnóstico (base pra janela deslizante + buffer)
--   2. aia_health_safety_events — eventos de safety (moderação, triggers
--      de emergência, jailbreak attempts) com acesso restrito

-- ═══════════════════════════════════════════════════════════════════
-- 1. CONVERSATION MESSAGES — histórico unificado cross-canal
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_conversation_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,

    -- Identificação do subject (polimórfica — pode ser phone, user_id, session_id)
    subject_phone TEXT,                    -- canal WhatsApp usa phone
    subject_id UUID,                       -- futuro: subjects polimórficos
    subject_type TEXT DEFAULT 'unknown',   -- 'patient' | 'caregiver' | 'family' | 'payer' | 'unknown'

    -- Contexto conversacional
    session_context TEXT,                  -- 'onboarding' | 'care_event' | 'teleconsultation' | 'companion' | 'general'
    session_id UUID,                       -- FK lógica pra session específica (onboarding_sessions.id, etc)

    -- Canal
    channel TEXT NOT NULL DEFAULT 'whatsapp' CHECK (channel IN (
        'whatsapp', 'alexa', 'voice_native', 'web', 'sms', 'internal'
    )),

    -- Direção
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),

    -- Conteúdo
    message_format TEXT NOT NULL DEFAULT 'text' CHECK (message_format IN (
        'text', 'audio', 'image', 'video', 'document', 'structured', 'system'
    )),
    content TEXT,                          -- texto (ou transcrição se audio)
    content_raw_ref TEXT,                  -- URL/ID do arquivo original (áudio/imagem em S3)
    metadata JSONB,                        -- context extra: modelo LLM, tokens, imagens, etc

    -- Momento
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Safety flags (rastro pra investigação)
    safety_moderated BOOLEAN NOT NULL DEFAULT FALSE,
    safety_score JSONB,                    -- output da moderação
    safety_event_id UUID,                  -- FK pra safety_events se houve trigger

    -- Processamento
    processed_at TIMESTAMPTZ,
    processing_agent TEXT,                 -- qual agente/handler processou
    processing_duration_ms INTEGER,

    -- External refs
    external_id TEXT,                      -- ID da mensagem no Evolution/Alexa/etc
    reply_to_id UUID REFERENCES aia_health_conversation_messages(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes para janela deslizante rápida
CREATE INDEX IF NOT EXISTS idx_conv_msg_phone_time
    ON aia_health_conversation_messages(subject_phone, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_conv_msg_subject_time
    ON aia_health_conversation_messages(subject_id, received_at DESC)
    WHERE subject_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conv_msg_session
    ON aia_health_conversation_messages(session_id, received_at ASC)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conv_msg_tenant_time
    ON aia_health_conversation_messages(tenant_id, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_conv_msg_safety
    ON aia_health_conversation_messages(safety_moderated, received_at DESC)
    WHERE safety_moderated = TRUE;


-- ═══════════════════════════════════════════════════════════════════
-- 2. SAFETY EVENTS — moderação + triggers de emergência
-- ═══════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS aia_health_safety_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,

    -- Contexto
    subject_phone TEXT,
    subject_id UUID,
    conversation_id UUID REFERENCES aia_health_conversation_messages(id) ON DELETE SET NULL,
    session_id UUID,

    -- Tipo do evento
    trigger_type TEXT NOT NULL CHECK (trigger_type IN (
        -- Críticos (requerem escalação humana imediata)
        'suicidal_ideation',         -- ideação suicida / auto-lesão
        'elder_abuse',               -- violência contra idoso
        'medical_emergency',         -- emergência médica reportada
        'csam',                      -- conteúdo sexual envolvendo menor

        -- Alertas (investigar)
        'violence_threat',           -- ameaça a terceiros
        'substance_abuse',           -- álcool/drogas em contexto de risco
        'severe_depression',         -- quadro depressivo severo

        -- Jailbreak / abuse
        'jailbreak_attempt',         -- tentou trocar persona / extrair prompt
        'prompt_injection',          -- injeção de instruções
        'persona_break_attempt',     -- tentou fazer Sofia "virar outra"

        -- Conteúdo inadequado
        'sexual_content_adult',      -- conteúdo sexual adulto
        'hate_speech',               -- discurso de ódio
        'violence_graphic',          -- violência gráfica

        -- Outros
        'unknown_high_risk',         -- moderação detectou risco sem categoria clara
        'rate_limit_suspicious'      -- volume anômalo de mensagens
    )),
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN (
        'info', 'warning', 'critical', 'emergency'
    )),

    -- Detalhes (conteúdo potencialmente sensível — acesso restrito)
    user_message_preview TEXT,             -- primeiros 500 chars
    user_message_full_ref TEXT,            -- ref pra mensagem completa (conversation_messages)
    moderation_score JSONB,                -- output das APIs (OpenAI Mod, regex hits, etc)
    detection_source TEXT,                 -- 'openai_moderation' | 'regex' | 'llm_classifier' | 'human_report'

    -- Ações executadas
    actions_taken TEXT[],                  -- ['bot_muted', 'atente_notified', 'family_notified', 'cvv_shown', 'blocked']
    bot_response_sent TEXT,                -- o que Sofia respondeu (se algo)

    -- Escalações
    atente_notified_at TIMESTAMPTZ,
    atente_ticket_id TEXT,
    family_notified_at TIMESTAMPTZ,
    family_notification_channel TEXT,
    external_authority_notified_at TIMESTAMPTZ,  -- Disque 100, SAMU, CVV
    external_authority_name TEXT,

    -- Revisão humana
    reviewed_by_user_id UUID,              -- admin/Atente que revisou
    reviewed_at TIMESTAMPTZ,
    review_decision TEXT,                  -- 'confirmed_emergency' | 'false_positive' | 'needs_followup'
    review_notes TEXT,
    followed_up_at TIMESTAMPTZ,

    -- Rate limit / abuse tracking
    attempts_count INTEGER NOT NULL DEFAULT 1,
    same_user_recent_events INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_safety_subject_time
    ON aia_health_safety_events(subject_phone, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_safety_severity_time
    ON aia_health_safety_events(severity, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_safety_unreviewed
    ON aia_health_safety_events(severity, created_at DESC)
    WHERE reviewed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_safety_trigger
    ON aia_health_safety_events(trigger_type, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════
-- 3. Triggers de updated_at
-- ═══════════════════════════════════════════════════════════════════

DROP TRIGGER IF EXISTS trg_conv_msg_touch ON aia_health_conversation_messages;
CREATE TRIGGER trg_conv_msg_touch
    BEFORE UPDATE ON aia_health_conversation_messages
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();

DROP TRIGGER IF EXISTS trg_safety_touch ON aia_health_safety_events;
CREATE TRIGGER trg_safety_touch
    BEFORE UPDATE ON aia_health_safety_events
    FOR EACH ROW EXECUTE FUNCTION aia_health_touch_updated_at();


COMMENT ON TABLE aia_health_conversation_messages IS
'Histórico unificado de mensagens cross-canal. Base para janela deslizante, buffer, memória e auditoria.';

COMMENT ON TABLE aia_health_safety_events IS
'Eventos de safety. Acesso restrito a admins + Atente. Separado da memória coletiva (não vai pra RAG).';
