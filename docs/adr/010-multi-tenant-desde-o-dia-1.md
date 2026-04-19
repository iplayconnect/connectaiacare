# ADR-010: Multi-tenant desde o dia 1 (mesmo com 1 tenant inicial)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: architecture, multi-tenancy, data-model

## Context and Problem Statement

ConnectaIACare tem um único tenant piloto no MVP (`connectaiacare_demo`), mas a estratégia comercial já prevê múltiplos clientes: SPAs da Tecnosenior, clínicas Amparo, hospitais Vita, operadoras de saúde futuras. Precisamos decidir se estruturamos multi-tenancy desde o dia 1 ou adicionamos posteriormente quando houver demanda real.

## Decision Drivers

- **Custo de refactor retroativo**: transformar single-tenant em multi-tenant é operação cara — touches em todo schema, queries, UI
- **Custo de preparar upfront**: incluir `tenant_id` em toda tabela/query custa ~5% de esforço a mais no código inicial
- **Isolamento de dados entre clientes**: LGPD exige que dados de pacientes da SPA X não vazem para SPA Y
- **Pricing model futuro**: cobrar por paciente/tenant requer segregação clara
- **Compliance**: auditoria LGPD deve responder "dados do paciente P estão onde?" — resposta simples com multi-tenant
- **Single-source-of-truth**: com 1 tenant inicial, o modelo não é complexidade extra, é apenas disciplina de schema

## Considered Options

- **Option A**: Multi-tenant desde o dia 1 — coluna `tenant_id` em todas as tabelas, queries sempre filtradas (escolhida)
- **Option B**: Single-tenant no MVP, refactor para multi quando crescer
- **Option C**: Schema-per-tenant (cada cliente em schema PostgreSQL próprio)
- **Option D**: Database-per-tenant

## Decision Outcome

Chosen option: **Option A — Coluna `tenant_id TEXT NOT NULL` em todas as tabelas `aia_health_*`, valor default `connectaiacare_demo`, todas as queries filtram por tenant**, porque o custo incremental é mínimo (~5% de esforço) e refactor retroativo seria 10-100× mais caro.

### Positive Consequences

- Zero débito técnico para escalar para N clientes
- Isolamento de dados natural (query sem `tenant_id = X` é bug óbvio)
- Pricing model futuro (por paciente/tenant) é trivial
- Auditoria LGPD: "mostrar todos os dados do tenant X" é uma query simples
- Multi-tenant habilita também multi-environment (dev, staging, demo, prod-cliente-A, prod-cliente-B no mesmo banco)

### Negative Consequences

- Todo código que toca DB deve incluir `tenant_id` — disciplina constante
- Índices ficam maiores (index compound `(tenant_id, ...)` em vez de simples `(...)`)
- Testes precisam setup de tenant mesmo para cenários triviais

## Pros and Cons of the Options

### Option A — Multi-tenant por coluna (row-level) ✅ Chosen

- ✅ Refactor retroativo custaria muito mais
- ✅ Disciplina constante mas simples
- ✅ Performance OK com índices compound
- ❌ Todo código precisa lembrar de filtrar
- ❌ "Vazar tenant" é bug comum se não atento

### Option B — Single-tenant + refactor futuro

- ✅ MVP mais simples (1% menos código)
- ❌ Refactor envolve migration de schema + touch em 30+ arquivos
- ❌ Downtime durante migration
- ❌ Risco de bugs sutis no refactor

### Option C — Schema-per-tenant

- ✅ Isolamento físico mais forte
- ❌ Migrations são N× mais caras (uma por schema)
- ❌ Queries cross-tenant (dashboards agregados) são complicadas
- ❌ Connection pooling fica mais complexo
- ❌ Backup de um tenant é trivial mas restore é complicado

### Option D — Database-per-tenant

- ✅ Isolamento máximo, escalabilidade horizontal natural
- ❌ Overkill para <100 tenants
- ❌ Custo operacional massivo (N DBs para operar)
- ❌ Cross-tenant analytics impossíveis sem ETL

## Design Notes

Padrão implementado:
- Toda tabela `aia_health_*` tem `tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo'`
- Todo index importante inclui `tenant_id` como primeiro campo ou em compound: `CREATE INDEX idx_X_tenant ON aia_health_X(tenant_id, ...)`
- Toda query em `src/services/*.py` recebe `tenant_id` como parâmetro
- Config via env: `TENANT_ID=connectaiacare_demo` em `.env` define tenant padrão para operações do webhook
- UI (futuro): seletor de tenant no header para usuários com acesso multi-tenant (operadoras olhando múltiplas SPAs)

### Quando adicionar novo tenant
1. Inserir em tabela `aia_health_tenants` (a criar — hoje usamos string direto, formalizar depois)
2. Criar cuidadores + pacientes com novo `tenant_id`
3. Configurar webhook WhatsApp Evolution com roteamento por número → tenant

## When to Revisit

- Quando um cliente exigir isolamento físico (database/schema próprio) por razão regulatória
- Quando volume de 1 tenant específico exigir otimizações que prejudicam outros (noisy neighbor)
- Quando cross-tenant analytics forem frequentes (avaliar se migrar para data warehouse separado)

## Links

- Schema: [001_initial_schema.sql](../../backend/migrations/001_initial_schema.sql) — todas tabelas têm `tenant_id`
- Config: [backend/config/settings.py](../../backend/config/settings.py) — `tenant_id`
- Documentação: [INFRASTRUCTURE.md §2 D10](../../INFRASTRUCTURE.md)
- Relacionado: [ADR-011](011-locale-aware-architecture-para-latam-europa.md) — locale expande o modelo de tenant
