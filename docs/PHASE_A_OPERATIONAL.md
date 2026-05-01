# Phase A · Foundations · Manual operacional

> Status: implementada na branch `feat/super-sofia-whatsapp-orchestrator`.
> Phase A é puramente infra — **zero impacto no comportamento de
> produção**. Prepara o terreno pras Phases B-E.

---

## O que entra com Phase A

| Componente | Arquivo | Função |
|---|---|---|
| Migration | `backend/migrations/061_super_sofia_foundation.sql` | 6 tabelas novas + extensões + tenant central + triggers imutabilidade |
| Redis client compartilhado | `backend/src/services/redis_client.py` | Pool singleton |
| IdentityResolver | `backend/src/services/identity_resolver.py` | Phone → Identity (5 fontes de match) |
| TenantResolver | `backend/src/services/tenant_resolver.py` | Instance/DID → Tenant + cache |
| LlmCostTracker | `backend/src/services/llm_cost_tracker.py` | Custo de cada call LLM + agregações |
| Audit log writer | `backend/src/services/audit_log_writer.py` | Append-only + redact PII helpers |

---

## Esquema novo (migration 061)

| Tabela | Propósito | Volume estimado |
|---|---|---|
| `aia_health_user_phone_history` | Phones antigos de users/caregivers/patients | dezenas |
| `aia_health_leads` | Funil B2B/B2C capturado | centenas/mês |
| `aia_health_human_handoff_queue` | Pedidos pra atendente humano | dezenas/dia |
| `aia_health_tenant_policies` | Rate limit, quotas, scopes por tenant | 1 por tenant |
| `aia_health_llm_cost_log` | Custo de cada LLM call | ~10k/dia (10k msgs * 1-2 calls) |
| `aia_health_audit_log` | Audit imutável (append-only via trigger) | ~30k/dia |

Extensões em `aia_health_sofia_sessions`:
- `active_channels TEXT[]`
- `sub_agent TEXT`
- `handoff_id UUID FK`
- `context_continuation_window_minutes INT DEFAULT 45`
- `trace_ids UUID[]`

Tenant novo:
- `connectaiacare_central` — pra phones anônimos / leads.

---

## Como aplicar em produção

### 1. Pull main + rebuild

```bash
ssh root@72.60.242.245 "cd /root/connectaiacare && git pull"
ssh root@72.60.242.245 "cd /root/connectaiacare && docker compose up -d --build api"
```

### 2. Aplicar migration

```bash
ssh root@72.60.242.245 \
  "docker exec -i connectaiacare-postgres \
     psql -U postgres -d connectaiacare \
     < /root/connectaiacare/backend/migrations/061_super_sofia_foundation.sql"
```

Esperado:
- `CREATE TABLE` ×6
- `CREATE INDEX` ×N
- `CREATE FUNCTION` ×2 (immutability + touch_updated_at)
- `CREATE TRIGGER` ×4
- `INSERT 0 1` (tenant central)
- `INSERT 0 1` (tenant central policy)

### 3. Smoke test

```bash
# IdentityResolver: phone do Henrique deve resolver pra admin_tenant
ssh root@72.60.242.245 "docker exec -w /app -e PYTHONPATH=/app connectaiacare-api \
  python -c \"
from src.services.identity_resolver import get_identity_resolver
r = get_identity_resolver().resolve('5551984928518')
print(r.to_dict())
\""

# TenantResolver: tenant central deve existir
ssh root@72.60.242.245 "docker exec -w /app -e PYTHONPATH=/app connectaiacare-api \
  python -c \"
from src.services.tenant_resolver import get_tenant_resolver
print(get_tenant_resolver().central().to_dict())
\""

# Audit log: insert + tenta UPDATE (deve falhar)
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"
INSERT INTO aia_health_audit_log (action, actor, payload)
VALUES ('phase_a_smoke_test', 'system', '{\"note\":\"smoke\"}'::jsonb);
\""

ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"
UPDATE aia_health_audit_log SET action='hacked' WHERE action='phase_a_smoke_test';
\""
# Esperado: ERROR: aia_health_audit_log is append-only — UPDATE rejected
```

### 4. Rodar testes unitários

```bash
ssh root@72.60.242.245 "docker exec -w /app -e PYTHONPATH=/app connectaiacare-api \
  python -m pytest tests/test_identity_resolver.py tests/test_audit_log_writer.py \
                   tests/test_llm_cost_tracker.py -v"
```

---

## Rollback

Migration é idempotente (todos `IF NOT EXISTS`), mas se precisar
reverter completamente:

```sql
-- Em ordem reversa pra não bater em FK:
ALTER TABLE aia_health_sofia_sessions
  DROP COLUMN IF EXISTS active_channels,
  DROP COLUMN IF EXISTS sub_agent,
  DROP COLUMN IF EXISTS handoff_id,
  DROP COLUMN IF EXISTS context_continuation_window_minutes,
  DROP COLUMN IF EXISTS trace_ids;

DROP TABLE IF EXISTS aia_health_audit_log CASCADE;
DROP TABLE IF EXISTS aia_health_llm_cost_log;
DROP TABLE IF EXISTS aia_health_tenant_policies;
DROP TABLE IF EXISTS aia_health_human_handoff_queue;
DROP TABLE IF EXISTS aia_health_leads;
DROP TABLE IF EXISTS aia_health_user_phone_history;

DELETE FROM aia_health_tenants WHERE id = 'connectaiacare_central';

DROP FUNCTION IF EXISTS aia_health_audit_log_immutable();
DROP FUNCTION IF EXISTS aia_health_touch_updated_at();
```

Não há código consumindo essas tabelas em prod ainda — Phase A é
puramente preparatória. Rollback é seguro.

---

## Próximas Phases

| Phase | Escopo | PR sugerida |
|---|---|---|
| **B** | Event bus Redis Streams + worker pool dedicado | feat/super-sofia-event-bus |
| **C** | Super Sofia orchestrator + sub-agents profile-aware + tools | feat/super-sofia-orchestrator |
| **D** | Admin UX (conversations, leads, handoff, cost, replay) | feat/super-sofia-admin-ux |
| **E** | Hardening + escala + multi-instance Evolution + stress test | feat/super-sofia-hardening |

Cada Phase é mergeable independente. Ordem A → B → C → D → E,
mas D pode rodar parcialmente em paralelo com B/C (frontend
não bloqueia backend).
