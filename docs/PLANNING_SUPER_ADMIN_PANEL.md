# Planejamento — Painel Super Admin separado (ConnectaIACare)

> Espelho da arquitetura que existe na ConnectaIA. Objetivo: tirar
> visões de **operação da plataforma** da tela do tenant operacional,
> mantendo `app.connectaia.com.br/admin/system/*` exclusivo do super_admin
> e separando por **domínio cross-tenant**.
>
> Status: **Fase 0 APLICADA em 2026-05-01** (separação de namespaces
> dentro do app principal, sem subdomínio dedicado ainda). Fase 1+
> ainda planejadas.

## Estado pós-Fase 0 (aplicada)

- Sidebar reorganizada em **4 grupos**: Operação, Administração do
  tenant, Governança Clínica, Sistema · Cross-tenant.
- Namespace `/admin/governance/*` (cross-tenant clínico, multi-role:
  `super_admin`, `admin_tenant`, `clinical_reviewer`, `medico`,
  `enfermeiro` conforme a página).
- Namespace `/admin/system/*` (cross-tenant operacional, **super_admin
  ONLY**).
- Páginas movidas via `git mv` (histórico preservado):
  - `corpus-review` → `governance/corpus-review`
  - `regras-clinicas` → `governance/clinical-rules`
  - `regras-clinicas/cascadas` → `governance/cascades`
  - `regras-clinicas/revisao` → `governance/review`
  - `testes-sinteticos` → `governance/synthetic-tests`
  - `cenarios-sofia` → `governance/scenarios`
  - `cenarios-sofia/versoes` → `governance/scenarios/versions`
  - `saude` → `system/health`
  - `seguranca/risk-score` → `system/health/risk-score`
  - `proactive-caller` → `system/operations/proactive-caller`
- **Redirects 308** em `next.config.js` cobrindo todas URLs antigas →
  novas. Bookmarks/links externos continuam funcionando.

### TODOs técnicos abertos

- **Apertar permissions backend** das rotas que viraram super_admin-only
  no frontend (`/api/admin/health` ainda aceita `admin_tenant`). Hoje
  o gate é só visual (sidebar). Apertar quando 2º tenant entrar.

---

## 1. Por que separar

Hoje o super_admin enxerga tudo dentro do mesmo sidebar do operador
clínico. Isso polui visualmente, faz o tenant pensar que itens de
infra são parte do produto dele, e mistura concerns:

- **Tenant operacional** (médico, enfermeiro, cuidador) → cuida de
  pacientes, alertas, escalonamentos.
- **Operador da plataforma** (super_admin, eng saúde, eng plataforma) →
  cuida de tenants, saúde do sistema, métricas, notificações
  institucionais, governança clínica.

Misturar os dois força a UI a renderizar 30+ itens no sidebar pra um
super_admin, e nunca renderiza errado mesmo quando o usuário só
opera 1 tenant.

## 2. Arquitetura proposta

```
app.connectaia.com.br/             ← painel operacional (tenant)
  /                                  Dashboard tenant
  /alertas, /reports, /patients      Operação clínica
  /sofia, /comunicacao              IA + canais
  /equipe                           Equipe do tenant
  /admin/usuarios                    Admin DENTRO do tenant
  /admin/perfis
  /admin/regras-clinicas
  /admin/biometria-voz
  /configuracoes

admin.connectaia.com.br/           ← painel super_admin (cross-tenant)
  /                                  Dashboard cross-tenant (já existe em /admin/system)
  /tenants                           Lista + detalhe + suspend
  /tenants/new                       Wizard onboarding
  /platform-health                   Saúde do sistema (métricas)
  /notifications                     Sistema de notificações institucionais
  /notifications/policies            Políticas (event_code → recipients)
  /notifications/log                 Audit de despachos
  /clinical-governance               Sub-domínio clínico
    /corpus-review                   Revisão de corpus
    /synthetic-tests                 Testes sintéticos + F1 timeline
    /scenarios                       Cenários Sofia (todos os tenants)
    /clinical-rules                  Regras clínicas master
  /commercial                        Sub-domínio comercial
    /scheduled-calls                 Calls agendadas
    /proactive-caller                Decisões do proactive caller
  /system                            Sub-domínio infra
    /audit-log                       Audit log cross-tenant
    /security                        Fila de revisão + risk score
    /shifts                          Plantões master
  /me                                Perfil do super_admin
```

**Decisões-chave**:
- **Subdomínio dedicado** (`admin.connectaia.com.br`) — não rota dentro
  do app principal. Permite quotas/rate-limit independentes, deploy
  isolado eventual, e mantém auth/cookies separados.
- **Mesma codebase frontend** (Next.js multi-app) ou app separado.
  Decidir conforme custo: app separado é mais limpo mas duplica
  components UI; multi-app dentro do mesmo Next reusa.
- **Backend único** — não duplica API. As mesmas rotas
  `/api/system/*`, `/api/admin/notifications/*` etc. continuam
  servindo, painel novo só consome.

## 3. Sistema de notificações institucionais (Sofia → equipe)

> Esta seção justifica a feature que motivou o doc.

### Conceito

A Sofia age como remetente institucional para **comunicações de
plataforma** (não comunicação clínica com paciente). Sub-agentes
especializados monitoram dimensões diferentes e disparam mensagens
quando critérios são atingidos.

```
Sofia (orquestrador institucional)
├── Sub-agente "saúde-do-sistema"  → primary: super_admin (sócios)
│       eventos: api_down, p99_latency_high, db_pool_starved,
│                deploy_finished, cost_spike
├── Sub-agente "clínico-corpus"    → primary: clinical_reviewer
│                                    cc: super_admin
│       eventos: corpus_review_invitation, corpus_review_pending,
│                f1_dropped, gold_standard_updated
├── Sub-agente "operacional"       → primary: admin_tenant
│                                    cc: super_admin (se tenant não-sócio)
│       eventos: pilot_milestone, integration_failed, quota_warning
└── Sub-agente "comercial"         → primary: super_admin
        eventos: lead_qualified_call, contract_signed, churn_risk
```

### Princípios de governança

1. **Hierarquia de cópia**:
   - Membro do **corpo societário** → recebe direto, sem CC.
   - Membro **fora do corpo societário** → primary recebe + sócio
     responsável da área recebe **CC**. Transparência hierárquica
     sem perder agilidade.

2. **Threshold de severidade**:
   - `info` → apenas log, não dispara mensagem.
   - `attention` → dispara pra primary apenas.
   - `urgent` → primary + CC habitual + canal alternativo (se >5min
     sem ACK).
   - `critical` → todos relevantes, ramp-up de canal (Zap → call → SMS).

3. **Anti-fadiga**:
   - Rate-limit por evento+destinatário (default: max 3/h, 10/dia).
   - Aggregation window de 5min — múltiplos eventos do mesmo tipo
     viram 1 mensagem.
   - Quiet hours por destinatário (default: nada `info|attention`
     entre 22h-7h).

4. **Identificação clara**:
   - Toda mensagem assinada `— Sofia · ConnectaIACare` no rodapé.
   - Header da mensagem identifica o **sub-agente** que disparou:
     `[Saúde do Sistema]`, `[Revisão Clínica]`, etc.
   - **Nunca** finge ser humano. Nunca usa primeira pessoa de membro
     da equipe.

### Esquema técnico (MVP)

**Tabelas**:

```sql
CREATE TABLE aia_health_notification_policies (
    id UUID PRIMARY KEY,
    tenant_id TEXT,                       -- NULL = cross-tenant
    event_code TEXT NOT NULL UNIQUE,
    sub_agent TEXT NOT NULL,              -- saude_sistema|corpus|operacional|comercial
    severity_threshold TEXT NOT NULL,
    -- Resolvedor de destinatário: por role ou user_id explícito
    primary_role TEXT,                    -- ex: 'clinical_reviewer'
    primary_user_id UUID,                 -- override quando necessário
    cc_role TEXT,                         -- ex: 'super_admin'
    cc_user_id UUID,
    template_text TEXT NOT NULL,          -- com placeholders {var}
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    rate_limit_per_hour INT DEFAULT 3,
    rate_limit_per_day INT DEFAULT 10,
    aggregate_window_seconds INT DEFAULT 300,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE aia_health_notifications_log (
    id UUID PRIMARY KEY,
    policy_id UUID REFERENCES aia_health_notification_policies(id),
    event_code TEXT NOT NULL,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    -- Resolução final
    primary_recipient_user_id UUID,
    primary_recipient_phone TEXT,
    cc_user_ids UUID[],
    rendered_text TEXT,                   -- mensagem final pós template
    delivery_status TEXT,                 -- pending|sent|failed|aggregated
    delivery_provider TEXT,               -- evolution|sms|fallback
    delivery_response JSONB,
    aggregated_into_id UUID REFERENCES aia_health_notifications_log(id),
    context JSONB
);
```

**Endpoints**:
- `POST /api/admin/notifications/dispatch` — gatilho manual (super_admin)
- `GET /api/admin/notifications/log` — audit
- `GET /api/admin/notifications/policies` — lista
- `PUT /api/admin/notifications/policies/<id>` — edita

**Service**:
- `notification_dispatcher.dispatch(event_code, context, severity=None)`
  - Resolve política
  - Aplica filtros (severity, quiet hours, rate limit, aggregation)
  - Renderiza template
  - Resolve destinatários (role → user_ids)
  - Envia via Evolution API (primary) + clones (CC)
  - Loga em `notifications_log`

**Templates iniciais** (seed):

```
event_code: corpus_review_invitation
sub_agent: corpus
primary_role: clinical_reviewer
cc_role: super_admin
template:
  [Revisão Clínica] Olá, {full_name}. Você foi designado(a) como
  revisor(a) clínico do classificador da ConnectaIACare. Acesse
  {url} pra começar (~30-45 min, mobile-friendly). Detalhes:
  {context_url}.
  — Sofia · ConnectaIACare
```

### Roadmap em fases

| Fase | Escopo | Tempo |
|---|---|---|
| **0 — Imediato** | Manual dispatch via endpoint admin (1 política seed: corpus_review_invitation). Tudo logado. | (já no escopo dessa sprint) |
| **1 — Próximas 2 semanas** | Painel admin.connectaia.com.br/notifications/log (UI auditoria). Política CRUD via UI. | 2-3 dias |
| **2 — Mês seguinte** | Triggers automáticos: saúde-sistema integrado a Prometheus, corpus → cron diário "X cases pendentes". Aggregation + rate limit ativos. | 5-7 dias |
| **3 — Madurez** | Sub-agentes IA-powered (não só template fixo, mas IA gera mensagem). Multi-canal (SMS fallback, push). Métricas de engajamento (taxa de leitura/ack). | escopo aberto |

## 4. Painel super_admin separado — fases

| Fase | Escopo | Resultado |
|---|---|---|
| **0 — Hoje** | `/admin/system/*` dentro do app principal. Funciona, mas polui. | Atual |
| **1** | Subdomain `admin.connectaia.com.br` apontando pro mesmo Next.js. Middleware de role no edge bloqueia não-super_admin. Sidebar específico. | 2-3 dias |
| **2** | Refatora UI components/superadmin separado dos componentes do tenant. Reusa primitivos UI (Button, Modal, etc) mas wireframes específicos. | 1 semana |
| **3** | Notification panel + clinical governance + commercial sub-domains | 1-2 semanas cada |
| **4** | Multi-tenant impersonation (super_admin "ver como" admin_tenant X pra debug) | 3-5 dias |

## 5. Decisões pendentes (precisa Alexandre)

1. **Subdomain ou rota?** `admin.connectaia.com.br` (recomendado) vs
   `app.connectaia.com.br/admin` (atual).
2. **App Next separado ou multi-app no mesmo repo?**
3. **Quem tem `super_admin`?** Hoje só Alexandre. Vai ter outros sócios?
   Se sim, definir granularidade — mesmo super_admin pra tudo, ou
   roles separadas (super_admin, super_clinical, super_commercial)?
4. **Quiet hours global da plataforma** vs. **quiet hours por
   destinatário**. Recomendo por destinatário (sócio em férias não
   deve receber 4am).

## 6. Quando retomar

Sinais de que é hora de implementar a Fase 1+:
- Mais de 1 sócio ativo no painel super_admin (Alexandre + outro).
- Mais de 1 tenant em produção (ConnectaIACare + parceiro integrador + outro).
- Volume de notificações manuais > 5/semana — vale automatizar.
- Algum incidente onde "ninguém viu o alerta" — precisa do canal
  institucional.

Por enquanto (1 super_admin, 1 tenant em piloto), continua manual e
focar no produto.
