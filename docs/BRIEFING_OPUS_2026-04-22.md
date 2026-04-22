# ConnectaIACare — Briefing de Estado Atual (22-abril-2026)

> Documento preparado para consulta técnica ao Claude Opus sobre **módulo de biometria de voz**.
> Objetivo paralelo: planejar enrollment de voz para paciente + cuidador + familiar, reutilizável no B2C futuro.

---

## 1. Visão do produto

**ConnectaIACare** é uma plataforma SaaS-healthcare de cuidado geriátrico que combina relato por áudio via WhatsApp, triagem IA, teleconsulta virtual e ponte com a central humana da Tecnosenior/MedMonitor (TotalCare).

### Parceria estratégica
- **ConnectaIA** (Alexandre) — plataforma tecnológica + IA
- **Tecnosenior** (CEO Murilo) — central de atendimento humano 24h + base de pacientes
- **MedMonitor** — backend clínico legado (TotalCare) com dados reais de idosos assistidos
- **Atente** — serviço humano final de escalação (substituiu SAMU automático — ADR-022)

### Demo
- **Data**: terça-feira 28/04/2026
- **Audiência**: Murilo (Tecnosenior CEO) + Maurício (sabe dados clínicos, não é médico)
- **Status**: Ondas 0–3 completas, Onda 4 em implementação

### Produto derivado planejado (B2C)
Mesmo stack, voltado ao consumidor final (famílias que cuidam de idosos em casa, sem vinculação a Tecnosenior). Biometria de voz é **o componente chave que justifica esse fork**.

---

## 2. Arquitetura técnica

### Stack
| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.12 + Flask + Gunicorn + Socket.IO |
| Frontend | Next.js 14 (App Router) + React + Tailwind + shadcn/ui |
| DB | PostgreSQL 16 + pgvector (database `connectaiacare`, isolado da ConnectaIA) |
| Cache | Redis 7 |
| WhatsApp | Evolution API V6 (instância dedicada, compartilhada com ConnectaIA) |
| STT | Deepgram nova-2 pt-BR |
| LLM | Anthropic Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 |
| Voz (TTS bidirecional) | Sofia Voz (Grok Voice Agent) via `sofia-service:5030` |
| Teleconsulta | LiveKit (WebRTC) — `meet.connectaia.com.br` |
| Proxy/TLS | Traefik compartilhado + Let's Encrypt |

### Topologia em produção
```
Cloudflare DNS
    ↓
Traefik (Hostinger 72.60.242.245)
    ├─ demo.connectaia.com.br → connectaiacare-api (Flask:5055)
    └─ care.connectaia.com.br → connectaiacare-frontend (Next:3000)
         ↓ REST
    Rede Docker: connectaiacare_net
    ├─ connectaiacare-postgres (5433 host)
    ├─ connectaiacare-redis (6380 host)
    ↓ HTTPS externa
    APIs: Anthropic · Deepgram · Evolution · LiveKit · MedMonitor (TotalCare)
```

### Regra de deploy (NUNCA editar na VPS)
```
Local → git commit → git push → VPS git pull → docker compose up -d --build <service>
```

---

## 3. Domínios já implementados

### Onda 0 — Base (done)
- Cadastro de pacientes com foto, nickname, condições, medicações, alergias, responsável
- Seed 3 pacientes realistas (Sra. Carmen, Sra. Antônia, Sr. Otacílio)
- Reports: áudio do cuidador → Deepgram STT → entidades extraídas → análise clínica LLM
- Classificações: **routine · attention · urgent · critical**
- Sinais vitais com aferições realistas (HAS 60%, DM2 22%, IC 12%, DPOC 15%) — seed 7536 leituras com variação circadiana

### Onda 1 — Care Events (ADR-018) (done)
Substituiu o modelo antigo de "sessão única" por **eventos de cuidado com ciclo de vida**:

```
analyzing → awaiting_ack → pattern_analyzed → escalating →
    awaiting_status_update → resolved | expired
```

- Múltiplos eventos paralelos por cuidador (unique constraint por paciente)
- Timeline agregada: messages, checkins, escalations, reports
- Scheduler background (`checkin_scheduler`) com `pg_try_advisory_lock` single-writer
- Check-ins automáticos: `pattern_analysis` (+5min) · `status_update` (+10min) · `closure_check` (+30min)
- Closed reasons: `cuidado_iniciado | encaminhado_hospital | transferido | sem_intercorrencia | falso_alarme | paciente_estavel | expirou_sem_feedback | obito | outro`
- **Fix aplicado hoje (22/04)**: auto-resolve quando cuidador responde ao `status_update` com reasseguramento ("tudo ok", "falso alarme") — evento fecha com `sem_intercorrencia` sozinho

### Onda 1.5 — Sinais vitais (ADR-014)
- Integração MedMonitor opcional (pull de vitais reais)
- Visualização em tabs 7d/30d/90d, sparklines Recharts com status glow + trend
- LLM cruza vitais com sintomas da consulta/relato

### Onda 2 — Framework Íris + Atente (ADR-021, 022)
- **Íris**: framework agêntico multi-papel (mensageira entre "deuses" — LLMs especializados)
- **Atente**: substitui chamada automática SAMU; humano real avalia e escala clinicamente

### Onda 3 — Teleconsulta completa (ADR-023) (done hoje)
- Sala LiveKit compartilhada + JWT por role (doctor | patient)
- Persona médica demo seeded: **Dra. Ana Silva CRM/RS 12345** (is_demo=true, tabela `aia_health_doctors`)
- State machine 9 estados: `scheduling → pre_check → consent_recording → identity_verification → active → closing → documentation → signed → closed`
- 6 agentes IA específicos do domínio (SOAP writer, prescription validator, FHIR emitter, etc.)
- 7 endpoints REST pós-sala:
  - `GET /api/teleconsulta/:id`
  - `POST /api/teleconsulta/:id/transcription`
  - `POST /api/teleconsulta/:id/soap/generate`
  - `GET/PUT /api/teleconsulta/:id/soap`
  - `POST /api/teleconsulta/:id/prescription`
  - `POST /api/teleconsulta/:id/sign`
- **Pós-sala no frontend**:
  - Editor SOAP com 4 seções (Subjetivo, Objetivo, Avaliação, Plano) + CID-10 + diferenciais + sinais de alerta
  - Modal de prescrição com validação **Critérios de Beers + interações + alergias + dose geriátrica**
  - Assinatura mockada (roadmap: Vidaas/ICP-Brasil)
  - Geração **FHIR R4 Bundle** determinístico (Patient, Practitioner, Encounter virtual, Condition, MedicationRequest, ClinicalImpression)
  - Sync automática com TotalCare (care-note) + fecha care_event como `cuidado_iniciado`
  - Celebração pós-assinatura + download JSON FHIR

### Dashboard live (done hoje)
- Client-side polling 5s — KPIs, donut, barras SLA, hero alert e feed atualizam em sincronia
- Chip "ao vivo" com segundos desde último refresh (pausável)

---

## 4. **Estado atual da biometria de voz** (crítico para sua consulta ao Opus)

### Infra já existe no banco
```sql
aia_health_voice_embeddings
  id uuid PK
  caregiver_id uuid FK → aia_health_caregivers(id) ON DELETE CASCADE
  tenant_id text default 'connectaiacare_demo'
  embedding vector(256)  -- pgvector
  sample_label text default 'enrollment'
  audio_duration_ms int
  quality_score numeric(4,3)
  consent_ip text
  consent_given_at timestamptz
  created_at timestamptz

aia_health_voice_consent_log
  id bigserial PK
  caregiver_id uuid FK (SET NULL)
  tenant_id text
  action text CHECK IN (
    'consent_given', 'consent_revoked', 'data_accessed',
    'data_deleted', 'enrollment_added'
  )
  ip_address text
  user_agent text
  metadata jsonb
  created_at timestamptz
```

**Fundamental**: hoje só há enrollment para **cuidador** (caregiver_id FK). Não há slot para paciente nem familiar.

### Serviço já existe
`backend/src/services/voice_biometrics_service.py`:
- **Encoder**: Resemblyzer (VoiceEncoder, 256-dim) — ADR-005 (em vez de pyannote)
- **Pré-processamento**: `audio_preprocessing.preprocess()` → VAD + normalização + quality gate
- **Thresholds conservadores (contexto médico)**:
  - 1:1 verify ≥ 0.75
  - 1:N identify ≥ 0.65
  - Diferença top1–top2 < 0.05 → rejeita (ambíguo)
- **Quality gates**:
  - Enrollment mínimo 0.55 (55%)
  - Identificação mínima 0.30 (30%)
- **Enrollment**: até 5 samples por cuidador, completo com 3+
- **Cache em memória 5min** por tenant (otimização pgvector)

### Pipeline em uso hoje
Em `pipeline.py._identify_caregiver_by_voice()`, toda vez que chega áudio via WhatsApp:
1. Telefone identifica caregiver no DB
2. Se cuidador tem enrollment (3+ samples), tenta matchar voz do áudio contra embedding médio
3. Se confirma: grava `caregiver_id` + `caregiver_voice_method='biometric'` no report
4. Se não confirma ou não tem enrollment: prossegue sem biometria (degrada graciosamente)

### O que FALTA (seu briefing pro Opus)
1. **Enrollment do paciente** — hoje paciente não tem enrollment. Casos de uso:
   - Verificação de identidade pré-teleconsulta (ADR-023 state `identity_verification`)
   - Detecção de quem está falando em áudios enviados pelo cuidador (é a dona Antônia falando ou é a filha?)
2. **Enrollment de familiar** — nova categoria além de "caregiver" profissional:
   - Cuidador primário no B2C pode ser filho(a)/cônjuge, não enfermeiro profissional
   - Precisa FK nova ou polimórfica
3. **Tela de enrollment** — UI pública/embarcada para gravação (3–5 amostras) com consent LGPD
4. **Fluxo em WhatsApp** — enviar prompt "grave um áudio de 10s dizendo X" para enrollment remoto
5. **Anti-spoofing** — detecção de áudio sintético/deepfake (relevante pro B2C)
6. **Multi-tenant isolation** — B2C terá tenants ≠ `connectaiacare_demo`
7. **Revogação + direito ao esquecimento** (LGPD Art. 18) — já tem log, falta fluxo UI
8. **Key rotation do encoder** — troca do Resemblyzer sem reenrollar (roadmap)

### Decisões já documentadas
- **ADR-005**: Resemblyzer > pyannote (pyannote tem dependência pesada + mesma arquitetura base em cenário de conversação curta)
- **pgvector em vez de Pinecone/Weaviate**: ADR-004 (infra simples, latência local, sem custo adicional)

---

## 5. Modelo de dados — tabelas `aia_health_*`

| Tabela | Propósito |
|--------|-----------|
| `aia_health_patients` | Cadastro de idosos (FHIR-like) |
| `aia_health_caregivers` | Cuidadores profissionais (liga ao cuidador + MedMonitor) |
| `aia_health_reports` | Áudio+transcrição+análise IA |
| `aia_health_care_events` | Evento de cuidado (modelo central ADR-018) |
| `aia_health_care_event_checkins` | Check-ins automáticos do scheduler |
| `aia_health_escalation_log` | Histórico de escalações hierárquicas |
| `aia_health_alerts` | Alertas proativos (pattern detection) |
| `aia_health_vital_signs` | Aferições (PA, FC, glicemia, SpO2, temp) |
| `aia_health_vital_ranges` | Faixas personalizadas por paciente |
| `aia_health_teleconsultations` | Sessão LiveKit + SOAP + FHIR |
| `aia_health_doctors` | Médicos cadastrados (Dra. Ana Silva demo) |
| `aia_health_voice_embeddings` | **Biometria — só cuidador hoje** |
| `aia_health_voice_consent_log` | **Audit LGPD — só cuidador hoje** |
| `aia_health_audit_chain` | Hash chain (OpenTimestamps — ADR-008) |
| `aia_health_tenant_config` | Multi-tenancy timings + features |
| `aia_health_legacy_conversation_sessions` | Sessões legacy (SIM/NÃO confirmação) |

---

## 6. Integrações externas ativas

| Serviço | Uso | Chaves |
|---------|-----|--------|
| **Anthropic** | SOAP writer (Opus), prescription validator (Sonnet), análise clínica, classificação | API key produção |
| **Deepgram** | Transcrição nova-2 pt-BR (áudios WhatsApp, teleconsulta) | API key produção |
| **Evolution API** | WhatsApp in/out — webhooks + send_text/send_media/set_presence | Instância V6 compartilhada |
| **LiveKit** | Sala WebRTC (wss://meet.connectaia.com.br) | Key `connectaiacare` dedicada |
| **MedMonitor (TotalCare)** | Pull de pacientes + caretakers + vitais + push de care-notes | Via Tecnosenior |
| **Sofia Voz (Grok)** | TTS bidirecional (roadmap — não ativo na teleconsulta ainda) | `sofia-service:5030` interno |

---

## 7. ADRs já escritos (23 docs em `docs/adr/`)

| # | Título | Decisão |
|---|--------|---------|
| 001 | Stack isolada da ConnectaIA | DB + rede Docker separados |
| 002 | Compartilhar infra Hostinger | Mesmo Traefik, domínios distintos |
| 003 | Postgres compartilhado, DB separado | 1 instância, 2 databases |
| 004 | pgvector | Sem Pinecone/Weaviate |
| 005 | Resemblyzer vs pyannote | Resemblyzer (lighter, 256-dim) |
| 006 | Reaproveitar Evolution V6 | Sem onboarding WhatsApp novo |
| 007 | Sofia Voz externa | Via `sofia-service:5030` |
| 008 | Hash chain OpenTimestamps | Sem blockchain dedicada |
| 009 | Next.js 14 App Router SSR | Server Components por padrão |
| 010 | Multi-tenant dia 1 | `tenant_id` em todas tabelas |
| 011 | Locale-aware LATAM+Europa | pt-BR default, i18n pronto |
| 012 | Telemed híbrido | LiveKit fork + app shell |
| 013 | Instância Evolution dedicada | Para escalar sem colisão |
| 014 | Integração MedMonitor vitais | Pull horário |
| 015 | Topologia redes Docker | Overlay por stack |
| 017 | Sessão conversacional persistente | (precursor de care_events) |
| 018 | Care events com ciclo de vida | Modelo central |
| 019 | Integração MedMonitor TotalCare | Push de care-notes |
| 020 | Escalação hierárquica Evolution+Sofia | SDR→enfermeiro→médico→Atente |
| 021 | Íris Framework Agêntico | Multi-agent healthcare |
| 022 | Atente Fallback Humano | Substitui SAMU automático |
| 023 | Teleconsulta arquitetura completa | State machine 9 estados |

---

## 8. Próximas ondas (roadmap)

### Onda 4 — Portal do paciente + preços (em implementação agora por mim)
- PIN 6 dígitos gerado na assinatura (bcrypt hash, expires_at 24h)
- Rota pública `/meu/[tc_id]` com PIN gate
- Resumo SOAP em linguagem simples (Claude Sonnet reformula)
- Busca **real** de preços de medicamentos prescritos (reaproveitar `scraper-service` da ConnectaIA principal)
- Envio WhatsApp automático com link+PIN pós-assinatura
- Download PDF formatado (além do JSON FHIR)

### Onda 5 — Biometria expandida (você + Opus planejam)
- Enrollment de **paciente** (novo FK em `aia_health_voice_embeddings`)
- Enrollment de **familiar** (nova tabela ou polimórfica)
- UI de enrollment web + fluxo WhatsApp
- Verify pré-teleconsulta (ADR-023 state `identity_verification`)
- Anti-spoofing/deepfake detection
- Revogação self-service (LGPD)

### Onda 6 — Consent LGPD + identity pré-sala
- Modal de consentimento gravação (CFM 2.314/2022 + LGPD Art. 11)
- Verificação de identidade na entrada da sala (usa biometria da Onda 5)

### Onda 7 — Botão teleconsulta no prontuário longitudinal
- Criar evento "sob demanda" a partir do prontuário (sem WhatsApp prévio)

### Onda 8 — Rehearsal + slides + demo 28/04

### Produto B2C (pós-MVP)
- Mesma stack, sem vínculo Tecnosenior
- Fork do frontend com branding próprio
- **Biometria de voz é o diferencial** que justifica o fork
- Onboarding self-service (família + cuidador + paciente gravam separado)

---

## 9. Compliance

- **CFM 2.314/2022** — teleconsulta requer consent de gravação + verificação de identidade
- **LGPD Art. 11** — dado biométrico é sensível, requer consent específico + direito ao esquecimento
- **FHIR R4** — Bundle determinístico, pronto pra troca com outros sistemas
- **ANVISA** — prescrição digital é válida via RDC 471/2021 (receita)
- **Vidaas/ICP-Brasil** — assinatura hoje mockada, roadmap integração

---

## 10. Credenciais e URLs úteis

| Item | URL/Host |
|------|----------|
| Repo | `git@github.com:iplayconnect/connectaiacare.git` |
| Branch principal | `main` |
| Backend prod | `https://demo.connectaia.com.br` |
| Frontend prod | `https://care.connectaia.com.br` |
| LiveKit | `wss://meet.connectaia.com.br` |
| VPS | `root@72.60.242.245` (Hostinger) |
| Projeto na VPS | `/root/connectaiacare/` |
| Database prod | `postgresql://postgres:***@postgres:5432/connectaiacare` |
| Compose services | `api · frontend · postgres · redis` |

---

## 11. Perguntas-guia para o Opus sobre biometria de voz

1. **Modelagem**: fazer o enrollment polimórfico (`subject_type` + `subject_id`) ou criar três tabelas separadas (`patient_voice_embeddings`, `caregiver_voice_embeddings`, `family_voice_embeddings`)? Trade-off entre normalização e complexidade de queries.

2. **Resemblyzer em idosos**: papers mostram degradação em vozes trêmulas/afônicas. Vale testar Titanet ou ECAPA-TDNN pra esse nicho? Ou manter Resemblyzer e adaptar thresholds dinamicamente por idade/condição?

3. **Enrollment remoto via WhatsApp**: qual é a UX mínima que captura 3 samples de qualidade sem frustrar? Quantos prompts? Que frases específicas (padronizadas ou livres)?

4. **Anti-spoofing**: ASV-style (RawNet3) ou basta quality_score do preprocessing? O que é proporcional ao risco de deepfake em healthcare?

5. **Key rotation**: se mudarmos o encoder (Resemblyzer → ECAPA), re-enrollment é obrigatório ou existe técnica de domain adaptation que preserve embeddings antigos?

6. **Multi-speaker em 1 áudio**: cuidador gravando enquanto paciente fala ao fundo — dá pra identificar ambos em 1 áudio? Usar diarização + dupla identify?

7. **Storage e footprint**: 256-dim × 5 samples × N pacientes — qual é o hard limit antes de migrar de pgvector pra Qdrant/Pinecone?

8. **B2C scale**: se esse módulo virar produto, qual é a arquitetura recomendada pra 100k+ usuários (GPU inference? Cache distribuído? Sharding por tenant?)

---

**Fim do briefing.** Qualquer dúvida sobre algo específico (código, esquema, histórico), Alexandre pergunta direto aqui ou pede pra eu detalhar mais.
