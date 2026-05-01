# Super Sofia · Arquitetura de plataforma conversacional escalável

> ⚠️ **Atualizado em 2026-05-01 com 4 decisões do Alexandre:**
> 1. Hospital piloto pode pedir número Zap próprio em <3 meses → multi-instance vai pra Phase A (infra preparada, mas começa com 1 instância ativa).
> 2. **Política white-label**: nome "Sofia" é fixo da plataforma. Não transferimos pra concorrente comercial (caso Tecnosenior — declinado). White-label completo só sob NDA + contrato uso interno.
> 3. Volume target 6 meses: **10k msgs/dia** → webhook async + worker pool 5-10 + cost tracking obrigatórios desde Phase A.
> 4. **Tenant central unificado** (Leitura A): TODO phone não-identificado entra em `connectaiacare_central` ("ConnectaIA Care Central"). Super Sofia classifica intent e ramifica pra B2C/B2B/suporte/clínico via sub-agentes. `sofiacuida_b2c` mantém só assinantes JÁ CONVERTIDOS — não recebe mais entrada direta de phone novo.

> Design definitivo. Pensa a Sofia como **agente multi-canal,
> multi-tenant, multi-profile** capaz de operar em escala (centenas
> de tenants, milhões de mensagens/mês) sem perda de coerência clínica
> nem segurança de identidade.
>
> Substitui `SUPER_SOFIA_ARCHITECTURE.md` (que era versão MVP).
>
> Branch: `feat/super-sofia-whatsapp-orchestrator`
> Status: em design — código vem só depois de aprovação total

---

## 0. Princípios não-negociáveis

| Princípio | Por quê |
|---|---|
| **Identidade é o phone E.164** | WhatsApp é canal primário; phone é a única chave consistente entre todos os perfis e tenants |
| **Tenant routing por number** | Cada tenant pode ter sua instância Evolution própria; webhook decide tenant pelo número que recebeu |
| **Webhook é assíncrono** | Resposta <100ms sempre. Processamento pesado vai pra worker via event bus |
| **Sofia é stateless por turno** | Estado mora em DB+Redis; qualquer worker pode pegar qualquer turno (escala horizontal) |
| **Tools são idempotentes** | Mesma tool com mesmo `idempotency_key` não cria registro duplicado |
| **Safety > UX > performance** | Em qualquer trade-off, segurança clínica vence; experiência do usuário vence performance |
| **Audit-first** | Todo turno, toda tool, todo handoff persistido com `trace_id` end-to-end pra LGPD/replay |
| **Multi-canal nativo** | WhatsApp, voice, web, email são *adapters*; lógica de Sofia é canal-agnóstica |
| **Custo rastreável por tenant** | Cada token LLM, cada minuto de voz, cada mensagem WhatsApp atribuída ao tenant correto |
| **Degradação graciosa** | Se LLM cair, Sofia fala "tive um problema, vou passar pra humano" e escala. Nunca trava silencioso |

---

## 0.1. Tenant central — ponto único de entrada (Leitura A)

```
WhatsApp inbound (qualquer phone)
   │
   ↓
[ IdentityResolver ]
   │
   ├─ phone resolvido em users/caregivers/patients ────→ tenant correspondente
   │                                                     (fluxos clínicos/admin existentes)
   │
   └─ phone NÃO resolvido (anônimo) ──────────────────→ tenant `connectaiacare_central`
                                                         "ConnectaIA Care Central"
                                                              │
                                                              ↓
                                                   [ Super Sofia + IntentClassifier ]
                                                              │
                                       ┌──────────────────────┼──────────────────────┐
                                       │                      │                      │
                              interesse_servico         agendar_demo            suporte_cliente
                                  (B2C ou B2B)               │                       │
                                       │                     │                       │
                          ┌────────────┴───────┐             │                       │
                          ↓                    ↓             ↓                       ↓
                onboarding sofiacuida_b2c   capture_lead   schedule_demo    escalate_to_human
                (sub-agente OnboardingB2C)  (B2B funnel)   (Calendly)       (Central 24h
                                                                            5551997354484)
```

**Mantemos `sofiacuida_b2c` como tenant** mas ele só **abriga
assinantes JÁ CONVERTIDOS**. Onboarding B2C continua sendo um
**sub-agente** do orquestrador no central — quando intent =
interesse_servico + perfil B2C, dispara máquina de estados de
onboarding que ao final cria o subscription em `sofiacuida_b2c`.

**Vantagens da Leitura A**:
- 1 ponto único de entrada lógico → debugging trivial
- Intent classifier decide o que é, não regex em saudação ("oi"/"olá")
- Lead B2B nunca mais cai em "envie áudio sobre paciente"
- Funil unificado: lead → qualified → converted (cria subscription
  ou cria tenant B2B novo)

---

## 1. Arquitetura em camadas

```
┌────────────────────────────────────────────────────────────────────┐
│  L1 · EDGE / INGEST                                                │
│  • Evolution webhook (multi-instance)                              │
│  • Voice inbound (PJSIP/Grok)                                      │
│  • Web Sofia chat (HTTP/WS)                                        │
│  • API integration (REST → futuro)                                 │
│  ▷ Validação, idempotência (message_id), rate-limit, audit         │
│  ▷ Resposta <100ms; despacha pra event bus                         │
├────────────────────────────────────────────────────────────────────┤
│  L2 · EVENT BUS                                                    │
│  • Redis Streams (`sofia:inbound`, `sofia:outbound`,               │
│    `sofia:tools`, `sofia:handoff`, `sofia:audit`)                  │
│  • Consumer groups por worker pool                                 │
│  • DLQ pra falhas + replay infrastructure                          │
├────────────────────────────────────────────────────────────────────┤
│  L3 · IDENTITY & ROUTING                                           │
│  • TenantResolver (instance/number → tenant)                       │
│  • IdentityResolver (phone → matches[] {tenant,profile,user_id})   │
│  • SessionResolver (canal-agnóstico, multi-turn coherent)          │
│  • PolicyResolver (scopes, permissions, quiet hours, rate limit)   │
│  ▷ Cache Redis (TTL 60s pra identidade, 5min pra tenant config)    │
├────────────────────────────────────────────────────────────────────┤
│  L4 · CONVERSATION ORCHESTRATOR (Super Sofia)                      │
│  • Profile-aware sub-agents:                                       │
│      clinical | commercial | support | onboarding | partner | admin│
│  • Memory layers:                                                  │
│      in-session (turn n) → active context cross-channel (45min) →  │
│      per-user long-term (LLM-summarized) → semantic recall (pgvec) │
│  • Anti-hallucination guardrail (já implementado pra voice)        │
│  • Safety guardrail (Sofia tem inteligência sem autoridade —       │
│    todo "ato clínico" passa por router central)                    │
│  • LLM router task-aware (Haiku judge, V4-Flash classifier,        │
│    Opus deep clinical, Grok voice realtime)                        │
├────────────────────────────────────────────────────────────────────┤
│  L5 · ACTION LAYER (Tools)                                         │
│  • Tool contract: input schema → policy check → execute → audit    │
│  • Idempotency keys (Redis SETNX TTL 24h)                          │
│  • Tool catalog versioned                                          │
│  • Each tool: 3 layers (validation, policy, execution)             │
├────────────────────────────────────────────────────────────────────┤
│  L6 · DELIVERY ADAPTERS                                            │
│  • Evolution pool (multi-instance, sticky por tenant)              │
│  • Voice (Grok WS, PJSIP outbound) — já produção                   │
│  • SMS fallback (Twilio/Meta — futuro)                             │
│  • Email (SES/Postmark — futuro)                                   │
│  ▷ Backoff exponencial, DLQ, ack tracking                          │
├────────────────────────────────────────────────────────────────────┤
│  L7 · OBSERVABILITY & COMPLIANCE                                   │
│  • Prometheus (canal, tenant, profile, intent, tool, latency)      │
│  • Structured logs (trace_id end-to-end, JSON)                     │
│  • Audit log imutável (append-only, LGPD)                          │
│  • Cost tracking (tokens, minutes, msgs por tenant)                │
│  • Replay engine (rebuild conversation from event bus)             │
├────────────────────────────────────────────────────────────────────┤
│  L8 · ADMIN UX                                                     │
│  • Cross-tenant dashboard (já existe parcial)                      │
│  • Conversation viewer (live + replay)                             │
│  • Lead funnel + handoff queue                                     │
│  • Tenant config UI                                                │
│  • Audit explorer + cost analytics                                 │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. L1 — Edge / Ingest detalhado

### 2.1 — Webhook multi-instance Evolution

**Atual** (gap):
```python
@bp.post("/webhook/whatsapp")
def whatsapp_webhook():
    event = request.get_json(silent=True)
    result = get_pipeline().handle_webhook(event)  # SÍNCRONO, bloqueia
    return jsonify(result), 200
```
Problema: Processing inteiro acontece dentro do timeout do webhook.
Evolution timeout ~10s → WhatsApp retry → mensagens duplicadas em
caso de processing demorado (LLM call >5s).

**Novo**:
```python
@bp.post("/webhook/whatsapp/<instance_name>")
def whatsapp_webhook(instance_name: str):
    event = request.get_json(silent=True)

    # 1. Idempotência: message_id no Redis SETNX (TTL 24h)
    msg_id = extract_message_id(event)
    if not redis.setnx(f"msg_seen:{msg_id}", 1, ex=86400):
        return jsonify({"status": "ok", "reason": "dup"}), 200

    # 2. Tenant resolve (instance_name → tenant_id) — cache 5min
    tenant_id = tenant_resolver.from_evolution_instance(instance_name)
    if not tenant_id:
        audit_log("webhook_unknown_instance", instance_name=instance_name)
        return jsonify({"status": "ignored"}), 200

    # 3. Validation hardening (signature do Evolution se config)
    # 4. Trace ID
    trace_id = uuid4()

    # 5. Despacha pro event bus (Redis Streams)
    redis.xadd("sofia:inbound", {
        "event": json.dumps(event),
        "tenant_id": tenant_id,
        "instance": instance_name,
        "trace_id": str(trace_id),
        "received_at": time.time(),
    })

    # Resposta <50ms
    return jsonify({"status": "queued", "trace_id": trace_id}), 200
```

**Caracteristicas**:
- URL `/webhook/whatsapp/<instance_name>` (cada Evolution instance
  posta no seu próprio path) → tenant resolve direto.
- Idempotência por message_id (Evolution as vezes retry mesma msg).
- Resposta <50ms sempre (despacha e sai).
- Audit de eventos descartados.

### 2.2 — Worker pool consumindo `sofia:inbound`

```
sofia-worker (gunicorn process pool, scale horizontal)
  └─ Redis Streams consumer group: 'sofia-inbound-cg'
      └─ Cada worker pega 1 mensagem
          └─ Processa → emite eventos (sofia:outbound, sofia:audit, etc.)
              └─ ACK na stream
```

Permite escala horizontal real (10 workers em paralelo). Hoje
gunicorn webhook==processing == 1 thread bloqueado.

### 2.3 — Outras ingest

- **Voice** (PJSIP) → atual já é assíncrono, vai continuar.
  Adapter publica eventos no mesmo `sofia:inbound` pra que
  Sofia oriente uniformemente.
- **Web Sofia chat** (HTTP/SSE) → idem, publica em inbound, mas
  consumer responde sync ao HTTP (cliente espera).
- **API integration** (futuro) → REST endpoints autenticados que
  publicam eventos (ex: agendamento via API parceira).

---

## 3. L2 — Event Bus

### Streams Redis

| Stream | Producer | Consumer | Retention |
|---|---|---|---|
| `sofia:inbound` | webhook, voice adapter, web | sofia-worker pool | 24h ou ack |
| `sofia:outbound` | sofia-worker | delivery-worker (Evolution send) | 1h |
| `sofia:tools` | sofia-worker | tool-executor pool | 12h |
| `sofia:handoff` | sofia-worker | handoff-notifier (Central 24h) | 7d |
| `sofia:audit` | todos | audit-writer (Postgres immutable) | streamed → DB |

### Por quê Redis Streams (não Kafka)?
- Já temos Redis em produção
- Volume estimado: ~10-100k msgs/dia x 1KB = ~100MB/dia → trivial
- Consumer groups: ack manual, retry, DLQ nativo
- Latência <5ms intra-cluster
- Escala vertical até 1M ops/sec antes de virar gargalo

### Quando migrar pra Kafka?
- > 10M msgs/dia (multi-region)
- Retention >7d (compliance forte)
- Replay massivo regular

Por enquanto Redis. Migration path documentado.

---

## 4. L3 — Identity & Routing

### 4.1 — TenantResolver

```python
class TenantResolver:
    def from_evolution_instance(self, instance: str) -> str | None:
        # Cache Redis 5min, fallback DB
        ...
    def from_voice_did(self, did: str) -> str | None: ...
    def from_origin_phone(self, phone: str) -> str | None:
        # Pra inbound voice quando phone está em aia_health_users etc.
        ...
```

DB:
- `aia_health_tenants.whatsapp_evolution_instance` (UNIQUE)
- `aia_health_tenants.voice_did`
- Tenant `connectaiacare_central` dedicado pra leads anônimos
  (decisão pendente §13).

### 4.2 — IdentityResolver

```python
class IdentityResolver:
    def resolve(self, phone: str, tenant_id: str | None = None) -> Identity:
        """
        Identity = {
          phone: '5551984928518',
          matches: [
            {tenant_id, profile, user_id?, caregiver_id?, patient_id?,
             full_name, source, last_active_at, confidence}
          ],
          primary: <best match>,
          is_anonymous: bool
        }
        """
```

**Fontes de match (ordenadas por força)**:
1. `aia_health_users.phone` (auth identity, mais forte)
2. `aia_health_caregivers.phone`
3. `aia_health_patients.proactive_call_phone` (paciente direto)
4. `aia_health_patients.responsible[*].phone` (familiar)
5. `aia_health_user_phone_history` (futuro: phone alternativos)

**Multi-tenant**: phone que aparece em N tenants → retorna todos
matches; Super Sofia decide ou pergunta. Heurística: último
`last_active_at` mais recente vence se confiança similar.

**Cache**: Redis hash `identity:{phone}` TTL 60s.
Invalidação: trigger Postgres em INSERT/UPDATE de
{users, caregivers, patients} → publica `identity:invalidate:{phone}`.

**Phone history**: tabela nova `aia_health_user_phone_history`
guarda phones antigos (idoso troca chip, cuidador troca emprego).
Resolve continuidade.

### 4.3 — SessionResolver canal-agnóstico

Hoje Sofia voice e Sofia chat criam sessions separadas. Novo
desenho: **uma sessão por (tenant, phone, profile)** ativa por
janela de tempo, independente do canal. Mensagens cross-channel
no mesmo período compartilham contexto.

Schema atualizado `aia_health_sofia_sessions`:
```sql
ALTER TABLE aia_health_sofia_sessions
  ADD COLUMN active_channels TEXT[] DEFAULT ARRAY['whatsapp'],
  ADD COLUMN context_continuation_window_minutes INT DEFAULT 45;
```

Quando Sofia voice abre nova session pro mesmo phone que tem
session whatsapp aberta há <45min, **append channel**, não cria
nova. Active context (já existe) garante que ela "lembra".

### 4.4 — PolicyResolver

Decide o que cada turno pode fazer:
- **Scope**: tools permitidas pra (tenant, profile, channel)
- **Quiet hours**: não dispara outbound entre 22h-7h salvo
  `severity=critical`
- **Rate limit**: tokens/hora por phone (anti-spam, anti-abuso)
- **Quota**: limite mensal por tenant (LLM tokens, voice minutes,
  msgs WhatsApp)

DB-backed config em `aia_health_tenant_policies`. Cache Redis 5min.

---

## 5. L4 — Conversation Orchestrator (Super Sofia)

### 5.1 — Profile-aware sub-agents

Não é um único prompt monstro. Cada profile tem:
- **System prompt** otimizado (existe parcial em `inbound_bridge.py`)
- **Tool subset** permitido
- **Memory scope** (do que ela "lembra")
- **Escalation policy** (quando passa pra humano)

```python
SUB_AGENTS = {
    "clinical": ClinicalSofiaAgent,        # medico/enfermeiro
    "caregiver": CaregiverSofiaAgent,      # cuidador_pro
    "family": FamilySofiaAgent,            # familia
    "patient_b2c": PatientSofiaAgent,      # paciente_b2c (idoso solo)
    "partner": PartnerSofiaAgent,          # parceiro
    "admin": AdminSofiaAgent,              # super_admin/admin_tenant
    "commercial": CommercialSofiaAgent,    # anonymous + intent comercial
    "support": SupportSofiaAgent,          # anonymous + intent suporte
    "onboarding_b2c": OnboardingB2CSofia,  # onboarding sofiacuida_b2c
    "onboarding_b2b": OnboardingB2BSofia,  # tenant onboarding (futuro)
}
```

Cada agente herda de `BaseSofiaAgent` que provê:
- Tool execution (com guardrail safety)
- Memory loading
- Token budgeting
- Output validation
- Streaming/chunking pra WhatsApp humanizado (já existe no
  humanizer_service)

### 5.2 — Memória em 4 camadas (já documentado em
`project_sofia_memory_layers.md`)

| Camada | Onde | Janela | Uso |
|---|---|---|---|
| **In-session** | Lista in-memory do worker | 1 turno | Context window LLM |
| **Active context cross-channel** | Postgres UNLOGGED + Redis | 45min | Sofia "lembra" entre canais |
| **Per-user long-term** | Postgres LLM-summarized | indefinido | Sofia conhece o usuário |
| **Semantic recall** | pgvector | indefinido | Sofia recupera fato específico |

**Guardrail anti-alucinação** (já implementado pra voice em
`grok_call_session.py`): impede persistência em active_context
quando Sofia narra dado clínico sem tool válida no turno.
**Estender pra chat WhatsApp também** — código portável.

### 5.3 — LLM Router task-aware

Já existe `LlmRouter` no codebase. Expandir:

| Task | Provider preferred | Fallback | Por quê |
|---|---|---|---|
| `intent_classifier` | DeepSeek V4-Flash | DeepSeek V4-Pro | Custo/latência |
| `entity_extractor` | DeepSeek V4-Flash | Gemini 2.0 Flash | Idem |
| `clinical_judge` | Claude Haiku 3.5 | Sonnet | Architecture independence |
| `clinical_deep_reasoning` | Claude Sonnet 4.6 | Opus | Cases hard |
| `voice_realtime` | Grok-voice-think-fast-1.0 | (sem fallback) | Único provider voice realtime |
| `humanization_chunking` | DeepSeek V4-Flash | Gemini 2.0 Flash | Saída curta |
| `summarization_long` | Claude Sonnet | DeepSeek V4-Pro | Qualidade |

**Provider-aware fallback**: se primary retorna 5xx ou >timeout,
fallback automático com mesmo prompt. Audit log marca qual
provider respondeu.

### 5.4 — Safety Guardrail Layer (já implementado parcial)

Sofia **NUNCA** executa ato clínico autônomo. Toda tool de ação
(create_care_event, schedule_teleconsulta, capture_lead com
severidade alta, dial_phone) passa por `safety/route-action`
que decide:
- `execute` → tool roda
- `queue` → vai pra fila de revisão humana, Sofia avisa "passei pra revisão"
- `reject` → tool não roda, Sofia explica
- `paused` → circuit breaker ativo, Sofia pausa toda ação automática

**Estender pra WhatsApp**: hoje só voice/chat web. Mesmas tools
chamadas via WhatsApp passam pelo mesmo guardrail.

---

## 6. L5 — Action Layer (Tools)

### 6.1 — Tool contract universal

```python
class Tool:
    name: str
    description: str
    input_schema: dict           # JSON schema
    output_schema: dict
    profile_scope: list[str]     # quais profiles podem chamar
    requires_safety_review: bool # passa por guardrail?
    severity_classifier: callable # extrai severity do input
    execute: callable            # contém: validate → execute → audit
    idempotency_key_fn: callable # extrai key dos inputs
```

### 6.2 — Catálogo de tools (consolidado)

**Tools de leitura clínica** (existentes, todas precisam ser
WhatsApp-friendly):
- `search_patients`
- `get_patient_summary`
- `read_care_event_history`
- `list_medication_schedules`
- `get_patient_vitals`
- `query_drug_rules`
- `check_drug_interaction`
- `check_medication_safety`
- `query_clinical_guidelines`
- `list_beers_avoid_in_condition`

**Tools de ação clínica** (existentes, com guardrail):
- `create_care_event`
- `schedule_teleconsulta`
- `escalate_to_attendant` (humano clínico)

**Tools de voz** (existentes):
- `dial_phone`
- `get_patient_responsible_phone`

**Tools comerciais** (novas):
- `capture_lead` — cria/atualiza `aia_health_leads`
- `qualify_lead_score` — calcula intent score (high|med|low)
- `schedule_demo` — gera link calendly + envia
- `request_proposal` — captura interesse formal de proposta
  comercial

**Tools de suporte** (novas):
- `escalate_to_human_whatsapp` — pra Central 24h
- `request_account_recovery` — phone perdido, etc.
- `request_data_export` — LGPD, lead pede dados dele

**Tools auxiliares** (novas):
- `verify_email` — manda OTP por email durante captura
- `verify_phone` — confirma phone via OTP WhatsApp
- `accept_terms` — registra aceite LGPD

### 6.3 — Tool registry centralizado

`backend/src/services/tools/registry.py` lista todas tools com
schema. Cada profile carrega só as suas. Versionamento:
`tool_version` no audit log → permite rollback se tool nova
quebrar.

### 6.4 — Idempotência

Tool `create_care_event` chamada 2x no mesmo turno (LLM bug) não
cria 2 eventos. Idempotency key = hash de
`(tenant, patient_id, summary[:100], turn_id)`. Redis SETNX TTL 24h.

---

## 7. L6 — Delivery Adapters

### 7.1 — Evolution multi-instance pool

Hoje 1 instância (`v6`). Hospital piloto pode pedir número
próprio em <3 meses → infra preparada desde Phase A:

- Cada tenant pode ter sua própria instância (campo
  `whatsapp_evolution_instance` já existe em `aia_health_tenants`).
- Pool de adapters carrega config por tenant.
- Send: `EvolutionPool.get(tenant_id).send_text(phone, text)`.
- Webhook: `/webhook/whatsapp/<instance_name>` permite cada
  instância postar no seu próprio path → tenant resolve direto
  (cache Redis 5min).
- **Adicionar instância nova é mudança de config + provisionamento
  Evolution, não código** — escala operacional.

### 7.5 — Política comercial white-label (constraint arquitetural)

Decisões fixas que alimentam o design:

1. **Nome "Sofia" é fixo da plataforma ConnectaIACare** em todos
   os tenants. NÃO transferimos pra concorrente comercial.
2. **Customização permitida** (sem ferir):
   - Greeting: `"Olá, aqui é a Sofia da ConnectaIACare,
     atendendo pelo Hospital XYZ"` (Hospital aparece, Sofia mantém
     autoria).
   - Footer/assinatura institucional pode mencionar o tenant.
   - Logo do tenant em portal/email/notificações de plataforma.
   - Cores/tema do tenant (campos `primary_color`, `accent_color`
     já existem em `aia_health_tenants`).
3. **White-label completo** (Sofia → outro nome/marca) **só sob**:
   - Cliente uso interno **sem revenda comercial**.
   - Contrato com cláusula de não-concorrência + NDA.
   - Decisão caso a caso (super_admin manual).
4. **Casos fechados**:
   - **Tecnosenior**: declinado. Vai ser concorrente. Sem branding,
     sem white-label, sem nada.
5. **Implicação técnica**: campo `aia_health_tenants.ai_name`
   default = `"Sofia"`. Override permitido apenas com flag
   `tenant.metadata.white_label_approved = true` (precisa
   super_admin marcar manualmente). Sem flag, prompt da Sofia
   força nome `"Sofia"` independente do `ai_name` do tenant.

### 7.2 — Outbound queue + retry

Adapter envia via Evolution. Falha (network, 5xx) → message volta
pra `sofia:outbound` com backoff exponencial (1s, 4s, 16s, 64s).
Após 5 falhas → DLQ + alert.

### 7.3 — Delivery confirmation

Evolution emite webhooks de status (`MESSAGES_UPDATE` com
`status: SENT|DELIVERED|READ`). Update audit log + métricas.

### 7.4 — SMS fallback (futuro)

Se Evolution caído >5min pra um phone específico, fallback SMS
pra mensagens criticas (alertas).

---

## 8. L7 — Observabilidade

### 8.1 — Métricas Prometheus (estende o que voice-call já tem)

```
sofia_messages_total{tenant, channel, profile, direction}
sofia_intent_classifier_duration_seconds{intent}
sofia_tool_executions_total{tenant, profile, tool, ok}
sofia_tool_latency_seconds{tool}
sofia_llm_tokens_total{provider, model, task, tenant}
sofia_llm_cost_usd_total{tenant}
sofia_handoff_total{reason, profile}
sofia_session_active{tenant, channel, profile}
sofia_active_context_size_bytes{tenant}
sofia_evolution_send_duration_seconds{instance}
sofia_evolution_send_failures_total{instance, reason}
```

### 8.2 — Trace ID end-to-end

`trace_id = uuid4` criado no webhook → propaga em todo log,
todo evento no bus, todo audit_log entry. Permite reconstruir
turno completo via grep do trace_id.

### 8.3 — Audit log imutável

Tabela `aia_health_audit_log` (já existe) → append-only, sem
UPDATE/DELETE. Trigger recusa modificações. Particionamento
mensal pra escala.

Eventos auditados:
- inbound_received, outbound_sent
- intent_classified
- identity_resolved (com matches)
- session_started, session_closed
- tool_called (input, output, ok)
- guardrail_decision
- handoff_initiated
- ldap_consent_accepted
- pii_redacted

### 8.4 — Replay engine

Dado um `trace_id` ou um `session_id`, reconstrói a conversação
completa lendo `sofia:audit` archived. Útil pra debug, pra
treinamento, pra LGPD.

### 8.5 — Cost tracking

Cada chamada LLM persiste em `aia_health_llm_cost_log` com
`tenant_id, provider, model, task, prompt_tokens, completion_tokens,
estimated_cost_usd`. Dashboard cross-tenant em
`/admin/system/health` mostra cost burn por tenant.

---

## 9. L8 — Admin UX

(detalhado no doc anterior, expanded aqui)

### 9.1 — `/admin/system/conversations`

Live view de todas conversas ativas. Filtros: tenant, channel,
profile. Drill-down pra turno-a-turno. Botão "intervir" passa
control pra humano (manual handoff). Replay de conversas
encerradas.

### 9.2 — `/admin/system/operations/leads`

Funil B2B/B2C. Status: new → qualified → demo_scheduled → in_demo
→ proposal_sent → converted | lost. Drill-down: histórico de
turns, identidade resolvida, intents detectados. Ações: qualify,
discard, convert (cria tenant via wizard).

### 9.3 — `/admin/system/operations/handoff`

Fila de pedidos pra humano. Tabs: pending, claimed, resolved.
SLA timer (P1 <5min, P2 <30min, P3 <2h). Histórico de respostas
do humano via Central 24h.

### 9.4 — `/admin/system/health/cost`

Cost burn por tenant, por provider, por task. Comparativo mês.
Forecast 30d. Alertas automáticos quando tenant excede 80% de
quota mensal.

### 9.5 — `/admin/system/health/replay`

Search por trace_id, session_id, phone. Reconstrução visual da
conversa com timing, latências de tool, decisões de guardrail.

---

## 10. Schemas Postgres novos / alterados

### 10.1 — Migrations necessárias

```sql
-- 061_super_sofia_foundation.sql

-- Identidade extra (phone history)
CREATE TABLE aia_health_user_phone_history (
  id UUID PRIMARY KEY,
  user_id UUID REFERENCES aia_health_users(id) ON DELETE CASCADE,
  phone TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  reason TEXT
);
CREATE INDEX ON aia_health_user_phone_history(phone) WHERE active;

-- Lead funnel
CREATE TABLE aia_health_leads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  phone TEXT NOT NULL,
  full_name TEXT,
  email TEXT,
  organization TEXT,
  role_self_declared TEXT,
  intent TEXT NOT NULL,
  confidence NUMERIC(3,2),
  source_channel TEXT NOT NULL DEFAULT 'whatsapp',
  source_metadata JSONB,
  status TEXT NOT NULL DEFAULT 'new',
  qualification_score INT,
  qualified_at TIMESTAMPTZ,
  demo_scheduled_at TIMESTAMPTZ,
  demo_link TEXT,
  converted_to_tenant_id TEXT,
  lost_reason TEXT,
  notes JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (status IN ('new','qualified','demo_scheduled','in_demo','proposal_sent','converted','lost'))
);
CREATE INDEX ON aia_health_leads(status, created_at);
CREATE INDEX ON aia_health_leads(phone);

-- Handoff queue
CREATE TABLE aia_health_human_handoff_queue (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  trace_id UUID NOT NULL,
  phone TEXT NOT NULL,
  tenant_id TEXT,
  channel TEXT NOT NULL,
  reason TEXT NOT NULL,
  context_summary TEXT NOT NULL,
  conversation_log JSONB NOT NULL,
  triggered_by TEXT NOT NULL DEFAULT 'sofia',
  priority TEXT NOT NULL DEFAULT 'P3',
  status TEXT NOT NULL DEFAULT 'pending',
  assigned_to_user_id UUID REFERENCES aia_health_users(id),
  notified_central_at TIMESTAMPTZ,
  claimed_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  resolution_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (priority IN ('P1','P2','P3')),
  CHECK (status IN ('pending','claimed','resolved','expired'))
);
CREATE INDEX ON aia_health_human_handoff_queue(status, created_at);

-- Tenant policies (rate limit, quotas, scopes)
CREATE TABLE aia_health_tenant_policies (
  tenant_id TEXT PRIMARY KEY REFERENCES aia_health_tenants(id) ON DELETE CASCADE,
  monthly_msg_quota INT,
  monthly_voice_minutes_quota INT,
  monthly_llm_tokens_quota_input BIGINT,
  monthly_llm_tokens_quota_output BIGINT,
  rate_limit_msgs_per_phone_per_hour INT DEFAULT 30,
  quiet_hours_start TIME DEFAULT '22:00',
  quiet_hours_end TIME DEFAULT '07:00',
  active_profiles TEXT[] NOT NULL DEFAULT ARRAY['cuidador_pro','familia'],
  custom_config JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- LLM cost log
CREATE TABLE aia_health_llm_cost_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id TEXT,
  trace_id UUID,
  session_id UUID,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  task TEXT NOT NULL,
  prompt_tokens INT NOT NULL,
  completion_tokens INT NOT NULL,
  estimated_cost_usd NUMERIC(10,6) NOT NULL,
  duration_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON aia_health_llm_cost_log(tenant_id, created_at);

-- Sofia sessions: estende
ALTER TABLE aia_health_sofia_sessions
  ADD COLUMN IF NOT EXISTS active_channels TEXT[] DEFAULT ARRAY['whatsapp'],
  ADD COLUMN IF NOT EXISTS sub_agent TEXT,
  ADD COLUMN IF NOT EXISTS handoff_id UUID REFERENCES aia_health_human_handoff_queue(id);
```

---

## 11. Stack & infraestrutura

### 11.1 — Worker pool

Hoje 1 gunicorn process. Novo: process pool dedicado.

```yaml
# docker-compose.yml additions
sofia-worker:
  image: connectaiacare-api  # mesma imagem
  command: python -m src.workers.sofia_inbound_worker
  scale: 4
  environment:
    - WORKER_TYPE=sofia_inbound
    - REDIS_STREAM=sofia:inbound
    - CONSUMER_GROUP=sofia-inbound-cg

delivery-worker:
  image: connectaiacare-api
  command: python -m src.workers.delivery_worker
  scale: 2

handoff-notifier:
  image: connectaiacare-api
  command: python -m src.workers.handoff_notifier
  scale: 1
```

API container só serve HTTP (webhooks + admin), não processa
msg. Reduz latency do webhook a <50ms always.

### 11.2 — Redis

Já temos. Adicionar config:
- maxmemory-policy: allkeys-lru
- streams retention via XTRIM scheduled (cron job)
- Replication slave em outra availability zone (futuro)

### 11.3 — Postgres

Já temos. Considerações:
- `aia_health_audit_log` particionado mensal (escala >10M rows)
- `aia_health_llm_cost_log` particionado mensal
- Read replica pra dashboards (escala >100k events/min)

### 11.4 — Observability stack

- **Prometheus + Grafana** (futuro): hoje temos /metrics em
  voice-call apenas. Estender pra api + sofia-worker.
- **Loki** ou **Datadog** pros logs (decisão pendente)
- **Sentry** pra erros (já integrado parcialmente)

---

## 12. Plano de migração (incremental, sem downtime)

### Estratégia: strangler fig pattern

Não trocar tudo de uma vez. Construir nova arquitetura ao lado,
desviar tráfego gradualmente.

**Phase A — Foundations** (1-2 semanas)
1. Migrations (leads, handoff, policies, cost_log, phone_history)
2. IdentityResolver + cache
3. TenantResolver + cache
4. LLM cost log + tracking infra
5. Audit log triggers + particionamento
6. Tests E2E mocks

**Phase B — Event bus + workers** (1-2 semanas)
1. Redis Streams + consumer groups
2. sofia-worker pool (processa inbound)
3. delivery-worker (Evolution send async)
4. Webhook nova versão `/webhook/whatsapp/<instance>` (paralelo
   ao antigo, opt-in por tenant)
5. Tenant ConnectaIACare migra primeiro (canary)
6. Rollback button: env flag desliga novo path

**Phase C — Super Sofia orchestrator** (2-3 semanas)
1. Profile-aware sub-agents (clinical, caregiver, family,
   commercial, support, admin)
2. Tool registry + idempotency
3. Memory layers (já temos parcial)
4. Safety guardrail estendido pra WhatsApp
5. Streaming/chunking unificado
6. Sofia chat WhatsApp (multi-turn) ativo

**Phase D — Admin UX** (1-2 semanas)
1. `/admin/system/conversations` (live + replay)
2. `/admin/system/operations/leads`
3. `/admin/system/operations/handoff`
4. `/admin/system/health/cost`
5. `/admin/system/health/replay`

**Phase E — Hardening + escala** (1 semana)
1. Particionamento Postgres
2. Worker scaling profile (CPU/memory)
3. Stress test (10k msgs/min)
4. DLQ + alerting
5. Multi-tenant onboarding completo (Hospital XYZ entra)
6. Documentação operacional

**Total**: 6-10 semanas. Cada fase é mergeable independente.

---

## 13. Decisões — fechadas e abertas

### 13.1 — Decisões fechadas (sign-off Alexandre 2026-05-01)

| # | Decisão | Resolvido |
|---|---|---|
| **A** | Multi-instance Evolution | **Phase A — infra preparada, mas só 1 instância ativa hoje. Hospital piloto pode pedir número próprio em <3 meses → adicionar = config + provisionamento, não código.** |
| **B** | White-label / branding Sofia | **Nome "Sofia" é fixo da plataforma. Não transferimos pra concorrente comercial. Customização permitida (greeting com tenant, footer, cores). White-label completo só sob NDA + uso interno (decisão caso a caso). Tecnosenior declinado.** Detalhes em §7.5. |
| **C** | Volume target 6 meses | **10k msgs/dia** → webhook async, worker pool 5-10, cost tracking obrigatórios desde Phase A. Headroom 3x = 30k/dia capacidade dimensionada. |
| **D** | Tenant central unificado (Leitura A) | **Todo phone não-identificado entra em `connectaiacare_central` ("ConnectaIA Care Central"). Super Sofia classifica intent e ramifica pra B2C/B2B/suporte/clínico via sub-agentes. `sofiacuida_b2c` continua existindo MAS só abriga assinantes JÁ CONVERTIDOS — não recebe mais entrada direta de phone novo via webhook.** Detalhes em §0.1. |

### 13.2 — Decisões abertas (Alexandre confirma)

| # | Decisão | Recomendação | Por quê |
|---|---|---|---|
| ~~1~~ | ~~Tenant central pra leads anônimos~~ | **DECIDIDA → §13.1.D (Leitura A · unificado)** | Fechada 2026-05-01 |
| 2 | Silence Sofia em handoff vs sinalizar | **Silenciar** | Evita confusão. Humano fala, Sofia volta após `resolved`. |
| 3 | 24h real ou diferido madrugada | **24h real** (você disse Central 24h) | Compromisso operacional. |
| 4 | Captura email no fluxo conversacional | **Sim, opt-in suave** | Reduz fricção pro humano. |
| ~~5~~ | ~~Calendly link~~ | **DECIDIDA → tool `schedule_demo` usa ConnectaLive (módulo próprio LiveKit já existente em ConnectaIA)** — Branding + transcrição automática nativos. Phase C investiga se módulo já está integrado em ConnectaIACare ou precisa portar. | Fechada 2026-05-01 |
| 6 | Provedor logs estruturados | **Loki self-hosted** | Custo zero, integra Grafana. Datadog é caro pra escala. |
| 7 | Vector store futuro (RAG semântico) | **pgvector** (já temos) | Evita 1 dep externa até precisar. |
| ~~8.a~~ | ~~Multi-region técnico (infra DR)~~ | **Não agora** | Postgres single-region até 100+ tenants. Confusão de termos minha. |
| 8.b | **Multi-region brasileiro (regionalização de produto)** | **Sim, via `tenant.region` + `tenant_policies.custom_config`** | Sul/Sudeste/Norte: sotaque Sofia, parceiros operacionais regionais, time atendimento humano regional, regulação estadual. Phase D inclui no schema `aia_health_tenants`. |
| 9 | Onboarding B2B (Hospital adere a plataforma) | **Phase D** — wizard hoje cobre criação básica, ampliar pra fluxo guiado conversacional | Será feature comercial chave |
| 10 | **Provider WhatsApp futuro** (não SMS — texto antigo errado) | **Investigação separada Phase E** — avaliar Meta Cloud API direta (oficial), nvoip (já usado pra voz), Twilio (oficial Meta partner), Wati/Z-API (intermediários BR). Hoje: Evolution API não-oficial (suficiente pro piloto). | Não bloqueia MVP. |
| 11 | Limite de mensagens grátis pra lead anônimo | **5 turnos antes de pedir email** | Anti-abuso, sem afastar lead real |
| 12 | Sofia atende mesmo phone em 2 tenants | **Pergunta no primeiro turno qual tenant** | Caso raro hoje, mas resolve com clareza |
| 13 | Conversation timeout | **Active context expira em 45min, session fecha em 2h** | Sofia "esquece" contexto pra evitar confusão |
| 14 | LGPD: lead pode pedir delete | **Tool `request_data_export` + ack manual** | Compliance básico |
| 15 | Backup de Redis (event bus) | **AOF habilitado, snapshot 30min** | Não-crítico (eventos ack ficam só horas), mas ajuda em incidente |

---

## 14. Critérios de aceite pra produção

Antes de declarar "Super Sofia em produção":

- [ ] 100% das mensagens WhatsApp passam pelo novo fluxo
- [ ] Webhook latency p99 <100ms
- [ ] Worker p99 turn processing <5s (excluindo LLM call)
- [ ] LLM call p95 <3s pra intent_classifier
- [ ] Zero quebras no fluxo cuidador atual (regression test passa)
- [ ] Audit trail 100% das tools auditadas
- [ ] Cost tracking funcional (DB + dashboard)
- [ ] Handoff Central 24h testado com Alexandre + Henrique
- [ ] Lead capture testado com phone real anônimo
- [ ] Rollback button operacional (1 flag desliga tudo novo)
- [ ] Documentação operacional completa
- [ ] Runbook de incidentes
- [ ] Smoke test E2E automatizado
- [ ] Tenant secundário em produção (Hospital piloto) usando o novo

---

## 15. Anti-patterns que NÃO vamos cometer

1. **Não vamos fazer Sofia ser um único prompt monstro** — sub-agents
   por profile, prompts focados.
2. **Não vamos misturar lógica de canal com lógica de Sofia** —
   adapters separam isso.
3. **Não vamos depender de 1 provider LLM** — router task-aware com
   fallback obrigatório.
4. **Não vamos confiar em LLM pra decisão clínica final** — guardrail
   layer, sempre.
5. **Não vamos escalar tudo pra humano** — Sofia decide quando vale,
   com critério explícito (não "achismo").
6. **Não vamos fazer feature flag everywhere** — flag de migração
   sim, flag de feature de produto não.
7. **Não vamos otimizar prematuramente** — Redis Streams chega até
   1M ops/sec; só migra pra Kafka quando dor real surgir.
8. **Não vamos persistir PII clínico em logs** — redaction layer
   antes de structured log; audit log persiste mas tem retention
   policy LGPD.
9. **Não vamos deixar Sofia executar tool sem `idempotency_key`**
   — protege contra retry/loop.
10. **Não vamos lançar sem replay engine** — debug em produção exige.

---

## 16. Próximos passos imediatos

1. **Você revisa este doc** e confirma decisões pendentes (§13)
2. **Eu refatoro o doc anterior** `SUPER_SOFIA_ARCHITECTURE.md` pra
   ser apenas um pointer pra este (evita confusão)
3. **Definimos juntos a ordem das phases A-E** (talvez priorizar
   uma ordem diferente conforme valor comercial vs técnico)
4. **Começamos Phase A** — Foundations (migrations + identity +
   tenant resolver + cost log)

Não vou codar nada sem teu sign-off do design. Quer que eu refine
alguma seção específica antes de você revisar inteira?
