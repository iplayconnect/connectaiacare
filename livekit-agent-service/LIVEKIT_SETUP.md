# LiveKit Agent Service — Setup Operacional

Migração da stack de voz para **LiveKit Cloud** + **SIP trunk Flux**, mantendo
`voice-call-service` (Grok+PJSIP) como fallback durante a transição.

## Arquitetura

```
                ┌────────────────────┐
                │  ConnectaIACare    │
                │  Backend (api)     │
                │  /communications/  │
                │  dial              │
                └──────────┬─────────┘
                           │ VOICE_BACKEND env switch
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
    ┌──────────────────┐      ┌──────────────────────┐
    │ voice-call-service│     │ livekit-agent-service│
    │ (Grok + PJSIP)    │     │ (LiveKit Agents)     │
    │ porta 5040        │     │ porta 5042           │
    └──────────────────┘      └──────────┬───────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │  LiveKit Cloud       │
                              │  - Agent dispatch    │
                              │  - SIP gateway       │
                              └──────────┬───────────┘
                                         │ SIP UDP
                                         ▼
                              ┌──────────────────────┐
                              │  Flux SIP Trunk      │
                              │  revendapbx.flux.    │
                              │  net.br              │
                              └──────────────────────┘
```

## Componentes

| Item | Onde | Função |
|---|---|---|
| `worker.py` | container, processo `worker` | Agent worker registrado no LK Cloud (long-lived). Recebe jobs (rooms novas), conecta, conversa via Sofia. |
| `dispatcher.py` | container, processo `dispatcher` (porta 5042) | HTTP API com mesmo contrato do voice-call-service. Cria room + dispatch + SIP outbound. |
| `tools.py` | importado por `worker.py` | 7 tools port com Safety Guardrail integrado |
| supervisord | container init | Mantém worker + dispatcher rodando |

## Pré-requisitos

### 1. LiveKit Cloud — projeto provisionado

Já existe (memória da sessão anterior):
- URL websocket: `wss://connectaiacare-3wludd0r.livekit.cloud`
- API key: `APIvSp99AMcrWXV`
- API secret: pendente recuperar (LiveKit dashboard → Settings → Keys)

### 2. Plugins de voz — API keys

| Plugin | Onde obter | Env var |
|---|---|---|
| Deepgram (STT, PT-BR nova-2) | console.deepgram.com → API Keys | `DEEPGRAM_API_KEY` |
| ElevenLabs (TTS, multilingual_v2) | elevenlabs.io → Profile → API Key | `ELEVENLABS_API_KEY` |
| ElevenLabs voice ID | elevenlabs.io → Voices → escolher voz PT-BR feminina natural → copiar Voice ID | `TTS_VOICE_ID` |
| xAI Grok (LLM via OpenAI-compat) | console.x.ai (ROTACIONAR — vazou em chat) | `XAI_API_KEY` |

Sugestão de voz ElevenLabs PT-BR: testar **"Sara"** (multilingual) ou **"Charlotte"** com configurações `eleven_multilingual_v2`. A/B test com 3 idosos antes de fixar.

### 3. SIP Trunk — outbound (LiveKit → Flux)

#### Passo 3.1 — Criar trunk no LiveKit Cloud

Via CLI (`lk` da LiveKit) ou dashboard:

```bash
# Instale o CLI: brew install livekit-cli (ou cargo install livekit-cli)
# Login: lk cloud auth (interativo)

cat > /tmp/outbound-trunk.json <<EOF
{
  "trunk": {
    "name": "Flux Outbound",
    "address": "revendapbx.flux.net.br",
    "transport": "TRANSPORT_AUTO",
    "numbers": ["${SEU_NUMERO_FLUX_E164}"],
    "auth_username": "${VOIP_SIP_USER}",
    "auth_password": "${VOIP_SIP_PASSWORD}"
  }
}
EOF

lk sip outbound-trunk create /tmp/outbound-trunk.json
# Resposta: { "sip_trunk_id": "ST_xxxxxxxxxxx" }
```

Copie o `sip_trunk_id` e adicione no `.env`:
```
LIVEKIT_OUTBOUND_TRUNK_ID=ST_xxxxxxxxxxx
```

#### Passo 3.2 — Inbound trunk (quando o número estiver definido)

Necessário para Sofia atender ligações que entram. Pula esse passo até o
operador Flux confirmar o DID disponível.

```bash
cat > /tmp/inbound-trunk.json <<EOF
{
  "trunk": {
    "name": "Flux Inbound",
    "numbers": ["${DID_RECEBIDO}"],
    "auth_username": "${VOIP_SIP_USER}",
    "auth_password": "${VOIP_SIP_PASSWORD}",
    "allowed_addresses": ["${IP_FLUX}"]
  }
}
EOF

lk sip inbound-trunk create /tmp/inbound-trunk.json
```

#### Passo 3.3 — Dispatch rule pra inbound (depois do 3.2)

Roteia ligações que chegam pra agent específico:

```bash
cat > /tmp/dispatch-rule.json <<EOF
{
  "name": "Sofia Inbound",
  "trunk_ids": ["ST_inbound_xxxxx"],
  "rule": {
    "dispatch_rule_individual": {
      "room_prefix": "sofia-inbound-"
    }
  },
  "agent_dispatches": [
    {"agent_name": "sofia-voice"}
  ]
}
EOF

lk sip dispatch-rule create /tmp/dispatch-rule.json
```

## .env (backend/.env) — variáveis novas

```bash
# Switch entre backends de voz (default = voice-call-service Grok)
VOICE_BACKEND=voice-call-service

# Quando trocar pra LiveKit:
# VOICE_BACKEND=livekit

# LiveKit Cloud
LIVEKIT_URL=https://connectaiacare-3wludd0r.livekit.cloud
LIVEKIT_WS_URL=wss://connectaiacare-3wludd0r.livekit.cloud
LIVEKIT_API_KEY=APIvSp99AMcrWXV
LIVEKIT_API_SECRET=<recuperar do dashboard>
LIVEKIT_OUTBOUND_TRUNK_ID=ST_xxxxxxxxxxx
LIVEKIT_AGENT_NAME=sofia-voice

# Plugins
DEEPGRAM_API_KEY=<gerar no console.deepgram.com>
DEEPGRAM_LANGUAGE=pt-BR
DEEPGRAM_MODEL=nova-2-general
ELEVENLABS_API_KEY=<gerar no elevenlabs.io>
ELEVENLABS_MODEL=eleven_multilingual_v2
TTS_PROVIDER=elevenlabs
TTS_VOICE_ID=<voice_id_escolhido>

# LLM (Grok via API OpenAI-compatível)
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-2-1212
XAI_API_KEY=<NOVA chave após rotação>
```

## Deploy

### Build local

```bash
docker compose --profile livekit build livekit-agent-service
```

### Subir o container (NÃO sobe por padrão — está atrás do profile `livekit`)

```bash
docker compose --profile livekit up -d livekit-agent-service
```

### Verificar saúde

```bash
docker logs --tail 50 connectaiacare-livekit-agent
curl http://livekit-agent.connectaia.com.br/health
# {"status":"ok","service":"livekit-agent-dispatcher", "agent_name":"sofia-voice"}
```

### Trocar backend de voz pra LiveKit

```bash
# No backend/.env, definir:
echo "VOICE_BACKEND=livekit" >> backend/.env

# Reiniciar API (lê env nova)
docker compose restart api
```

Backend agora roteia `/api/communications/dial` pro livekit-agent-service.
Próxima ligação Sofia já vai pelo LiveKit.

### Rollback rápido

```bash
sed -i '' 's/VOICE_BACKEND=livekit/VOICE_BACKEND=voice-call-service/' backend/.env
docker compose restart api
```

## Validação manual (depois do número definido)

1. **Trunk outbound conectado:**
   ```bash
   lk sip outbound-trunk list   # confirma trunk listado
   ```
2. **Worker registrado no LK Cloud:**
   ```bash
   docker logs -f connectaiacare-livekit-agent | grep "registered worker"
   ```
3. **Dispatcher saudável:**
   ```bash
   curl http://livekit-agent:5042/health   # config_issues vazio
   ```
4. **Dial test:** via UI `/admin/cenarios-sofia` ou direto:
   ```bash
   curl -X POST http://api:5055/api/communications/dial \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "scenario_code": "paciente_checkin_matinal",
       "destination": "5551996161700",
       "full_name": "Sr José"
     }'
   # Esperado: {"call_id": "sofia-call-...", "voice_backend": "livekit"}
   ```
5. **Logs em tempo real durante a call:**
   ```bash
   docker logs -f connectaiacare-livekit-agent | grep -E "agent_started|stt_metrics|llm_metrics"
   ```

## Limitações conhecidas (esta versão de scaffolding)

1. **Pipeline mode (não Grok Voice nativo)**: Esta versão usa STT (Deepgram)
   + LLM (Grok text) + TTS (ElevenLabs). Trade-off: perde a prosódia native
   do Grok Voice Realtime, ganha framework LiveKit Agents estável. Para
   reativar Grok Voice, basta `VOICE_BACKEND=voice-call-service`.

2. **Inbound não testado**: dispatcher tem outbound funcional. Inbound exige
   passo 3.2+3.3 do setup que depende de DID Flux confirmado.

3. **A/B com Grok Voice deferred**: build de plugin LiveKit pra Grok Voice
   Realtime pode ser feito depois — manter os dois backends coexistindo é
   estratégia segura.

4. **Custos plug-in pay-as-you-go**: Deepgram + ElevenLabs + LK Cloud todos
   cobram por minuto. Para escala, monitorar custos via `lk room list-rooms`
   e dashboards das APIs.

## Próximos passos sugeridos

| Passo | Quem | Critério |
|---|---|---|
| Recuperar `LIVEKIT_API_SECRET` do dashboard | Alexandre | imediato |
| Rotacionar `XAI_API_KEY` | Alexandre | imediato (vazou em chat) |
| Gerar `DEEPGRAM_API_KEY` | Alexandre | quando for deployar |
| Escolher voz ElevenLabs PT-BR | Alexandre + Henrique | A/B com 3 idosos |
| Criar outbound trunk Flux no LiveKit | Alexandre | quando confirmar Flux 403 resolvido |
| Configurar inbound trunk + dispatch rule | Alexandre | quando DID definido |
| Test call dial outbound | Alexandre | após trunk |
| Validar tools (escalate, get_patient_summary, drug_rules) | Alexandre + Henrique | em test calls |
| Trocar `VOICE_BACKEND=livekit` em produção | Alexandre | após validação |

---

ConnectaIACare © 2026
