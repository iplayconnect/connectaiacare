# ADR-008: Hash-chain + OpenTimestamps para auditoria (em vez de blockchain pleno)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: security, lgpd, audit, blockchain

## Context and Problem Statement

Documentos iniciais do projeto (Jan-Set 2025) propuseram **Hyperledger Fabric** para tokenizar prontuário do paciente — argumento era "alta segurança e inviolabilidade dos dados". Escopo revisado do usuário (Mai 2025) já havia removido blockchain sem justificativa explícita. Precisamos formalizar por que **NÃO** usamos blockchain para PHI e o que usamos em vez disso.

## Decision Drivers

- **LGPD Art. 18 VI (direito à eliminação)**: titular pode exigir exclusão. Blockchain imutável torna isso tecnicamente inviável ou juridicamente questionável (crypto-shredding ainda deixa o dado cifrado lá)
- **Performance**: Hyperledger Fabric ~500 TPS em produção vs PostgreSQL ~50k TPS — volume esperado exige orders of magnitude acima do blockchain
- **Custo operacional**: rede permissionada Hyperledger custa 10-50× mais que PostgreSQL sem benefício proporcional
- **Complexidade de chaves**: paciente idoso perder chave privada = perda de acesso próprios dados — UX desastrosa
- **Interoperabilidade**: padrão mundial saúde é **HL7 FHIR** — blockchain não é FHIR-native
- **Falsa promessa de segurança**: auditoria imutável + criptografia são atingíveis sem blockchain
- **Estado da indústria**: nenhum EHR global (Epic, Cerner, Athenahealth) usa blockchain para prontuário em produção em escala. Estônia usa blockchain **só para hash de auditoria**, não para dados

## Considered Options

- **Option A**: Hyperledger Fabric para PHI (proposta original, descartada)
- **Option B**: PostgreSQL com audit log tradicional (simples mas sem prova de não-adulteração)
- **Option C**: **Hash-chain em PostgreSQL + ancoragem diária em blockchain pública via OpenTimestamps** (escolhida)
- **Option D**: Amazon QLDB (managed ledger database)

## Decision Outcome

Chosen option: **Option C — Append-only hash-chain em `aia_health_audit_chain` + ancoragem diária no Bitcoin via OpenTimestamps**, porque entrega inviolabilidade matematicamente provável, performance de PostgreSQL, compatibilidade com LGPD (dados apagáveis, mas auditoria permanece hash-encoded), e custo marginal irrisório (centavos/dia).

### Positive Consequences

- **LGPD-friendly**: dados apagáveis; auditoria guarda só hashes e timestamps, não PII
- **Performance**: audit log é uma simples INSERT em tabela com índice
- **Inviolabilidade criptográfica equivalente ao blockchain pleno**: qualquer adulteração histórica quebra a cadeia de hashes e a âncora pública
- **Custo**: ~R$ 2-5/mês (ancoragem) vs R$ 150-400k/ano (Hyperledger managed)
- **Interoperabilidade**: dados continuam em PostgreSQL → fácil exportar para FHIR

### Negative Consequences

- Marketing menor que "blockchain real" em conversas com stakeholders não-técnicos
- Validação externa requer verificar âncoras OpenTimestamps — passo extra para auditores
- Comitê auditando precisa entender o modelo de hash-chain (educar)

## Pros and Cons of the Options

### Option A — Hyperledger Fabric

- ✅ Marketing "blockchain"
- ❌ Viola LGPD Art. 18 VI
- ❌ Custo 10-50× maior
- ❌ Performance inadequada
- ❌ Zero adoção em EHRs reais

### Option B — PostgreSQL audit log simples

- ✅ Simples e performático
- ❌ Sem prova de não-adulteração (admin do DB pode editar histórico)
- ❌ Não satisfaz requisito de inviolabilidade

### Option C — Hash-chain + OpenTimestamps ✅ Chosen

- ✅ LGPD-compliant
- ✅ Performance PostgreSQL
- ✅ Custo irrisório
- ✅ Inviolabilidade equivalente
- ❌ Narrativa técnica mais sofisticada (não é "blockchain" puro)

### Option D — Amazon QLDB

- ✅ Managed, cryptographically verifiable
- ❌ AWS lock-in — dados médicos em AWS tem implicações LGPD (transferência internacional)
- ❌ Custo por operação
- ❌ Interoperabilidade com Postgres requer sync custoso

## Design

Schema já implementado em [001_initial_schema.sql](../../backend/migrations/001_initial_schema.sql):
```sql
CREATE TABLE aia_health_audit_chain (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    resource_type TEXT,
    resource_id TEXT,
    action TEXT,
    data_hash TEXT NOT NULL,
    prev_hash TEXT,
    curr_hash TEXT NOT NULL,
    payload JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Pseudo-código do audit helper (a implementar em P0):
```python
data_hash = sha256(canonical_json(payload))
curr_hash = sha256(prev_hash || event_data || data_hash)
```

Ancoragem diária via `ots stamp <last_curr_hash>` (biblioteca OpenTimestamps).

## When to Revisit

- Se auditor/regulador externo exigir explicitamente blockchain nomeado
- Se volume de audit events exceder capacidade PostgreSQL (>10M/dia)
- Se OpenTimestamps for descontinuado (plano B: ancoragem em Ethereum ou outra chain pública)

## Links

- Migration: [001_initial_schema.sql](../../backend/migrations/001_initial_schema.sql)
- Documentação: [SECURITY.md §8 Blockchain](../../SECURITY.md)
- Relacionado: [ADR-003](003-postgres-compartilhado-database-separado.md)
