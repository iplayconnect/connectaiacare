# Auditoria — Sofia no WhatsApp em produção

> Levantamento do que está rodando hoje no canal WhatsApp e do que
> falta pra suportar fluxo comercial (cadastro, demo, qualificação
> de lead B2B).
>
> Data: 2026-05-01 · Branch consultada: `main` (HEAD `12f80fd`)

---

## TL;DR

| Fluxo | Estado | Observação |
|---|---|---|
| Cuidador relata sobre paciente (áudio) | ✅ funciona | Pipeline maduro: transcrição, identificação por voz, classificação, alerta |
| Cuidador follow-up texto em evento ativo | ✅ funciona | Detecta evento ativo, casa nome de paciente, atualiza |
| Confirmação SIM/NÃO de paciente | ✅ funciona | Sessão legada |
| Confirmação de medicação | ✅ funciona | Handler dedicado |
| **Onboarding B2C** (cliente individual) | ⚠️ **funciona MAS isolado** | State machine completa mas só pra `sofiacuida_b2c` (não `connectaiacare_demo`); 1 sessão ativa em 30d |
| **Lead B2B / agendar demo** | ❌ **inexistente** | Mensagem de phone novo não-cuidador cai em "envie um áudio" |
| **Qualificação comercial via WhatsApp** | ❌ **inexistente** | Persona `comercial` existe SÓ em voice_call (46 sessões em 30d), não WhatsApp |
| Sofia chat livre via WhatsApp | ❌ **inexistente** | Não há sessão `aia_health_sofia_sessions` channel=whatsapp em prod (0 em 30d) |

**Conclusão crucial**: o WhatsApp hoje atende **apenas** cuidador relatando + onboarding B2C de assinante de plano. Quem manda mensagem fora desse contexto recebe orientação seca pra mandar áudio.

---

## 1. Como o webhook funciona hoje

### Entry point

`POST /webhook/whatsapp` (`backend/src/handlers/routes.py:25`) → `pipeline.handle_webhook()`.

### Decisões em cascata em `pipeline.handle_webhook` (caminho do TEXTO)

```
1. presence.update?         → atualiza buffer de digitação, retorna
2. fromMe?                  → ignora
3. áudio?                   → pipeline clínico completo (transcrição → análise → alerta)
4. texto?                   ↓
   ├ é confirmação de medicação?           → handler dedicado
   ├ tem sessão legada (SIM/NÃO pendente)? → handler dedicado
   ├ tem sessão de onboarding B2C ativa?   → Sofia Onboarding Service
   ├ tem care_event ativo?                 → follow-up de evento
   └ NENHUM dos acima                      → "👋 Para registrar relato sobre idoso, envie áudio"
```

**Gap crítico**: No último ramo (sem nenhum contexto), Sofia **não tenta entender** se o usuário quer informação, demo, contratar, falar com humano, etc. Resposta hardcoded.

### Tenant é decidido onde?

- `settings.tenant_id` = env `TENANT_ID` (default `connectaiacare_demo`).
- Pipeline usa SEMPRE `connectaiacare_demo`.
- **Exceção forçada**: `_try_handle_onboarding()` consulta `aia_health_onboarding_sessions WHERE tenant_id = 'sofiacuida_b2c'` (hardcoded). Quem entra em onboarding via saudação ("oi", "ola", etc.) cai em B2C.
- Se você criar Hospital XYZ no wizard, eles **não recebem WhatsApp** — só voice. WhatsApp é mono-tenant na prática.

---

## 2. Estado real em produção (últimos 30 dias)

### Sessões Sofia por canal/persona

```
voice_call · comercial      46  ← Sofia atende ligação inbound de phone novo
voice_call · cuidador_pro   18
voice_call · medico         17
voice_call · anonymous      16
voice_call · super_admin    10
voice      · super_admin     8  (browser)
voice_call · familia         3
web        · super_admin     1
─────────────────────────────────
whatsapp   · qualquer       0   ← ZERO. Sofia chat NÃO existe via Zap em prod.
```

### Onboarding B2C
- **1 única sessão ativa** em 30 dias (phone 555199541518, 13 mensagens, parou em 23/04).
- O fluxo existe e tá maduro (state machine de 14 estados, intent classification, anti-fadiga, objection handler) — só não tá sendo usado.

### Care events
- 31 em 30 dias (todos do canal voz/cuidador via WhatsApp/áudio).

### Tabelas relacionadas a comercial
```
SELECT tablename FROM pg_tables
WHERE tablename ILIKE '%lead%'
   OR tablename ILIKE '%demo%'
   OR tablename ILIKE '%comercial%';

→ 0 rows
```

**Não existe persistência pra leads B2B**. Quando alguém liga (voice_call) com persona comercial, a única captura é via tool `escalate_to_attendant` que abre `aia_health_action_review_queue` — mesmo lugar de outras escalações clínicas. Não há funil dedicado.

---

## 3. O que existe DE comercial (e onde)

### A — Voice call inbound `comercial` (funcional)
Em `voice-call-service/services/inbound_bridge.py`, quando phone NÃO está cadastrado, persona = `comercial`. Sofia recebe prompt institucional comercial completo (~7 parágrafos) com:
- Apresentação (Sofia da ConnectaIACare)
- Pergunta sobre identidade + perfil (gestor ILPI, médico, familiar, etc.)
- Pitch adaptado ao perfil
- Captura: nome, contato, e-mail, papel, dor
- Tool obrigatória no fim: `escalate_to_attendant(reason="lead_comercial_qualificado", summary=...)` → cai em fila de revisão

**Funciona bem em produção** — 46 sessões em 30d. Mas é VOZ, não WhatsApp.

### B — Onboarding B2C `sofiacuida_b2c` (funcional)
State machine de 14 estados. Coleta dados, valida CPF, gera link de pagamento, aceita LGPD.

Triggers de entrada:
- Saudação ("oi", "ola", "quero saber", "info") **sem care_event ativo**
- Sessão de onboarding já existe e está em estado intermediário

Funcional mas pouco usado (1 sessão em 30d).

### C — Sofia Voice (browser) `super_admin` (uso interno)
8 sessões em 30d, todas suas. Conversa livre com Sofia via voz no painel admin. Tools clínicas + memória.

### D — Sofia Chat texto via interface web `web` (uso interno)
1 sessão em 30d. Existe a infra mas não tá sendo testada.

### E — `escalate_to_attendant` (tool universal)
Disponível em voice e voz browser. Cria entrada em `aia_health_action_review_queue` com `reason="lead_comercial_qualificado"` ou similar. Notifica equipe humana.

---

## 4. Gaps específicos do canal WhatsApp para fluxo comercial

### Gap #1 — Phone novo sem saudação não conversa

Quem manda "Quero conhecer a plataforma", "Vocês fazem demo?", "Sou diretor de ILPI" → cai em "envie um áudio sobre paciente". Lead frio perdido.

**Causa**: `_try_handle_onboarding` só dispara em saudações curtas (lista hardcoded). Mensagens descritivas não acionam Sofia.

### Gap #2 — Onboarding B2C tem 1 público só

`sofiacuida_b2c` é tenant separado. Quem manda mensagem pelo número da `connectaiacare_demo` (Hospital, ILPI parceira, comercial) NÃO entra no onboarding mesmo se mandar "oi". Tenant errado, fluxo errado.

### Gap #3 — Não há fluxo "agendar demo" ou "falar com vendas"

Não há intent dedicado a: agendar reunião, marcar demo, pedir proposta. Tudo cai em care_event ou onboarding B2C.

### Gap #4 — Sofia chat livre via WhatsApp inexistente

A Sofia que existe via voz (com memória, tools, RAG) NÃO tem o equivalente em WhatsApp texto. Você esperaria conversar com Sofia como conversa com Voice — mas não existe ponte.

### Gap #5 — Múltiplos números / tenants

Cada tenant em `aia_health_tenants` tem campos `whatsapp_phone` + `whatsapp_evolution_instance`, mas o webhook não roteia por número de origem. Tudo cai em `connectaiacare_demo`. Hospital XYZ que receber Zap via instância dele cai como se fosse demo.

---

## 5. Arquitetura proposta (mínimo viável pra atacar GAP #1, #3, #4)

### Princípio

Adicionar um **classificador de intent inicial** ANTES do "envie áudio" hardcoded. Quando phone novo manda texto, Sofia classifica em uma de 5 categorias:

| Intent | Ação |
|---|---|
| `relato_clinico` | "Pode mandar áudio que eu analiso" (comportamento atual) |
| `interesse_servico` | Inicia onboarding B2C (se número da instância B2C) ou fluxo demo (se B2B) |
| `agendar_demo` | Coleta nome/empresa/papel + cria evento em `leads_qualified` + envia link Calendly |
| `suporte_cliente` | Detecta tenant via phone, escalate pra humano |
| `outros / unclear` | Pergunta clarificadora aberta ("Em que posso ajudar?") |

### Componentes a criar

**Backend**:
1. **`aia_health_leads`** (tabela) — `phone, full_name, email, company, role, source_channel, intent, status, captured_at, qualified_at, scheduler_link_clicked_at, notes_jsonb`
2. **`SofiaIntentClassifier`** (serviço) — DeepSeek V4-Flash (já usado em outras classificações da plataforma) classifica em 5 buckets acima. ~$0.001/classification.
3. **`SofiaWhatsappChat`** (serviço) — wrapper conversa multi-turn que:
   - Mantém contexto em `aia_health_sofia_sessions` channel=whatsapp
   - Carrega tools restritas por intent
   - Tem tool `capture_lead`, `schedule_demo`, `escalate_to_human`
4. **Roteamento de tenant por número Evolution** — webhook olha qual instância recebeu a mensagem e seleciona o tenant correto.

**Frontend** (painel super_admin):
- Página `/admin/system/operations/leads` — lista leads capturados, status, ações (qualificar, descartar, criar tenant)
- Componente WhatsApp transcript viewer

### Fases de execução

| Fase | Escopo | Tempo | Resultado |
|---|---|---|---|
| **0 (já amanhã)** | Trocar resposta hardcoded "envie áudio" por classificador de intent + handlers de 5 buckets. Mensagens de interesse comercial caem em fluxo dedicado. | 1 dia | Lead frio para de virar suporte clínico |
| **1** | Tabela `leads` + tool `capture_lead` + página admin `/admin/system/operations/leads` | 2 dias | Funil capturado |
| **2** | Sofia chat WhatsApp livre (multi-turn, com tools restritas) — equivalente da voice | 2-3 dias | Lead pode conversar com Sofia em texto sem cair em onboarding |
| **3** | Roteamento multi-tenant por número Evolution | 2 dias | Hospital XYZ usa o Zap dele, Sofia/Emília atende com persona certa |
| **4** | Integração com Calendly / Google Calendar pra agendamento de demo automático | 1 dia | "Agendar demo" → link no Zap, calendar sync |

---

## 6. Riscos / cuidados antes de mexer

1. **Não quebrar fluxo cuidador** — 31 care_events em 30d dependem do path atual. Qualquer mudança no webhook tem que preservar prioridade: medicação > sessão legada > onboarding > care_event > novo handler de intent.

2. **Tenant routing primeiro ou intent classifier primeiro?** — Decisão de design. Roteamento por número Evolution PRIMEIRO simplifica tudo (cada tenant tem seu prompt, seus dados, seu funil). Mas exige config + provisionamento por tenant.

3. **Anti-spam / rate-limit** — Hoje rate-limit do `aia_health_rate_limit_*` (existe pelo onboarding) precisa cobrir o novo handler de intent classifier também, senão lead malicioso esgota tokens DeepSeek.

4. **LGPD / consent** — Onboarding B2C tem step de consent_lgpd. Lead B2B (gestor de ILPI) também precisa? Provavelmente sim, mais leve. Modelo: "Concorda em receber retorno?" antes de capturar.

5. **Sofia institucional pode disparar Zap** — fluxo Henrique provou que dá. Mesmo padrão pode ser usado pra "Sofia retoma lead que abandonou conversa" ou "Sofia confirma agendamento de demo amanhã às 14h".

---

## 7. Recomendação imediata

**Atacar Fase 0 esta semana** (testes reais começam semana que vem):

- Trocar o handler "envie áudio" por classificador DeepSeek V4-Flash com 5 buckets.
- Criar handler stub pros 4 buckets novos (mesmo que apenas "vou passar pro humano" + audit log no DB).
- Persistência mínima: `aia_health_leads` com 6 colunas básicas, sem UI ainda.
- Quando o teste real começar e alguém mandar interesse comercial, você consegue:
  - Ver no DB que houve interesse
  - Reagir manualmente pelo Zap
  - Entender qual o funil real antes de codar a UI

**Sequência sugerida pra próxima sessão**:
1. Decidir tenant routing (multi-tenant por número Evolution: sim ou não pra MVP?)
2. Codar Fase 0 com gating manual
3. Testar disparando msgs B2B no número de prod
4. Iterar

Quer que eu já abra issue/branch pra esse trabalho? Ou prefere conversar antes de codar?
