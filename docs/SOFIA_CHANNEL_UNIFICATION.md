# Sofia Channel Unification — Diagnóstico e Plano Faseado

> Doc decisório. Estado: pendente revisão de Alexandre + Henrique + Willian.
> Última atualização: 2026-05-06

## Por que isso importa

ConnectaIACare opera Sofia em **3 canais hoje** (WhatsApp, Voz Web/Browser, VoIP/SIP),
mas cada canal tem implementação isolada com:
- **Tools próprias** (lógica farmacovigilância duplicada em 3 lugares)
- **Persistência separada** (`aia_health_conversation_messages` no WhatsApp,
  `aia_health_care_events` no voice, nada estruturado no VoIP)
- **Memória parcialmente compartilhada** (active_context cross-channel já existe)

Consequência prática: cuidador que conversa de manhã no WhatsApp sobre Diazepam
e depois liga à tarde — Sofia VoIP NÃO consegue consultar o `safety_review`
unificado, NÃO sabe que cenário acabou em handoff clinical, e pode contradizer
o que o agent WhatsApp já alertou.

## Estado atual (auditado 2026-05-06)

### Canal 1 — WhatsApp (Phase C v2 — 2026-05-06)

```
Evolution API → /webhook/whatsapp → sofia:inbound stream
                    ↓
              SuperSofiaOrchestrator
                    ↓
              identity_resolver
                    ↓
              factory.get_agent_for(profile, intent)
                    ↓
              CareSofiaAgent / CommercialSofiaAgent / SupportSofiaAgent / Passthrough
                    ↓ (tool calls via execute_tool)
              sofia_tools.TOOL_REGISTRY
                    ↓ (3 tools care + 3 tools comercial)
              evolution_send_text
                    ↓
              Persistência: aia_health_conversation_messages (PR 1) +
                           aia_health_sofia_active_context (cross-channel)
```

### Canal 2 — Sofia Voz Web (browser → WebSocket)

```
Browser audio → /voice WebSocket (sofia-service:5031)
                    ↓
              voice_app._make_voice_session
                    ↓
              GrokCallSession (Grok Realtime API)
                    ↓
              _build_tools_for_call (13 tools próprias)
                    ↓
              execute_voice_tool (services/persistence.py)
                    ↓
              Browser audio out
                    ↓
              Persistência: aia_health_care_events +
                           aia_health_sofia_active_context (mesma tabela
                           que WhatsApp ✓)
```

### Canal 3 — Sofia VoIP (SIP/PJSIP — voice-call-service)

```
SIP DID 5130624363 → PJSIP → audio_bridge
                    ↓
              GrokCallSession (mesma classe do Voice Web)
                    ↓
              _build_tools_for_call (13 tools próprias — idêntico ao Voice)
                    ↓
              execute_voice_tool (mesmo handler)
                    ↓
              Audio out via SIP
                    ↓
              Persistência: igual Voice Web
```

## O que JÁ está unificado ✅

1. **Memória cross-channel** (`aia_health_sofia_active_context`)
   - Voice (Web + VoIP) escreve via `services/persistence.append_active_context`
   - WhatsApp escreve via `src/services/active_context.append_turn`
   - Ambos leem a mesma tabela com mesmo schema (`user_id|patient_id|phone` + role + content + channel)
2. **GrokCallSession** compartilhado entre Voice Web e VoIP
   - Mesmo arquivo `voice-call-service/services/grok_call_session.py`
   - Mesmas 13 tools, mesma persistência
   - Diferença é só o transport de áudio (WebSocket browser vs SIP/PJSIP)
3. **Drug Safety Service como wrapper canônico** (Phase C v2)
   - `DrugSafetyService.safety_review_prescriptions` é referência única
   - Mas SÓ CareSofiaAgent (WhatsApp) consome — voice tem tools antigas

## O que NÃO está unificado ⚠️

### 1. Tools duplicadas

| Função | WhatsApp | Voice/VoIP |
|---|---|---|
| Validar prescrição | `safety_review_prescriptions` (1 tool, 11 checks) | `query_drug_rules` + `check_drug_interaction` + `check_medication_safety` (3 tools, lógica antiga) |
| Cadastrar relato | `register_caregiver_report` | `create_care_event` |
| Escalar pra humano | `escalate_to_human_clinical` | `escalate_to_attendant` |
| Consultar paciente | (não tem — usa contexto carregado) | `get_patient_summary`, `read_care_event_history`, `list_medication_schedules`, `get_patient_vitals` |
| Buscar paciente | (identity_resolver) | `search_patients` |

**Risco**: regra clínica nova (ex: novo critério Beers, nova interação) precisa ser
adicionada em 2 lugares. Drift inevitável.

### 2. Persistência conversational divergente

| Canal | Mensagens | Tools/Reports | Sessions |
|---|---|---|---|
| WhatsApp | `aia_health_conversation_messages` | `aia_health_reports` | `aia_health_legacy_conversation_sessions` |
| Voice/VoIP | (transcript em logs + `care_events` quando tool é chamada) | `aia_health_care_events` | (nenhuma — sessão é Grok-side) |

**Risco**: query "todas msgs do paciente X" não funciona cross-channel.
UI de operador no painel não vê o que cuidador falou na voz se não tem tool
chamada.

### 3. Identity resolution

WhatsApp passa por `identity_resolver.resolve(phone)`. Voice/VoIP usa
`caller_resolver.py` próprio — lógica similar mas implementação separada.

## Plano de unificação faseado

### Fase 1 — **Drug safety unificado** (1 sessão, baixo risco) ⏭️

Migrar voice/VoIP pra usar `safety_review_prescriptions` como tool canônica.

Mudanças:
- `voice-call-service/services/persistence.py`: novo handler `safety_review_prescriptions`
  que importa `from src.services.sofia_tools import safety_review_prescriptions` (mesmo
  wrapper que CareSofiaAgent já usa)
- `_build_tools_for_call`: substitui as 3 tools antigas por 1 nova
- Tools antigas (`query_drug_rules`, `check_drug_interaction`, `check_medication_safety`)
  ficam como aliases que delegam pra wrapper (deprecação gradual)

Benefícios imediatos:
- Beers/STOPP/cascade/ACB rodam consistente em todos os canais
- Henrique faz curadoria 1 vez (regra entra em `aia_health_drug_*`, todos canais
  pegam)
- Phase C v2 fix do `dose_unparseable` (rodado hoje) automaticamente vale pra voice

### Fase 2 — **Persistência conversational unificada** (1 sessão)

Voice/VoIP escrevem cada turno em `aia_health_conversation_messages` (mesmo schema
do WhatsApp), com `channel='voice'|'voip'`. Pode coexistir com `care_events` (que
continua pra eventos clínicos estruturados).

Benefícios:
- Painel operador vê histórico cross-channel
- Audit LGPD completo
- Sofia em qualquer canal pode chamar `load_recent_messages(patient_id)` e ver
  o que foi conversado

### Fase 3 — **Identity resolver unificado** (1 sessão)

Voice/VoIP migra pra usar `src/services/identity_resolver.resolve(phone)` em vez
de `caller_resolver` próprio. Lógica converge nos 5 lookups (users, caregivers,
patients_proactive, patients_responsible, phone_history).

### Fase 4 — **Orchestrator unificado** (sessão grande, requer decisão arquitetural)

Voice/VoIP publicam inbound em `sofia:inbound` stream com `channel='voice'`.
Orchestrator faz routing (factory.get_agent_for), agent processa, response
volta via `sofia:outbound` que voice consome.

**Decisão pendente**: hoje voice usa Grok Realtime API com modelo de turno
contínuo (modelo decide quando interromper, quando responder, sem volta-e-volta
discreto que orchestrator faz). Migrar pra orchestrator significa ou:
- (a) Voice continua Grok mas com tool `delegate_to_orchestrator` que dispara
  o agente principal (perde streaming nativo)
- (b) Reescrever voice em cima de orchestrator (perde Grok Realtime, ganha
  consistência total)
- (c) Mantém voice independente, orchestrator e voice **compartilham 100%
  das tools + persistência** (Fases 1+2+3 só, sem orchestrator unificação)

Recomendação: **(c)** — ganha 90% do benefício com 30% do esforço. Voice continua
otimizado pra latência baixa de áudio, orchestrator continua focado em
conversation control. Eles compartilham as tools (memory layer 1) e a persistência
(memory layer 2).

## Próximos passos sugeridos

1. **Fase 1** já — sessão de 2-3h. Resolve a maior dor (drift de regras
   farmacológicas) e tem rollback trivial (toggle nas tools antigas).
2. **Doc revisado por Henrique** — ele que define se as 13 tools voice cobrem
   tudo que falta pra cuidador. Talvez adicionar `safety_review` à voice já é
   suficiente.
3. **Decidir (a)/(b)/(c) com Willian** — afeta cronograma de roadmap. (c) cabe
   em sessões de manutenção; (a)/(b) requerem sprint dedicada.
