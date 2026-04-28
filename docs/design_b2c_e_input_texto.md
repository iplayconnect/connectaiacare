# Design — Tenant B2C + Input por Texto

**Data**: 2026-04-28
**Origem**: 2 pontos levantados pelo Alexandre durante a discussão da
biometria + plantão.

> 1. Cuidador em frente ao paciente pode preferir **texto a áudio**
>    (não quer expor o que está digitando em voz alta).
> 2. Tenant pode ser **B2C** — paciente assistido em casa, sem ILPI.

Documento mapeia os 2 problemas e propõe roadmap. Implementação
parcial já feita (migration 052 + helper sem voz). Resto fica pra
sprint dedicado porque depende do classifier de 8 classes
(consolidação do panel LLM).

---

## 1. Tenant B2C — modelos de cliente

### 1.1 Os 5 tipos cobertos

Migration 052 adiciona `aia_health_tenant_config.tenant_type`:

| Tipo | Cenário | Plantão | Biometria | Pacientes |
|------|---------|---------|-----------|-----------|
| `ILPI` | Lar de idosos | Obrigatório | Pool plantão (3-4) | Multi (10-50) |
| `clinica` | Clínica geriátrica | Fixo | Pool plantão | Multi (50-200) |
| `hospital` | Internação | Plantão 12x36 | Pool plantão | Multi (alta rotação) |
| `B2C` | Casa com cuidador particular | Opcional | 1:1 ou 1:N pequeno | 1-2 |
| `individual` | Paciente que assina sozinho | Não tem | 1:1 com paciente | 1 |

### 1.2 Implicações no comportamento

**Plantão**:
- ILPI/clinica/hospital: `shift_resolver.list_active_caregiver_ids()`
  vazio = warning operacional (ninguém de plantão = problema).
- B2C/individual: pool vazio é normal. Não logar warning.

**Biometria**:
- B2C com 1 cuidador particular: 1:1 verify direto. Sem fallback de
  "você é X, Y, Z" (só 1 opção).
- individual: o "cuidador" é o próprio paciente. Persona = paciente.
  Sofia fala em primeira pessoa direto ("você", não "ela").

**Tom da Sofia** (impacto futuro):
- ILPI/clinica/hospital: técnico, direto, registro clínico.
- B2C: acolhedor, mais explicativo, considera que não há
  treinamento clínico.
- individual: conversacional, confortante, pergunta se quer falar
  com humano se algo grave.

### 1.3 Onde o tenant_type já é lido

Hoje só está no schema (migration 052). Próximas integrações:

- `shift_resolver_service.list_active_caregivers()` → log diferente
  baseado em tenant_type
- `pipeline._handle_audio` / `_handle_text` → escolha de prompt
  por tenant_type
- `sofia-service` → carrega system prompt diferente por tenant_type
- Frontend: telas de cadastro de plantão escondidas em B2C/individual

---

## 2. Input por texto

### 2.1 Cenário real

Cuidador está no quarto, paciente acordado. Vai gravar áudio dizendo
"a dona Maria recusou o jantar e tá com diurese reduzida"? **Não**:

- Paciente ouve o relato sobre si mesmo
- Cuidador se sente exposto / desrespeitoso
- Em ambiente silencioso (madrugada) áudio é invasivo

Cuidador prefere digitar texto. Sistema deve aceitar **com toda a
mesma análise** que faz pra áudio:
- Classificação multi-label nas 8 classes
- Extração estruturada (PA, glicemia, etc.)
- Severidade
- Possível confirmação

### 2.2 Estado atual (parcialmente coberto)

`_handle_text` hoje:

- ✅ Detecta sessões legadas (confirmação SIM/NÃO de paciente)
- ✅ Detecta resposta a lembrete de medicação
- ✅ Detecta sessão de onboarding B2C (ADR-026)
- ✅ Faz follow-up de evento ATIVO via texto
- ✅ **Agora** identifica caregiver via phone_type + plantão (commit
  hoje)
- ❌ **NÃO** cria evento novo a partir de texto (manda "envie áudio")

A lacuna é o item 6: **texto não inicia relato novo**. Hoje força o
cuidador a usar áudio mesmo quando não pode/quer.

### 2.3 O que falta — sprint dedicado

Quando o classifier de 8 classes estiver pronto
(`input_classifier_service.py` da consolidação do panel), refatorar
`_handle_text` pra:

```
Mensagem de texto chega
  ↓
Tem evento ativo do mesmo phone?
  ↓
SIM → follow-up text (já funciona)
NO  → roda input_classifier sobre o texto
       ↓
       Classifier diz: classe + severidade + extracted + confidence
       ↓
       É relato substantivo? (classifier retornou classes != [])
       ↓
       SIM → cria report + care_event direto, igual fluxo de áudio
              (skipping STT, já é texto)
       NO  → texto curto/saudação. Sofia conversa, não cria evento.
```

Estrutura proposta:

```python
def _handle_text(self, phone: str, text: str, data: dict) -> dict:
    tenant = settings.tenant_id

    # ... (sessões legadas, onboarding — sem mudança)

    active_events = self.events.list_active_by_caregiver(tenant, phone)

    if active_events:
        # Follow-up — comportamento atual
        return self._handle_followup_text(...)

    # NOVO: tenta interpretar texto como relato
    classified = self.input_classifier.classify(
        transcription=text, source="whatsapp_text",
    )
    if classified["classes"]:
        # Relato substantivo — roda fluxo de criação igual ao áudio
        return self._create_event_from_text(phone, text, classified, data)

    # Texto sem conteúdo clínico — Sofia conversa
    return self._handle_chitchat(phone, text)
```

`_create_event_from_text` é basicamente `_handle_audio` sem STT
nem biometria. Reusa: `reports.create_initial`,
`_identify_caregiver_no_voice` (já existe), `_resolve_patient`,
`events.create`, etc.

### 2.4 Riscos a resolver

1. **False positive** — "obrigado" classifica como relato? Threshold
   de confidence + classifier ter intent "saudação" como uma das
   classes (que NÃO cria evento).

2. **Texto ambíguo** — "Maria está mal" pode ser dor, agitação,
   confusão. Classifier retorna confidence baixa → Sofia pergunta:
   "Pode descrever melhor o que tá acontecendo? Dor, agitação ou
   outra coisa?".

3. **Cuidador não cita paciente** — em ILPI multi-paciente, "ela
   recusou jantar" não diz quem. Mesma lógica que áudio: pergunta
   nome/desambigua se há múltiplos eventos ativos.

---

## 3. Cruzamento dos 2 pontos

B2C + texto interagem:

- **B2C com 1 paciente**: cuidador particular manda "PA 14/9 da
  dona Maria" → não precisa perguntar quem é (só 1 paciente). Cria
  evento direto.

- **individual** (paciente solo): manda "tô com dor de cabeça forte"
  → persona = paciente, primeira pessoa, severidade alta → Sofia
  cria evento e pergunta se chama emergência.

- **ILPI com texto**: cuidador entrou no quarto, digita "Sr José
  caiu, sem trauma aparente" → classifier vê queda + nome → cria
  evento crítico, dispara escalation, igual áudio.

---

## 4. Roadmap de implementação

### Sprint 1 (já feito, neste merge)

- [x] Migration 052: `tenant_type` enum em tenant_config
- [x] Helper `_identify_caregiver_no_voice` no pipeline
- [x] `_handle_followup_text` registra caregiver_id e fallback_options

### Sprint 2 (depende do classifier 8 classes)

- [ ] `input_classifier_service.py` operacional
- [ ] Refactor `_handle_text` pra criar evento a partir de texto
- [ ] `_create_event_from_text` espelhando `_handle_audio` sem STT
- [ ] Tratamento de confidence baixa em texto (pergunta de
      desambiguação)
- [ ] Tratamento de saudação / chitchat sem criar evento

### Sprint 3 (B2C-specific)

- [ ] `tenant_type` lido pelo `shift_resolver` (não logar warning
      em B2C/individual com pool vazio)
- [ ] Sofia carrega system prompt por tenant_type
- [ ] Frontend: tela de cadastro de plantão escondida em
      B2C/individual
- [ ] Onboarding diferente para B2C/individual (já parcialmente
      coberto pelo ADR-026)

---

## 5. Decisões pendentes pra Alexandre

1. **B2C: 1 paciente ou múltiplos?** Modelo de licenciamento (filho
   contrata pra mãe E pai = 2 pacientes B2C, ou são 2 contas
   individual?).

2. **Tom de Sofia em individual**: trato por "você" mesmo ou
   pergunta no onboarding como prefere? (Senhor/senhora vs primeiro
   nome).

3. **Limite de mensagens texto**: hoje qualquer cuidador pode mandar
   N textos por dia. Em B2C com mensalidade, vale ter cap?
