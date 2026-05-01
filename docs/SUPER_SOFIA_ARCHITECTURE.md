# Super Sofia — Orquestrador WhatsApp multi-tenant

> Resolve os 5 gaps da auditoria de 2026-05-01 com uma única
> arquitetura: WhatsApp como canal principal, phone como chave de
> identidade, Sofia como orquestrador inteligente que decide o
> fluxo certo (clínico, comercial, suporte) e sabe quando passar
> pra humano.
>
> Branch: `feat/super-sofia-whatsapp-orchestrator`
> Status: em execução

---

## 1. Princípio central

**O `phone E.164` (com DDI 55) é a chave primária de identidade no
WhatsApp.** A partir dele, Super Sofia resolve:

```
phone (E.164)
  └─→ tenant_id  (qual cliente da plataforma)
      └─→ profile (qual papel: paciente, cuidador, médico,
                   familiar, parceiro, comercial não-cadastrado)
          └─→ context (memória, paciente associado, eventos ativos,
                      conversa em andamento)
              └─→ flow (qual handler: clínico, onboarding, comercial,
                       suporte, escalate)
```

Quando phone NÃO é encontrado em nenhum registro, **Super Sofia
assume que é um lead frio** e entra em fluxo comercial/suporte.

---

## 2. Fluxograma completo

```
WhatsApp inbound → /webhook/whatsapp
   ↓
[Super Sofia Router]
   │
   ├─ 1. Resolve phone → identity
   │   • aia_health_users.phone     → super_admin/admin/medico/etc
   │   • aia_health_caregivers.phone → cuidador profissional
   │   • aia_health_patients.responsible[].phone → familiar
   │   • aia_health_patients (proactive_call_phone) → paciente B2C
   │   • Não encontrado → identity = anonymous
   │
   ├─ 2. Se identidade resolvida → roteia por (profile + intent)
   │   • Cuidador + áudio → pipeline clínico atual (preserva)
   │   • Cuidador + texto + evento ativo → follow-up (preserva)
   │   • Médico/enfermeiro + texto → Sofia chat clínico
   │   • Familiar + texto → Sofia chat família (status do idoso)
   │   • Paciente B2C → Sofia chat suporte/companhia
   │   • Parceiro → Sofia chat parceiro (info da integração)
   │   • Super_admin/admin → Sofia chat livre (todas tools)
   │
   └─ 3. Se identidade = anonymous → intent_classifier
       (DeepSeek V4-Flash, ~$0.001/call)
       • interesse_servico → Sofia comercial → captura lead
       • agendar_demo → Sofia comercial → tool schedule_demo
       • suporte_cliente → pergunta tenant + escalate humano
       • spam/abuso → silencia + audit log
       • unclear → Sofia faz pergunta clarificadora aberta

   Em qualquer fluxo, Sofia tem tool escalate_to_human →
   - Salva contexto na fila aia_health_human_handoff_queue
   - Notifica Central ConnectaIACare 24h: 5551997354484
   - Responde ao usuário: "Vou passar pra atendente, você
     receberá retorno em até X minutos pelo número Central"
```

---

## 3. Componentes a criar

### 3.1 — `phone_identity_resolver` (service)

```python
def resolve_whatsapp_identity(phone: str) -> dict:
    """
    Retorna: {
      "phone": "5551984928518",           # normalizado E.164 BR
      "matches": [                         # pode ser >1 (multi-perfil)
        {"tenant_id": "...", "profile": "medico", "user_id": "...",
         "full_name": "Dr. Henrique", "match_source": "users.phone"},
        ...
      ],
      "primary": {...},                    # match preferencial (mais alto)
      "is_anonymous": False
    }
    """
```

Ordem de prioridade pra match (do mais forte pro mais fraco):
1. `aia_health_users.phone`        (auth identity)
2. `aia_health_caregivers.phone`   (cuidador profissional)
3. `aia_health_patients.proactive_call_phone` (paciente direto)
4. `aia_health_patients.responsible[*].phone` (familiar)
5. Não encontrado → anonymous

Multi-tenant: se mesmo phone aparece em 2 tenants, retorna ambos
matches em `matches[]`. Super Sofia pergunta ao usuário ou usa
heurística (último ativo).

### 3.2 — `intent_classifier` (service)

DeepSeek V4-Flash classifica em buckets fixos. Reusa `LlmRouter`
task=`intent_classifier` que já existe no codebase (usado pelo
onboarding service, comprovadamente robusto).

Buckets pra phone anonymous:
```
{
  "intent": "interesse_servico" | "agendar_demo" |
            "suporte_cliente" | "spam_abuso" | "unclear",
  "confidence": 0.0-1.0,
  "reasoning": "..."
}
```

Pra phone identificado, intent é OPCIONAL (Sofia chat já trata
livremente). Mas dispara classificador também pra casos ambíguos
(ex: paciente B2C dizendo "quero cancelar" → escalation comercial).

### 3.3 — `super_sofia_router` (orquestrador novo)

Substitui o `_handle_text` atual do pipeline. Mantém compatibilidade
preservando os ramos existentes (medicação, sessão legada, care
event ativo) — mas adiciona o ramo "anonymous → intent" e o ramo
"identidade resolvida → Sofia chat por profile".

### 3.4 — `super_sofia_chat` (LLM-powered chat WhatsApp)

Equivalente texto da Sofia voz. Multi-turn em `aia_health_sofia_sessions`
channel=whatsapp. Tools restritas por profile:

| Profile | Tools |
|---|---|
| medico/enfermeiro | search_patients, get_patient_summary, list_medication_schedules, get_patient_vitals, query_drug_rules, check_drug_interaction, check_medication_safety, escalate_to_human |
| cuidador_pro | search_patients, get_patient_summary, create_care_event, schedule_teleconsulta, escalate_to_human |
| familia | get_patient_summary (read-only do próprio idoso), schedule_teleconsulta, escalate_to_human |
| paciente_b2c | escalate_to_human, schedule_teleconsulta |
| parceiro | (apenas RAG da integração + escalate) |
| admin/super_admin | tudo |
| anonymous (lead) | capture_lead, schedule_demo, escalate_to_human |

### 3.5 — Tabela `aia_health_leads` (migration)

```sql
CREATE TABLE aia_health_leads (
  id UUID PRIMARY KEY,
  phone TEXT NOT NULL,
  full_name TEXT,
  email TEXT,
  organization TEXT,
  role_self_declared TEXT,    -- 'gestor_ilpi' | 'medico' | 'familiar' | 'parceiro' | 'outro'
  intent TEXT NOT NULL,       -- intent_classifier output
  source_channel TEXT NOT NULL DEFAULT 'whatsapp',
  source_metadata JSONB,      -- utm, referrer, primeira mensagem
  status TEXT NOT NULL DEFAULT 'new',  -- new|qualified|in_demo|converted|lost
  notes JSONB,                -- log de turns relevantes
  qualified_at TIMESTAMPTZ,
  converted_to_tenant_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.6 — Tabela `aia_health_human_handoff_queue` (migration)

```sql
CREATE TABLE aia_health_human_handoff_queue (
  id UUID PRIMARY KEY,
  phone TEXT NOT NULL,
  tenant_id TEXT,           -- null = lead/anonymous
  reason TEXT NOT NULL,
  context_summary TEXT,     -- Sofia escreveu resumo
  conversation_log JSONB,
  triggered_by TEXT NOT NULL DEFAULT 'sofia',
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|claimed|resolved
  assigned_to_user_id UUID,
  notified_central_at TIMESTAMPTZ,         -- quando avisamos Central 24h
  created_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);
```

### 3.7 — Tools novas

- **`capture_lead`**: Sofia chama quando coletou dados (nome,
  empresa, papel, dor) → insert em `aia_health_leads`.
- **`escalate_to_human_whatsapp`**: argumentos `(reason, summary,
  urgency)` → insert em `human_handoff_queue` + envia mensagem
  pro Central 24h `5551997354484` com link/resumo.
- **`schedule_demo`**: gera link Calendly com pré-fill (V1 manual,
  V2 integração API).

### 3.8 — Frontend `/admin/system/operations/leads`

- Tabela com filtros por status, intent, idade.
- Drawer de detalhe com conversation log.
- Ações: marcar qualificado, converter pra tenant (link pro
  wizard), descartar.

### 3.9 — Frontend `/admin/system/operations/handoff`

- Fila de pedidos de atendimento humano.
- Status, contexto, assigned_to.
- "Reivindicar" (claim) → assigned_to_user_id = current.

---

## 4. Roteamento multi-tenant

Hoje `settings.tenant_id` é fixo (`connectaiacare_demo`). Pra
multi-tenant via WhatsApp:

1. Mensagem chega em Evolution → webhook recebe `instance_name`.
2. Lookup: `aia_health_tenants WHERE whatsapp_evolution_instance = X` →
   tenant.
3. Cada tenant pode ter sua própria instância Evolution (ou compartilhar).
4. Phone resolver então faz lookup **dentro daquele tenant** primeiro.
5. Anonymous (não encontrado em nenhum tenant) → roteia pro tenant
   "central" (`connectaiacare_demo` por enquanto, depois um
   `connectaiacare_central` dedicado).

---

## 5. Central ConnectaIACare 24h

**Número operacional**: `5551997354484` (51 99735-4484)

Função:
- Quando `escalate_to_human_whatsapp` dispara, Sofia manda **2
  mensagens via Evolution**:
  1. Pro **usuário**: "Vou passar pra atendente. Você receberá
     retorno em até X minutos pelo número Central +55 51 99735-4484
     ou por aqui mesmo."
  2. Pro **Central**: "[NOVO HANDOFF] phone X, motivo Y, resumo Z.
     Conversa completa: link admin. Reivindicar em
     /admin/system/operations/handoff."

Quando humano da Central reivindica, Sofia para de responder
naquele phone até o status voltar pra `resolved`.

---

## 6. Fases de execução (refinadas, atacando 5 gaps em paralelo)

| Fase | Componente | Resolve gap | Tempo |
|---|---|---|---|
| **1** | Migrations: `leads` + `handoff_queue` | infra | 1h |
| **2** | `phone_identity_resolver` | G1, G2, G5 | 3h |
| **3** | `intent_classifier` (reuse LlmRouter task) | G1, G3 | 2h |
| **4** | `super_sofia_router` (orquestrador novo) | G1, G2, G4, G5 | 4h |
| **5** | `super_sofia_chat` service (multi-turn) | G4 | 4h |
| **6** | Tools: `capture_lead`, `escalate_to_human_whatsapp`, `schedule_demo` | G3 | 3h |
| **7** | Integração no `pipeline.handle_webhook` | tudo | 2h |
| **8** | Frontend `/admin/system/operations/leads` | UX | 3h |
| **9** | Frontend `/admin/system/operations/handoff` | UX | 3h |
| **10** | Multi-tenant routing por instance Evolution | G5 | 2h |
| **11** | Smoke tests E2E | todos | 2h |
| **12** | Deploy + audit | — | 1h |

**Total**: ~30h efetivas. Realisticamente 3-4 dias úteis de trabalho
focado. Bate com a janela "antes de testes reais semana que vem".

### Estratégia de commits

Cada fase = 1 commit (ou 2-3 se fizer sentido separar). PRs
agrupando logicamente:
- **PR A**: Migrations + resolver + classifier + router (núcleo
  infra) — Fases 1-4
- **PR B**: Super Sofia chat + tools + integração (núcleo
  conversa) — Fases 5-7
- **PR C**: Frontend leads + handoff (UX admin) — Fases 8-9
- **PR D**: Multi-tenant routing + smoke tests + deploy — Fases 10-12

PRs atomicas merguem em paralelo se não tiverem dependência cruzada
(A → B → C; D depende de B). Cada PR é revisável em <30min.

---

## 7. Decisões pendentes (Alexandre confirmar antes de codar)

1. **Multi-tenant central**: Phone anonymous cai em
   `connectaiacare_demo` ou criamos tenant `connectaiacare_central`
   dedicado pra leads frios? Recomendo **central dedicado** (limpa
   métricas).

2. **Resposta automática quando phone está em handoff**: Sofia
   silencia 100% (humano assume) ou só sinaliza "atendente está
   comigo, pode mandar mensagens que repasso"? Recomendo **silenciar**
   pra não confundir.

3. **Horário comercial vs 24h**: Central 24h significa Sofia escala
   a qualquer hora pro humano? Ou madrugada Sofia diz "atendente
   responde de manhã, mas pode deixar mensagem"? Recomendo **24h
   real** (você disse Central 24h).

4. **Captura de email de lead**: Pedimos no fluxo conversacional ou
   só nome/empresa/dor + a Central pega email depois? Recomendo
   **pedir email** durante conversa (reduz fricção do humano).

5. **Schedule demo**: Calendly é o que você usa? Tem link público
   pra onboarding ou personalizado por vendedor? Pra Fase 4 só
   preciso saber qual link inserir.

---

## 8. Riscos

- **Não quebrar fluxo cuidador atual** (31 care_events em 30d
  dependem dele). `super_sofia_router` preserva ordem dos ramos
  existentes.
- **Falsa identificação**: phone que coincidir com cuidador antigo
  desativado — resolver tem que filtrar por `active=TRUE`.
- **Loop infinito Sofia ↔ Sofia**: Central 24h é phone humano
  cadastrado. Quando Sofia mandar pra ele, webhook NÃO pode achar
  que é cuidador relatando — flag explícita "from_sofia=true" no
  metadata.
- **Custos LLM**: classificador roda em toda mensagem de phone
  anonymous. Rate limit + cache em phones repetidos.
- **Privacy**: lead leva phone até DB sem consent_lgpd explícito.
  Usar mesma flag de `accepted_terms` que onboarding B2C usa, +
  step "concorda em receber retorno?" antes de salvar.

---

## 9. Próximos commits desta branch

1. ✅ Doc arquitetural (este arquivo)
2. Migration leads + handoff
3. phone_identity_resolver
4. intent_classifier (reuse + ajuste)
5. super_sofia_router (orquestrador)
6. super_sofia_chat
7. Tools (capture_lead, escalate_to_human_whatsapp)
8. Integração pipeline
9. Frontend leads
10. Frontend handoff
11. Sidebar + permissions
12. Tests + deploy
