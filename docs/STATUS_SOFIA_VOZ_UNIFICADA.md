# Status — Sofia Voz Unificada (sessão noturna 2026-04-29)

**Branch**: `claude/auto-while-away`
**Status**: implementado, validado, pronto pra revisão de manhã. **Não deployado.**

---

## TL;DR

Sofia Voz (voice-call-service) deixou de ser um "Grok burro" isolado.
Agora identifica quem está ligando pelo phone, carrega memória da
Sofia Chat/WhatsApp, dá contexto clínico do paciente desde o primeiro
segundo, e entra em **modo comercial** quando o lead é desconhecido.

5 fixes principais entregues:

1. **caller_resolver.py** — resolve phone do INVITE em
   `(persona, user_id, patient_id, caregiver_id, contexto enriquecido)`
2. **inbound_bridge.py** — system prompt persona-aware (cuidador, família,
   paciente B2C, médico/enfermeiro, comercial)
3. **Modo comercial** — quando phone NÃO bate em ninguém cadastrado,
   Sofia entra em fluxo de qualificação de lead e escala pro time
4. **Memory writeback** — no fim de toda chamada (inbound E outbound)
   dispara `update_user_memory_force` pra Sofia "lembrar" no próximo
   contato em qualquer canal
5. **Migration 056** — 2 cenários comerciais seedados em
   `aia_health_call_scenarios` editáveis via `/admin/cenarios-sofia`

---

## Detalhe técnico do que foi implementado

### `voice-call-service/services/caller_resolver.py` (novo)

Cascata de resolução em 5 níveis:

| Match | Persona | Carrega no contexto |
|-------|---------|---------------------|
| `caregivers.phone` | `cuidador_pro` | nome, phone_type, user_id se vinculado |
| `users.phone` | `medico` / `enfermeiro` / `admin_tenant` | nome, role |
| `patients.responsible.phone` | `familia` | **Paciente enriquecido** |
| `patients.responsible.phone` AND `is_self_reporting=TRUE` | `paciente_b2c` | **Paciente enriquecido** |
| Nenhum | `comercial` | (lead novo) |

Variantes do phone testadas (`5551996161700`, `551996161700`,
`51996161700`, `+5551996161700`) pra cobrir cadastros em formatos
diferentes.

**Paciente enriquecido** em `extra_context.patient`:
- Dados básicos (nome, apelido, condições, alergias, unidade, quarto)
- **Top 5 medicações ativas** (nome, dose, via, horários)
- **Último care_event** (human_id, tipo, classificação, summary, status)
- **Alertas abertos** (count por severidade)

Tudo isso vai automaticamente no system prompt da Sofia via
`GrokCallSession.start()` (que já injeta `extra_context.patient`).

### `voice-call-service/services/inbound_bridge.py`

Prompt específico por persona resolvida. Highlights:

- **Cuidador**: técnico, direto, pergunta paciente se necessário,
  tools clínicas completas
- **Família**: acolhedor, empático, foco em atualização
- **Paciente B2C**: linguagem MUITO simples, fala devagar, escalate
  pra humano em queixa grave
- **Médico/enfermeiro**: linguagem técnica, tools completas
- **Comercial**: apresenta plataforma adaptada ao perfil, qualifica
  (nome+contato+empresa+dor), escala pro time via
  `escalate_to_attendant` no fim

Cada uma reaproveita as tools certas (memory + active_context são
injetados automaticamente pelo `GrokCallSession.start()`).

### Memory writeback no `_on_call_state` (inbound + outbound)

Quando call vai pra `DISCONNECTED`:

```python
user_id = persona_ctx.get("user_id")
if user_id:
    update_user_memory_force(user_id)
```

Isso chama `sofia-service/sofia/memory/update` que extrai aprendizado
do transcript da chamada e atualiza `aia_health_sofia_user_memory`.
Resultado: na próxima conversa em chat/whatsapp/voz, Sofia já lembra
o que foi discutido.

### Migration 056 — cenários comerciais

`inbound_lead_qualifier`: prompt completo de qualificação de lead.
Code referenciado pelo `inbound_bridge` quando cair em
`persona='comercial'`.

`outbound_commercial_followup`: pra Sofia ligar pra leads pré-cadastrados
em follow-up (precisa ser disparado via `/api/communications/dial`
passando `scenario_code='outbound_commercial_followup'`).

Ambos com `ON CONFLICT DO UPDATE` — são idempotentes e o Alexandre
pode editar via painel `/admin/cenarios-sofia` sem perder.

---

## O que ESTÁ pronto pra teste de manhã

1. **Outbound clínico** (cenários atuais): Sofia liga pra paciente
   com contexto enriquecido (meds, último evento, alertas) +
   memória do user que disparou a call.

2. **Inbound clínico**: paciente/familiar/cuidador liga pro DID e
   Sofia identifica pelo phone, carrega memória + contexto do
   paciente + ativo_context cross-channel. Funciona quando inbound
   estiver completando (ainda depende de Flux/nVoip rotear chamada).

3. **Inbound comercial**: phone desconhecido → Sofia entra em modo
   comercial, qualifica e escala. Fluxo testável apenas quando
   inbound estiver chegando.

4. **Outbound comercial**: time comercial dispara via API/painel
   passando `scenario_code='outbound_commercial_followup'`. Sofia
   liga pro lead com prompt comercial.

---

## O que NÃO está pronto (não-bloqueante)

1. **Inbound roteamento real**: depende de configuração no painel do
   trunk SIP (Flux ou nVoip) pra chamada chegar até nós. Hoje
   `5130624363` parece ser user técnico, não DID público. Nome do
   DID público precisa ser confirmado com Flux suporte.

2. **Lead persistido em CRM**: `escalate_to_attendant` registra em
   audit + manda alert, mas não cria entry de "lead" estruturado em
   tabela própria. Pra fazer isso depois (tabela `aia_health_leads`
   + tool `register_lead` + integração CRM externo).

3. **Voice biometrics no inbound**: a infra está toda implementada
   (migration 050+051, `voice_biometrics_service`, plantões), mas
   `inbound_bridge` ainda não usa biometria pra desempate quando
   `phone_type=shared`. Próxima iteração.

4. **Persistência de transcript em sofia_active_context**:
   `GrokCallSession` JÁ persiste mensagens em
   `sofia_messages` via `append_message_voice_call`. Ativo_context
   (cross-channel) é atualizado pelo sofia-service no writeback.

---

## Como testar manhã

### Pré-requisito: aplicar migration 056

```bash
ssh root@72.60.242.245 'cd /root/connectaiacare && \
  docker compose exec -T postgres psql -U postgres -d connectaiacare \
  < backend/migrations/056_call_scenarios_commercial_seed.sql'
```

### Outbound (já funciona com Flux)

Disparar pelo painel `/comunicacao` ou via curl direto:

```bash
ssh root@72.60.242.245 \
  'docker exec connectaiacare-voice-call curl -s -X POST \
   http://localhost:5040/api/voice-call/dial \
   -H "content-type: application/json" \
   -d "{\"destination\":\"5551996161700\",\
        \"persona\":\"medico\",\
        \"user_id\":\"<UUID_DO_USER>\",\
        \"patient_id\":\"<UUID_PACIENTE>\",\
        \"full_name\":\"Dr. Alexandre\",\
        \"tenant_id\":\"connectaiacare_demo\"}"'
```

Logs vão mostrar:
- Memory carregada (`MEMÓRIA SOBRE O USUÁRIO`)
- Patient context com meds, alertas, último evento
- TX bidirecional funcionando

### Inbound (depende de Flux rotear pro nosso REGISTER)

Liga pro `5130624363` (ou outro DID Flux ativo). Esperado se Flux
rotear:
- Log `incoming_call call_id=... caller=5551996161700`
- Log `inbound_persona_ctx persona=cuidador_pro user_id=...`
  (ou `familia` ou `comercial` etc.)
- Sofia atende com prompt apropriado pra persona
- Áudio bidirecional funciona (já validado outbound, mesma stack)

---

## Commits

```
[a fazer] feat(voice-call): caller_resolver + inbound enriched + commercial mode
```

---

## Próximos passos depois disso

1. Resolver inbound DID Flux/nVoip (configuração trunk side)
2. Tabela `aia_health_leads` + tool `register_lead`
3. Voice biometrics integration no inbound (já implementado infra)
4. nVoip homologação STIR-SHAKEN com Anatel
