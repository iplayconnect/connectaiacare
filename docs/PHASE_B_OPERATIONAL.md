# Phase B · Event Bus + Workers · Manual operacional

> Status: implementada na branch `feat/super-sofia-phase-b-event-bus`.
> Phase B torna o webhook **assíncrono** (resposta <100ms sempre)
> e introduz worker pool pra processar mensagens horizontalmente.
>
> Phase B preserva 100% do comportamento atual de produção via
> compat layer no `sofia-inbound-worker` que chama o
> `pipeline.handle_webhook` legado.

---

## O que entra com Phase B

| Componente | Arquivo | Função |
|---|---|---|
| EventBus service | `backend/src/services/event_bus.py` | Wrapper Redis Streams: publish/consume/ack/nack/DLQ |
| Idempotency helper | `backend/src/services/idempotency.py` | SETNX pra dedupe message_id |
| Webhook async v2 | `backend/src/handlers/webhook_async_routes.py` | `POST /webhook/whatsapp/v2/<instance>` |
| sofia-inbound-worker | `backend/src/workers/sofia_inbound_worker.py` | Consome `sofia:inbound`, chama pipeline legado |
| delivery-worker | `backend/src/workers/delivery_worker.py` | Consome `sofia:outbound`, manda Evolution |
| docker-compose updates | adiciona 2 services workers | escala via `replicas` |

---

## Streams Redis

| Stream | Producer | Consumer | Uso |
|---|---|---|---|
| `sofia:inbound` | webhook v2 | sofia-inbound-worker | Mensagens recebidas pra processar |
| `sofia:outbound` | orchestrator (Phase C) | delivery-worker | Mensagens pra enviar via Evolution |
| `sofia:tools` | (futuro Phase C) | tool-executor (futuro) | Tool calls assíncronos |
| `sofia:handoff` | (futuro Phase C) | handoff-notifier (futuro) | Pra Central 24h |
| `sofia:audit` | broadcast | audit-writer (futuro) | Audit log async |

Cada stream tem `{stream}:dlq` (dead letter queue) pra eventos que
falharam após `max_delivery=5` retries.

---

## Garantias

- **At-least-once delivery** (eventos podem ser re-entregues)
- **Manual ack** (XACK só após processar com sucesso)
- **Reclaim de idle** (worker que crashou: outro worker pega)
- **DLQ após N retries** (max_delivery=5)
- **Stream trim** (XADD MAXLEN ~100k entries por stream)
- **Idempotência por message_id** (Redis SETNX TTL 24h no webhook)

Workers **devem ser idempotentes** porque eventos podem ser
re-entregues. A migração da Phase B preserva isso porque o
`pipeline.handle_webhook` legado já tem dedupe de eventos via
care_event status checks.

---

## Como aplicar em produção

### 1. Pull main + rebuild

```bash
ssh root@72.60.242.245 "cd /root/connectaiacare && git pull"
ssh root@72.60.242.245 "cd /root/connectaiacare && \
  docker compose up -d --build api sofia-inbound-worker delivery-worker"
```

Importante: `api` precisa rebuild pra carregar o novo blueprint
(`webhook_async_routes`) + os services novos.

### 2. Configurar Evolution pra postar em `/v2/<instance>`

Hoje a Evolution posta em `/webhook/whatsapp` (síncrono legado).
Pra ativar Phase B:

1. Decidir o `instance_name` (hoje é `v6` por env `EVOLUTION_INSTANCE`).
2. Setar campo `whatsapp_evolution_instance` em `aia_health_tenants`
   pra cada tenant que receberá Zap (mesmo nome da Evolution).
3. Configurar Evolution pra postar em
   `https://demo.connectaia.com.br/webhook/whatsapp/v2/v6`
   (ou o `instance` que estiver usando).

**Migração gradual recomendada**:
- Mantém `/webhook/whatsapp` (síncrono) ATIVO no Evolution.
- Quando v2 estiver validado, troca a config Evolution → `/v2/<instance>`.
- Se algo der errado, volta pra URL antiga com 1 click no Evolution.

### 3. Smoke test

```bash
# 1. Streams criadas? (worker cria automaticamente no startup)
ssh root@72.60.242.245 "docker exec connectaiacare-redis redis-cli -n 5 XINFO STREAM sofia:inbound" 2>&1 | head -10

# 2. Worker rodando?
ssh root@72.60.242.245 "docker ps | grep sofia-inbound-worker"

# 3. Webhook v2 responde?
ssh root@72.60.242.245 "curl -sX POST -H 'Content-Type: application/json' \
  -d '{\"event\":\"messages.upsert\",\"data\":{\"key\":{\"id\":\"smoke-test-1\",\"remoteJid\":\"5551999999999@s.whatsapp.net\",\"fromMe\":false},\"message\":{\"conversation\":\"smoke phase B\"}}}' \
  http://api:5055/webhook/whatsapp/v2/v6"
```

Esperado:
```json
{"status":"queued","trace_id":"...","stream_entry_id":"..."}
```

### 4. Verificar event flowing

```bash
# Inbound stream tem o evento?
ssh root@72.60.242.245 "docker exec connectaiacare-redis redis-cli -n 5 XLEN sofia:inbound"

# Worker processou e ack'd?
ssh root@72.60.242.245 "docker exec connectaiacare-redis redis-cli -n 5 XPENDING sofia:inbound sofia-inbound-cg"
# pending=0 = tudo ack'd

# Audit log
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"
SELECT action, payload, created_at FROM aia_health_audit_log
WHERE action LIKE 'webhook%' ORDER BY created_at DESC LIMIT 5\""
```

---

## Métricas/observability

- Logs estruturados: `webhook_v2_queued`, `sofia_inbound_processed`,
  `delivery_sent`, `event_bus_dlq`.
- DLQ inspection: `XRANGE sofia:inbound:dlq - +` mostra tudo que
  falhou com `delivery_count > 5`.
- Pending count: `XPENDING sofia:inbound sofia-inbound-cg`.
- Phase B.6 adiciona Prometheus metrics (`sofia_messages_total`,
  `sofia_inbound_processing_duration_seconds`, etc) — implementação
  futura.

---

## Rollback

Webhook async é **opt-in via Evolution config**. Pra desligar Phase B
no run-time:

```bash
# Variante 1: feature flag
ssh root@72.60.242.245 "cd /root/connectaiacare && \
  docker compose exec api sh -c 'export ASYNC_WEBHOOK_ENABLED=false'"
# (na prática: editar .env + restart api)

# Variante 2: voltar Evolution pra /webhook/whatsapp legado
# (config no painel da Evolution API)
```

Workers podem rodar parados (consumer groups vazios) sem prejuízo —
streams expiram via XTRIM ~100k entries.

---

## Próximas Phases

- **C** · Super Sofia orchestrator: substitui o pipeline legado dentro
  do `sofia-inbound-worker.process_entry`. Sub-agents profile-aware,
  memory layers, intent classifier, tools.
- **D** · Admin UX: `/admin/system/conversations` (live + replay),
  `/admin/system/operations/leads`, `/admin/system/operations/handoff`.
- **E** · Hardening: scale, multi-instance Evolution real, stress
  test 30k msgs/dia, particionamento Postgres.
