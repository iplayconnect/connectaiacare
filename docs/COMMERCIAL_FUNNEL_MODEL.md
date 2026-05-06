# Commercial Funnel Model — Phase D Comercial

> Build noturno 2026-05-06 → 05-07. Implementa fundação completa do
> fluxo comercial pra Sofia (Whats + Voz + VoIP) capturar leads,
> agendar demos/calls, enviar propostas e fechar venda.

## Estado anterior (gap diagnosticado)

✅ `aia_health_leads` (migration 061) — funil base com workflow
`new→qualified→demo_scheduled→in_demo→proposal_sent→converted|lost`.

✅ Tools antigas: `capture_lead`, `schedule_demo` (placeholder
genérico — só setava status + link estático).

✅ Endpoints `GET/PATCH /api/admin/leads`.

❌ **Faltava** (este PR fecha):
- Tabelas pra demos com data/hora real, calls registradas, propostas
  com valor/plano, timeline cross-table, catálogo de planos
- Tools Sofia pra cobrir o funil inteiro (consulta planos, agenda demo
  com calendário, callback, registra atividade, envia proposta,
  consulta status, atualiza qualificação)
- Endpoints pra UI kanban + agenda
- Cross-channel: tools precisam estar em Sofia VoIP também

## O que foi entregue

### 1. Migration 068 — Schema (5 tabelas novas)

`backend/migrations/068_commercial_funnel.sql`

| Tabela | Função |
|---|---|
| `aia_health_plans` | Catálogo (sku, preço, features, pitch). 4 planos seed: B2C Básico (R$99), B2C Premium (R$249), ILPI Starter, Hospital |
| `aia_health_lead_demos` | Demos agendadas (data/hora, sala, responsável, status, outcome) |
| `aia_health_lead_calls` | Ligações registradas (Sofia VoIP/Voz inbound, comercial outbound, callbacks) |
| `aia_health_lead_proposals` | Propostas enviadas (valor, plano, validade, conversão) |
| `aia_health_lead_activities` | Timeline cross-table — UI detail page renderiza |

Trigger `aia_health_log_lead_status_activity` popula timeline
automaticamente quando lead muda de status.

### 2. Tools comerciais Sofia (8 novas em `sofia_tools.py`)

Todas no mesmo registry (`TOOL_REGISTRY`) que CareSofiaAgent +
CommercialSofiaAgent já consumiam:

| Tool | O que faz |
|---|---|
| `query_plans` | Sofia consulta catálogo (filtra por target_persona) |
| `schedule_demo_with_calendar` | Substitui `schedule_demo` placeholder. Agenda com data/hora real, idempotente por dia |
| `schedule_callback_call` | Lead pediu "me liga depois" → registra em lead_calls |
| `register_lead_activity` | Sofia anota observação no timeline (objeção, sinal positivo, concern) |
| `send_proposal` | Cria proposta + atualiza status. Idempotente por (lead, plano) |
| `get_lead_status` | Sofia consulta lead pelo phone — sabe se é novo, em demo, com proposta |
| `update_lead_qualification` | Sofia atualiza score (0-100) baseado em sinais |
| `capture_lead` | (já existia) — atualizado pra novo schema |

Cada tool tem audit_log + idempotência onde apropriado +
`_message_for_sofia` orientativo (LLM sabe como narrar resultado).

### 3. Endpoints REST (16 novos)

`backend/src/handlers/commercial_funnel_routes.py`

| Endpoint | Função |
|---|---|
| `GET /api/admin/plans` | Lista planos (com filtros) |
| `POST /api/admin/plans` | Cria plano (super_admin) |
| `PATCH /api/admin/plans/<id>` | Edita plano |
| `GET /api/admin/leads/funnel` | Kanban — leads agrupados por status |
| `POST /api/admin/leads` | Cria lead manual (humano) |
| `GET /api/admin/leads/<id>/timeline` | Timeline cross-table |
| `POST /api/admin/leads/<id>/demos` | Agenda demo |
| `PATCH /api/admin/lead-demos/<id>` | Atualiza demo (confirma, completa) |
| `POST /api/admin/leads/<id>/calls` | Registra ligação |
| `POST /api/admin/leads/<id>/proposals` | Cria proposta |
| `PATCH /api/admin/lead-proposals/<id>` | Aceita/rejeita proposta (auto-converte lead) |
| `GET /api/admin/leads/upcoming-demos` | Agenda próximas demos |
| `GET /api/admin/leads/upcoming-callbacks` | Callbacks pendentes |

RBAC: `super_admin | admin_tenant | comercial`.

### 4. Cross-channel (Sofia VoIP + Voz Web)

Mesma estratégia da unificação Phase C v2.x:

**Backend** (1 endpoint interno novo):
- `POST /api/internal/commercial/execute-tool` — whitelist das 8
  tools comerciais. Voice/sofia chama via HTTP.

**voice-call-service** (`services/persistence.py`):
- 8 handlers thin wrappers que delegam pra `_call_commercial_backend()`
- Adicionados ao `_LOCAL_TOOLS` registry
- `_build_tools_for_call` no `grok_call_session.py` agora expõe tools
  comerciais pra personas `comercial | anonymous | admin_tenant |
  super_admin`. Cuidador comum NÃO tem (não é trabalho dele captar lead).

**CommercialSofiaAgent (WhatsApp)**:
- `allowed_tools()` agora inclui as 8 novas
- `COMMERCIAL_TOOLS_SCHEMA` ganhou os 7 schemas novos pra LLM saber
  chamar via tool-use nativo

## Fluxo end-to-end pós-deploy

### Cenário 1 — Lead chega via WhatsApp

1. Phone novo manda msg pra `Connectaiacare`
2. `identity_resolver.resolve()` → anonymous
3. `intent_classifier` → `interesse_servico_b2b`
4. `factory.get_agent_for(anonymous, intent)` → `CommercialSofiaAgent`
5. Sofia cumprimenta, identifica lead, chama:
   - `capture_lead` (gravação imediata)
   - `query_plans(target_persona='ilpi')` se lead é gestor de ILPI
   - `register_lead_activity` pra cada sinal captado
   - `update_lead_qualification` baseado nos sinais
   - Lead aceita demo → `schedule_demo_with_calendar`
   - Time humano confirma + manda link real

### Cenário 2 — Lead liga pra DID Sofia VoIP

1. PJSIP recebe INVITE
2. `inbound_bridge` → `resolve_caller_unified()` (Fase 3 unificação)
3. Phone NÃO bate → `persona='comercial'` (ou anonymous)
4. GrokCallSession spawn com tools comerciais habilitadas
5. Sofia atende: cumprimenta, identifica via voz, chama:
   - `get_lead_status(phone)` (descobre se já tem lead)
   - Se novo: `capture_lead` + qualifica
   - Lead pede info → `query_plans`
   - Lead aceita: `schedule_demo_with_calendar`
   - Cruza canais: cuidador da família mandou WhatsApp ontem,
     active_context tem o histórico — Sofia VoIP referencia

### Cenário 3 — Time comercial humano opera funil

1. Acessa `/comercial/funil` (frontend a fazer próxima sessão)
2. Vê kanban com leads agrupados por status
3. Clica num lead → detail page com timeline (`/api/admin/leads/<id>/timeline`)
4. Pode:
   - Adicionar nota manual
   - Agendar demo manualmente (`POST /api/admin/leads/<id>/demos`)
   - Registrar call que fez (`POST /api/admin/leads/<id>/calls`)
   - Enviar proposta (`POST /api/admin/leads/<id>/proposals`)
   - Aceitar proposta (`PATCH /api/admin/lead-proposals/<id>` status=accepted) → lead vira `converted` automático

## Próximos passos (próximas sessões)

### A — Frontend (1-2 sessões)

Criar páginas:
- `/comercial/funil` — kanban (drag-and-drop entre colunas, atualiza status via PATCH)
- `/comercial/leads/<id>` — detail com timeline
- `/comercial/agenda` — calendário com upcoming-demos + upcoming-callbacks
- `/comercial/planos` — CRUD do catálogo (super_admin)

Stack: Next.js + Tailwind + shadcn-ui (já em uso) + react-beautiful-dnd
ou similar pro kanban.

### B — Integração Google Calendar (1 sessão)

Hoje `schedule_demo_with_calendar` cria placeholder no DB. Próximo:
- OAuth Google do super_admin
- Tool cria evento real + invite pro lead via email
- Webhook recebe confirmações/cancelamentos do Google
- Lembrete automático via WhatsApp 1h antes

### C — Geração de proposta PDF (1 sessão)

Hoje `send_proposal` cria placeholder. Próximo:
- Template HTML/CSS pra proposta
- Geração via WeasyPrint ou similar
- Hospedagem em S3/Cloudflare R2 com link público
- Track abertura via pixel (incrementa `viewed_at`)
- Email automático com PDF anexo

### D — Lead routing inteligente (1 sessão)

Quando lead converge, criar tenant novo automaticamente:
- Migration `069_lead_to_tenant_conversion.sql`
- Endpoint `POST /api/admin/lead-proposals/<id>/convert` que:
  - Cria tenant em `aia_health_tenants`
  - Cria admin_tenant user a partir do lead
  - Migra responsibilities (handoff, leads ativos)
  - Notifica time de onboarding

## Risco

**Baixo**:
- Migration 068 puramente aditiva (5 tabelas novas, FKs CASCADE pra
  cleanup limpo)
- Tools comerciais novas não substituem antigas (capture_lead/
  schedule_demo continuam funcionando — placeholder agora coexiste
  com versão real)
- Endpoints novos sem impacto em código existente
- Voice handlers fail-safe (HTTP timeout 8s + _message_for_sofia
  orientativo se falha)

**Médio**:
- LLM Sofia VoIP pode não saber escolher entre `schedule_demo`
  (placeholder) e `schedule_demo_with_calendar` (real). Mitigado via
  `[DEPRECATED]` no description da antiga e prompt instructions
  claras. Removeremos a placeholder após 1 semana de validação.
- Idempotência por (lead, dia) pode bloquear cenários legítimos
  (lead remarca pra mesmo dia em horário diferente). Aceitar pra
  primeiro release; revisar se aparecer.

## Risco LGPD

- `aia_health_lead_calls.recording_url` + `recording_consent` —
  recordings só com consent explícito do lead
- `aia_health_lead_proposals.proposal_html` pode conter dados
  pessoais. Retention: ~6 meses (legal pra disputa contratual)
- `aia_health_lead_activities.details` é jsonb livre — review periódico
  pra evitar PII em campos não estruturados
