# ADR-015: Topologia de redes Docker na Hostinger co-habitada

- **Date**: 2026-04-20
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: infrastructure, networking, security, lgpd
- **Refines**: [ADR-002](002-compartilhar-infra-hostinger-traefik.md) (co-habitação), [ADR-003](003-postgres-compartilhado-database-separado.md) (PG dedicado)

## Context and Problem Statement

ADR-002 decidiu que o ConnectaIACare co-habita a VPS Hostinger com o ConnectaIA SaaS, e ADR-003 decidiu por um container PostgreSQL dedicado. O `docker-compose.yml` do MVP inicial usava uma única rede bridge local `connectaiacare_net` com portas expostas no host (`5433:5432` para Postgres, `6380:6379` para Redis), desacoplada do Traefik da Hostinger.

Ao preparar o deploy real na Hostinger, identificamos problemas concretos:

1. **Isolamento insuficiente**: PG e Redis expostos em portas do host → qualquer container ou processo na VPS pode tentar alcançá-los. Para dado sensível de saúde (LGPD Art. 11), superfície de ataque deve ser minimizada.
2. **Integração Traefik faltando**: `connectaiacare_net` não tem visibilidade do Traefik (`infra-traefik-1`, rede `infra_proxy`), então os routers `demo.connectaia.com.br` e `care.connectaia.com.br` não funcionariam sem ajuste.
3. **Ambiguidade com múltiplas redes**: quando um container está em mais de uma rede Docker, o Traefik precisa saber em qual delas alcançá-lo.
4. **HTTP não redirecionado para HTTPS**: tráfego claro numa plataforma de saúde é inaceitável.

Precisamos formalizar a topologia de redes Docker que resolve os quatro problemas.

## Decision Drivers

- **LGPD Art. 11 (dado sensível)**: Postgres/Redis com dado de saúde não devem estar acessíveis a nenhum outro serviço do host
- **Reuso do Traefik existente** (ADR-002): zero duplicação de reverse proxy
- **Clareza operacional**: topologia fácil de diagnosticar com `docker network inspect`
- **HTTPS obrigatório**: toda superfície pública em TLS, sem exceção
- **Compatibilidade com Sofia Voice**: a api precisa alcançar a `sofia-service` quando expusermos a Phase 2 (ligação proativa) — Sofia vive na rede do SaaS

## Considered Options

- **Option A**: Uma única rede externa `infra_proxy` (todos containers conectados a ela)
- **Option B**: Dupla rede — `infra_proxy` (external, compartilhada com Traefik) + `connectaiacare_internal` (bridge local dedicada para PG/Redis) (escolhida)
- **Option C**: Três redes — adicional `sofia_bridge` para expor canal controlado com Sofia Voice

## Decision Outcome

Chosen option: **Option B — Dupla rede Docker**.

### Topologia

```
┌──────────────────────────────────────────────────────────────┐
│ VPS Hostinger 72.60.242.245                                 │
│                                                              │
│  ┌──────────────────── infra_proxy (external) ────────┐    │
│  │                                                      │    │
│  │  infra-traefik-1  ←→  connectaiacare-api  ←→  web  │    │
│  │   (80/443 host)      connectaiacare-frontend        │    │
│  │                                                      │    │
│  │  [+ 20 outros containers do SaaS]                   │    │
│  │                                                      │    │
│  └──────────────────────────┼──┼──────────────────────┘    │
│                              │  │                             │
│           ┌──── connectaiacare_internal (bridge) ────┐      │
│           │                                            │      │
│           │  connectaiacare-postgres  (sem port bind) │      │
│           │  connectaiacare-redis     (sem port bind) │      │
│           │  connectaiacare-api       (multi-homed)   │      │
│           │  connectaiacare-frontend  (multi-homed)   │      │
│           │                                            │      │
│           └────────────────────────────────────────────┘      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Regras de conexão

| Container | `infra_proxy` | `connectaiacare_internal` | Porta exposta no host |
|---|---|---|---|
| `connectaiacare-postgres` | ❌ | ✅ | **Nenhuma** (acesso `docker exec` only) |
| `connectaiacare-redis` | ❌ | ✅ | **Nenhuma** |
| `connectaiacare-api` | ✅ | ✅ | Nenhuma (Traefik alcança via `infra_proxy:5055`) |
| `connectaiacare-frontend` | ✅ | ✅ | Nenhuma (Traefik alcança via `infra_proxy:3000`) |

### Labels Traefik críticas

- `traefik.docker.network: "infra_proxy"` em `api` e `frontend` — resolve ambiguidade de rede quando container está em múltiplas redes
- `traefik.http.routers.*-http.middlewares: "*-https-redirect"` — redirect HTTP→HTTPS permanente
- `traefik.http.routers.*.tls.certresolver: "letsencrypt"` — cert automático

### Positive Consequences

- **PG e Redis inacessíveis** para qualquer container fora da rede `connectaiacare_internal` — nenhum container do SaaS (incluindo Sofia, MCP, tiktok-tracker) consegue se conectar.
- **Sem port binding no host** → `ss -tlnp` na VPS não mostra 5432/6379/5055/3000 da ConnectaIACare; atacante que comprometer SSH precisa entrar no container para alcançar o DB.
- **Traefik unificado** — TLS, logs de acesso, rate limiting e IP allowlist (se configurarmos no futuro) aplicam-se uniformemente.
- **HTTP→HTTPS permanente** via redirect — HSTS do backend reforça no navegador.
- **Migração futura para VPS dedicada é trivial**: `docker compose down` aqui + `docker compose up` lá + restore do dump; topologia idêntica só troca se `infra_proxy` é external ou local.

### Negative Consequences

- Containers multi-homed adicionam 1 linha de config (`networks: [infra_proxy, connectaiacare_internal]`) vs rede única.
- Diagnóstico de rede requer saber em qual rede procurar (`docker network inspect infra_proxy` vs `connectaiacare_internal`).
- Acesso ao PG de fora do container (ex: para backup externo ou pgAdmin) exige `docker exec` ou túnel SSH ad-hoc em vez de `psql -h host -p 5433`.

## Pros and Cons of the Options

### Option A — Rede única `infra_proxy` ❌

- ✅ Simplicidade (1 rede só)
- ❌ PG e Redis visíveis para 20+ containers do SaaS — violação clara de menor privilégio
- ❌ Um container do SaaS comprometido pode varrer `5432` em todos os hosts da rede

### Option B — Dupla rede ✅ Chosen

- ✅ Isolamento forte de dado sensível (LGPD)
- ✅ Reuso total do Traefik
- ✅ Multi-homing é idiomatic Docker Compose
- ❌ +1 rede para operar

### Option C — Três redes (adiciona `sofia_bridge`) ❌ Adiado

- ✅ Canal controlado e auditável para Sofia Voice
- ❌ Complexidade prematura — na Phase 2 (ligação proativa) avaliamos se Sofia vira rede dedicada ou se chamamos via HTTP público com autenticação mútua
- ❌ Sofia não é parte do MVP de sexta

## Implementation checklist

- [x] `docker-compose.yml` atualizado com `infra_proxy` external + `connectaiacare_internal` bridge
- [x] Labels `traefik.docker.network` definidas em `api` e `frontend`
- [x] Middleware redirect HTTP→HTTPS configurado
- [x] Port binding removido de `postgres` e `redis`
- [ ] Deploy validado na Hostinger (próxima task)
- [ ] Runbook de acesso emergencial ao PG documentado (`docker exec` + túnel SSH)

## When to Revisit

- Se adicionarmos Sofia Voice no stack (Phase 2) — avaliar Option C ou HTTP público com mTLS
- Se sensor de IDS/IPS apontar ataques L4 ao PG — evidência de que Option A teria sido comprometido
- Se migrarmos para VPS dedicada — `infra_proxy` deixa de ser external e vira bridge local, ADR futuro formaliza

## Links

- [docker-compose.yml](../../docker-compose.yml)
- [ADR-001](001-stack-isolada-da-connectaia.md), [ADR-002](002-compartilhar-infra-hostinger-traefik.md), [ADR-003](003-postgres-compartilhado-database-separado.md)
- [Traefik multi-network docs](https://doc.traefik.io/traefik/providers/docker/#docker-api-access)
