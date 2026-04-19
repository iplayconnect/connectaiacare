# ADR-004: pgvector em vez de vector DB dedicado (Qdrant/Pinecone/Weaviate)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: database, vectors, biometrics, cost

## Context and Problem Statement

ConnectaIACare precisa de busca por similaridade vetorial para:
1. **Biometria de voz** — embeddings 256-dim do Resemblyzer, identificação 1:N entre cuidadores de um tenant
2. **RAG por paciente (futuro)** — embeddings de histórico narrativo

O volume estimado no piloto é baixo: 10-30 cuidadores × 3-5 embeddings = ~150 vectors por tenant. Na escala 18 meses: 10-50 tenants × ~100 cuidadores = ~50k vectors. Precisamos decidir se usamos um serviço de vector DB dedicado ou uma extensão do PostgreSQL.

## Decision Drivers

- **Volume**: baixíssimo no MVP, baixo na escala de 12-18 meses
- **Latência**: identificação biométrica tem budget de ~500ms para o fluxo WhatsApp ser fluido
- **Simplicidade operacional**: +1 serviço managed = +1 contrato + monitoring + billing
- **Backup**: manter tudo em 1 DB simplifica DR
- **Filtragem multi-tenant**: queries tipicamente `WHERE tenant_id = X AND ...` — joins relacionais são comuns
- **Custo**: Pinecone inicia ~US$70/mês sem workload real; Qdrant self-hosted custa recurso; pgvector é grátis

## Considered Options

- **Option A**: pgvector (extensão PostgreSQL) (escolhida)
- **Option B**: Qdrant self-hosted (container próprio)
- **Option C**: Pinecone (managed cloud)
- **Option D**: Weaviate (managed ou self-hosted)

## Decision Outcome

Chosen option: **Option A — pgvector nativo no PostgreSQL do ConnectaIACare**, porque o volume é baixo, a simplicidade operacional é crítica com time de 1 pessoa, e queries com join relacional (tenant + caregiver) dominam o padrão de acesso.

### Positive Consequences

- Zero serviços adicionais — mesmo container, mesmo backup, mesmo monitoring
- Queries podem combinar vetor + filtros relacionais nativamente (`WHERE tenant_id = %s ORDER BY embedding <=> %s::vector`)
- Custo zero marginal
- pgvector 0.7+ tem HNSW index — escala bem até milhões de vectors
- Usa ferramental PostgreSQL conhecido (psql, pg_dump, monitoring)

### Negative Consequences

- Performance p99 degrada mais cedo que vector DBs dedicados em escala massiva (>10M vectors)
- IVFFlat/HNSW tuning requer atenção quando volume crescer
- Não tem features avançadas (sparse-dense hybrid, quantization fina)

## Pros and Cons of the Options

### Option A — pgvector ✅ Chosen

- ✅ Custo zero
- ✅ Queries híbridas (vetor + relacional) triviais
- ✅ Backup/restore único
- ✅ Performance adequada para <1M vectors
- ❌ Não escala tão bem quanto Qdrant/Pinecone em volume massivo
- ❌ Tuning de index requer experiência

### Option B — Qdrant self-hosted

- ✅ Performance vector-native superior
- ✅ Features avançadas (payload filtering, quantization)
- ❌ +container para operar
- ❌ Sync de metadados com Postgres complexifica joins
- ❌ Backup separado

### Option C — Pinecone managed

- ✅ Zero ops, alta performance
- ✅ Auto-scaling
- ❌ US$70+/mês sem justificativa comercial
- ❌ Latência de rede para serviço cloud externo
- ❌ Dados médicos saem do nosso perímetro (complica LGPD/DPA)
- ❌ Vendor lock-in

### Option D — Weaviate

- ✅ Open-source + managed option
- ❌ Mesmas desvantagens de Qdrant (self) ou Pinecone (managed)
- ❌ Menos maduro que os outros dois

## When to Revisit

- Quando volume passar de ~1M vectors ativos OU p99 query > 200ms
- Se aparecerem casos de uso com sparse-dense hybrid que pgvector não suporta bem
- Se custos do backup do Postgres ficarem altos por causa do volume vetorial

## Links

- Migration: [003_voice_biometrics.sql](../../backend/migrations/003_voice_biometrics.sql)
- Código: [voice_biometrics_service.py](../../backend/src/services/voice_biometrics_service.py)
- Relacionado: [ADR-003](003-postgres-compartilhado-database-separado.md), [ADR-005](005-resemblyzer-em-vez-de-pyannote.md)
- Documentação: [INFRASTRUCTURE.md §2 D4](../../INFRASTRUCTURE.md)
