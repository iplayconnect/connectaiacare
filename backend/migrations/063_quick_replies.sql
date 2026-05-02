-- ====================================================================
-- 063_quick_replies.sql
--
-- Phase A — Handoff Chat
-- Respostas rápidas pré-aprovadas pra operador humano 24/7.
--
-- Operador atendendo handoff via /admin/system/operations/handoff/<id>/chat
-- precisa responder rápido em situações comuns (emergência, medicação,
-- rotina, fechamento). Esta tabela armazena templates por tenant que
-- vão pra sidebar do chat.
--
-- Idempotente.
-- ====================================================================

CREATE TABLE IF NOT EXISTS aia_health_quick_replies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,

    -- Categoria livre (texto), mas seedada com 4 categorias clínicas:
    -- 'emergencia', 'medicacao', 'rotina', 'fechamento'.
    category TEXT NOT NULL,

    -- Slug curto pra exibição (ex: 'samu_acionado'). Único por tenant.
    shortcut TEXT NOT NULL,

    -- Título legível (ex: 'SAMU acionado').
    label TEXT NOT NULL,

    -- Texto completo da resposta. Suporta placeholder {nome} (substituído
    -- no client com nome do lead).
    content TEXT NOT NULL,

    -- Hotkey opcional (ex: 'Ctrl+1'). NULL = sem atalho fixo (usa Ctrl+N
    -- baseado em ordem de uso).
    hotkey TEXT,

    created_by_user_id UUID REFERENCES aia_health_users(id) ON DELETE SET NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    usage_count INT NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_quick_replies_tenant_shortcut
    ON aia_health_quick_replies(tenant_id, shortcut)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_quick_replies_tenant_active_category
    ON aia_health_quick_replies(tenant_id, category)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_quick_replies_tenant_usage
    ON aia_health_quick_replies(tenant_id, usage_count DESC)
    WHERE active = TRUE;

-- Reusa function aia_health_set_updated_at() criada no 001_initial_schema.sql.
DROP TRIGGER IF EXISTS trg_quick_replies_updated_at ON aia_health_quick_replies;
CREATE TRIGGER trg_quick_replies_updated_at
    BEFORE UPDATE ON aia_health_quick_replies
    FOR EACH ROW
    EXECUTE FUNCTION aia_health_set_updated_at();

-- ── Seeds iniciais (tenant connectaiacare_demo) ─────────────────────
-- Conjunto inicial enxuto pra demo. Henrique Bordin (referência clínica)
-- deve revisar antes do piloto real — especialmente as de emergência.
INSERT INTO aia_health_quick_replies
    (tenant_id, category, shortcut, label, content)
VALUES
    -- Emergência (P1)
    ('connectaiacare_demo', 'emergencia', 'samu_acionado',
     'SAMU acionado',
     'SAMU acionado. Mantenha o(a) idoso(a) deitado(a) de lado, sem oferecer água ou comida. Estou na escuta — me avise qualquer mudança.'),
    ('connectaiacare_demo', 'emergencia', 'enfermagem_chegando',
     'Enfermagem a caminho',
     'Já estou acionando a enfermagem agora. Em até 10 minutos chegamos. Se tiver alguma piora, me avise imediatamente.'),
    ('connectaiacare_demo', 'emergencia', 'medico_plantao',
     'Médico de plantão',
     'Estou ligando pro médico de plantão agora. Pode descrever em uma frase o que está acontecendo? Isso acelera a triagem.'),

    -- Medicação (P2)
    ('connectaiacare_demo', 'medicacao', 'checar_dose_farma',
     'Checar dose com farmacêutico',
     'Vou checar essa dose com o farmacêutico de plantão. Te confirmo em até 10 minutos. Por enquanto, não administre.'),
    ('connectaiacare_demo', 'medicacao', 'foto_bula',
     'Pedir foto da bula',
     'Pode me mandar uma foto da caixa ou da bula? Quero confirmar o nome exato e a concentração antes de orientar.'),
    ('connectaiacare_demo', 'medicacao', 'beers_ok_validar',
     'Posologia parece ok, validar',
     'Pela primeira leitura a posologia parece adequada, mas vou validar com o protocolo (Beers/STOPP) pra ter certeza. Já te volto.'),

    -- Rotina (P3)
    ('connectaiacare_demo', 'rotina', 'registrado_prontuario',
     'Registrado no prontuário',
     'Recebido. Vou registrar no prontuário do(a) idoso(a). Algo mais a reportar nesse turno?'),
    ('connectaiacare_demo', 'rotina', 'agradecimento_atualizacao',
     'Agradecimento + nova pergunta',
     'Obrigada pela atualização. Tudo certo do lado de vocês? Algo mais que eu deva saber?'),
    ('connectaiacare_demo', 'rotina', 'qualquer_urgencia_chama',
     'Plantão silencioso',
     'Boa noite! Qualquer urgência me chama por aqui mesmo. Estou de plantão até amanhã de manhã.'),

    -- Fechamento
    ('connectaiacare_demo', 'fechamento', 'caso_resolvido',
     'Caso resolvido',
     'Vou marcar esse atendimento como resolvido. Bom dia/tarde/noite — qualquer coisa, é só me chamar de novo.'),
    ('connectaiacare_demo', 'fechamento', 'transferido_especialista',
     'Transferido para especialista',
     'Esse caso vai pra um especialista da nossa equipe. Em até 1h alguém entra em contato com você. Obrigada pela paciência.')
ON CONFLICT DO NOTHING;
