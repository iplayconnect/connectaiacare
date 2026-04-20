# ADR-013: Instância Evolution dedicada com chip próprio (supersedes ADR-006 Option A)

- **Date**: 2026-04-20
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: whatsapp, infrastructure, integration, isolation
- **Supersedes**: [ADR-006](006-reaproveitar-evolution-instancia-v6.md) (parcialmente — reaproveitar infra Evolution continua; reaproveitar instância V6 NÃO)

## Context and Problem Statement

No ADR-006, escolhemos **Option A (reaproveitar a instância V6 com webhook repointado)** pelo critério de urgência do sprint e ausência de chip dedicado. A Option B (nova instância com número novo) foi descartada **por custo temporal** — criação + onboarding de chip + QR code seria 1-2 dias, inaceitável no sprint de 4 dias.

A premissa mudou em 2026-04-20: Alexandre informou que **tem um chip disponível** (`5551994548043`) e pode criar uma instância dedicada imediatamente. Isso desbloqueia a opção que era tecnicamente superior desde o início.

## Decision Drivers

- **Isolamento real entre produtos**: V6 é tenant `bbmd` (CRM ConnectaIA). Mesmo com webhook repointed, há risco de confusão operacional, logs misturados, métricas cruzadas
- **Reversibilidade sem impacto**: se algo quebrar no ConnectaIACare, não afeta CRM pagante
- **Narrativa de produto**: "instância dedicada ConnectaIACare" é mais limpo que "reusando V6 do CRM" quando apresentar a parceiros/investidores
- **Evolução futura**: quando o produto virar JV/spin-off, já tem instância desacoplada
- **Zero custo temporal**: chip disponível + API Evolution + painel = <30 min de setup

## Considered Options (revisitadas)

- **Option A**: Manter ADR-006 original (V6 repointada) — válido mas subótimo
- **Option B**: **Instância `connectaiacare` nova com chip próprio** (escolhida — supersedes A)
- **Option C**: Nova Evolution API dedicada (container separado) com número novo — overkill
- **Option D**: Meta WhatsApp Cloud API oficial — não reavaliado (roadmap)

## Decision Outcome

Chosen option: **Option B — Instância dedicada `connectaiacare` na mesma Evolution API compartilhada, com chip próprio `5551994548043`**.

A Evolution API continua sendo compartilhada (ADR-006 original sobre reuso de **infra** Evolution permanece válido). O que muda: **instância** dedicada em vez de V6 repurposed.

### Positive Consequences

- **Isolamento completo**: logs, métricas, rate limits, credenciais independentes por instância
- **Zero risco ao CRM**: qualquer bug/incidente fica contido em `connectaiacare`
- **Narrativa clara**: na demo, número `+55 51 99454-8043` é do produto ConnectaIACare, não do CRM
- **Reverter em caso de falha é trivial**: deletar a instância, reconectar o chip
- **Pronto para JV/spin-off**: migrar essa instância pra conta Evolution separada no futuro é simples

### Negative Consequences

- **Chip queima**: se o chip `5551994548043` for banido/perdido pelo WhatsApp, precisa de outro
- **Dependência do WhatsApp Business API não oficial**: mesma do CRM — aceito
- **+1 instância para operar**: pequeno custo de monitoring

## Configuração operacional

### Dados da instância
```
instanceName:    connectaiacare
phoneNumber:     5551994548043
integration:     WHATSAPP-BAILEYS
webhook URL:     https://demo.connectaia.com.br/webhook/whatsapp
events:          ["MESSAGES_UPSERT"]
tenant mapping:  connectaiacare_demo (TENANT_ID no .env)
```

### Criação (one-time)

Ver `docs/DEPLOY.md` seção "Instância Evolution API — referência rápida".

### Divisão de responsabilidade com ConnectaIA

| Aspecto | Compartilhado | Dedicado |
|---------|---------------|----------|
| Container Evolution API (`evolution_v2`) | ✅ shared | — |
| `EVOLUTION_API_KEY` master | ✅ shared | — |
| Instâncias (v5, v6, connectaia) | — | V6 **continua** para o CRM (se necessário no futuro) |
| Instância `connectaiacare` | — | ✅ ConnectaIACare |
| Chip / número | — | ✅ dedicado `5551994548043` |
| Webhook URL | — | ✅ `demo.connectaia.com.br/webhook/whatsapp` |
| Logs Evolution | ✅ shared | (filtráveis por instanceName) |

## When to Revisit

- Se o chip `5551994548043` for banido pelo WhatsApp → obter novo chip, mesma instância (renomear)
- Quando ConnectaIACare formalizar como JV → migrar para conta Evolution separada
- Se volume de mensagens exceder rate limits do Evolution compartilhado → Evolution API dedicada (Option C)
- Se Meta WhatsApp Cloud API oficial virar opcional→ reavaliar (Option D)

## Superseded from ADR-006

A recomendação de **Option A (reaproveitar V6)** do ADR-006 é formalmente superseded. Todas as demais decisões do ADR-006 (reusar container Evolution compartilhado, não duplicar infra) permanecem válidas.

## Links

- Supersedes parcial: [ADR-006](006-reaproveitar-evolution-instancia-v6.md)
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md) — isolamento entre produtos
- Operacional: [docs/DEPLOY.md](../DEPLOY.md) seção "Instância Evolution API"
- Código: [evolution.py](../../backend/src/services/evolution.py) — cliente HTTP
- Config: `EVOLUTION_INSTANCE=connectaiacare` em `backend/.env`
