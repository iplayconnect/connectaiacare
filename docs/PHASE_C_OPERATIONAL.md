# Phase C · Super Sofia Orchestrator (v1) · Manual operacional

> Status: implementada na branch `feat/super-sofia-phase-c-orchestrator`.
> **Phase C v1 cobre o caminho do lead anônimo** (commercial + support),
> que é o gap mais doloroso da auditoria. Perfis identificados
> (cuidador, médico, etc.) continuam no pipeline legado via
> PassthroughSofiaAgent — zero regressão clínica.

---

## O que entra com Phase C v1

| Componente | Arquivo |
|---|---|
| WhatsApp Intent Classifier | `backend/src/services/whatsapp_intent_classifier.py` |
| Base agent abstrato | `backend/src/services/sofia_agents/base.py` |
| CommercialSofiaAgent | `backend/src/services/sofia_agents/commercial.py` |
| SupportSofiaAgent | `backend/src/services/sofia_agents/support.py` |
| PassthroughSofiaAgent | `backend/src/services/sofia_agents/passthrough.py` |
| Sub-agent factory | `backend/src/services/sofia_agents/factory.py` |
| Tools (capture_lead, schedule_demo, escalate_to_human_whatsapp) | `backend/src/services/sofia_tools.py` |
| **SuperSofiaOrchestrator** | `backend/src/services/super_sofia_orchestrator.py` |
| LLM routing tasks novas | `backend/config/llm_routing.yaml` (3 tasks) |
| Worker integration | `backend/src/workers/sofia_inbound_worker.py` |
| Tests unit | `backend/tests/test_sofia_orchestrator.py` |

---

## Fluxo Phase C v1

```
inbound (Phase B sofia:inbound stream)
    ↓
sofia_inbound_worker.process_entry()
    ↓
SUPER_SOFIA_ENABLED=true (default) → SuperSofiaOrchestrator.process()
    ↓
1. Extract phone/text do payload Evolution
2. TenantResolver.by_id() ou .central() (fallback)
3. IdentityResolver.resolve(phone, tenant_id) — Phase A
4. Active context cross-channel (45min)
5. Anonymous? → IntentClassifier (DeepSeek V4-Flash)
6. Factory: get_agent_for(is_anonymous, profile, intent) → sub-agent
7. agent.process(ctx) → AgentResponse (text + tools + handoff)
8. Anti-hallucination guardrail (chat-friendly)
9. Execute tools (capture_lead/schedule_demo/escalate)
10. Publish response em sofia:outbound (delivery worker manda)
    ↓
Se response.next_action == 'passthrough_legacy':
    pipeline.handle_webhook() ← compat layer (cuidador/médico/etc)
```

---

## Sub-agents implementados (v1)

### CommercialSofiaAgent
- **Quando**: phone anônimo + intent in (interesse_servico_b2c, _b2b, agendar_demo, unclear, spam_abuso)
- **Tools**: capture_lead, schedule_demo, escalate_to_human_whatsapp
- **Tom**: brasileiro coloquial profissional, curto, empático
- **NÃO faz**: prometer preço, fechar venda, falar de contrato

### SupportSofiaAgent
- **Quando**: phone anônimo + intent suporte_cliente
- **Tools**: escalate_to_human_whatsapp
- **Tom**: acolhedor, triagem rápida → escala
- **NÃO faz**: reset senha, dar suporte clínico

### PassthroughSofiaAgent
- **Quando**: phone identificado (cuidador, médico, familia, paciente B2C, admin)
- **Comportamento**: NÃO responde — sinaliza pro worker chamar pipeline.handle_webhook legado
- **Phase C v2**: substituir cada um por sub-agent dedicado

---

## Tools (v1)

### capture_lead
```python
capture_lead(
    phone="5511...", intent="interesse_servico_b2b",
    full_name="João Silva", email="...", organization="ILPI XYZ",
    role_self_declared="gestor_ilpi", confidence=0.85,
)
```
Cria/atualiza row em `aia_health_leads`. Idempotente por phone+intent na última hora.

### schedule_demo
```python
schedule_demo(phone="...", full_name="...", organization="...")
```
Atualiza lead pra status='demo_scheduled'. Phase C v1: link genérico
ConnectaLive (`https://connectaiacare.com.br/agendar-demo`). Phase C v2:
integração real com módulo ConnectaLive (cria sala + Calendar invite).

### escalate_to_human_whatsapp
```python
escalate_to_human_whatsapp(
    phone="...", reason="lead_high_value",
    summary="Lead da ILPI XYZ pediu proposta detalhada",
    urgency="P2",  # P1 <5min, P2 <30min, P3 <2h
)
```
- Cria entry em `aia_health_human_handoff_queue`
- Publica msg pro Central 24h (5551997354484) via `sofia:outbound`
- Idempotente: 1 handoff por phone por hora

---

## Anti-hallucination guardrail

Portado de voice (já implementado em produção em
`grok_call_session.py`). Aplica-se a Sofia comercial/support porque
elas NÃO devem inventar dado clínico.

Se response.text contém padrão clínico (idade específica, PA, glicemia,
medicação, dose, condição, alergia) E nenhuma tool válida foi
chamada → substitui texto por mensagem segura genérica + audit log
`hallucination_replaced`.

---

## Feature flag

```bash
# Liga Phase C (default)
SUPER_SOFIA_ENABLED=true

# Desliga (worker volta 100% pro pipeline legado)
SUPER_SOFIA_ENABLED=false
```

Rollback é só env var + restart worker.

---

## Como aplicar em produção

### 1. Pull main + rebuild

```bash
ssh root@72.60.242.245 "cd /root/connectaiacare && git pull"
ssh root@72.60.242.245 "cd /root/connectaiacare && \
  docker compose up -d --build api sofia-inbound-worker delivery-worker"
```

### 2. Smoke test — phone anônimo (vira lead)

```bash
ssh root@72.60.242.245 "docker exec connectaiacare-api curl -sX POST \
  -H 'Content-Type: application/json' \
  -d '{\"event\":\"messages.upsert\",\"data\":{\"key\":{\"id\":\"phaseC-smoke-001\",\"remoteJid\":\"5511987654321@s.whatsapp.net\",\"fromMe\":false},\"message\":{\"conversation\":\"Boa tarde, sou diretor de uma ILPI em São Paulo, queria conhecer a plataforma de vocês\"}}}' \
  -w '\nlatency=%{time_total}s\n' \
  http://localhost:5055/webhook/whatsapp/v2/Connectaiacare"

# Ver logs do worker (deve mostrar super_sofia_handled)
ssh root@72.60.242.245 "docker logs connectaiacare-sofia-inbound-worker-1 --tail 30 2>&1 | grep -E 'super_sofia|intent|agent_turn'"

# Ver lead criado
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"
SELECT id, phone, full_name, intent, status, created_at
FROM aia_health_leads ORDER BY created_at DESC LIMIT 3\""
```

### 3. Smoke test — phone identificado (passthrough legado)

```bash
ssh root@72.60.242.245 "docker exec connectaiacare-api curl -sX POST \
  -H 'Content-Type: application/json' \
  -d '{\"event\":\"messages.upsert\",\"data\":{\"key\":{\"id\":\"phaseC-smoke-passthrough\",\"remoteJid\":\"5551984928518@s.whatsapp.net\",\"fromMe\":false},\"message\":{\"conversation\":\"oi\"}}}' \
  http://localhost:5055/webhook/whatsapp/v2/Connectaiacare"

# Logs devem mostrar passthrough_legacy
ssh root@72.60.242.245 "docker logs connectaiacare-sofia-inbound-worker-1 --tail 20 2>&1 | grep passthrough"
```

---

## Próximas Phases

- **C v2**: Sub-agents dedicados pra clinical/caregiver/family/
  patient_b2c/admin (substituem passthrough). Tool-use loop multi-turn.
- **D**: Admin UX (`/admin/system/operations/leads`,
  `/admin/system/operations/handoff`, conversations live + replay).
- **E**: Hardening, métricas Prometheus, multi-instance Evolution
  real, stress test 30k msgs/dia, particionamento Postgres.
