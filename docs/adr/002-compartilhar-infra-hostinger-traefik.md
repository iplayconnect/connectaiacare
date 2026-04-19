# ADR-002: Compartilhar nó Hostinger + Traefik com ConnectaIA

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: infrastructure, cost, hosting

## Context and Problem Statement

O ConnectaIACare precisa de hosting para MVP antes da reunião de sexta (24/04/2026). A ConnectaIA já opera na VPS Hostinger (72.60.242.245) com Traefik gerenciando certificados Let's Encrypt. ADR-001 exige isolamento lógico, mas não define hardware dedicado. Precisamos decidir onde rodar os containers do ConnectaIACare no MVP.

## Decision Drivers

- **Urgência**: MVP deve estar de pé em 4 dias úteis
- **Custo MVP**: nova VPS custa R$ 200-400/mês que não temos validação comercial para justificar
- **Operação**: equipe é 1 pessoa — complexidade operacional dupla é proibitiva
- **Traefik existente**: já configurado com Let's Encrypt + routing por host; adicionar container é trivial
- **Isolamento lógico**: ADR-001 exige isolamento de código e dados, não necessariamente de hardware
- **Trajetória**: quando validado, escalar para VPS dedicada é uma operação bem conhecida

## Considered Options

- **Option A**: Mesma VPS Hostinger + Traefik compartilhado (escolhida)
- **Option B**: VPS dedicada nova (Contabo, Hetzner, DigitalOcean)
- **Option C**: Cloud gerenciado (AWS ECS, Google Cloud Run, Railway)

## Decision Outcome

Chosen option: **Option A — Mesma VPS Hostinger, containers com prefixo `connectaiacare-*`, rede Docker própria, Traefik compartilhado**, porque entrega isolamento lógico necessário com custo marginal zero no MVP.

### Positive Consequences

- Deploy imediato sem aprovação de hardware
- Traefik labels no `docker-compose.yml` já resolvem routing + TLS
- Zero custo adicional no MVP
- Operação unificada (1 comando SSH faz diagnóstico dos dois produtos)

### Negative Consequences

- **Falha hardware derruba ambos os produtos** — risco aceito para MVP
- Recursos compartilhados (CPU, memória, disco) — possível contention se um produto tiver pico
- Se ConnectaIA for invadida, ConnectaIACare está no mesmo host (mas DB e código separados)

## Pros and Cons of the Options

### Option A — Hostinger + Traefik compartilhado ✅ Chosen

- ✅ Custo zero marginal
- ✅ Deploy imediato
- ✅ Traefik já faz TLS automático
- ❌ Falha de host afeta ambos os produtos
- ❌ Recursos compartilhados

### Option B — VPS dedicada

- ✅ Isolamento de hardware
- ✅ Escalabilidade independente
- ❌ R$ 200-400/mês sem justificativa de tração
- ❌ Dobra trabalho operacional (cert, backup, monitoring, SSH, updates)
- ❌ Migração de DNS + repointing webhook = downtime

### Option C — Cloud gerenciado (Cloud Run/ECS)

- ✅ Auto-scaling, HA nativo
- ✅ Managed TLS, logs, secrets
- ❌ Custo imprevisível (pay-per-use pode variar)
- ❌ Latência cold start em idle (webhook WhatsApp tem SLA informal)
- ❌ Vendor lock-in
- ❌ Curva de aprendizado (IAM, networking, observabilidade cloud-specific)

## When to Revisit

- Quando ConnectaIACare tiver 100+ pacientes reais em produção
- Se incidente de segurança em um produto forçar isolamento de hardware
- Se picos de carga causarem contention mensurável

## Links

- Configuração: [docker-compose.yml](../../docker-compose.yml) com labels Traefik
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md), [ADR-003](003-postgres-compartilhado-database-separado.md)
- Documentação: [INFRASTRUCTURE.md §2 D2](../../INFRASTRUCTURE.md), [DEPLOY.md](../DEPLOY.md)
