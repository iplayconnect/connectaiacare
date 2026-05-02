# Briefing — Módulo Marketing & Social na ConnectaIACare

> Documento de briefing pra implementação futura. **Não codar a partir
> deste doc sem antes produzir `MARKETING_SOCIAL_ARCHITECTURE.md`** (ver
> §"O que preciso de você").
>
> Status: **planejado, não implementado**. Atualizado: 2026-05-01.

## Antes de qualquer código, leia

1. `docs/SUPER_SOFIA_PLATFORM_ARCHITECTURE.md` — arquitetura escalável
2. `docs/PHASE_A_OPERATIONAL.md` até `PHASE_D_OPERATIONAL.md` — estado prod
3. `docs/PLANNING_SUPER_ADMIN_PANEL.md` — framework Sofia institucional
4. Memory `~/.claude/projects/.../memory/project_mcp_foundation.md` —
   MCP server padrão (Google Workspace ativo desde abril/26)

## Visão geral

Módulo unificado **Marketing & Social** dentro da plataforma
ConnectaIACare. Cobre 3 frentes em ordem de prioridade:

### BLOCO 1 · Posts orgânicos (PRIORIDADE ALTA)
Geração e publicação de conteúdo no **Instagram** (principal) e
**Facebook** (secundário). Pillars editoriais → Claude gera copy +
prompt de imagem → provider de imagem renderiza → aprovação humana
obrigatória → publica via Meta Graph API.

### BLOCO 2 · Inbound social (PRIORIDADE ALTA, junto com Bloco 1)
Comentários e DMs do FB/IG → Sofia institucional (sub-agent
`social_media`) responde dentro de policy + escala humano quando
preciso. Reusa Super Sofia orchestrator.

### BLOCO 3 · Meta Ads via MCP (SEGUNDO MOMENTO)
MCP server `mcp-meta-ads` integrado à Sofia. Alexandre conversa
naturalmente: "lista campanhas / pausa as com CTR baixo / cria
campanha B2B captação". Mesma infra MCP do Google Workspace.
Tools com guardrail de safety pra ações que movem dinheiro.

## Princípios não-negociáveis

- **Conta única institucional** (não multi-tenant) — é a marca
  ConnectaIACare. Provavelmente tenant técnico
  `connectaiacare_marketing` (ver decisão #2 abaixo).
- **Aprovação humana 100% sempre** nas primeiras 4 semanas
  (saúde é sensível, LGPD, Meta App Review).
- **Política comercial fixa**: NUNCA mencionar fornecedores de
  IA (Claude, Anthropic, etc.) em material exposto ao público.
  Internamente sem restrição.
- **Audit-trail-driven**: toda publicação, resposta, ação Meta
  Ads → `aia_health_audit_log` (já existe, append-only).
- **Cost tracking dia 1**: Claude tokens, provider de imagem,
  Meta API calls (mesmo que de graça) — `aia_health_llm_cost_log`.
- **Idempotência**: mesma geração não publica 2x; mesmo comment
  não responde 2x.
- **Fail-soft**: Meta caiu → enfileira, não perde.
- **Reusa Sofia institucional WhatsApp**: aprovações pendentes
  → Sofia avisa Alexandre via padrão validado em
  PLANNING_SUPER_ADMIN_PANEL (5551996161700).

## Reutilizar o que JÁ TEMOS em produção

| Já existe | Como aproveitar |
|---|---|
| `aia_health_audit_log` (Phase A) | Toda publicação + resposta + Meta Ads call vira audit |
| `aia_health_llm_cost_log` (Phase A) | Claude tokens já trackeados; adicionar provider de imagem + Meta API |
| `aia_health_tenant_policies` (Phase A) | Configurar policy do tenant marketing |
| `redis_client` + `event_bus` (Phase B) | Streams `social:publish_queue`, `social:inbound_comment`, `social:inbound_dm`, `meta_ads:operations` |
| `super_sofia_orchestrator` + factory (Phase C) | Add `SocialMediaSofiaAgent` (sub-agent) + branch source=fb_dm/ig_dm/fb_comment/ig_comment |
| `aia_health_human_handoff_queue` (Phase C) | Comentários/DMs que escalam pra humano vão pra mesma fila |
| `audit_log_writer` + redaction (Phase A) | Redação de PII em logs de DM (FB user_id é PII) |
| **MCP foundation** (abril/26, Google Workspace ativo) | `mcp-meta-ads` segue mesmo padrão (FastMCP + streamable-http porta 8091) |
| Framework Sofia institucional (já validado com Henrique/Corpus) | Aprovações pendentes + alertas Meta Ads → Sofia → Alexandre Zap |
| Frontend `/admin/system/operations/*` (Phase D) | Padrão pra páginas novas: `/marketing/posts`, `/marketing/inbox`, `/marketing/ads` |

## Schema novo (migration ~062 unificada)

```sql
-- ─── Bloco 1: Posts orgânicos ───
aia_health_social_credentials
  (page_id PK, platform: fb|ig, page_name, page_username,
   business_account_id, ig_business_account_id,
   access_token_encrypted, token_expires_at, token_refreshed_at,
   scopes text[], created_at)

aia_health_social_content_pillars
  (id, name, description, weight INT, last_used_at,
   tone_guidelines TEXT, hashtag_preset TEXT[], example_posts JSONB)

aia_health_social_posts
  (id PK, pillar_id FK, status: draft|pending_review|approved|
                                scheduled|published|rejected|failed,
   platform_targets TEXT[],  -- ['ig'] | ['fb'] | ['ig','fb']
   copy_text, image_url, image_prompt, image_provider,
   hashtags TEXT[], call_to_action,
   approved_by UUID FK, approved_at, rejection_reason,
   scheduled_for, published_at,
   meta_post_ids JSONB,  -- {'ig': 'post_id', 'fb': 'post_id'}
   meta_response JSONB, meta_error TEXT,
   metrics_jsonb JSONB,  -- impressions, reach, engagement, saves
   metrics_updated_at, trace_id, created_at, updated_at)

-- ─── Bloco 2: Inbound social ───
aia_health_social_inbound
  (id PK, platform: fb|ig|fb_dm|ig_dm,
   meta_object_id UNIQUE, post_id_target FK,  -- comment vinculado a post
   parent_comment_id FK,  -- replies
   author_meta_id, author_name, author_username, author_profile_pic_url,
   text_content, sentiment: positive|neutral|negative|spam,
   intent: question|complaint|praise|sales_interest|spam|other,
   sofia_response_id FK, handoff_id FK,
   status: pending|sofia_responded|claimed_human|resolved|silenced,
   trace_id, received_at, resolved_at)

aia_health_social_responses
  (id PK, inbound_id FK, response_text, response_meta_id,
   sub_agent, llm_call_id, sent_at, audit_id)

-- ─── Bloco 3: Meta Ads (preparação Phase 3) ───
aia_health_meta_ads_credentials
  (tenant_id PK FK, business_account_id, ad_account_id,
   system_user_token_encrypted,  -- não expira (Business verified)
   scopes TEXT[], created_at, updated_at)

aia_health_meta_ads_audit
  (id PK, tenant_id, trace_id, action, actor: sofia|user|system,
   actor_user_id FK, target_type: campaign|adset|ad|audience|budget,
   target_meta_id, before_jsonb, after_jsonb, mcp_call_id,
   safety_guardrail_decision, llm_cost_usd, created_at)
```

## Componentes novos

### Bloco 1 · Posts orgânicos

**Service** `meta_graph_adapter`:
- Wrapper Meta Graph API (Python `requests` direto, sem SDK pesado)
- `publish_ig_feed(image_url, caption, hashtags, mention[])`
- `publish_fb_feed(image_url, caption, link?)`
- `schedule_post(post_id, when)` (Meta nativo)
- `refresh_token()` (cron: faz rotation 7d antes expirar)
- Rate limit-aware (200 calls/hora/app)

**Service** `content_generator`:
- Pipeline: pillar → planejar (Sonnet) → copy (Sonnet) →
  image_prompt (Sonnet) → image (provider escolhido) → assemble
- Modo "lote semanal": 1 trigger admin gera N posts da semana
- Reusa `LlmRouter` task `sofia_chat_response`; nova task
  `social_image_prompt` (Haiku, frio + estruturado)

**Worker** `social_publisher_worker` (consume `social:publish_queue`):
- Pega post `approved` + `scheduled_for` no horário
- Chama meta_graph_adapter
- Persiste `meta_post_ids` + status=`published`
- Falha → retry com backoff → DLQ → alerta Alexandre via Sofia Zap

### Bloco 2 · Inbound social

**Webhook** `POST /webhook/meta/<page_id>`:
- Meta dispara em comentário, DM, mention
- Idempotência via Redis SETNX
- Dispatch pra `social:inbound_comment` ou `social:inbound_dm`

**Worker** `social_inbound_worker`:
- Consume → SuperSofiaOrchestrator com sub-agent `social_media`
- `SocialMediaSofiaAgent` herda BaseSofiaAgent:
  - System prompt com policy específica (NUNCA conselho médico,
    sempre redireciona pra Central 24h ou link de cadastro)
  - Tools: `tag_for_review` (nova), `escalate_to_human_whatsapp`
    (já existe), `respond_publicly` (nova — gera resposta no
    próprio comment), `send_dm` (nova)
  - Anti-hallucination guardrail aplicado FORTE (saúde pública)

### Bloco 3 · Meta Ads MCP (Phase futura, mesma arquitetura)

**Container Docker** `mcp-meta-ads` (porta 8091, FastMCP):
- Mesma estrutura do `mcp-google-workspace`
- 10 tools (4 read-only + 6 mutação com guardrail)
- System User token (Business Verified, sem expiração)
- Audit em `aia_health_meta_ads_audit`

**MCPManager** já tem suporte (não precisa alterar).
**Tenant config** adiciona seção `mcp_servers.meta_ads` em
`tenants/connectaiacare_demo.yaml` (ou marketing).

## Frontend novo (Phase D-style padrão)

| Página | Função |
|---|---|
| `/admin/system/operations/marketing/calendar` | Kanban draft→pending→approved→scheduled→published com edição inline + botão "gerar lote semanal" |
| `/admin/system/operations/marketing/inbox` | Comentários + DMs pendentes; ações claim/respond/escalate/silence |
| `/admin/system/operations/marketing/credentials` | Conectar páginas FB/IG via OAuth |
| `/admin/system/operations/marketing/pillars` | CRUD pillars editoriais (admin define tom/exemplos) |
| `/admin/system/operations/marketing/ads` (Phase 3) | Campanhas Meta Ads + queue aprovação + insights |

Sidebar grupo "Sistema · Cross-tenant" ganha 1 entry agrupado:
**Marketing & Social** (sub-itens dropdown).

## Decisões abertas (Alexandre confirma antes do código)

1. **Provider de imagem** (essencial pra Bloco 1):
   - **Replicate Flux-schnell** (recomendação default) — $0.003/img,
     license OK, qualidade alta, latência ~5s.
   - Stability AI direto (mais barato $0.001 mas qualidade inferior)
   - Imagen 3 Google ($0.04/img, qualidade premium)
   - Midjourney via proxy não-oficial (ToS arriscado)

2. **Tenant**:
   - **Recomendação default**: criar `connectaiacare_marketing`
     dedicado (limpa métricas, separa permissions, permite
     branding diferente).
   - Alternativa: reusar `connectaiacare_demo`.

3. **Pilares editoriais iniciais** (Bloco 1) — sugestão default:
   - Cuidado e bem-estar do idoso (40% — educativo)
   - Tecnologia em saúde / IA Sofia (20% — diferencial)
   - Casos reais e depoimentos (20% — prova social, com consent
     LGPD)
   - Bastidores e equipe (10% — humanização)
   - Datas comemorativas / sazonais (10%)
   Ajustar conforme estratégia do Alexandre.

4. **Volume e cadência Bloco 1**:
   - **Default**: 4 posts/semana Instagram + 2 Facebook.
   - Alexandre dispara "gerar lote da semana" 1x/semana, aprova
     em batch, sistema agenda automaticamente.

5. **Aprovação humana**:
   - **100% obrigatória 4 semanas**, depois Alexandre decide
     soltar `respond_publicly` pra comments classificados como
     `praise|question_simple` com confidence>0.85.

6. **Stories/Reels Bloco 1**: começar **só Feed**. Stories
   (efêmero) e Reels (vídeo) Phase 2.

7. **Meta App Review**: Alexandre roda em paralelo. Code pronto
   pra rodar quando aprovar (1-3 semanas Meta).

8. **Build vs reuse MCP Meta Ads** (Bloco 3):
   - Pesquisar GitHub se existe `mcp-meta-ads` público de
     qualidade.
   - **Recomendação default**: construir próprio em
     Python+FastMCP (consistência com mcp-google-workspace,
     audit nosso, padrões da plataforma).

9. **Notificações proativas Sofia → Alexandre**:
   - Posts pendentes >24h sem aprovação → lembrete Zap.
   - Comments classificados como `complaint` → alerta imediato.
   - Engagement de post explodiu (>10x média) → notifica.
   - Meta Ads CPA fora do target (Bloco 3) → notifica.

10. **DM Instagram tem Política Meta restritiva** — só pode
    responder dentro de 7 dias da última msg do usuário (Standard
    Messaging Window). Sofia precisa respeitar. Default:
    **mensagem padrão "passamos pra atendente humano"** quando
    fora da janela; humano via Central 24h responde.

## Plano de execução · 5 fases

| Phase | Bloco | Escopo | Tempo |
|---|---|---|---|
| **1** | 1 | Migration unificada + meta_graph_adapter (publish only) + content_generator stub + frontend calendar manual | 4 dias |
| **2** | 1 | content_generator full pipeline (pillar→copy→image) + provider de imagem + worker publisher + token rotation cron | 3 dias |
| **3** | 2 | Webhook Meta inbound + social_inbound_worker + SocialMediaSofiaAgent + frontend inbox | 4 dias |
| **4** | 1+2 | Notificações proativas Sofia (posts pendentes, complaints, engagement spikes) | 1-2 dias |
| **5** | 3 | mcp-meta-ads container + 10 tools + frontend ads + guardrail integration | 5-7 dias |

**Total**: ~3 semanas spread, mas Alexandre prioriza Bloco 1+2.
Phase 5 só depois de Phase 1-4 validadas em produção real.

## Critérios de aceite Phase 1+2 (Bloco 1 funcional)

- [ ] OAuth Meta funcionando, tokens criptografados em DB
- [ ] Pilares CRUD operável em admin
- [ ] "Gerar lote semanal" produz N posts em status `pending_review`
- [ ] Calendar kanban: aprovar → status `scheduled` → worker
      publica no horário
- [ ] Audit log registra cada step
- [ ] Cost tracking captura tokens Claude + custo image provider
- [ ] Smoke test: gerar 1 post → aprovar → publicar real no
      Instagram da empresa → verificar no app

## Critérios de aceite Phase 3 (Bloco 2 funcional)

- [ ] Webhook Meta recebe comentários e DMs
- [ ] SocialMediaSofiaAgent responde dentro de policy
- [ ] Política "nunca conselho médico" testada (10 prompts adversariais)
- [ ] Inbox admin mostra pendentes + ações funcionam
- [ ] Escalate pra Central 24h via Sofia institucional funciona

## Critérios de aceite Phase 5 (Bloco 3 — Meta Ads via MCP)

- [ ] Container mcp-meta-ads ativo, MCPManager descobre tools
- [ ] Sofia chat: "lista minhas campanhas" → resposta com dados
      reais
- [ ] Tool `create_campaign` passa por guardrail → queue revisão
      → Alexandre aprova → executa
- [ ] Audit completo de toda mutação Meta Ads
- [ ] LLM cost log captura tool decisions

## O que preciso de você (próxima sessão dedicada)

1. **Audit do estado atual**: lê os 5 docs operacionais e
   `project_mcp_foundation` memory note.
2. **Pesquisar** `mcp-meta-ads` público (npm/pip/github
   awesome-mcp-servers) pra Phase 5.
3. **Antes de codar**: produzir
   `docs/MARKETING_SOCIAL_ARCHITECTURE.md` com:
   - Esquema final integrado das 6 tabelas
   - Fluxograma Bloco 1 (geração → aprovação → publicação)
   - Fluxograma Bloco 2 (webhook → Sofia → resposta/escalate)
   - Fluxograma Bloco 3 (Sofia chat → MCP → Meta Ads)
   - Análise das 10 decisões abertas com recomendação default +
     trade-off.
4. **Esperar confirmação Alexandre** antes da Phase 1.

Não tem prazo. Quero arquitetura sólida igual o resto da
plataforma. Commits incrementais. Mantém estilo dos PRs #72-78.
