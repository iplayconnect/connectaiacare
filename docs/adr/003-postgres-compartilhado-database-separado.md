# ADR-003: PostgreSQL mesmo Docker Engine, database separado

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: infrastructure, database, isolation

## Context and Problem Statement

ADR-001 exige isolamento de dados entre ConnectaIA e ConnectaIACare. ADR-002 compartilha o host Hostinger. Precisamos decidir o grau de isolamento de PostgreSQL: container separado, cluster separado, ou mesmo cluster com schemas isolados?

## Decision Drivers

- **LGPD Art. 11**: dados médicos têm requisitos de auditoria e segregação distintos dos dados comerciais do CRM
- **Facilidade de backup e restore**: operações devem ser independentes (ex: restaurar ConnectaIACare não deve afetar ConnectaIA)
- **Performance isolation**: query pesada em um não deve degradar o outro
- **Operação**: manter 2 clusters é ~2x trabalho; mesmo cluster com schemas é frágil
- **Extensões diferentes**: ConnectaIACare precisa de `pgvector` e `pg_trgm`; ConnectaIA atual não usa vector extension no momento
- **Versão**: ConnectaIACare quer `pgvector/pgvector:pg16`; ConnectaIA usa imagem postgres padrão

## Considered Options

- **Option A**: Mesma instância postgres, mesmo database, schemas separados (`aia_health.*` vs `public.bbmd_*`)
- **Option B**: Mesma instância postgres, databases separados (`connectaiacare` vs `evolution`)
- **Option C**: Instâncias postgres separadas (containers diferentes, mesmo host) (escolhida)
- **Option D**: Cluster Postgres dedicado em host separado

## Decision Outcome

Chosen option: **Option C — Container postgres dedicado `connectaiacare-postgres` usando imagem `pgvector/pgvector:pg16`, na rede `connectaiacare_net`**, porque entrega isolamento completo (processo, filesystem, configuração) mantendo o mesmo host.

### Positive Consequences

- Backup/restore totalmente independente
- Versão do PostgreSQL pode divergir (pgvector exige build específico)
- Queries pesadas não causam contention no CRM
- Extensões isoladas (`pgvector`, `pg_trgm` instaladas só neste)
- Credenciais separadas (nenhum vazamento permite acesso cross-produto)

### Negative Consequences

- Uso dobrado de memória base (~150MB por cluster postgres)
- Backup de DR é 2 jobs independentes
- Pool de conexões separado (não pode compartilhar idle)

## Pros and Cons of the Options

### Option A — Mesmo DB, schemas separados ❌

- ✅ Zero overhead de recurso
- ❌ GRANT/REVOKE complexo para isolar acesso
- ❌ Backup mistura dados médicos + comerciais
- ❌ Extensão instalada no cluster afeta ambos
- ❌ LGPD: single breach vaza tudo

### Option B — Mesmo cluster, databases separados ❌

- ✅ Melhor que schemas — isolamento DB-level
- ❌ Ainda compartilha versão e extensões
- ❌ Single point of failure (cluster caiu = tudo caiu)
- ❌ Config de tuning (shared_buffers, work_mem) é global

### Option C — Containers postgres separados ✅ Chosen

- ✅ Isolamento de processo + filesystem + config
- ✅ Versões independentes (pg16+pgvector aqui, pg padrão lá)
- ✅ Backup/restore independentes
- ✅ Tuning específico por workload
- ❌ +150MB memória
- ❌ 2 backup jobs

### Option D — Cluster em host separado ❌

- ✅ Isolamento máximo (hardware)
- ❌ Latência de rede entre api e DB
- ❌ Custo VPS extra (R$ 150+/mês)
- ❌ Overkill no MVP

## When to Revisit

- Quando volume exigir tuning específico incompatível com container single-host
- Se backup volume exceder capacidade de disco do host compartilhado
- Se DR requirements exigirem replicação cross-region

## Links

- Configuração: [docker-compose.yml](../../docker-compose.yml) service `postgres`
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md), [ADR-002](002-compartilhar-infra-hostinger-traefik.md), [ADR-004](004-pgvector-em-vez-de-vector-db-dedicado.md)
- Migrations: [001_initial_schema.sql](../../backend/migrations/001_initial_schema.sql)
