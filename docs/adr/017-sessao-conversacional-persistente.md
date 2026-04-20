# ADR-017: Sessão conversacional persistente pós-confirmação de paciente

- **Date**: 2026-04-20
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: ux, conversational, session, state-machine

## Context and Problem Statement

No MVP inicial (deployed 2026-04-20 19:47 UTC), o pipeline tratava cada webhook do WhatsApp como um evento isolado:

```
áudio chega → cria sessão (state=awaiting_patient_confirmation)
            ↓
cuidador responde "SIM"
            ↓
análise + resposta → sessions.clear()   ← sessão MORRE aqui
            ↓
próximo áudio/texto = começa do ZERO (sem contexto, re-pergunta paciente)
```

Consequências operacionais observadas no primeiro smoke test real (sexta, 2026-04-24 demo):

1. **Cuidador que envia follow-up 30s depois** ("Ela agora tá tonta") recebe o onboarding genérico como se nunca tivesse falado com o sistema.
2. **Áudio subsequente sobre o mesmo paciente** força re-identificação completa — cuidador vê foto/nome novamente e tem que confirmar outra vez.
3. **LLM analisa cada relato sem saber da conversa anterior** — não consegue classificar como "piora" vs "estabilidade" porque não tem referência do momento anterior.

Cuidadores reais reportam sobre o mesmo paciente em múltiplas mensagens ao longo de minutos ou horas. O sistema precisa entender continuidade — ou será percebido como um chatbot stateless, não um assistente clínico.

## Decision Drivers

- **UX clínica real**: o tempo entre "Dona Maria caiu" e "ela agora tá tonta" é tipicamente 2-15 minutos, janela em que o paciente pode deteriorar. O sistema não pode ser reset-happy.
- **Valor diferencial**: classificação evolutiva (upgrade para `urgent` quando sintomas novos aparecem depois de `attention`) é um dos pontos que diferencia do chatbot genérico.
- **LGPD/auditoria**: cada troca de mensagem é um evento clínico que precisa ser registrado em ordem — sessão agrega isso.
- **Custos de LLM**: classificar no contexto da conversa usa mais tokens, mas evita trabalho redundante (não precisa pedir confirmação de paciente a cada áudio).
- **Existência da infra**: tabela `aia_health_conversation_sessions` com campo `context jsonb` já existe; estava subutilizada.

## Considered Options

- **Option A**: Manter modelo stateless atual; usuário relembra o paciente todo o áudio (status quo)
- **Option B**: Sessão persiste pós-confirmação como `active_with_patient` até TTL de inatividade; follow-ups ficam no mesmo contexto clínico (escolhida)
- **Option C**: Sessão eterna até comando explícito "encerrar"
- **Option D**: Sessão por paciente (não por cuidador) — um cuidador pode ter múltiplas sessões paralelas

## Decision Outcome

Chosen option: **Option B — Sessão persistente com TTL rolling de 30 min**.

### Máquina de estados

```
    idle
      │
      │ [áudio novo]
      ▼
awaiting_patient_confirmation  (TTL 30 min)
      │
      ├─ [SIM] ────────────────────────────────┐
      └─ [NÃO] → clear → idle                  ▼
                                   active_with_patient  (TTL 30 min rolling)
                                     │
                                     ├─ [áudio novo] → análise contextualizada (mesmo paciente, renova TTL)
                                     ├─ [texto] → answer_followup_text (LLM responde, renova TTL)
                                     ├─ [texto indicando piora] → should_re_analyze=true → pede áudio detalhado
                                     └─ [30 min silêncio] → expira silenciosamente → idle
```

### Persistência do contexto

Campo `context jsonb` da tabela `aia_health_conversation_sessions` passa a armazenar:

```json
{
  "patient_id": "uuid",
  "patient_name": "Maria da Silva Santos",
  "patient_nickname": "Dona Maria",
  "messages": [
    {"role": "caregiver", "kind": "audio", "text": "...", "timestamp": "..."},
    {"role": "assistant", "kind": "analysis_summary", "summary": "...", "classification": "..."},
    {"role": "caregiver", "kind": "text", "text": "...", "timestamp": "..."}
  ],
  "last_analysis": { "summary": "...", "classification": "...", "recommendations_caregiver": [] },
  "last_report_id": "..."
}
```

### Truncamento defensivo

Após 40 mensagens na sessão, mantemos a primeira (seed da conversa) e as últimas 39 — protege o context window do LLM sem perder o ponto de partida.

### Injeção no prompt

Tanto o prompt clínico principal (`clinical_analysis.py`) quanto o novo prompt de follow-up (`followup_answer.py`) recebem bloco `<conversation_history>` formatado como diálogo legível:

```
[19:54] Cuidador (áudio transcrito): "Dona Maria teve uma queda..."
[19:54] Sistema (resumo/classificação): "ATENÇÃO. Queda leve, PA elevada..."
[19:58] Cuidador: "Ela agora tá tonta"
```

### Positive Consequences

- **Classificação evolutiva real**: LLM vê piora desde o relato anterior e pode escalar.
- **Zero atrito em follow-up**: áudio subsequente sobre mesmo paciente vai direto pra análise.
- **Respostas contextuais a texto livre**: cuidador pode perguntar ("posso dar água?"), comentar ("ela aceitou o remédio"), ou reportar piora ("piorou") em linguagem natural — sistema responde com contexto.
- **Auditoria agregada**: todas as trocas de uma mesma conversa ficam num único registro (`id` da sessão), simplifica relatório de evento clínico.
- **Reuso de infra**: tabela já existia, sem migration nova.

### Negative Consequences

- **Sessão pode ficar com paciente "errado"** se cuidador começar a falar de outra pessoa sem dizer explicitamente. Mitigação: prompt de follow-up detecta troca de paciente (intent `clinical_update` com nome diferente) e sugere "é outro paciente? manda novo áudio". Refinamento em versão futura.
- **Mais tokens de LLM por chamada** (contexto de conversa adiciona ~200-800 tokens). Aceitável para o ganho de UX e sem impacto operacional no MVP.
- **Truncamento de 40 msgs** pode perder meio da conversa em sessões longas. TTL de 30min na prática limita: conversa típica ~10-20 mensagens.
- **State machine mais complexa** — mais casos pra testar (novo áudio em active, texto em active, texto em awaiting, etc).

## Pros and Cons of the Options

### Option A — Stateless ❌ Rejeitada

- ✅ Zero mudança de código
- ❌ UX pobre, não diferencia de chatbot
- ❌ Impossível classificação evolutiva
- ❌ Re-pergunta paciente a cada áudio

### Option B — Sessão persistente TTL 30min ✅ Chosen

- ✅ UX natural ("conversa continuando")
- ✅ Classificação evolutiva
- ✅ Respostas contextuais a texto
- ❌ Máquina de estados mais complexa
- ❌ +tokens por chamada

### Option C — Sessão eterna até "encerrar" ❌

- ✅ Sem expiração artificial
- ❌ Cuidador esquece de encerrar → contexto gruda
- ❌ Risco de responder como "Dona Maria" dias depois sobre outro paciente
- ❌ Não modela realidade: conversa clínica tem ciclo natural

### Option D — Múltiplas sessões por cuidador ❌ Adiado

- ✅ Permite cuidar de vários pacientes "em paralelo"
- ❌ UX de chat: cuidador precisa contextualizar "estou falando da Dona Maria" ou "estou falando do Seu João" a cada mensagem
- ❌ Troca de paciente fica implícita (o cuidador pode errar)
- ❌ Complexidade prematura — 99% dos casos são 1 paciente por vez. Se aparecer demanda, evoluímos.

## Implementation

- [x] `session_manager.py`: `append_message`, `touch`, `transition` + truncamento defensivo (40 msgs)
- [x] `pipeline.py`: estado `STATE_ACTIVE`, `_handle_followup_audio`, `_handle_followup_text`; `_on_patient_confirmed` não mais apaga sessão
- [x] `analysis_service.py`: `analyze` aceita `conversation_history`; novo método `answer_followup_text`
- [x] `prompts/followup_answer.py`: novo prompt para resposta a texto livre do cuidador
- [x] `prompts/clinical_analysis.py`: reconhece bloco `<conversation_history>`
- [ ] Teste E2E: áudio inicial → confirmação → texto de piora → LLM responde contextualizado
- [ ] Smoke test na produção com paciente seed (Dona Maria)

## When to Revisit

- Se análise evolutiva começar a confundir (classificações yo-yo entre urgent/attention sem mudança real do paciente) — pode precisar de ancoragem temporal mais rígida.
- Se cuidadores reclamarem de "sessão não desliga" — considerar comando explícito "/encerrar" (retira Option C parcialmente).
- Se > 10% das sessões passarem de 40 mensagens — criar serviço de sumarização incremental em vez de truncar.
- Se chegar a vertical com múltiplos pacientes por cuidador (ex: home care) — avaliar Option D.

## Links

- Implementação: [session_manager.py](../../backend/src/services/session_manager.py), [pipeline.py](../../backend/src/handlers/pipeline.py), [analysis_service.py](../../backend/src/services/analysis_service.py), [followup_answer.py](../../backend/src/prompts/followup_answer.py)
- Relacionado: [ADR-016 (a criar)](.) confirmação forte de identidade
- SECURITY.md §4 Prompt Injection — defesas mantidas no novo prompt de follow-up
