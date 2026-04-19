# ADR-006: Evolution API compartilhado, instância V6 dedicada ao ConnectaIACare

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: whatsapp, infrastructure, integration

## Context and Problem Statement

A comunicação primária do ConnectaIACare é via WhatsApp. A ConnectaIA já opera Evolution API v2 com múltiplas instâncias configuradas (V5, V6, `connectaia`). Para o MVP, precisamos decidir se subimos uma instalação Evolution separada ou reaproveitamos a existente, e como rotear mensagens do ConnectaIACare sem afetar o CRM.

## Decision Drivers

- **Urgência**: MVP deve estar funcional em 4 dias úteis — setup Evolution novo demora 1-2 dias
- **Instância V6 inativa**: alexandre confirmou que V6 (número 555189592617) não está em uso no CRM atual
- **Webhook routing**: Evolution permite configurar webhook URL por instância (não por mensagem) — solução nativa
- **Custo**: Evolution API tem custo fixo (hosting + manutenção) — duplicar adds pouco valor no MVP
- **Número WhatsApp**: conseguir chip novo + onboarding + QR code leva dias
- **Risco operacional**: mudança na instância V6 precisa de comando único reversível em 5 segundos

## Considered Options

- **Option A**: Mesma Evolution API + V6 com webhook repointed para ConnectaIACare (escolhida)
- **Option B**: Nova Evolution API dedicada (container separado) com número novo
- **Option C**: Meta WhatsApp Cloud API oficial
- **Option D**: Twilio WhatsApp Business API

## Decision Outcome

Chosen option: **Option A — Evolution API compartilhado, instância V6 com webhook repointed para `https://demo.connectaiacare.com/webhook/whatsapp`**, porque aproveita infra em produção, elimina setup de 1-2 dias, e o repointing é uma única chamada HTTP reversível.

### Positive Consequences

- Zero tempo de setup de WhatsApp
- Número 555189592617 já conectado e validado
- Repointing webhook é 1 comando (curl PUT)
- Reverter para ConnectaIA é igualmente trivial

### Negative Consequences

- **Falha da Evolution compartilhada derruba WhatsApp dos dois produtos** — risco aceito no MVP
- Credencial de API Evolution (`EVOLUTION_API_KEY`) compartilhada — se vazar, afeta ambos
- Limites de rate/quota do Evolution são compartilhados
- Se ConnectaIA precisar reusar V6, ConnectaIACare tem que liberar ou arranjar novo número

## Pros and Cons of the Options

### Option A — Evolution compartilhado + V6 ✅ Chosen

- ✅ Setup zero (instância já conectada)
- ✅ Repointing trivial e reversível
- ✅ Custo marginal zero
- ❌ Single point of failure compartilhado
- ❌ Credencial compartilhada

### Option B — Nova Evolution dedicada

- ✅ Isolamento total
- ✅ Credenciais separadas
- ❌ 1-2 dias setup
- ❌ Novo chip WhatsApp + re-onboarding
- ❌ +custo hosting
- ❌ +1 container para operar

### Option C — Meta WhatsApp Cloud API oficial

- ✅ Infra Meta gerenciada
- ✅ Compliance oficial
- ❌ Templates obrigatórios para mensagens iniciais
- ❌ Fluxo de aprovação de número (dias/semanas)
- ❌ Custo por conversa em escala
- ❌ Restrições em uso de áudio (que é nosso principal input)

### Option D — Twilio WhatsApp

- ✅ Managed e bem documentado
- ❌ Custo por mensagem elevado
- ❌ Mesmos desafios de aprovação oficial Meta
- ❌ API muito diferente da Evolution que já dominamos

## When to Revisit

- Quando ConnectaIACare sair de piloto (>100 pacientes) → migrar para instância dedicada ou Meta oficial
- Se ocorrer ban/suspensão da instância V6 na rede Evolution → planejar substituição
- Quando ConnectaIA precisar da V6 de volta → obter novo número para ConnectaIACare

## Links

- Configuração: [docker-compose.yml](../../docker-compose.yml) — `EVOLUTION_INSTANCE=v6`
- Código: [evolution.py](../../backend/src/services/evolution.py)
- Comando de repointing: [docs/DEPLOY.md](../DEPLOY.md) seção "Webhooks do Evolution"
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md), [ADR-007](007-sofia-voz-como-servico-externo.md)
