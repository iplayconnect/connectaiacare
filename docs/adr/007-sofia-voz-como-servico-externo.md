# ADR-007: Sofia Voz consumida como microsserviço (não clonagem de código)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: integration, architecture, reuse

## Context and Problem Statement

ConnectaIACare precisa de capacidade de **ligação proativa em voz natural** para notificar familiares em casos críticos ("Olá, senhora Ana, aqui é a ConnectaIACare, sua mãe Maria apresentou sintomas...") — feature WOW da demo. A ConnectaIA já opera **Sofia Voz** em produção via Grok Voice Agent API, rodando no container `sofia-service:5030` com 10 tools e integração ao DB. Clonar todo esse código para o ConnectaIACare custaria dias.

A regra de ouro do ADR-001 (isolamento de código mutável + estado compartilhado) precisa ser balanceada com a realidade do sprint.

## Decision Drivers

- **Urgência do MVP**: clonar Sofia Voz + testar integração Grok + deploy = 3-5 dias de trabalho
- **Sofia Voz é um container isolado**: já expõe API HTTP estável (`POST /api/voice/call`)
- **Fronteira clara**: uma API HTTP é um "serviço externo" conceitualmente — análogo a como consumimos Anthropic, Deepgram, Grok
- **Isolamento de dados**: Sofia Voz recebe contexto mínimo necessário (script da ligação + telefone + nome) — não acessa nosso DB diretamente
- **Personalização futura**: perfil geriátrico (fala mais pausada, tom acolhedor) pode ser um parâmetro `voice_profile` na API, não requer fork

## Considered Options

- **Option A**: Clonar código `sofia-service` para `connectaiacare-sofia-voice` dedicado
- **Option B**: Consumir Sofia Voz existente via HTTP API como serviço externo (escolhida)
- **Option C**: Usar outro provider de Voice Agent (ElevenLabs Conversational, Vapi, Retell)
- **Option D**: Implementar do zero com Grok Voice API direto

## Decision Outcome

Chosen option: **Option B — Sofia Voz consumida via HTTP API, tratada como microsserviço interno**, porque é o padrão arquitetural correto para serviços já containerizados e estáveis, permitindo entrega em horas em vez de dias.

### Positive Consequences

- Entrega em <1h (só escrever cliente HTTP + configurar URL/key no env)
- Melhorias em Sofia Voz beneficiam automaticamente ConnectaIACare
- Zero duplicação de código pesado (10 tools, DB integration, Grok auth)
- Fronteira HTTP é uma proteção natural contra acoplamento indevido

### Negative Consequences

- **Dependência de runtime**: se `sofia-service` cair, ConnectaIACare perde feature de ligação
- Custo de Sofia Voz é compartilhado (sem segmentação por produto)
- Se ConnectaIACare virar JV, precisa migrar para fork dedicado (plano existente)
- Mudanças breaking em Sofia Voz API podem afetar ConnectaIACare

## Pros and Cons of the Options

### Option A — Clonar código

- ✅ Isolamento total
- ✅ Pronta para virar JV
- ❌ 3-5 dias de trabalho adiando demo
- ❌ Duplicação de 10 tools complexas
- ❌ Manutenção paralela

### Option B — HTTP API (microsserviço) ✅ Chosen

- ✅ Entrega em horas
- ✅ Fronteira conceitual limpa
- ✅ Aproveitar melhorias upstream
- ❌ Runtime dependency
- ❌ Eventual fork necessário para JV

### Option C — Provider externo (ElevenLabs/Vapi/Retell)

- ✅ SLAs managed, features avançadas
- ❌ +integração nova (auth, SDK, billing)
- ❌ Dados de paciente saem para novo provider (DPA extra)
- ❌ Custo adicional sem substituir Sofia Voz

### Option D — Grok Voice API direto

- ✅ Bypass da Sofia — uso direto
- ❌ Perde toda a orquestração de tools que Sofia provê
- ❌ Reimplementação de ~30% do valor da Sofia em menos recursos

## Design Notes

- Cliente em [sofia_voice_client.py](../../backend/src/services/sofia_voice_client.py) com timeout explícito e tratamento de falha graceful (retornar `{"status": "skipped"}` em vez de quebrar o pipeline)
- Configurar via env: `SOFIA_VOICE_API_URL=http://sofia-service:5030` (rede Docker interna)
- Autenticação separada: `SOFIA_VOICE_API_KEY` dedicada (token emitido por operador da Sofia)

## When to Revisit

- Quando ConnectaIACare for formalizado como empresa separada (JV) → fork do código
- Se Sofia Voz tiver incidentes que impactem SLA do ConnectaIACare (>3 no trimestre)
- Quando perfil geriátrico exigir customização que operadora de Sofia não queira manter upstream

## Links

- Código cliente: [sofia_voice_client.py](../../backend/src/services/sofia_voice_client.py)
- Uso no pipeline: [pipeline.py](../../backend/src/handlers/pipeline.py) — método `_try_proactive_call`
- Sofia Voz (ConnectaIA): container `sofia-service`, porta 5030 (cross-project network)
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md)
