# ADR-020: Escalação hierárquica — WhatsApp Evolution + Sofia Voice

- **Date**: 2026-04-20
- **Status**: Accepted (WhatsApp real / Voice real em sprint pós-demo)
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: escalation, integration, evolution, sofia-voice, clinical-workflow

## Context and Problem Statement

O ADR-018 define o modelo de **Care Events** com ciclo de vida. Um dos momentos críticos é a **escalação**: quando uma classificação é `urgent` ou `critical`, o sistema precisa notificar humanos em ordem hierárquica, **com SLA de resposta e fallback entre níveis**. Isso não pode ser "mandar WhatsApp e torcer" — precisa ser:

1. **Auditável**: cada notificação precisa ficar registrada com timestamps de sent → delivered → read → responded
2. **Multi-canal**: WhatsApp é default, mas familiares em situações críticas merecem **ligação de voz real** (mais assertivo, garante contato)
3. **Com fallback temporal**: se ninguém do nível N responder em X minutos, escala automaticamente para N+1
4. **Com mensagens adaptadas por papel**: a mensagem pro médico é técnica; a pra família é acolhedora
5. **Confiável em produção**: essa é a parte mais sensível — uma escalação silenciosamente perdida pode ter consequência grave

A Hostinger já roda Sofia Voice (via Ultravox) na mesma rede Docker (`infra_proxy`) usada pelo ConnectaIACare — temos acesso nativo a ligações de voz de IA. O Evolution API também está lá com a instância `Connectaiacare` conectada ao chip `5551994548043`.

Precisamos decidir **arquitetura de escalação**: como orquestrar níveis, canais, timings e fallback.

## Decision Drivers

- **Gravidade clínica**: mensagem para urgent/critical não pode ser ignorada silenciosamente
- **Múltiplos canais**: profissionais internos (central, enfermagem, médico) → WhatsApp; família nível 1-3 → WhatsApp + ligação voz
- **Política por tenant**: alguns SPAs podem querer só familia_1 em urgent, outros familia completa em critical (ADR-018 tenant_config.escalation_policy)
- **SLA real**: esperar 5min por resposta do médico antes de ir pra família é razoável; 5min pra central é agressivo (pode estar em atendimento)
- **Mensagem contextual**: roteiro de ligação Sofia Voice diferente de texto WhatsApp; mensagem pra família diferente de mensagem pra médico
- **Auditoria LGPD**: cada notificação é processamento de dado pessoal → timestamps + conteúdo + status de leitura = evidência legal

## Considered Options

- **Option A**: Envio único broadcast pra todos os contatos simultaneamente
- **Option B**: Escalação em cascata estrita (1 nível por vez, espera resposta, sobe)
- **Option C**: Híbrido — institucional paralelo (central+enfermagem+médico simultâneo) + família em cascata (escolhida)
- **Option D**: Delegação total pra serviço externo tipo PagerDuty/OpsGenie

## Decision Outcome

Chosen option: **Option C — Escalação híbrida com dois estágios**.

### Estágio 1: Institucional paralelo (imediato ao abrir evento urgent/critical)

Roles `central`, `nurse`, `doctor` são disparados em **paralelo imediato** via WhatsApp. Justificativa:
- São pessoas que já esperam receber alertas (profissionais de plantão)
- WhatsApp tem entrega confiável e é canal já usado para operação
- Em paralelo porque **redundância** é desejada — se central estiver ocupada, enfermagem ainda recebeu

### Estágio 2: Família em cascata (após espera)

Após `escalation_level1_wait_min` (default 5min) sem resposta institucional registrada, scheduler dispara escalação família nível 1. Se nível 1 não responder em `escalation_level2_wait_min` (default 10min) → nível 2. E assim por diante.

Justificativa:
- Família é notificada com calma, sem pânico — por isso aguarda profissional responder antes
- Cascata serial (1 por vez) porque **família inteira não deve ser alertada simultaneamente** (causa ansiedade generalizada)
- Nível 1, 2, 3 respeita hierarquia escolhida pela família no cadastro

### Política configurável por classificação

`tenant_config.escalation_policy` (JSONB):

```json
{
  "critical": ["central", "nurse", "doctor", "family_1", "family_2", "family_3"],
  "urgent":   ["central", "nurse",           "family_1"],
  "attention":["central"],
  "routine":  []
}
```

Cada tenant pode ajustar sem deploy.

### Canais por role

| Role | WhatsApp | Ligação Sofia Voice |
|---|---|---|
| `central` | ✅ | ❌ (operadora já está ligando quando responde) |
| `nurse` | ✅ | ❌ |
| `doctor` | ✅ | ❌ |
| `family_1` | ✅ | ✅ (paralelo ao WhatsApp) |
| `family_2` | ✅ | ✅ |
| `family_3` | ✅ | ✅ |

Familiares recebem **WhatsApp + ligação simultaneamente** — dobra chance de contato. WhatsApp registra e arquiva; ligação garante assertividade imediata.

Flag `features.sofia_voice_calls` no tenant_config controla ligações voz — pode desligar se SPA preferir só WhatsApp.

### Templates de mensagem por role

Implementados em `escalation_service._build_whatsapp_message` + `_build_voice_script`:

**Central (`central`)** — tom institucional:
```
*🆘 CRÍTICO* — Central de atendimento

Evento #0011 aberto em SPA Vida Plena — Ala A.
Paciente: *Seu Pedro*
Classificação: 🆘 CRÍTICO

📋 Seu Pedro apresenta apatia persistente com recusa alimentar...

Favor confirmar recebimento e encaminhar ao plantão.
```

**Enfermagem (`nurse`)** — tom clínico:
```
*🆘 CRÍTICO* — Enfermagem

Paciente *Seu Pedro* (SPA Vida Plena — Ala A) precisa de avaliação.

🆘 CRÍTICO
📋 Seu Pedro apresenta apatia persistente...

Por favor, confirmar ao receber e avaliar presencialmente.
```

**Familiar** — tom acolhedor:
```
Olá, Filho(a) 💙

Aqui é a assistente ConnectaIACare, do cuidado de *Seu Pedro*.

Houve uma situação agora que achamos importante te avisar com calma:

📋 Seu Pedro apresenta apatia persistente, recusou o almoço hoje...

A equipe do SPA Vida Plena já foi acionada e está atendendo.
Vou te avisar novamente quando tivermos mais informações.
Se quiser, pode responder aqui mesmo. 💙
```

**Ligação Sofia Voice** — script estruturado:
```
Você é a ConnectaIACare, assistente de cuidado do SPA Vida Plena.
Você está ligando para [nome], [relação] de Seu Pedro, com tom calmo,
acolhedor e pausado.

Situação: classificação crítica. [resumo].

Script:
1. Cumprimente pelo nome
2. Explique que houve uma situação crítica
3. Resuma em 1-2 frases
4. Informe que a enfermagem foi acionada
5. Pergunte se há informação recente relevante
6. Ofereça transferir para equipe humana se desejar
7. Encerre com tranquilidade
```

### Detecção de resposta

`aia_health_escalation_log.status` transita:
- `queued` → `sent` (Evolution retorna 201)
- `sent` → `delivered` (Evolution delivery callback; P1 pós-demo)
- `delivered` → `read` (Evolution read callback; P1)
- `read`/`sent` → `responded` quando cuidador/familiar envia mensagem no mesmo WhatsApp

Quando alguém responde, **scheduler detecta no `list_due_checkins` do tipo `post_escalation`** e **não sobe mais níveis** (verifica `responded_any = any(e.status == 'responded' for e in escalations)`).

### Positive Consequences

- **Compliance**: cada escalação é linha em tabela auditável com timestamps
- **Redundância inteligente**: institucional em paralelo (sem esperar) + família em cascata (sem flood)
- **Configurável por cliente**: Tecnosenior pode ter política diferente de Amparo
- **Dois canais em urgent/critical**: WhatsApp + voz aumenta chance de contato em horas absurdas
- **Interrompível**: quem responder primeiro cancela escalações pendentes

### Negative Consequences

- **Dependência de Evolution uptime**: se Evolution API cair, escalação para. Mitigação: healthcheck + alerta interno + fallback SMS (pós-MVP)
- **Dependência de Sofia Voice**: se Ultravox/Grok API cair, só WhatsApp funciona. Mitigação: degrade gracioso — ligação falha não aborta WhatsApp
- **Leitura de WhatsApp não 100% detectável**: nem todo cliente Evolution retorna `read` — precisamos fallback de "sem resposta em X min"
- **False positive**: familiar responder "ok" pode ser insuficiente — mas pipeline classifica intent via LLM (ADR-017/018) e pode escalar de volta

## Pros and Cons of the Options

### Option A — Broadcast simultâneo ❌

- ✅ Máxima chance de alguém responder
- ❌ Flood: família inteira recebe alerta sem hierarquia
- ❌ Causa ansiedade desnecessária
- ❌ Sem priorização clínica

### Option B — Cascata estrita ❌

- ✅ Ordem clara
- ❌ Central pode estar ocupada, desperdiça 5min antes de enfermagem ser avisada
- ❌ Lenta para eventos críticos

### Option C — Híbrido (institucional paralelo + família cascata) ✅ Chosen

- ✅ Velocidade onde importa (institucional imediato)
- ✅ Respeito onde importa (família cascata)
- ✅ Configurável por tenant
- ❌ Complexidade de lógica de dispatch

### Option D — Delegação PagerDuty/OpsGenie ❌

- ✅ Produto maduro
- ❌ Vendor lock-in
- ❌ Sem integração nativa com nosso contexto clínico
- ❌ Custo adicional
- ❌ Incompatível com posicionamento "plataforma principal"

## Implementation

### Serviços

- `escalation_service.py` — orquestra dispatch + escalate_next_level + build messages
- `care_event_service.py` — trilha em `aia_health_escalation_log`
- `checkin_scheduler.py` — dispara `post_escalation` kind no tempo certo
- `evolution.py` — client Evolution API (pré-existente)
- `sofia_voice_client.py` — client Sofia Voice (graceful degradation se URL não configurada)

### Configuração testada em produção (2026-04-20)

5 contatos distribuídos para teste real no Alexandre:

| Role | Número |
|---|---|
| central | 555196161700 |
| nurse | 5551993178926 |
| doctor | 5551994267222 |
| family_1 | 5551989592976 |
| family_2 | 5551989592617 |
| family_3 | 555196161700 (fallback) |

Evento #0009 (critical — queda Seu João) disparou todas as 3 escalações institucionais em 3 segundos (central 00:36:40 → nurse 00:36:42 → doctor 00:36:43) + agendou família_1 para +2min.

### Sofia Voice — status

Sofia está na Hostinger, rede `infra_proxy`. Acessível via `http://sofia-service:5030` sem expor endpoint público.

Endpoint de outbound call via Ultravox direto (pulando `sofia_ultravox_routes.py` que é pra frontend) está **adiado para quarta-feira** pós-demo:
- Ultravox expõe `/calls` com `first_speaker: FIRST_SPEAKER_AGENT` para outbound
- Key `ULTRAVOX_API_KEY` já existe no env da Sofia
- Integração trivial uma vez plumbing definido

Por ora, `sofia_voice_client.place_call()` faz graceful return se `SOFIA_VOICE_API_URL` vazio (adiado) — **WhatsApp continua funcionando integral**.

## When to Revisit

- Se Evolution API começar a apresentar latência alta em horários de pico → implementar outbox + retry
- Se um tenant pedir canal adicional (SMS, email, Telegram) → abstrair `Channel` como interface
- Se família reclamar de ligações em horas incorretas → adicionar `quiet_hours` no tenant_config
- Se escalação voltar a família nível 1 múltiplas vezes num dia → adicionar dedup por pessoa/dia
- Se tivermos necessidade de dar "ack" estruturado (botão no WhatsApp ao invés de responder texto) → integrar WhatsApp Business Interactive Messages

## Links

- [escalation_service.py](../../backend/src/services/escalation_service.py)
- [sofia_voice_client.py](../../backend/src/services/sofia_voice_client.py)
- [care_event_service.py](../../backend/src/services/care_event_service.py)
- [checkin_scheduler.py](../../backend/src/services/checkin_scheduler.py)
- [Evolution docs](https://doc.evolution-api.com/)
- [Ultravox docs](https://docs.ultravox.ai/)
- [ADR-007 Sofia como serviço externo](007-sofia-voz-como-servico-externo.md)
- [ADR-013 Instância Evolution dedicada](013-instancia-evolution-dedicada-chip-proprio.md)
- [ADR-018 Care Events](018-care-events-com-ciclo-de-vida.md)
