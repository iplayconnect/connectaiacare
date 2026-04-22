# ADR-023: Teleconsulta — arquitetura completa (Opção 3 demo 28/04)

- **Date**: 2026-04-21
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: telemedicine, livekit, clinical-ai, compliance, cfm
- **Refines**: [ADR-012](012-telemed-hibrido-livekit-fork-aplicacao.md) (tele-consulta híbrida — reuso LiveKit)

## Context and Problem Statement

ADR-012 decidiu por "tele-consulta híbrida" (reusa LiveKit existente + fork da camada de aplicação clínica), mas não materializou a arquitetura da camada médica. Com a demo adiada pra 28/04 incluindo Maurício como stakeholder com conhecimento profundo de dados clínicos, o escopo se expandiu pra **Opção 3 (completa)**:

- Sala LiveKit + consentimento + identidade
- Transcrição ao vivo durante consulta (Deepgram streaming)
- Sugestão de hipóteses CID-10 durante a consulta (apoio, não decisão)
- Prontuário SOAP automático pós-consulta (médico edita antes de assinar)
- Validação de interações medicamentosas (mocked, aponta roadmap Vidaas/ICP-Brasil)
- FHIR R4 Bundle ao final (interop com futuros sistemas)
- Sync automático pro TotalCare como care-note (ADR-019)

Precisamos decidir a arquitetura dos agentes, prompts, state machine, e endpoints.

## Decision Drivers

- **Demo 28/04 com Maurício precisa impressionar** sem cair em falsidade ("isso é mock" dito ao vivo)
- **Separação clara de responsabilidades**: IA é *scribe clínico + apoio*, médico é *decisor*
- **Compliance CFM 2.314/2022**: médico valida SOAP antes de assinar; IA nunca diagnostica
- **LGPD Art. 11 (dado sensível de saúde)**: consentimento explícito de gravação, retenção 20 anos
- **Reuso do framework Íris** (ADR-021): teleconsulta é 1 workflow, não monólito
- **Prescrição mocked agora, real depois**: arquitetura preparada pra ICP-Brasil/Vidaas sem refactor
- **Persona médica demo** (Dra. Ana Silva CRM/RS 12345): Maurício pode "vestir" pra simular consulta na demo

## Considered Options

- **Option A**: Minimal — só sala LiveKit + resumo pós (1 agente, sem compliance)
- **Option B**: Realista — sala + consent + SOAP automático pós + edição do médico + sync TotalCare (4 agentes)
- **Option C**: Completa — tudo de B + transcrição ao vivo durante consulta + sugestão diagnóstica em tempo real + validação de prescrição + FHIR bundle (6 agentes) (escolhida)

## Decision Outcome

Chosen option: **Option C — arquitetura completa** (6 agentes clínicos + workflow Íris de 9 estados + infraestrutura LiveKit + prescrição mocked).

### Workflow Íris: `teleconsultation.py`

State machine de 9 estados. Diferente do `geriatric_incident` (event-driven), esse é **session-driven** — representa uma sessão de consulta.

```
scheduling               ← agendada, médico vê no dashboard
  ↓ [medico clicou "iniciar"]
pre_check                ← 30s antes de criar sala, médico revisa ficha
  ↓ [start click]
consent_recording        ← paciente entra, sistema pergunta "autorizo gravação?"
  ↓ [sim registrado]
identity_verification    ← sistema mostra nome/doc esperado, paciente confirma
  ↓ [match]
active                   ← consulta em andamento, transcrição ao vivo + agentes IA
  ↓ [medico clica "encerrar"]
closing                  ← medico revisa o que quer formalizar
  ↓ [system processing]
documentation            ← IA gera SOAP estruturado + hipóteses CID + receita sugerida
  ↓ [medico edita e aprova]
signed                   ← prontuário assinado (digital mocked), FHIR bundle emitido
  ↓ [close click]
closed                   ← care_event resolvido, care-note criada no TotalCare
```

### 6 Agentes clínicos (específicos, não reaproveitados)

Cada um tem prompt próprio em `src/prompts/teleconsulta/`.

| Agente | Arquivo | Modelo | Quando roda |
|---|---|---|---|
| `consent_recorder` | `clinical/consent_recorder.py` | Claude Haiku | `consent_recording` — valida resposta de consentimento |
| `identity_verifier` | `clinical/identity_verifier.py` | Claude Haiku | `identity_verification` — valida identidade via pergunta de segurança |
| `anamnesis_taker` | `clinical/anamnesis_taker.py` | Claude Sonnet | `active` (streaming) — estrutura HDA em tempo real a partir da transcrição |
| `diagnosis_suggester` | `clinical/diagnosis_suggester.py` | Claude Opus | `active` (batch a cada 2min) — propõe CID-10 candidatos no painel do médico |
| `prescription_validator` | `clinical/prescription_validator.py` | Claude Sonnet | `documentation` (on-demand) — valida interações/alergias se médico prescreve |
| `soap_writer` | `clinical/soap_writer.py` | Claude Opus | `closing → documentation` — gera prontuário SOAP estruturado |
| `fhir_emitter` | `clinical/fhir_emitter.py` | Determinístico | `signed` — converte SOAP pra FHIR R4 Bundle (sem LLM) |

### Schema de dados

Nova migration 006:

```sql
CREATE TABLE aia_health_teleconsultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    care_event_id UUID REFERENCES aia_health_care_events(id),
    patient_id UUID NOT NULL REFERENCES aia_health_patients(id),
    doctor_id UUID,                 -- FK futura pra tabela de medicos
    doctor_name TEXT,
    doctor_crm TEXT,

    state TEXT NOT NULL DEFAULT 'scheduling'
        CHECK (state IN ('scheduling','pre_check','consent_recording',
                         'identity_verification','active','closing',
                         'documentation','signed','closed')),

    -- Sala LiveKit
    livekit_room_name TEXT,
    livekit_room_sid TEXT,

    -- Consent
    consent_recorded_at TIMESTAMPTZ,
    consent_audio_hash TEXT,         -- hash SHA256 do áudio de consentimento

    -- Identidade
    identity_verified_at TIMESTAMPTZ,
    identity_method TEXT,            -- 'security_question' | 'document_photo'

    -- Transcrição
    transcription_full TEXT,
    transcription_language TEXT DEFAULT 'pt-BR',

    -- Estruturado (output dos agentes)
    anamnesis JSONB,                 -- HDA estruturada
    diagnosis_suggestions JSONB,     -- [{cid, description, confidence, reasoning}]
    soap JSONB,                      -- {subjective, objective, assessment, plan}
    prescription JSONB,              -- [{medication, dose, schedule, duration, validated}]
    fhir_bundle JSONB,               -- Bundle completo pra interop

    -- Assinatura
    signed_at TIMESTAMPTZ,
    signed_by TEXT,                  -- nome do médico
    signature_method TEXT,           -- 'mock' | 'vidaas' | 'icp_brasil'
    signature_ref TEXT,              -- ref externa (vidaas signature_id ou null)

    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_teleconsult_patient ON aia_health_teleconsultations(patient_id);
CREATE INDEX idx_teleconsult_care_event ON aia_health_teleconsultations(care_event_id);
CREATE INDEX idx_teleconsult_state ON aia_health_teleconsultations(tenant_id, state)
    WHERE state NOT IN ('signed','closed');
```

### Endpoints REST (a implementar em `src/handlers/teleconsulta_routes.py`)

```
POST   /api/teleconsulta/start                  cria sessão + sala LiveKit (corpo: care_event_id, doctor_info)
POST   /api/teleconsulta/:id/consent             valida e registra áudio de consentimento
POST   /api/teleconsulta/:id/verify-identity     valida resposta de pergunta de segurança
POST   /api/teleconsulta/:id/transcription       ingest chunks de transcrição (Deepgram streaming)
GET    /api/teleconsulta/:id/diagnosis-hints     retorna sugestões CID-10 (polling do painel médico)
POST   /api/teleconsulta/:id/close               médico clica "encerrar", inicia documentação
GET    /api/teleconsulta/:id/soap                retorna SOAP gerado pra médico editar
PUT    /api/teleconsulta/:id/soap                médico salva edição
POST   /api/teleconsulta/:id/prescription        valida prescrição (mocked)
POST   /api/teleconsulta/:id/sign                assina (mocked) + gera FHIR + sync TotalCare
GET    /api/teleconsulta/:id                     estado completo
```

### Transcrição ao vivo durante consulta

Arquitetura streaming:

```
Browser (livekit-client) captura áudio
    ↓ (WebRTC track)
LiveKit server
    ↓ (egress track → audio stream)
connectaiacare-api (websocket ou long polling)
    ↓
Deepgram Streaming API (pt-BR, nova-3 quando disponível)
    ↓
Transcription chunks → POST /api/teleconsulta/:id/transcription
    ↓
anamnesis_taker (roda batch a cada 30s sobre chunk acumulado)
    ↓
Painel médico atualiza em tempo real
```

**Alternativa pra demo (simpler)**: transcrição **não é streaming real**, médico clica "encerrar" e a gravação inteira vai pra Deepgram batch. Mostra resultado em ~3s. Funciona bem pra demo de 15min de consulta = ~500KB de áudio.

Decisão pra demo: **batch pós-consulta** (não streaming). Streaming fica pós-demo (complexity vs payoff pra demo não vale).

### Prescrição mocked (estrutura pronta pra real)

```python
# Quando médico prescreve (UI), sistema:
# 1. prescription_validator valida (interação + alergia + dose usual)
# 2. Se OK, cria registro com signature_method='mock'
# 3. Gera PDF visual com template oficial (CRM, CID, RENAME)
# 4. QR code no PDF aponta pra care.connectaia.com.br/verify/{id}
#    (tela que mostra "assinatura de demonstração — integração Vidaas em dev")
# 5. Na página de verify: banner amarelo "demo — produção: integração ICP-Brasil"
```

Na demo, Alexandre mostra: *"Esta é a interface final. Na produção, o botão 'assinar' dispara assinatura digital via Vidaas/ICP-Brasil — integração em cronograma Q3."*

### Compliance mínimo

- **Consentimento** gravado em áudio + hash SHA256 no campo `consent_audio_hash`
- **Audit trail hash-chain** (ADR-008) — estado transita → hash-chain registra
- **Retenção 20 anos** do FHIR bundle (campo `fhir_bundle` nunca é deletado, só arquivado)
- **Identidade** verificada por pergunta de segurança na demo (em produção, pode virar doc photo OCR)
- **Médico valida e edita SOAP** antes de assinar — IA nunca decide

### Positive Consequences

- **Entrega completa pra demo** — 6 agentes cobrindo todo ciclo da consulta
- **Compliance-ready desde dia 1** — hash-chain, consentimento, edição médica, retenção
- **Interop FHIR R4** — qualquer hospital integra no futuro sem transformação
- **Prescrição mocked realista** — estrutura idêntica à produção, só assinatura muda
- **Framework Íris consolidado** — workflow teleconsultation prova que framework escala
- **Narrativa comercial forte**: "vocês estão vendo prontuário estruturado gerado por IA em <10s após a consulta, com hipóteses diagnósticas, interações medicamentosas validadas e FHIR pronto pra qualquer sistema"

### Negative Consequences

- **Demo 28/04 apertada** — 6 agentes + 9 estados + schema + endpoints em 5-6 dias
- **Dependência Deepgram batch** — áudio inteiro pra API (custo + latência ~3s)
- **Prescrição mocked** — precisa ficar visualmente claro que é mock (senão compliance/CFM pode alertar)
- **Persona Dra. Ana Silva mocked** — precisa ficar claro que CRM 12345 é demo (na tela, em todo lugar)

## Pros and Cons das 3 Options

### Option A — Minimal ❌

- ✅ Rápido
- ❌ Sem compliance, sem estrutura, sem interop
- ❌ Demonstra tecnologia básica (LiveKit), não valor clínico

### Option B — Realista ❌ Descartado

- ✅ Compliance + SOAP + sync
- ❌ Sem transcrição ao vivo (sem "wow factor")
- ❌ Sem sugestão diagnóstica (Maurício vai procurar esse feature)
- ❌ Sem FHIR (perde argumento de interop)

### Option C — Completa ✅ Chosen

- ✅ Tudo que diferencia plataforma clínica de "chat médico"
- ✅ Prova técnica definitiva
- ✅ Roadmap de prescrição real fica trivial (só troca assinatura)
- ❌ 5-6 dias apertados, exige disciplina

## Implementation plan

### Dia 1 (hoje 21/04, restante)
- [x] ADR-022 Atente fallback + ADR-023 Teleconsulta
- [x] Infra LiveKit (sala + JWT tokens + endpoints start/end/participants)
- [ ] Migration 006 `aia_health_teleconsultations` + seed persona demo (Dra. Ana Silva)

### Dia 2 (qua 22/04)
- [ ] Agentes `soap_writer` + `anamnesis_taker` + prompts específicos
- [ ] Endpoints SOAP (get, put, sign)
- [ ] Persistência de transcrição batch
- [ ] Brief Claude Design atualizado

### Dia 3 (qui 23/04, Claude Design chega 10h)
- [ ] Agente `diagnosis_suggester` + `prescription_validator` (mocked)
- [ ] Agente `fhir_emitter` determinístico
- [ ] Frontend: tela sala + consent + editor SOAP (Claude Design)

### Dia 4 (sex 24/04)
- [ ] Integração Deepgram batch pós-consulta
- [ ] Persona + mock digital signature
- [ ] Sync TotalCare via care-note na transição `signed → closed`

### Dia 5-6 (sáb 25 + dom 26)
- [ ] Gráficos de vitais (Recharts)
- [ ] Seed vitais 37 pacientes TotalCare
- [ ] Testes E2E + polish + fixes

### Dia 7 (seg 27)
- [ ] Rehearsal completo + slides + buffer

### Dia 8 (ter 28) — DEMO

## When to Revisit

- Se streaming ao vivo passar a ser essencial (feedback Maurício) → implementar Deepgram streaming pós-demo
- Se CFM/ANS exigir assinatura real antes do go-to-market → antecipar Vidaas/ICP-Brasil
- Se volume de consultas crescer >100/dia → migrar agentes LLM pra prompt caching agressivo (Claude suporta)
- Se tenant pedir multi-idioma → prompt dos agentes vira template

## Links

- [teleconsulta_service.py](../../backend/src/services/teleconsulta_service.py)
- [ADR-012 Telemed híbrido](012-telemed-hibrido-livekit-fork-aplicacao.md)
- [ADR-021 Íris framework](021-iris-framework-agentico-healthcare.md)
- [LiveKit docs](https://docs.livekit.io)
- [FHIR R4 Bundle](https://www.hl7.org/fhir/bundle.html)
- [CFM 2.314/2022](https://sistemas.cfm.org.br/normas/visualizar/resolucoes/BR/2022/2314)
