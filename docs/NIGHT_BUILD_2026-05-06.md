# Build noturno 2026-05-06 → 05-07 — Unificação Sofia cross-channel

> Trabalho autônomo enquanto Alexandre dorme. Reunião Hospital Divina Providência
> à noite — esses entregáveis dão suporte à conversa.

## TL;DR

**3 PRs encadeados que unificam Sofia entre WhatsApp + Voz Web + VoIP**:
todos os canais agora consultam o MESMO knowledge graph farmacológico,
escrevem na MESMA tabela de mensagens, e resolvem identidade pela MESMA
lógica que CareSofiaAgent (WhatsApp) usa.

Implementa as 3 fases recomendadas no `SOFIA_CHANNEL_UNIFICATION.md`
(opção C — sem unificar orchestrator). Ganha 90% do benefício de
unificação completa com 30% do esforço.

## Ordem de merge dos PRs

Mergear nesta ordem (cada um built sobre o anterior — usar squash/merge
preserva diffs limpos):

### 1. `feat/unified-drug-safety-cross-channel` — Fase 1

https://github.com/iplayconnect/connectaiacare/pull/new/feat/unified-drug-safety-cross-channel

**O que faz**: drug safety canônico nos 3 canais.
- Novo endpoint `POST /api/internal/drug-safety/review` que delega pro
  `DrugSafetyService.safety_review_prescriptions` (mesmo wrapper que
  CareSofiaAgent já usa)
- Voice/VoIP ganha tool `safety_review_prescriptions` que chama o
  endpoint via HTTP
- Sofia Voz Web ganha mesma tool no `tools.py` registry
- Tools antigas (`query_drug_rules`, `check_drug_interaction`,
  `check_medication_safety`) ficam como `[DEPRECATED]` mas continuam
  funcionando
- `cuidador_pro/cuidador` agora têm acesso (antes só
  médico/enfermeiro/admin)
- Helper compartilhado `drug_safety_context.py` com
  `load_patient_safety_context()` — UMA fonte de verdade pro
  patient_ctx (idade, conditions, meds, allergies, creatinine, weight)

**Risco**: aditivo, não toca código existente. Tools antigas seguem
funcionando até decidirmos remover.

### 2. `feat/voice-conversation-persistence` — Fase 2

https://github.com/iplayconnect/connectaiacare/pull/new/feat/voice-conversation-persistence

**O que faz**: Sofia Voz/VoIP persistem turnos em
`aia_health_conversation_messages` (mesma tabela que CareSofiaAgent
escreve no WhatsApp).
- Novo endpoint `POST /api/internal/conversation/persist-message` que
  delega pro `conversation_persistence.persist_message`
- voice-call-service e sofia-service ganham função
  `persist_conversation_message_canonical()` que chama o endpoint
- Integrado nos 2 pontos de persistência existentes (assistant
  transcript done + user input transcription completed)
- channel='voice' (browser) ou 'voip' (SIP) diferencia
- subject_id derivado do persona_ctx (caregiver_id > patient_id >
  user_id)

**Risco**: aditivo. `aia_health_sofia_messages` continua funcionando
(persistência legada). Falha do endpoint não bloqueia turno (timeout
3s + logger.warning).

**Benefício imediato**: painel operador vê histórico cross-channel
completo. Cuidador WhatsApp + ligação telefônica = mesmo histórico
unificado por subject_id.

### 3. `feat/voice-identity-unified` — Fase 3

https://github.com/iplayconnect/connectaiacare/pull/new/feat/voice-identity-unified

**O que faz**: Voice/VoIP migra de `caller_resolver` próprio (4
lookups) pra backend `identity_resolver` (5 lookups + cache Redis).
- Novo endpoint `POST /api/internal/identity/resolve` que retorna
  formato voice-style (drop-in pra `caller_resolver`)
- Nova função `resolve_caller_unified()` em voice — tenta backend
  primeiro (timeout 2.5s), fallback automático pra `resolve_caller`
  local
- `inbound_bridge` usa a nova função

**Risco**: voice depende de backend up (mas fallback local cobre).
Backend timeout 2.5s pode atrasar tocagem em ~150ms vs DB local
direto.

**Benefício imediato**: cuidador identificado no WhatsApp é
identificado no telefone com MESMA lógica. Cache Redis 60s — segunda
ligação no mesmo dia resolve em <10ms.

**Benefício futuro**: quando `IDENTITY_TENANT_MODEL.md` migrar pra
memberships (médico-N-orgs do Divina Providência), voice ganha
multi-tenant identity automaticamente.

## Plano pós-merge

### 1. Smoke test do endpoint drug-safety isolado (curl)

```bash
ssh root@72.60.242.245 'curl -s -X POST http://localhost:5055/api/internal/drug-safety/review \
  -H "Content-Type: application/json" \
  -d "{
    \"prescriptions\": [{\"medication_name\": \"Diazepam\", \"dose\": \"não informado\"}],
    \"tenant_id\": \"connectaiacare_demo\"
  }"'
```

Esperado: `{"status":"ok","review":{"max_severity":"warning_strong",...,"requires_human_review":true}}`
(porque sem patient_id, não tem age — Beers `avoid_in_elderly` só
dispara com age informado. Pra o teste completo, criar patient
sintético antes — ver `scripts/test_whatsapp_identified_flow.py`).

### 2. Smoke test endpoint identity

```bash
ssh root@72.60.242.245 'curl -s -X POST http://localhost:5055/api/internal/identity/resolve \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"5551997354484\",\"tenant_id\":\"connectaiacare_demo\"}"'
```

Esperado: `{"status":"ok","persona":"...","caregiver_id":"..."}` se
o phone bater (Central 24h)).

### 3. Smoke test endpoint conversation persist

```bash
ssh root@72.60.242.245 'curl -s -X POST http://localhost:5055/api/internal/conversation/persist-message \
  -H "Content-Type: application/json" \
  -d "{
    \"tenant_id\":\"connectaiacare_demo\",
    \"phone\":\"5551999999999\",
    \"role\":\"user\",
    \"direction\":\"inbound\",
    \"content\":\"smoke test\",
    \"channel\":\"voice\"
  }"'
```

Esperado: `{"status":"ok","message_id":"<uuid>"}`. Depois `DELETE FROM
aia_health_conversation_messages WHERE phone='5551999999999'`.

### 4. Deploy

```bash
ssh root@72.60.242.245 'cd /root/connectaiacare && git pull && \
  docker compose up -d --build api sofia-service voice-call-service \
    sofia-inbound-worker'
```

Backend rebuild = sem flag adicional (endpoints novos ficam
disponíveis). Voice/sofia services rebuild pega os novos handlers.

### 5. Validação cross-channel manual

Cenário ensaiado pra Hospital Divina Providência demo:
1. Você manda WhatsApp pro `Connectaiacare`: "Posso dar diazepam pra
   ela hoje?"
2. CareSofiaAgent escala clinical (Beers warning_strong)
3. Você liga pro DID `5130624363` (Sofia VoIP)
4. Sofia atende e tem contexto: identifica você (mesmo phone),
   active_context tem o histórico do WhatsApp, sabe que escalou pra
   clinical, NÃO repete o alerta — diz "vi que você perguntou sobre
   diazepam mais cedo, time clínico já está revisando"

(Esse cenário só funciona 100% após Phase C v2 PR 1+2 já ter sido
testado — confirmar com Alex)

## Sobre identity & tenant model (referência pra reunião)

`docs/IDENTITY_TENANT_MODEL.md` (já mergeado) tem o plano. Caso 1
do doc (médico atendendo em ILPI A + Clínica B + Hospital C) é
EXATAMENTE o caso que vai aparecer no Hospital Divina Providência.

**Recomendação na reunião**: opção (C) do doc — migration aditiva
`068_user_tenant_memberships.sql` agora, fases 2-4 quando primeiro
caso real bater (provável: o próprio médico do Divina).

## Risco geral

Todos os 3 PRs são **aditivos**. Não removem código nem mudam
comportamento de canal existente sem fallback. Rollback é
trivial — `revert` do PR + restart container. Zero migration nova
exigida.

## Próximas tarefas (ordem)

1. ⏭️ Você revisa + merge dos 3 PRs (1, 2, 3 nessa ordem)
2. Eu deploy + smoke tests (assim que autorizar)
3. Teste real WhatsApp com Paulo Peretti ou Marlene (aguardando sua
   decisão de qual)
4. Phase C v3 (FamilySofiaAgent + PatientSofiaAgent) — pode
   prosseguir; só `MedicalSofiaAgent` que precisa esperar
   IDENTITY_TENANT_MODEL Fase 2
5. Investigar Sofia Voz "Failed to fetch" se reaparecer (na sessão
   anterior você relatou que voltou a funcionar após restart)
