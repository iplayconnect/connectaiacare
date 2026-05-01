# Phase D · Admin UX · Manual operacional

> Status: implementada na branch `feat/super-sofia-phase-d-admin-ux`.
> Phase D dá visibilidade pra leads e handoffs capturados pela
> Super Sofia (Phase C). Sem isso, leads ficam invisíveis no DB.

---

## O que entra com Phase D

### Backend (3 blueprints)

| Blueprint | Endpoints |
|---|---|
| `admin_leads_routes` | `GET /api/admin/leads`, `GET /api/admin/leads/<id>`, `PATCH /api/admin/leads/<id>`, `GET /api/admin/leads/stats` |
| `admin_handoff_routes` | `GET /api/admin/handoff`, `GET /api/admin/handoff/<id>`, `POST /api/admin/handoff/<id>/claim`, `POST /api/admin/handoff/<id>/resolve`, `GET /api/admin/handoff/stats` |
| `admin_conversations_routes` | `GET /api/admin/conversations/by-phone/<phone>`, `GET /api/admin/conversations/by-trace/<trace>`, `GET /api/admin/conversations/recent` |

### Frontend (3 páginas)

| Página | Função |
|---|---|
| `/admin/system/operations/leads` | Funil B2B/B2C, filtros, drawer com timeline + ações (qualificar / descartar / nota) |
| `/admin/system/operations/handoff` | Fila de atendimento humano, prioridades P1/P2/P3, claim + resolve |
| `/admin/system/conversations` | Replay por phone ou trace_id; lista de phones com atividade recente |

### Sidebar (3 itens novos)

Grupo **Sistema · Cross-tenant**:
- Leads · Funil (super_admin + admin_tenant)
- Handoff · Atendimento Humano (super_admin + admin_tenant + medico + enfermeiro)
- Conversas · Replay (super_admin + admin_tenant)

---

## Como aplicar em produção

```bash
ssh root@72.60.242.245 "cd /root/connectaiacare && git pull"
ssh root@72.60.242.245 "cd /root/connectaiacare && \
  docker compose up -d --build api frontend"
```

## Smoke test

```bash
# 1. Endpoint leads
ssh root@72.60.242.245 "docker exec connectaiacare-api curl -s \
  http://localhost:5055/api/admin/leads/stats?days=30 | head -50"

# 2. Página leads (status code)
curl -sI https://care.connectaia.com.br/admin/system/operations/leads | head -3

# 3. Lead capturado (Phase C smoke real)
ssh root@72.60.242.245 "docker exec connectaiacare-postgres \
  psql -U postgres -d connectaiacare -c \
  \"SELECT phone, full_name, intent, status FROM aia_health_leads ORDER BY created_at DESC LIMIT 5\""
```

## Próximas Phases

- **C v2**: sub-agents dedicados pros perfis identificados (clinical, caregiver, family). Substituem PassthroughSofiaAgent.
- **E**: métricas Prometheus, multi-instance Evolution real, stress test, particionamento Postgres mensal de audit_log + llm_cost_log.
