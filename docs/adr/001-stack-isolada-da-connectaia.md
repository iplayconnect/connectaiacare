# ADR-001: Stack isolada da ConnectaIA produção

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: architecture, isolation, risk-management

## Context and Problem Statement

O ConnectaIACare começa como MVP sprint para uma reunião de sexta (24/04/2026) com Tecnosenior, MedMonitor e Amparo. A ConnectaIA produção atende clientes pagantes do CRM de automação comercial (SDRs/Closers) 24/7. Qualquer bug ou regressão no MVP não pode afetar o CRM em produção. Além disso, dados médicos são sensíveis sob LGPD Art. 11 — superfície de risco muito diferente da do CRM.

## Decision Drivers

- **Risco ao CRM pagante**: um erro no ConnectaIACare não pode derrubar a ConnectaIA
- **LGPD Art. 11**: dados médicos têm controles diferentes (consentimento, retenção, criptografia)
- **Velocidade de iteração**: sprint de 4 dias não pode ser travado por revisão de impacto no CRM
- **Futuro como JV**: potencial spin-off precisa de arquitetura já desacoplada
- **Migração conceitual**: mais barato isolar agora que desacoplar depois

## Considered Options

- **Option A**: Módulo novo dentro do monorepo ConnectaIA, mesmo tenant separado
- **Option B**: Repo separado + database separado + containers isolados (escolhida)
- **Option C**: VPS dedicada desde o dia 1

## Decision Outcome

Chosen option: **Option B — Repo separado, containers isolados, database próprio**, porque combina isolamento real com reuso máximo de infra (economia operacional no MVP).

### Positive Consequences

- Zero acoplamento de código runtime — pull do ConnectaIA não pode quebrar ConnectaIACare
- Iteração rápida sem medo de regressão no CRM
- LGPD: separação clara de escopo de tratamento de dados médicos
- Pronto para virar JV com cap-table separado

### Negative Consequences

- Duplicação de código (auth JWT, WhatsApp wrapper, Deepgram, LLMRouter copiados)
- Manutenção paralela de correções de segurança
- Engenheiro precisa operar em dois contextos

## Pros and Cons of the Options

### Option A — Módulo no monorepo ConnectaIA ❌

- ✅ Reuso direto de código (sem duplicação)
- ❌ Qualquer bug afeta CRM pagante
- ❌ Onboarding de parceiros clínicos tem acesso ao repo do CRM
- ❌ Deploy acoplado
- ❌ LGPD: escopo de tratamento misturado

### Option B — Repo separado, containers isolados ✅ Chosen

- ✅ Isolamento real (código + runtime + DB)
- ✅ Desacoplamento pronto para spin-off
- ✅ LGPD escopo claro
- ❌ Duplicação de código
- ❌ Manutenção paralela

### Option C — VPS dedicada ❌

- ✅ Isolamento máximo (hardware)
- ❌ Custo duplicado (~R$200-400/mês) injustificável no MVP
- ❌ Complexidade operacional extra
- ❌ Traefik + cert management duplicado

## Links

- Código: repo `iplayconnect/connectaiacare`
- Relacionado: [ADR-002](002-compartilhar-infra-hostinger-traefik.md), [ADR-003](003-postgres-compartilhado-database-separado.md)
- Documentação: [INFRASTRUCTURE.md §2 D1](../../INFRASTRUCTURE.md)
