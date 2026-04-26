# Plano: Ligações VoIP com Grok Voice + memória/contexto da Sofia

> **Status**: rascunho pra revisão. **Não executar nada sem aprovação do Alexandre.**
> Data: 2026-04-26

## 1. Estado atual (auditado)

### voip-service (container existente)
- **Localização**: `/root/assistenteia/voip-service/` (pertence à plataforma ConnectaIA SaaS — **não** ConnectaIACare)
- **Compose**: `docker-compose.contabo.yml` da pasta `/root/assistenteia/`
- **Runtime**: Python + Flask + Socket.IO + PJSIP nativo (compilado no Dockerfile)
- **SIP trunk ativo**: `revendapbx.flux.net.br:5060` UDP
- **Usuário SIP**: `5130624656` (Porto Alegre, DDD 51)
- **Ramais configurados**: 501, 502, 0001, 0003, 0006 (cada um com senha própria)
- **Pipeline atual**: PJSIP RTP → Deepgram STT → MONOLITH (LLM call HTTP) → ElevenLabs TTS → PJSIP RTP
- **Latência típica**: ~2-3s por turn (3 hops sequenciais)
- **Endpoints HTTP** em `:5010`:
  - `POST /api/v1/voip/call` — inicia chamada outbound
  - `POST /api/v1/voip/hangup`
  - `GET /api/v1/voip/status`
  - `GET /api/v1/voip/health`

### ConnectaIACare hoje
- `backend/src/handlers/voip_routes.py` é **só proxy HTTP** pro voip-service
- Não tem código próprio de VoIP/SIP

## 2. O que muda com Grok Voice

Grok Voice (xAI Realtime) é **speech-to-speech end-to-end**:
- Entrada: chunks PCM (24kHz pcm16)
- Saída: chunks PCM (24kHz pcm16)
- Internamente já faz STT + LLM + TTS
- **Latência ~500-800ms por turn** (vs 2-3s do pipeline atual)
- Suporte nativo a tools (function calling)
- Suporte nativo a system_prompt = persona injection

Pra ligação SIP, o desafio é só:
1. Codec convert: SIP usa PCMU/PCMA (G.711, 8kHz) → upsample pra 24kHz Linear16 pra Grok
2. Path inverso: Grok 24kHz → downsample pra 8kHz → PCMU/PCMA → PJSIP

## 3. Duas opções arquiteturais

### Opção A — Container dedicado `connectaiacare-voice-call`

**O que é**: Novo container só pra ligações da ConnectaIACare. Reusa pattern PJSIP do voip-service mas tudo enxuto.

**Componentes**:
- PJSIP nativo (mesmo Dockerfile pattern do voip-service — copia)
- WebSocket cliente pra Grok Realtime
- Audio bridge: SIP RTP ↔ Grok WS (com resample 8k↔24k)
- Reuso 100% das tools/persona/memória da Sofia (importa `sofia-service/src/tools.py`, `memory_service.py`, `collective_memory_service.py` via shared volume OU duplica)
- Endpoint próprio `POST /api/voice-call/dial`
- Persistência em `aia_health_sofia_messages` igual à Sofia Voz browser

**Trunk SIP**: pode reusar o do voip-service (mesmo `5130624656@revendapbx.flux.net.br`) com senha compartilhada via env, OU registrar um novo ramal específico (ex: `0007`) — depende do contrato com a operadora.

**Prós**:
- Zero risco de quebrar a outra plataforma
- Latência mínima (sem hop pelo orquestrador antigo)
- Grok permite Sofia ter contexto + memória + tools full
- Código limpo, fácil de debugar

**Contras**:
- 1-2 dias de trabalho (Dockerfile + audio bridge + tests)
- Requer conta SIP — provavelmente reuso é OK, validar com operador

### Opção B — Adicionar modo "grok" no voip-service existente

**O que é**: Adicionar flag `voice_provider: 'grok' | 'deepgram_pipeline'` em `bbmd_ramal_config`. Quando grok, o orchestrator pula deepgram/elevenlabs e usa Grok Realtime direto.

**Prós**:
- 4-6h de trabalho
- Reusa toda infra SIP que já tá funcionando

**Contras**:
- **Modifica container compartilhado** com a outra plataforma — qualquer bug afeta os dois
- Acoplamento: a Sofia da ConnectaIACare passa a depender de código que vive em outro repo
- Tools/memória precisam ser injetadas via HTTP — perde a clareza da injeção direta
- Audit/persistência fica ambígua (vai pra `bbmd_*` ou `aia_health_*`?)

## 4. Recomendação

**Opção A — container dedicado.**

Motivos:
1. Healthcare (LGPD) exige separação clara: o voip-service hoje compartilha PG `evolution` com a outra plataforma. Misturar áudio de pacientes + audit clínico nesse fluxo é complicado de auditar.
2. O ganho de latência do Grok end-to-end já justifica reescrever a camada bridge.
3. A outra plataforma continua sem mudanças = zero regressão.
4. Sofia precisa de contexto+memória+tools full (você reforçou isso) — Opção A faz isso de forma natural via import direto; Opção B exige HTTP roundtrips.

## 5. Arquitetura técnica (Opção A)

```
┌──────────────┐  POST /api/voice-call/dial   ┌──────────────────────────┐
│  Frontend    │─────────────────────────────►│  connectaiacare-api      │
│  (botão      │                              │  /api/voice-call/...     │
│  "Ligar")    │                              │  (proxy + JWT auth)      │
└──────────────┘                              └────────┬─────────────────┘
                                                       │ POST /dial
                                                       ▼
                                        ┌─────────────────────────────────┐
                                        │ connectaiacare-voice-call (NEW) │
                                        │ ┌─────────────────────────────┐ │
                                        │ │  PJSIP (registra na trunk)  │ │
                                        │ │  Inicia INVITE pro número   │ │
                                        │ └──────────┬──────────────────┘ │
                                        │            │ RTP PCMU 8k        │
                                        │            ▼                    │
                                        │ ┌─────────────────────────────┐ │
                                        │ │  AudioBridge                │ │
                                        │ │  - resample 8k↔24k          │ │
                                        │ │  - jitter buffer            │ │
                                        │ └─────┬────────────────┬──────┘ │
                                        │       │ PCM 24k        │        │
                                        │       ▼                │        │
                                        │ ┌──────────────┐       │        │
                                        │ │ GrokVoice    │       │        │
                                        │ │ Realtime WS  │───────┘        │
                                        │ │ (system_prompt│  PCM 24k       │
                                        │ │ + memory +   │  output         │
                                        │ │ tools)       │                 │
                                        │ └──────────────┘                 │
                                        └─────────────────────────────────┘
                                                  │
                                                  ▼ persiste
                                        aia_health_sofia_messages
                                        aia_health_sofia_user_memory
                                        aia_health_audit_chain
```

## 6. Itens de trabalho (Opção A) com estimativa

| # | Item | Esforço | Risco |
|---|------|---------|-------|
| 1 | Novo `connectaiacare-voice-call/` (Dockerfile + PJSIP install) | 3h | médio (compilação PJSIP) |
| 2 | `audio_bridge.py` — resample 8k↔24k via `audioop` ou scipy | 1h | baixo |
| 3 | `grok_call_session.py` — adapta GrokVoiceSession pra fonte de áudio SIP | 2h | baixo |
| 4 | `routes/dial.py` — POST /dial recebe número, persona, patient_id; cria sessão | 1h | baixo |
| 5 | Compose: novo serviço + rede `connectaiacare_internal` + env vars | 30m | baixo |
| 6 | `backend/voip_routes.py` — adicionar proxy POST `/api/voice-call/dial` | 30m | baixo |
| 7 | Frontend: botão "Ligar via Sofia" no painel de paciente | 1h | baixo |
| 8 | Smoke: ligação pro `51996161700` com Sofia conversando | 1h | médio (codec/SIP) |
| 9 | Persistência + audit + memory hook | 1h | baixo |
| 10 | Documentação + runbook | 30m | - |

**Total**: ~11h + 1h de buffer = 1.5 dia.

## 7. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Compilação PJSIP no Dockerfile demora | Copiar exatamente o Dockerfile do voip-service que já funciona |
| Operadora SIP não permitir 2 registros simultâneos da mesma conta | Pedir ao operador um sub-ramal exclusivo (ex: 0007) — custo zero |
| Grok desconectar no meio da chamada | Retry automático + fallback pra mensagem TTS-only em PT |
| Latência codec ainda alta | Profile end-to-end, otimizar buffer sizes |
| Grok não suportar codec de baixa qualidade | Sempre upsample antes de enviar; Grok recebe PCM16 limpo |

## 8. Pré-requisitos do Alexandre antes de eu codar

- [ ] **Aprovação do plano** (Opção A ou pedir alteração)
- [ ] **Confirmar reuso da conta SIP** `5130624656` ou pedir ramal novo ao operador
- [ ] **Manter `XAI_API_KEY`** no `.env` (já está)
- [ ] **Confirmar número alvo do teste**: `51996161700` (formato E.164: `+5551996161700`)
- [ ] **Confirmar qual paciente/contexto** Sofia carrega na ligação de teste (pra ver memória funcionando)

## 9. Cronograma sugerido (post-aprovação)

- **Sessão 1 (3-4h)**: itens 1-3 (container + bridge + Grok session) com smoke isolado (chamada SIP de loopback)
- **Sessão 2 (3-4h)**: itens 4-7 (rotas + frontend + integração com api)
- **Sessão 3 (2h)**: smoke real ligando pro teu número, ajustes de qualidade

## 10. Decisões pendentes pro Alexandre

1. **Opção A ou B?** (recomendo A — container dedicado)
2. **Sub-ramal SIP separado ou compartilhado** com voip-service?
3. **Fallback**: se Grok cair, deve a Sofia desligar OU tocar mensagem "tente novamente"?
4. **Identificação na chamada**: caller_id deve ser o do trunk (`5130624656`) ou um número virtual do tenant?

---

**Quando voltar, conversamos sobre as 4 decisões e eu inicio a Sessão 1.**
