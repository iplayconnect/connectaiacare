# Próxima sessão · Handoff Chat Fase A — port componentes CRM ConnectaIA

> Esta doc é instrução completa pra atacar o port dos componentes de chat
> do CRM ConnectaIA pra ConnectaIACare. Baseline: PR #91 já mergeado em
> 2026-05-02 entregou versão 1.0 do chat (esqueleto funcional com polling
> + bubbles simples + composer textarea). Fase A é upgrade UX/feature.

---

## TL;DR

Atualmente `/admin/system/operations/handoff/[id]/chat/page.tsx`:
- Bubble simples (apenas role + content)
- Textarea simples como composer
- Polling 3s
- Modal "Resolver" funcional

Falta (Fase A):
- **MessageBubble rico** (edit/reply/audio playback do CRM ConnectaIA)
- **QuickRepliesSidebar** (respostas pré-aprovadas — crítico pra 24/7)
- **FinalizationModal mais polido**
- **ContextPanel** sidebar com info do lead/snapshot Sofia

---

## Inventário do que existe no CRM ConnectaIA

Caminho dos componentes referência (worktree `awesome-einstein` do AssistenteIA):
```
/Users/macnovo/Library/Mobile Documents/com~apple~CloudDocs/Python/AssistenteIA/.claude/worktrees/awesome-einstein/frontend/src/components/chat/
├── ChatInput.tsx              (507 linhas) — composer rico
├── MessageBubble.tsx          (438 linhas) — bubble com edit/reply/audio
├── QuickRepliesSidebar.tsx    (449 linhas) — respostas pré-definidas
├── ContextPanel.tsx           (182 linhas) — sidebar info lead
├── LeadCardMini.tsx           (135 linhas) — card resumido
├── FinalizationModal.tsx      (116 linhas) — modal terminar atendimento
└── QuickRepliesDropdown.tsx   (56 linhas)  — dropdown rápido
```

**Total: 1883 linhas.** Não copiar verbatim — port adaptado.

---

## Diferenças entre os 2 projetos

| Aspecto | ConnectaIA (CRM) | ConnectaIACare (este) |
|---|---|---|
| API client | `apiClient.getLeadsInbox()` | `api.request("/api/...")` |
| Auth context | `@/context/AuthContext` | `@/context/auth-context` |
| Type primário | `Lead` (id numeric, campaign) | `Handoff` (UUID, P1/P2/P3) |
| Backend endpoints | `/api/leads/...` | `/api/admin/handoff/...` |
| Status flow | leads: `new`→`assigned`→`closed` | handoff: `pending`→`claimed`→`resolved` |
| Concurrency control | `assign_to_me` + `assigned_to_user_id` | `claim` + `claimed_by_user_id` |
| Quick replies storage | tabela `bbmd_quick_replies` no CRM | **CRIAR** tabela `aia_health_quick_replies` |

---

## Plano de port em 4 PRs (~30min cada)

### PR 1 — `MessageBubble` adaptado (~30min)

**Arquivo destino:** `frontend/src/components/handoff/MessageBubble.tsx`

**Features pra portar:**
- Bubble com avatar + role (Sofia/Humano/Lead/Tool)
- Audio playback (ícone Mic + Play/Pause + slider de progresso)
- Edit msg do operador (Pencil icon → abre inline edit)
- Reply (Reply icon → quoted msg acima do composer)
- Delete msg (Trash icon → soft delete via metadata)
- Status: enviando (Loader2), enviado (Check), entregue (CheckCheck)

**Mudanças do CRM original:**
- Tipo `Message` → adaptar pra nosso `LiveMessage` (tem actor='human'/'sofia')
- Audio URL: hoje não persistimos audios. Skip audio playback no Fase A
  (Fase B adiciona quando tivermos áudio no fluxo)
- Edit/delete: PRECISA endpoint backend novo
  - `PATCH /api/admin/handoff/<id>/messages/<msg_id>` (edita)
  - `DELETE /api/admin/handoff/<id>/messages/<msg_id>` (soft delete)
  - Validações: só claimed_by_user_id pode editar suas msgs; só
    msgs com `actor=human`; janela de 5min após envio (depois fica
    imutável pra audit)

**Validação:**
- Edit: operador erra digitação → click Pencil → corrige → Save → bubble atualiza
- Reply: operador click Reply → bubble alvo aparece quoted no composer
- Delete: operador click Trash → confirma → bubble vira "[Mensagem apagada]"

### PR 2 — `QuickRepliesSidebar` adaptado (~45min)

**Crítico pra operação 24/7.** Atendentes precisam de respostas pré-aprovadas
pra responder rápido em situações comuns.

**Arquivo destino:** `frontend/src/components/handoff/QuickRepliesSidebar.tsx`

**Backend novo necessário:**
1. Migration `063_quick_replies.sql`:
   ```sql
   CREATE TABLE aia_health_quick_replies (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       tenant_id TEXT NOT NULL,
       category TEXT NOT NULL,  -- 'emergencia', 'medicacao', 'rotina', 'fechamento'
       label TEXT NOT NULL,     -- "SAMU acionado"
       content TEXT NOT NULL,   -- texto completo da resposta
       hotkey TEXT,             -- "Ctrl+1", opcional
       created_by_user_id UUID REFERENCES aia_health_users(id),
       active BOOLEAN NOT NULL DEFAULT TRUE,
       usage_count INT NOT NULL DEFAULT 0,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   CREATE INDEX idx_quick_replies_tenant_active
       ON aia_health_quick_replies(tenant_id, category)
       WHERE active = TRUE;
   ```

2. Seeds iniciais (categorias clínicas pra ConnectaIACare):
   - **emergencia**: "SAMU acionado, mantenha o(a) idoso(a) deitado, chego em 5min", "Já estou chamando enfermagem agora", "Ligando pro médico de plantão"
   - **medicacao**: "Vou checar dose com farmacêutico, te confirmo em 10min", "Pode me mandar foto da bula?", "Posologia parece ok pelo Beers, mas vou validar"
   - **rotina**: "Recebido. Vou registrar no prontuário", "Obrigado pela atualização. Algo mais a reportar?", "Boa noite, qualquer urgência me chama"
   - **fechamento**: "Vou marcar como resolvido. Bom dia/tarde/noite", "Caso encerrado. Se precisar, é só chamar"

3. Endpoints novos:
   - `GET /api/admin/quick-replies?category=emergencia`
   - `POST /api/admin/quick-replies` (admin cria)
   - `PUT /api/admin/quick-replies/<id>` (admin edita)
   - `DELETE /api/admin/quick-replies/<id>` (admin soft delete via active=false)
   - `POST /api/admin/quick-replies/<id>/use` (track usage_count++)

**Frontend:**
- Sidebar collapsible no chat (right side)
- Tabs por categoria (Emergência, Medicação, Rotina, Fechamento)
- Click numa quick reply → injeta no composer (não envia direto, deixa
  operador customizar antes de enviar)
- Hotkeys: Ctrl+1..Ctrl+9 pra top 9 mais usadas
- Badge "★" nas top 5 mais usadas (via usage_count)

**Validação:**
- Operador click "SAMU acionado" → texto vai pro composer → ele edita
  detalhe (ex: adiciona "ele está consciente") → envia
- Hotkey Ctrl+3 → quick reply 3 vai pro composer
- Sidebar collapse pra ver só chat em telas menores

### PR 3 — `ContextPanel` sidebar (~30min)

**Arquivo destino:** `frontend/src/components/handoff/ContextPanel.tsx`

**Conteúdo do panel (left side):**
- Card lead: phone, primeiro contato, total de turnos com Sofia
- Card snapshot Sofia (última msg, dados extraídos do CSM se houver)
- Card timing: criado há X, claimed há Y, SLA target Z, breach prediction
- Card capabilities relevantes: lista whitelist filtrada pelo intent
  detectado (ex: se intent=emergencia → mostra "atendimento humano 24h"
  como destacada)

**Backend reuso:**
- `GET /api/admin/handoff/<id>` (já existe, retorna handoff completo)
- `GET /api/admin/handoff/<id>/context` **NOVO**: agrega dados do
  CSM `aia_health_conversation_state` + sofia_user_memory + capabilities
  + estatísticas conversa.

**Layout final 3 colunas em desktop:**
```
┌──────────────┬──────────────────┬─────────────────┐
│ ContextPanel │ Chat (mensagens) │ QuickReplies    │
│ (lead info)  │ + composer       │ Sidebar         │
│              │                  │                 │
│ lg: 280px    │ flex-1           │ lg: 320px       │
└──────────────┴──────────────────┴─────────────────┘
```

Mobile/tablet: panels viram bottom sheets / dropdowns.

### PR 4 — `FinalizationModal` polido (~15min)

**Arquivo destino:** `frontend/src/components/handoff/FinalizationModal.tsx`

**Features extras vs nosso modal atual:**
- Categorias de desfecho (radio): `resolved_by_phone`, `escalated_to_specialist`,
  `lead_lost`, `closed_by_lead`, `system_error`, `other`
- Tags multi-select (issues comuns): `medicacao_alterada`, `urgencia_real`,
  `falso_positivo`, `paciente_internado`, `familia_orientada`
- Outcome rating (1-5 estrelas) — operator self-eval pra coaching
- Preview da próxima ação automatizada:
  - Se `resolved_by_phone` → Sofia volta a atender
  - Se `escalated_to_specialist` → cria followup_schedule
  - Se `lead_lost` → arquiva sem follow-up

**Migration nova:**
```sql
ALTER TABLE aia_health_human_handoff_queue
    ADD COLUMN IF NOT EXISTS outcome_category TEXT,
    ADD COLUMN IF NOT EXISTS outcome_tags TEXT[],
    ADD COLUMN IF NOT EXISTS outcome_rating INT;
```

---

## Roadmap após Fase A

### Fase B (sessão dedicada de operação 24/7)

- WebSocket real-time (substitui polling 3s) — Socket.IO já tem no projeto
- Inbox dashboard centralizado: lista de handoffs ativos + atribuição
  manual a operadores específicos
- Multi-operador transfer: operador-A passa pra operador-B sem perder
  contexto
- Notificações cross-tab: operador em outra aba do navegador recebe
  badge "novo handoff P1!" + som
- SLA timer visual: contador regressivo no header, vermelho se SLA
  breach predicted < 2min

### Fase C (operação enterprise)

- Métricas operador: avg handle time, satisfaction (lead pode rate
  via emoji após resolved), SLA compliance %
- Coaching: super_admin revisa conversas claimed por operador, dá
  feedback inline em msgs específicas
- Templates dinâmicos: quick replies com variáveis (`{nome_lead}`,
  `{idade_idoso}`) preenchidas automaticamente do CSM
- Voice handoff: operador click "Ligar" → dispara Sofia Voz pro
  número do lead

---

## Pré-requisitos antes de iniciar Fase A

1. **PR #91 mergeado** ✅ (feito 2026-05-02)
2. **E2E T2 validado pelo user** (passos 1-6 da sessão 2026-05-02)
3. **bbmd-v6 restaurado nos seeds** ✅ (a fazer antes de fechar sessão)
4. Inventário §3.1 do CLAUDE.md atualizado ✅
5. Decidir prioridade dos 4 PRs (A1-A4) — recomendo:
   - **A2 primeiro** (QuickRepliesSidebar) — operação 24/7 não é viável sem
   - **A1 segundo** (MessageBubble rico) — UX qualitativa
   - **A3 terceiro** (ContextPanel) — produtividade
   - **A4 quarto** (FinalizationModal) — analytics/coaching

---

## Comandos úteis pra retomar

```bash
# Worktree
cd "/Users/macnovo/Library/Mobile Documents/com~apple~CloudDocs/Python/ConnectaIACare/.claude/worktrees/auth-impl"
git fetch origin main && git stash && git checkout -b feat/handoff-fase-a-quickreplies origin/main && git stash pop

# Ver estado atual handoff
ssh root@72.60.242.245 "docker compose -f /root/connectaiacare/docker-compose.yml exec -T postgres psql -U postgres -d connectaiacare -c \"SELECT id::text, phone, status, priority FROM aia_health_human_handoff_queue ORDER BY created_at DESC LIMIT 10;\""

# Após cada PR mergeado:
ssh root@72.60.242.245 "cd /root/connectaiacare && bash scripts/deploy.sh"

# Testar quick reply (após PR A2):
curl https://demo.connectaia.com.br/api/admin/quick-replies?category=emergencia \
  -H "Authorization: Bearer <JWT>"
```

---

## Riscos / pontos de atenção

1. **Quick replies precisam de revisão clínica antes de seed:**
   Henrique Bordin (referência clínica do time) deve revisar a lista de
   respostas pré-aprovadas antes de seed. Especialmente as de emergência.

2. **Audit trail rigoroso:** TODA edição/delete de msg pelo operador
   precisa de audit log (`aia_health_audit_chain`) pra LGPD/CFM.

3. **Edit window de 5min:** decisão de design — depois de 5min msg
   vira imutável. Bom pra audit, ruim se operador percebe erro tarde.
   Validar com Henrique se 5min é ok pra contexto clínico.

4. **WebSocket vs polling:** se Fase B trouxer WebSocket, todo o
   `useEffect setInterval` da Fase A vira morto. Mas adiar pra Fase B
   é ok (polling 3s é aceitável até 50 operadores concorrentes).

5. **Pra retomar essa sessão**: leia este doc + `CLAUDE.md` §3.1 (inventário
   de processos) e §3.2 (checklist de escala). Rode os 6 perguntas de
   §3.2 antes de começar a codar.
