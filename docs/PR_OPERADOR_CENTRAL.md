# PR `feat/operador-central` — Painel da Central ATENT 24/7

**Branch**: `feat/operador-central`
**Data**: 2026-05-08
**Escopo**: introduzir role `operador_central` + painel dedicado pra operação 24/7 da ATENT atender handoffs cross-tenant, com leitura privilegiada do contexto do paciente, chat WhatsApp pelo painel e escalation pra equipe clínica.

---

## 1. Decisão de produto que motivou

A ATENT é a operação humana 24/7 que atende clientes da parceiro integrador (botão de emergência, pulseira de queda) e os clientes diretos da ConnectaIACare. Hoje os operadores trabalham respondendo WhatsApp manualmente sem audit estruturado. Com volume crescente (~900 SOS parceiro integrador + clientes ConnectaIACare em onboarding), isso não escala.

A decisão (Alexandre 2026-05-08) é trazer o operador pra dentro da plataforma com:
- Painel próprio (`/admin/system/operations/central`)
- Fila de handoffs cross-tenant
- Leitura privilegiada do paciente (todos os dados clínicos relevantes pra atender)
- Chat estruturado via WhatsApp (msg sai pelo nosso webhook, audit completo)
- Escalation pra plantão clínico em 1 clique
- Audit fino de todas as ações (LGPD/compliance)

---

## 2. O que foi implementado neste PR

### 2.1 Migration `071_operador_central.sql`

3 novas tabelas e 1 alteração:

| Tabela | Propósito |
|---|---|
| `aia_health_operator_states` | 1 row por operador. `is_online`, `last_heartbeat_at`, `current_shift_id`, `current_handoff_id`, `handoffs_handled_today`. |
| `aia_health_operator_shifts` | Audit de plantões. `started_at`, `ended_at`, `handoffs_handled`, `auto_ended` (timeout). `duration_seconds` é GENERATED. |
| `aia_health_operator_actions` | Audit fino. Toda ação relevante (claim, message_sent, escalate_clinical, view_patient_context, resolve, etc.) vira row aqui. |
| `aia_health_human_handoff_queue.handoff_type` | Constraint estendida pra aceitar `'operator'` (além de `commercial`/`clinical`/`support`). |

### 2.2 Role `operador_central`

- Adicionado em `VALID_ROLES` (`backend/src/handlers/users_routes.py`)
- Adicionado em `Role` type (`frontend/src/lib/auth.ts`)
- Adicionado em `ROLE_LABEL` (`frontend/src/lib/permissions.ts`) → exibido como "Operador · Central 24/7"

### 2.3 Backend — `operator_routes.py` (novo blueprint)

Prefixo `/api/operator/`. Acesso: `super_admin` + `operador_central`.

| Endpoint | Função |
|---|---|
| `GET  /me` | Snapshot estado do operador logado (online, shift atual, handoff atual) |
| `POST /online` | Marca online + abre nova shift (idempotente) |
| `POST /offline` | Marca offline + fecha shift. Bloqueia se há handoff ativo |
| `POST /heartbeat` | Keep-alive (frontend bate a cada 60s) |
| `GET  /queue` | Fila cross-tenant filtrada (status, type, priority, mine) |
| `GET  /queue/stats` | Stats agregadas (pending, P1 abertos, SLA estourado, online operators) |
| `GET  /handoff/<id>/patient-context` | Leitura privilegiada — patient + responsáveis + medicações + 30 vital signs + 10 care_events + cuidadores |
| `POST /handoff/<id>/escalate-clinical` | Cria novo handoff `clinical` referenciando o atual |
| `GET  /operators` | (super_admin/admin_tenant) Lista todos os operadores com seus estados |

### 2.4 Backend — extensão de `admin_handoff_routes.py`

- `_tenant_scope()`: agora `operador_central` é cross-tenant (não filtra por tenant_id, igual super_admin)
- Decorators `@require_role(...)` extendidos pra incluir `operador_central` em:
  - `/handoff/<id>/context` (ler contexto)
  - `/handoff/<id>/claim` (reivindicar)
  - `/handoff/<id>/resolve` (resolver)
  - `/handoff/<id>/messages` (GET histórico)
  - `/handoff/<id>/send` (enviar msg)
  - `/handoff/<id>/messages/<msg_id>` (PATCH/DELETE)

### 2.5 Sofia tool — `escalate_to_central_operator`

Variante de `escalate_to_human_*` que cria handoff com `handoff_type='operator'`. Usado quando Sofia não tem certeza se o caso é clínico ou comercial — operador 24/7 triagem e roteia. Idempotência: 1/30min por phone+patient.

Adicionado ao `TOOL_REGISTRY` em `sofia_tools.py`. **Ainda não está na `allowed_tools` de nenhum agent** — isso é uma decisão de produto pra um próximo PR (decidir em quais sub-agents a Sofia pode escolher essa tool).

### 2.6 Frontend — painel `/admin/system/operations/central/page.tsx`

Layout em 3 zonas:

- **Topo**: header com botão Online/Offline (entra/sai de plantão), botão Atualizar
- **Stats bar**: 6 contadores (Pendentes / Em atendimento / P1 abertos / SLA estourado / Resolvidos 24h / Operadores online)
- **Atendimento em curso** (banner amarelo se operador tem handoff claimed ativo)
- **Filtros**: chips por tipo (operator/clinical/commercial/support) e prioridade (P1/P2/P3)
- **Tabela da fila**: Tipo / Prioridade / Phone / Razão / Resumo / Status / Espera (formatada) / botão "Pegar"
  - Linha em vermelho se SLA estourado
- **Painel modal full-screen** ao clicar num handoff:
  - Coluna esquerda (4/12): contexto do paciente
    - Resumo do handoff (do `context_summary`)
    - Dados do paciente (nome, CPF, nascimento, unidade/quarto, nível de cuidado, alergias destacadas em amber)
    - Responsáveis (parsing tolerante a string/array/object)
    - Medicações vigentes
    - Últimos 6 vital signs com valor + unidade
    - Últimos 5 care_events com classification colorida
  - Coluna direita (8/12): chat
    - Histórico com bubbles (inbound vs outbound)
    - Auto-scroll, refresh polling 10s
    - Input com Enter pra enviar (Shift+Enter quebra linha)
    - Disabled se não estiver atendendo o handoff
  - Header tem badges (tipo, prioridade, status) e ações:
    - **Pegar atendimento** se status=pending
    - **Escalar pra clínico** (modal com motivo + urgência P1/P2/P3 → cria novo handoff clinical)
    - **Resolver** (modal com desfecho + summary → marca resolvido)
- **Heartbeat automático**: enquanto operador está online, frontend bate `/api/operator/heartbeat` a cada 60s. Servidor detecta operadores stale.

### 2.7 Frontend — sidebar + permissions

- Novo item "Central · ATENT 24/7" no grupo `system` (visível pra `super_admin` + `operador_central`)
- Role aparece em ROLE_LABEL como "Operador · Central 24/7"

---

## 3. Como testar (passo a passo)

### 3.1 Subir migrations
```sql
-- Rodar em ordem (071 inclui as tabelas novas + extensão do CHECK constraint)
\i backend/migrations/071_operador_central.sql
```

### 3.2 Criar um operador no banco
```sql
INSERT INTO aia_health_users (email, full_name, password_hash, role, active)
VALUES (
    'operador1@atent.com',
    'Operador Teste',
    crypt('senha-de-teste', gen_salt('bf')),  -- ou hash via auth_routes
    'operador_central',
    TRUE
);
```

(Ou via UI: super_admin cria via `/admin/usuarios` agora que `operador_central` está em VALID_ROLES.)

### 3.3 Logar e abrir o painel
1. Login com o operador criado
2. Sidebar → "Central · ATENT 24/7"
3. Botão "Entrar de plantão" — abre shift, marca online, dispara heartbeat
4. Fila aparece (vazia se não há handoffs)

### 3.4 Criar um handoff de teste
Pode ser via Sofia (real) ou direto:
```bash
# Via API admin_handoff (se tiver permission)
# Ou via INSERT direto no banco pra teste rápido:
psql evolution -c "
INSERT INTO aia_health_human_handoff_queue (
    trace_id, phone, channel, reason, context_summary,
    conversation_log, triggered_by, priority, status,
    handoff_type, sla_target_seconds
) VALUES (
    gen_random_uuid(), '5551999999999', 'whatsapp',
    'caregiver_uncertain',
    'Cuidador relatou que Dona Maria tá estranha hoje, sem clareza do que é.',
    '[]'::jsonb, 'sofia', 'P3', 'pending',
    'operator', 7200
);
"
```

### 3.5 Pegar e atender
1. No painel, clicar "Pegar" no handoff novo
2. Painel modal abre com contexto do paciente (vazio se patient_id NULL no handoff)
3. Digitar mensagem e enviar (vai pelo `/handoff/<id>/send` → Evolution → WhatsApp)
4. Mensagens recebidas aparecem por polling (10s) — quando lead responder via WhatsApp

### 3.6 Escalar pra clínico
1. Botão "Escalar pra clínico" → modal
2. Preencher motivo + urgência (P1)
3. Confirmar → cria novo handoff `clinical` referenciando o atual
4. Médico/enfermeiro de plantão vê no painel `/admin/system/operations/handoff`

### 3.7 Resolver
1. Botão "Resolver" → modal
2. Selecionar desfecho + summary
3. Confirmar → handoff vira `resolved`

### 3.8 Sair de plantão
1. "Online · sair de plantão" → fecha shift, decrementa contador, marca offline
2. Bloqueia se ainda tem handoff ativo (precisa resolver/escalar primeiro)

---

## 4. Audit gerado

Cada interação relevante deixa rastro:

- `aia_health_operator_actions`: `shift_start`, `shift_end`, `claim_handoff`, `view_patient_context`, `escalate_clinical`, `message_sent` (TODO no admin_handoff_routes, atualmente só audit_log clássico), `resolve_handoff`
- `aia_health_audit_log`: ações que tem semântica de governança (ex: `operator_escalated_clinical`)
- `aia_health_operator_shifts`: timeline de plantões com duração e contagem
- `aia_health_human_handoff_queue`: `claimed_at`, `claimed_by_user_id`, `resolved_at`, `resolved_by_user_id`

---

## 5. Decisões de design

### 5.1 Cross-tenant por padrão
Operador da ATENT atende handoffs de TODOS os tenants — o `_tenant_scope()` do admin_handoff agora trata `operador_central` igual a `super_admin` (sem filtro). Comercial admin de tenant continua restrito ao próprio tenant.

### 5.2 Heartbeat client-side em vez de WebSocket
Mais simples e tolerante a desconexão. Frontend POST a cada 60s; servidor considera offline se `last_heartbeat_at < now - 5min`. Trade-off: não é instantâneo. Pra MVP é OK; futuramente migrar pra Socket.IO.

### 5.3 `escalate_to_central_operator` como tool da Sofia
Estrutura criada mas **não wireada em nenhum agent ainda**. A decisão de em qual agent disponibilizar (passthrough? care? novo agent triagem?) vale uma conversa de produto. Por enquanto a tool fica latente no registry.

### 5.4 Painel modal full-screen vs nova rota
Optei por modal porque o operador faz triagem rápida — clicar num handoff não pode "perder" o contexto da fila. Se viu que outro handoff entrou em P1, fecha modal e pega o outro.

### 5.5 Audit em camadas
Decidi 2 camadas paralelas em vez de unificar:
- `audit_log` (existente): governança/compliance, ações com peso jurídico
- `operator_actions` (novo): operacional, granular, pra dashboards de gestão
A duplicação é proposital — limpeza de uma não afeta a outra.

---

## 6. Sugestões / próximos passos

### 6.1 Priorizado
1. **Worker de auto-end shift**: hoje o `auto_ended` na tabela está sem ninguém preenchendo. Cron job que olha operadores online com `last_heartbeat_at > 5min` e fecha shift. Importante pra remuneração não inflar com sessões esquecidas abertas.

2. **Notificação push de novo handoff**: hoje o operador descobre por refresh de 15s. Vale ligar Socket.IO ou Server-Sent Events pra empurrar `new_handoff` em real-time pros operadores online — especialmente pra P1.

3. **Wiring do `escalate_to_central_operator` na Sofia**: decidir em quais agents (Care? Passthrough?) a Sofia pode escolher essa tool quando intent é ambíguo. Valor agregado grande, é desnecessariamente latente hoje.

4. **Mostrar mensagem operador no audit log do operator_actions**: hoje quando operador envia mensagem via `/handoff/<id>/send`, NÃO grava em `operator_actions` (apenas no audit_log clássico). Vale adicionar um hook no `handoff_send` pra também logar lá pra dashboard "última mensagem enviada por operador X".

5. **Handoff "transferir" entre operadores**: hoje só dá pra `claim → resolve` ou `claim → escalate`. Operador A passa pra Operador B é fluxo comum (ex: troca de plantão a meia-noite com handoff aberto). Endpoint `/handoff/<id>/transfer` + UI.

### 6.2 Médio prazo
6. **Métricas de SLA por operador**: quem tem maior taxa de SLA respeitado? Tempo médio de resolução? View materializada com agregações pode virar uma página `/admin/system/operations/central/operators-stats` (super_admin/admin_tenant).

7. **Treinamento via shadow mode**: novo operador "ouve" handoff sem poder enviar mensagem (read-only) por X plantões antes de poder claim de fato. Flag `is_in_training` em operator_states + UI bloqueando botão de claim.

8. **Skill routing**: quando volume crescer, vai querer que P1 clínico vá só pra operadores treinados em emergência, e suporte simples pra operadores júnior. Tabela `aia_health_operator_skills` + filtro de fila.

9. **Quick replies / templates**: operador atende 50 handoffs por plantão, muito é repetido ("Olá, como posso ajudar?", "Vou transferir pro plantão clínico", etc.). Já existe `admin_quick_replies_routes.py` na base — vale conectar.

### 6.3 Pra Reunião PUC (Coordenadora de Farmácia)
A operadora central é o ponto de contato humano com cuidadores e idosos. Quando aparecer dúvida farmacêutica ("posso dar dipirona junto com warfarina?"), a operadora **não deve responder** — deve escalar pra plantão clínico (botão já existe). A coordenadora de Farmácia provavelmente vai querer:
- Garantia de que perguntas farmacológicas SEMPRE escalonam pro farmacêutico/médico (não a operadora dá receita)
- Audit de quantas escaladas farmacológicas viraram intervenções clínicas reais

A audit em `operator_actions` (com `escalate_clinical` e payload incluindo `reason`) já permite essa métrica. Vale mostrar pra ela.

---

## 7. Arquivos modificados/criados

### Criados
- `backend/migrations/071_operador_central.sql`
- `backend/src/handlers/operator_routes.py`
- `frontend/src/lib/api-operator.ts`
- `frontend/src/app/admin/system/operations/central/page.tsx`
- `docs/PR_OPERADOR_CENTRAL.md` (este doc)

### Modificados
- `backend/app.py` (registra blueprint operator_bp)
- `backend/src/handlers/users_routes.py` (VALID_ROLES)
- `backend/src/handlers/admin_handoff_routes.py` (`_tenant_scope` + `@require_role` extendido)
- `backend/src/services/sofia_tools.py` (escalate_to_central_operator + TOOL_REGISTRY)
- `frontend/src/lib/auth.ts` (Role type)
- `frontend/src/lib/permissions.ts` (ROLE_LABEL)
- `frontend/src/components/sidebar.tsx` (entry "Central · ATENT 24/7")

---

## 8. Validação técnica

- Python: `python3 -c "compile(...)"` em todos os arquivos backend tocados → ✅ compila
- TypeScript: `tsc --noEmit` no frontend → ✅ 0 erros
- Migration: idempotente (ALTER COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS, DO $$ blocks)
- Audit: cada ação relevante grava em `operator_actions`

---

## 9. Riscos conhecidos / pontos pra revisar

1. **Tenant_id em handoffs cross-tenant**: alguns handoffs criados pela Sofia comercial podem ter `tenant_id=NULL` (lead anônimo). O painel mostra "(sem tenant)" — não há quebra, mas pode confundir operador. Talvez criar tenant "central" e usar como default.

2. **patient_context endpoint sem PHI minimization**: hoje retorna alergias, medicações completas, todos vital signs dos últimos 30. LGPD-wise tudo bem porque operador é staff autorizado, mas pra futuros papéis (ex: estagiário, auditor) precisa de visões com mais ou menos campos.

3. **Refresh polling vs push real-time**: acceptable pra MVP mas vai cair quando volume passar de ~100 handoffs/dia. Migrar pra Socket.IO ou Pub/Sub no Redis.

4. **Sem prevenção de claim simultâneo**: 2 operadores podem clicar "Pegar" no mesmo handoff em milissegundos. O endpoint `claim` em admin_handoff já tem proteção (CHECK status='pending' no UPDATE), então só 1 vence — mas a UI não dá feedback claro pro perdedor. Adicionar toast "outro operador já pegou" quando o claim retornar erro.

5. **Sem rate-limiting em send_message**: operador pode disparar 50 msgs em 5s acidentalmente. Existe rate limit no nível Evolution mas vale adicionar throttle local.

---

## 10. Como subir em produção (quando aprovado)

```bash
# 1. Merge da PR via GitHub
# 2. Deploy backend
ssh root@72.60.242.245
cd /root/connectaiacare
git pull origin main
psql -h infra-postgres-1 -U evolution evolution \
    -f backend/migrations/071_operador_central.sql
docker compose up -d --build api sofia-service

# 3. Deploy frontend
docker compose up -d --build frontend

# 4. Criar primeiro operador via super_admin no painel /admin/usuarios
# 5. Testar /admin/system/operations/central
```

Sem env vars novas. Migration é o único stateful change.
