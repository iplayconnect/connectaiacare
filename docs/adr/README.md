# Architecture Decision Records (ADRs)

Registros de decisões arquiteturais significativas do ConnectaIACare.
Format: **MADR** (Markdown Architecture Decision Records).

## Sobre

Cada ADR documenta **uma** decisão arquitetural com contexto, opções consideradas, trade-offs e consequências. ADRs são **imutáveis** — quando superados, novo ADR é criado com status `Superseded by ADR-NNN` no anterior.

Seguir: `NNN-kebab-case-title.md` (zero-padded, kebab-case).

## Índice

| # | Decisão | Status | Data |
|---|---------|--------|------|
| [001](001-stack-isolada-da-connectaia.md) | Stack isolada da ConnectaIA produção | Accepted | 2026-04-19 |
| [002](002-compartilhar-infra-hostinger-traefik.md) | Compartilhar nó Hostinger + Traefik com ConnectaIA | Accepted | 2026-04-19 |
| [003](003-postgres-compartilhado-database-separado.md) | Postgres mesmo host, database separado | Accepted | 2026-04-19 |
| [004](004-pgvector-em-vez-de-vector-db-dedicado.md) | pgvector em vez de Qdrant/Pinecone | Accepted | 2026-04-19 |
| [005](005-resemblyzer-em-vez-de-pyannote.md) | Resemblyzer para biometria de voz | Accepted | 2026-04-19 |
| [006](006-reaproveitar-evolution-instancia-v6.md) | Evolution API compartilhado, instância V6 dedicada | ⚠️ Superseded by [013](013-instancia-evolution-dedicada-chip-proprio.md) | 2026-04-19 |
| [007](007-sofia-voz-como-servico-externo.md) | Sofia Voz consumida como microsserviço | Accepted | 2026-04-19 |
| [008](008-hash-chain-opentimestamps-em-vez-de-blockchain.md) | Hash-chain + OpenTimestamps (não blockchain pleno) | Accepted | 2026-04-19 |
| [009](009-nextjs-14-app-router-com-ssr.md) | Next.js 14 com App Router + SSR | Accepted | 2026-04-19 |
| [010](010-multi-tenant-desde-o-dia-1.md) | Multi-tenant desde o dia 1 | Accepted | 2026-04-19 |
| [011](011-locale-aware-architecture-para-latam-europa.md) | Arquitetura locale-aware para LATAM + Europa | Accepted | 2026-04-19 |
| [012](012-telemed-hibrido-livekit-fork-aplicacao.md) | Tele-consulta híbrida — reuso LiveKit + fork da camada médica | Accepted | 2026-04-19 |
| [013](013-instancia-evolution-dedicada-chip-proprio.md) | Instância Evolution dedicada com chip próprio (supersedes ADR-006) | Accepted | 2026-04-20 |
| [014](014-integracao-medmonitor-sinais-vitais.md) | Integração MedMonitor + modelo de dados de sinais vitais | Accepted (estrutura) / Proposed (integração real) | 2026-04-20 |
| [015](015-topologia-redes-docker-hostinger.md) | Topologia de redes Docker na Hostinger co-habitada (refina 002+003) | Accepted | 2026-04-20 |
| [017](017-sessao-conversacional-persistente.md) | Sessão conversacional persistente pós-confirmação de paciente | ⚠️ Superseded by [018](018-care-events-com-ciclo-de-vida.md) | 2026-04-20 |
| [018](018-care-events-com-ciclo-de-vida.md) | Care Events como objeto de domínio (supersedes ADR-017) | Accepted | 2026-04-20 |
| [019](019-integracao-medmonitor-totalcare.md) | Integração MedMonitor/TotalCare — ConnectaIACare como plataforma principal | Accepted | 2026-04-20 |
| [020](020-escalacao-hierarquica-evolution-sofia.md) | Escalação hierárquica — WhatsApp Evolution + Sofia Voice | Accepted | 2026-04-20 |
| [021](021-iris-framework-agentico-healthcare.md) | **Íris** — Framework agêntico próprio, workflow-first, healthcare-specific | Accepted | 2026-04-21 |
| [022](022-atente-fallback-humano-escalacao.md) | Atente como fallback humano de escalação (substitui SAMU automático) | Accepted | 2026-04-21 |
| [023](023-teleconsulta-arquitetura-completa.md) | Teleconsulta — arquitetura completa (Opção 3 demo 28/04) | Accepted | 2026-04-21 |

## Como contribuir

1. Use `/add-adr` (slash command a criar) OU siga o template MADR existente
2. Pegue o próximo número sequencial
3. Nome kebab-case descritivo
4. **Nunca edite** um ADR existente — crie novo com `Superseded by` no original
5. Atualize este índice

## Convenções

- **Título**: frase nominal imperativa (ex: "Use PostgreSQL", não "Devemos usar PostgreSQL?")
- **Context**: as _forças_ que tornaram a decisão necessária
- **Consequences**: trade-offs **honestos** (não só positivos)
- **Length**: 200-500 palavras idealmente

## Referências

- [MADR format](https://adr.github.io/madr/)
- [Nygard original format](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Skill `.claude/skills/create-adr/` neste repo
