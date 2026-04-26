# voice-call-service — Sofia em ligações telefônicas (Grok Realtime)

Container dedicado da ConnectaIACare. Atende/origina ligações SIP e
bridgea áudio com **Grok Voice Realtime** (xAI), dando à Sofia as
mesmas capacidades da Sofia Voz browser: persona, memória cross-session,
tools.

**Não confundir** com o `voip-service` da outra plataforma (ConnectaIA SaaS),
que usa Deepgram + ElevenLabs + monolito. Esse aqui é independente.

## Estado atual: SKELETON pronto, NÃO deployado

Tudo compila localmente, código revisado, mas:
- [ ] Build do Docker ainda **não rodou** na VPS (PJSIP demora ~10min)
- [ ] Bloco no `docker-compose.yml` está **comentado**
- [ ] Smoke de SIP+áudio com `51996161700` aguarda aprovação

## Quick start (quando aprovar)

```bash
# 1. Mirror SIP creds da outra plataforma pra ConnectaIACare
ssh root@72.60.242.245 "
  source /root/assistenteia/.env
  echo VOIP_SIP_DOMAIN=\$VOIP_SIP_DOMAIN >> /root/connectaiacare/.env
  echo VOIP_SIP_USER=\$VOIP_SIP_USER >> /root/connectaiacare/.env
  echo VOIP_SIP_PASSWORD=\$VOIP_SIP_PASSWORD >> /root/connectaiacare/.env
"

# 2. Descomentar bloco voice-call-service em docker-compose.yml

# 3. Build (10-15min na primeira vez por causa do PJSIP)
ssh root@72.60.242.245 "cd /root/connectaiacare && docker compose up -d --build voice-call-service"

# 4. Validar SIP registrado
ssh root@72.60.242.245 "docker logs --tail 30 connectaiacare-voice-call 2>&1 | grep -i 'sip_initialized\\|registered'"

# 5. Smoke: ligação pra um número (substitua o teu)
ssh root@72.60.242.245 "docker exec connectaiacare-voice-call curl -sS -X POST http://localhost:5040/api/voice-call/dial \
  -H 'Content-Type: application/json' \
  -d '{\"destination\":\"5551996161700\",\"persona\":\"medico\",\"full_name\":\"Dr. Alexandre\"}'"
```

## Arquitetura

```
┌──────────────┐  POST /api/voip/voice-call/dial   ┌─────────────────┐
│  Frontend    │──────────────────────────────────►│ connectaiacare- │
│  (botão      │                                   │ api (proxy + JWT)│
│  "Ligar")    │                                   └────────┬────────┘
└──────────────┘                                            │
                                                            ▼
                                ┌──────────────────────────────────────┐
                                │  voice-call-service (THIS CONTAINER) │
                                │  ┌────────────────────────────────┐  │
                                │  │ Flask :5040                    │  │
                                │  │ POST /api/voice-call/dial      │  │
                                │  └──────────┬─────────────────────┘  │
                                │             │ cria GrokCallSession   │
                                │             │ + invoca SipLayer.dial │
                                │  ┌──────────▼─────────────────────┐  │
                                │  │ SipLayer (PJSIP wrapper)       │  │
                                │  │ - registra na trunk SIP        │  │
                                │  │ - INVITE pro destino           │  │
                                │  │ - audio in: PCM 16-bit 8kHz    │  │
                                │  │ - audio out: PCM 16-bit 8kHz   │  │
                                │  └──────────┬───────────┬─────────┘  │
                                │             ▼           ▲            │
                                │  ┌─────────────────────────────────┐ │
                                │  │ AudioBridge                     │ │
                                │  │  upsample 8k→24k                │ │
                                │  │  downsample 24k→8k              │ │
                                │  └──────────┬───────────┬──────────┘ │
                                │             ▼           ▲            │
                                │  ┌─────────────────────────────────┐ │
                                │  │ GrokCallSession                 │ │
                                │  │  WebSocket xAI Realtime         │ │
                                │  │  + system_prompt persona        │ │
                                │  │  + memória cross-session        │ │
                                │  │  + 3 tools (patient/event/tele) │ │
                                │  └─────────────────────────────────┘ │
                                └──────────────────────────────────────┘
                                                  │
                                                  ▼
                                  PG: aia_health_sofia_messages
                                      (mesma tabela do chat texto/voz browser)
```

## Arquivos

| Arquivo | Função |
|---------|--------|
| `Dockerfile` | Build PJSIP 2.14 + Python 3.11 + deps |
| `requirements.txt` | flask, websockets, psycopg2, numpy |
| `config.py` | Config via env (SIP creds, Grok, DB, fallback msg) |
| `voice_call_app.py` | Flask entry. Inicializa PJSIP em background no boot. |
| `services/sip_layer.py` | Singleton PJSIP. dial(), hangup(), ports custom |
| `services/audio_bridge.py` | upsample 8k↔24k via audioop+numpy fallback |
| `services/grok_call_session.py` | WebSocket cliente xAI Realtime |
| `services/persistence.py` | Persiste em aia_health_sofia_*, replica execute_tool minimal |
| `routes/dial.py` | POST /dial /hangup /calls — orquestra SipLayer + Grok |

## Limitações conhecidas (Fase 1)

- **Apenas outbound** (originar ligação). Inbound (atender) fica pra Fase 2.
- **3 tools só**: `get_patient_summary`, `create_care_event`, `schedule_teleconsulta`. Adicionar mais conforme casos reais.
- **Memória cross-session é só LEITURA** — atualização da memória após a call ainda não está hooked aqui (acontece quando user volta a usar chat texto). Próxima iteração.
- **Sem failover Grok**: se WS cair no meio, ligação termina. Pra Fase 2: TTS pré-gravado + retry.
- **Frame size SIP**: marcado como `TODO_SMOKE` em sip_layer.py — pode precisar ajuste fino quando real call rodar (PJSIP normalmente pede 160 bytes/20ms, mas validar).

## Decisões pendentes

1. **SIP**: reusar trunk `5130624656` da outra plataforma OU pedir sub-ramal exclusivo (default: reusar)
2. **Frontend**: criar botão "Ligar via Sofia" — ainda não feito (próxima iteração)
3. **Permissão**: quem pode disparar ligação? Sugiro `medico|enfermeiro|admin_tenant|super_admin` por enquanto
