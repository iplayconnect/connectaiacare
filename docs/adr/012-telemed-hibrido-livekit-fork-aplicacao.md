# ADR-012: Tele-consulta híbrida — reuso LiveKit + fork da camada médica

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: architecture, telemedicine, integration, ecosystem

## Context and Problem Statement

A ConnectaIACare pretende incluir **tele-consulta médica com insights em tempo real** — médico conectado ao paciente via vídeo com **dashboard lateral mostrando prontuário, sinais vitais live, histórico de relatos, alertas de biometria e análise IA**, com **prescrição digital integrada**. Essa feature não é só "mais um vídeo" — transforma a proposta de "plataforma" em **ecossistema de cuidado**.

A ConnectaIA já opera **ConnectaLive** (módulo de videoconferência com LiveKit WebRTC + transcription Deepgram + Socket.IO bridge), usado para reuniões comerciais (SDR ↔ lead). A pergunta natural é: **reusar ConnectaLive** (padrão ADR-007) ou **clonar** e customizar para saúde?

Esta decisão é **diferente** da tomada em ADR-007 (Sofia Voz), porque tele-consulta médica tem particularidades que criam acoplamento profundo com o resto do sistema de saúde.

## Decision Drivers

- **Acoplamento com prontuário**: diferente de Sofia Voz (input/output delimitado), tele-consulta precisa **ler e escrever no prontuário durante a sessão** — mostrar histórico, anexar transcription, salvar prescrição
- **UI radicalmente diferente**: ConnectaLive foca em UX comercial (SDR prepara pitch, vê lead data). Tele-med precisa de **dashboard clínico lateral** (vital signs streaming, timeline relatos, alertas biométricos) — divergência de produto, não só de cores
- **Compliance específica**: CFM Resolução 2.314/2022 define requisitos de registro da consulta, consentimento informado registrado, arquivamento 20 anos (CFM 1.821). ConnectaLive hoje não cobre isso
- **Integrações novas e críticas**:
  - **Memed / Nexodata**: prescrição digital com farmácias credenciadas
  - **ICP-Brasil**: assinatura digital médica com validade jurídica
  - **MedMonitor**: streaming de sinais vitais live durante consulta
- **Vocabulário da transcription**: ConnectaLive transcreve linguagem comercial; tele-med precisa de prompts médicos, reconhecimento de CID-10, nomes de medicamentos
- **Storage/retention**: prontuário médico = 20 anos CFM; gravação de venda = prazo comercial curto
- **Eventual JV/Spin-off**: se ConnectaIACare virar empresa separada, código e dados precisam ser separáveis

## Considered Options

- **Option A**: Reuso completo via API (padrão ADR-007 Sofia Voz) — chamar ConnectaLive como microsserviço
- **Option B**: Clone completo do ConnectaLive (fork do repo + LiveKit próprio + tudo duplicado)
- **Option C**: **Modelo híbrido — reuso da infra técnica + fork da camada de produto médico** (escolhida)

## Decision Outcome

Chosen option: **Option C — Híbrido**

**Reusa**: infra técnica de LiveKit (WebRTC signaling, TURN servers, containers de relay), scheduling base, primitives de branding. Isso é tecnologia genérica, clonar seria desperdício.

**Fork**: camada de produto — UI do médico, integrações (MedMonitor, Memed, ICP-Brasil), transcription clínica, compliance CFM, storage/retention. Isso é produto específico que não pertence ao ConnectaLive.

### Positive Consequences

- **Evita divergência de infra LiveKit** — LiveKit é caro de operar bem (STUN/TURN, reliability); reusar faz sentido operacionalmente
- **Liberdade total na camada de produto** — dashboard médico evolui sem pedir permissão ao time ConnectaLive
- **Compliance isolada** — CFM/ANVISA requirements ficam no nosso escopo, não contaminam o produto comercial
- **Facilita JV/spin-off** — quando ConnectaIACare virar empresa, a camada médica vai junto; ConnectaLive fica com a ConnectaIA
- **Tempo ao mercado razoável** — não precisamos reconstruir WebRTC, só montar a camada médica em cima

### Negative Consequences

- **Dependência contratual** do time ConnectaLive para mudanças na infra LiveKit (ex: upgrade de versão, ajuste de codec)
- **Custo operacional compartilhado** de LiveKit — precisa ter acordo claro sobre rateio de TURN bandwidth
- **Complexidade operacional**: 2 camadas para debugar (LiveKit genérico + lógica médica nossa)
- **Risco de incompatibilidade futura**: se ConnectaLive fizer breaking change na API de signaling, precisamos migrar

## Pros and Cons of the Options

### Option A — Reuso completo via API ❌

- ✅ Entrega rápida (ADR-007 já provou o padrão)
- ❌ **Impossível**: dashboard médico precisa acessar prontuário em tempo real — não encaixa em API call-response
- ❌ Compliance CFM exige controle do código (como transcription é armazenada, como prescrição é assinada)
- ❌ UI do médico é um produto diferente, não uma skin do ConnectaLive

### Option B — Clone completo

- ✅ Autonomia total, zero dependência
- ✅ Pronto para JV desde o dia 1
- ❌ Duplicação de infra LiveKit (STUN/TURN, signaling) — custo operacional ~R$ 3-8k/mês sem valor agregado
- ❌ Dias/semanas de trabalho para recriar o que já funciona
- ❌ Manutenção paralela de infra genérica (upgrades LiveKit, correções de bug)
- ❌ Se LiveKit lançar feature nova, precisa portar manualmente

### Option C — Modelo híbrido ✅ Chosen

- ✅ Reusa o que faz sentido reusar (infra técnica genérica)
- ✅ Forka o que faz sentido forkar (produto médico específico)
- ✅ Melhor trade-off custo/autonomia
- ✅ Facilita JV/spin-off futuro (camada médica já separada)
- ❌ 2 times precisam de alinhamento para API de integração
- ❌ Incompatibilidade futura de LiveKit é risco residual

## Design Notes

### Estrutura do fork

```
connectaiacare/
├── backend/src/services/
│   ├── telemed/
│   │   ├── livekit_client.py        # SDK LiveKit — chama a infra da ConnectaLive
│   │   ├── consultation_service.py  # Lógica de consulta (create, join, end)
│   │   ├── prescription_service.py  # Memed/Nexodata + ICP-Brasil
│   │   ├── realtime_insights.py     # Streaming MedMonitor + prontuário live
│   │   └── transcription_clinical.py # Deepgram + prompts médicos
│   └── handlers/telemed_routes.py   # API REST para frontend
├── frontend/src/app/
│   ├── telemed/
│   │   ├── join/[session_id]/page.tsx   # Paciente entra na consulta
│   │   └── doctor/[session_id]/page.tsx # Médico com dashboard lateral
│   └── components/telemed/
│       ├── VideoPanel.tsx              # Wrapper LiveKit React
│       ├── PatientLivePanel.tsx        # Dashboard lateral médico
│       ├── VitalsStreamCard.tsx        # MedMonitor live
│       ├── ReportTimelineCard.tsx      # Relatos recentes
│       ├── PrescriptionPad.tsx         # Prescrição digital
│       └── ConsentModal.tsx            # CFM 2.314 consentimento
```

### Integração com LiveKit (reuso)

ConnectaLive expõe:
- Endpoint para criar room (retorna token JWT LiveKit)
- Webhook de eventos (participant joined/left, recording ready)
- Storage de recording (com acesso via URL assinada)

ConnectaIACare chama esses endpoints, mas **NÃO** usa a UI da ConnectaLive — tem sua própria integração LiveKit React SDK direto.

### Novas tabelas

```sql
-- Migration futura:
CREATE TABLE aia_health_consultations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    patient_id UUID REFERENCES aia_health_patients(id),
    doctor_id UUID REFERENCES aia_health_doctors(id),  -- nova tabela
    livekit_room_name TEXT NOT NULL,
    livekit_recording_url TEXT,
    scheduled_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    consent_ip TEXT,
    consent_at TIMESTAMPTZ,
    transcription_clinical JSONB,  -- completa com timestamps
    clinical_notes TEXT,            -- médico pode anotar durante
    classification TEXT,            -- followup | stable | urgent
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE aia_health_prescriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    consultation_id UUID REFERENCES aia_health_consultations(id),
    patient_id UUID REFERENCES aia_health_patients(id),
    doctor_id UUID REFERENCES aia_health_doctors(id),
    items JSONB NOT NULL,             -- medicamentos, dosagem, posologia
    icp_signature TEXT NOT NULL,      -- assinatura digital
    memed_id TEXT,                    -- ID na Memed se integrado
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE aia_health_doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    crm TEXT NOT NULL,                -- registro profissional
    crm_uf TEXT NOT NULL,
    specialty TEXT,
    icp_brasil_cert TEXT,             -- referência ao certificado
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Fluxo de consulta

```
1. Agendamento: paciente/cuidador pede consulta → sistema cria aia_health_consultations
2. Notificação: WhatsApp pra paciente + email pro médico com link
3. Consentimento: paciente abre link, lê termo CFM 2.314, aceita (consent_at)
4. Médico entra no /telemed/doctor/<id>: vê
   - Painel central: vídeo do paciente
   - Painel direito: dashboard live
     · Sinais vitais MedMonitor (último streaming)
     · Timeline dos 10 relatos mais recentes
     · Alertas biometria (se qualquer cuidador reportou algo nas últimas 48h)
     · Condições + medicações atuais
     · Análise IA do último relato
5. Durante: transcrição clínica em tempo real, médico anota em clinical_notes
6. Ao fim: médico preenche prescrição (opcional) → assina via ICP-Brasil → Memed gera receita
7. Pós: consultation_service salva recording, transcription, prescription; envia resumo pro paciente via WhatsApp
```

### Roadmap de implementação

| Fase | Prazo estimado | Entrega |
|------|---------------|---------|
| 0 | — | **Este ADR** |
| 1 | 2-3 semanas (pós-MVP ConnectaIACare) | Ajustar ConnectaLive para expor API de "create room" + webhook de eventos. Alinhar com time ConnectaIA |
| 2 | 3-4 semanas | Backend tele-consulta: `consultation_service`, `telemed_routes`, migrations |
| 3 | 3-4 semanas | Frontend `/telemed/doctor` + `/telemed/join` com painel lateral dinâmico |
| 4 | 2 semanas | Integração MedMonitor live (WebSocket streaming de sinais vitais) |
| 5 | 3-4 semanas | Prescrição digital: Memed API + ICP-Brasil + PrescriptionPad |
| 6 | 2 semanas | Compliance CFM: ConsentModal, auditoria completa, retention 20 anos |

**Total estimado**: 15-20 semanas após MVP atual. Considerar começar em paralelo à Fase 1 do eldercare.

## When to Revisit

- Se ConnectaLive for deprecada ou pivotar em direção incompatível → migrar para LiveKit SDK direto ou Daily.co
- Se volume de consultas exceder capacidade da infra ConnectaLive compartilhada → negociar dedicado ou mover para infra própria
- Quando ConnectaIACare formalizar como JV separada → migrar camada LiveKit para infra própria no cap-table

## Non-goals (explicit)

- **Não substituir a consulta presencial** — tele-consulta é uma modalidade adicional, não exclusiva
- **Não fazer diagnóstico autônomo** — IA gera **insights**, médico decide (mesma postura do pipeline ConnectaIACare)
- **Não substituir prontuário hospitalar** — consultas tele-med integram via FHIR (roadmap) com prontuário da rede
- **Não fazer triagem clínica** pelo chat do paciente — isso fica com atenção primária (Amparo integration futura)

## Links

- Relacionado: [ADR-007](007-sofia-voz-como-servico-externo.md) — padrão de reuso que NÃO se aplica aqui (contraste)
- Relacionado: [ADR-001](001-stack-isolada-da-connectaia.md) — princípio de isolamento que a camada forkada respeita
- Relacionado: [ADR-011](011-locale-aware-architecture-para-latam-europa.md) — tele-consulta precisa ser locale-aware no dia 1 (termos CFM em pt-BR, GDPR em EU)
- Externo: [CFM Resolução 2.314/2022](https://sistemas.cfm.org.br/normas/visualizar/resolucoes/BR/2022/2314)
- Externo: [LiveKit Self-Hosted](https://docs.livekit.io/home/self-hosting/deployment/)
- Externo: [Memed API](https://api.memed.com.br/docs)
- Externo: Memória de projeto: `project_connectalive.md`, `project_connectalive_transcription.md`
