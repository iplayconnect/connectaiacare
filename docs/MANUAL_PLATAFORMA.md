# Manual ConnectaIACare — Plataforma de Cuidado Integrado com IA

**Versão:** 2.0 · 2026-05-17
**Audiência:** Parceiros comerciais, equipe interna, equipe clínica em onboarding, devops
**Última atualização técnica:** sprint E-H (sidebar + modais + escalation health) — commit `84055ff`

---

# 📑 Sumário

### PARTE I — Visão e Conceito
1. [Sumário executivo (1 página)](#1-sumário-executivo)
2. [O que é a ConnectaIACare](#2-o-que-é-a-connectaiacare)
3. [Arquitetura conceitual](#3-arquitetura-conceitual)
4. [Personas e fluxos principais](#4-personas-e-fluxos-principais)

### PARTE II — Guia das Telas (UI Walkthrough)
5. [Grupo Geral (operação diária)](#5-grupo-geral-operação-diária)
6. [Grupo Administração do Tenant](#6-grupo-administração-do-tenant)
7. [Grupo Governança Clínica](#7-grupo-governança-clínica)
8. [Grupo Sistema · Cross-tenant](#8-grupo-sistema--cross-tenant)
9. [Páginas auxiliares](#9-páginas-auxiliares)

### PARTE III — Sofia em Detalhe
10. [Anatomia de um turno](#10-anatomia-de-um-turno)
11. [Pre-check de sintomas agudos](#11-pre-check-de-sintomas-agudos)
12. [Tools disponíveis](#12-tools-disponíveis)
13. [Memória em 4 camadas](#13-memória-em-4-camadas)
14. [Sub-agents (care/commercial/support)](#14-sub-agents)
15. [Identity Resolver](#15-identity-resolver)
16. [Biometria de Voz](#16-biometria-de-voz)

### PARTE IV — Manual Operacional (Como fazer X)
17. [Onboarding de novo tenant](#17-onboarding-de-novo-tenant)
18. [Importação de pacientes em massa](#18-importação-de-pacientes-em-massa)
19. [Cadastro completo de paciente (wizard)](#19-cadastro-completo-de-paciente-wizard)
20. [Configurar plantão técnico P1](#20-configurar-plantão-técnico-p1)
21. [Criar/aprovar regra clínica curada](#21-criaraprovar-regra-clínica-curada)
22. [Revisar corpus de classificação](#22-revisar-corpus-de-classificação)
23. [Auditar decisão Sofia](#23-auditar-decisão-sofia)
24. [Atender handoff P1 (operador 24/7)](#24-atender-handoff-p1)
25. [Exportar/deletar dados (LGPD)](#25-exportar-deletar-dados-lgpd)
26. [Deploy + rollback](#26-deploy--rollback)

### PARTE V — Casos Clínicos Detalhados
27. [10 cenários reais comentados](#27-cenários-clínicos-detalhados)

### PARTE VI — Compliance e Segurança
28. [LGPD por artigo](#28-lgpd-por-artigo)
29. [Padrões clínicos adotados](#29-padrões-clínicos-adotados)
30. [Supervisão clínica + Conselho Científico](#30-supervisão-clínica)
31. [Plano de resposta a incidente](#31-plano-de-resposta-a-incidente)
32. [Safety Guardrail layer](#32-safety-guardrail-layer)

### PARTE VII — Operação 24/7
33. [Modelo de plantão multi-camada](#33-modelo-de-plantão)
34. [Central ATENT 24/7](#34-central-atent-247)
35. [SLA e métricas operacionais](#35-sla-e-métricas)

### PARTE VIII — Integração e Parcerias
36. [Modelo SaaS B2B/B2C](#36-modelo-saas)
37. [Integração com parceiros (Tecnosenior, ILPIs)](#37-integração-com-parceiros)
38. [APIs externas + webhooks](#38-apis-externas)

### PARTE IX — Troubleshooting
39. [Problemas comuns + diagnóstico](#39-troubleshooting)

### PARTE X — Apêndices Técnicos
40. [Modelo de dados (principais tabelas)](#40-modelo-de-dados)
41. [Actions canônicas do audit log](#41-actions-canônicas-do-audit-log)
42. [Estados (state machines)](#42-state-machines)
43. [Endpoints da API](#43-endpoints-da-api)
44. [Variáveis de ambiente](#44-variáveis-de-ambiente)
45. [Métricas e KPIs](#45-métricas-e-kpis)

### PARTE XI — Referência
46. [FAQ](#46-faq)
47. [Glossário](#47-glossário)
48. [Roadmap detalhado](#48-roadmap-detalhado)
49. [Anexos referenciados](#49-anexos-referenciados)

---

# PARTE I — Visão e Conceito

---

## 1. Sumário executivo

**ConnectaIACare** é uma plataforma SaaS que conecta a **Sofia** (IA conversacional clinicamente supervisionada) com a equipe humana de cuidado, dentro de um modelo de **operação 24/7 multi-camada**.

### O problema

Cuidado de idosos hoje é fragmentado: cuidador relata sintoma por WhatsApp/áudio → ninguém estrutura → equipe perde sinais críticos. Família quer saber como o paciente está → ninguém responde até próxima visita. Médico precisa de contexto → depende da memória do cuidador. ILPI quer escalar → não atende 100 famílias com 5 funcionários.

Consequência: **eventos clínicos perdidos**, retrabalho, judicialização, custo alto, satisfação baixa.

### Como resolvemos

3 camadas que trabalham juntas:

1. **Sofia (IA)** recebe relatos por WhatsApp/voz, classifica clinicamente (rotina/atenção/urgente/crítico), responde com tom apropriado e abre **care events** estruturados no prontuário.

2. **Safety Guardrail** valida cada ação clínica da IA contra:
   - CIDs curados pelo nosso time (Coordenadora PUC + Henrique)
   - Doses e interações farmacológicas (Beers Criteria + cascatas)
   - Regras de cross-validation (ex: paciente com FA sem anticoagulante = alerta crítico)

3. **Equipe humana 24/7** recebe handoff dos casos críticos via push WhatsApp (P1 em 5min), enquanto rotineiros ficam disponíveis na fila pra triagem assíncrona.

### O que entrega de diferente

- **Plataforma B2B2C de verdade**: mesmo backend serve ILPI + família + paciente solo (multi-tenant nativo)
- **Sofia clinicamente supervisionada**: tudo que ela diz/faz passa por regras curadas + audit log imutável (LGPD Art. 11)
- **Acúmulo de papéis**: gestor pode ser também enfermeiro/médico (real no Brasil), sistema modela
- **Identificação multi-sinal**: phone + voiceprint + role declarado → roteamento clínico correto
- **Provenance por dado clínico**: cada condição, medicamento, alergia carrega "quem declarou, quando, quem validou" — rastreabilidade total

### Status (maio/2026)

| Item | Estado |
|---|---|
| Plataforma em produção | ✅ `care.connectaia.com.br` |
| Multi-tenant | ✅ schema desde dia 1 |
| Sofia clínica conversacional | ✅ Phase C v2 (CSM + memory layers) |
| Pre-check de sintomas agudos (P1) | ✅ regex + LLM bypass em <3s |
| Fila de handoff humano 24/7 | ✅ com SLA + push WhatsApp P1 |
| Bases curadas (CID-10, medicamentos, cross-validation) | ✅ + painel de revisão pra clínicos |
| Pacientes em piloto | Tecnosenior validado · 200+ importados |
| Equipe clínica de validação | Henrique Bordin · Coord. PUC · Geriatra UFRGS (em convite) |

---

## 2. O que é a ConnectaIACare

### Posicionamento

> Plataforma SaaS de cuidado integrado com IA, **clinicamente supervisionada**, pra idosos e pacientes crônicos. Conecta cuidadores, família, médicos e Sofia (IA) num único fluxo operacional 24/7.

### Quem usa

| Segmento | Caso de uso |
|---|---|
| **ILPI / Senior Living** | Centraliza relatos de 30-200 idosos. Cuidador relata por áudio, Sofia estrutura, equipe clínica recebe alerta priorizado. |
| **Clínica geriátrica** | Acompanhamento longitudinal de pacientes ambulatoriais. Família reporta sinais entre consultas. |
| **Atendimento domiciliar** | Cuidador profissional contratado pela família relata via WhatsApp. Médico vê tudo na mesma timeline. |
| **B2C — Idoso solo** | Idoso autônomo conversa direto com Sofia. Filhos cadastrados recebem alertas críticos. |
| **Parceiro tecnológico** (Tecnosenior, etc.) | Integra dados de prontuário próprio + recebe enriquecimento da Sofia. |

### Pilares de valor

```
                ╔═══════════════════════╗
                ║   ConnectaIACare      ║
                ╚═══════════╦═══════════╝
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │  Sofia IA   │   │  Equipe     │   │  Compliance │
  │  conversa-  │   │  clínica    │   │  + Audit    │
  │  cional     │   │  24/7       │   │  Imutável   │
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                  │                  │
    ┌────┴────┐        ┌────┴────┐        ┌────┴────┐
    │ Phone   │        │ Plantão │        │ LGPD    │
    │ E.164 + │        │ multi-  │        │ Art.11  │
    │ voz +   │        │ camada  │        │ + DPIA  │
    │ context │        │ L1-L4   │        │ + DSAR  │
    └─────────┘        └─────────┘        └─────────┘
```

---

## 3. Arquitetura conceitual

### Fluxo de uma mensagem inbound

```
┌──────────────────────────────────────────┐
│   Cuidador / Familiar / Paciente B2C     │
│   "PA tá 140x90, ele dormiu mal"         │
└──────────────────┬───────────────────────┘
                   │ WhatsApp (texto/áudio)
                   ▼
┌──────────────────────────────────────────┐
│   Evolution API (gateway WhatsApp)       │
│   Instance dedicada por tenant           │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│   Webhook v2 async (Redis Streams)       │
│   • Resolve tenant (instance → tenant)   │
│   • Idempotência por message_id          │
│   • Response < 100ms                     │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│   sofia-inbound-worker (consumer)        │
│   • Identity resolver (phone E.164)      │
│   • Voice biometrics (1:N opcional)      │
│   • CSM load (sessão ativa, lead data)   │
│   • Roteia pro sub-agente certo:         │
│     - care (cuidador identificado)       │
│     - commercial (lead anônimo)          │
│     - support (cliente cadastrado)       │
│     - passthrough (legado)               │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│   Sofia (Sonnet 4.6 + tool-use)          │
│   • Pre-check: sintoma agudo → P1 em <3s │
│   • Tools (12+): register_caregiver_report,
│     safety_review, escalate_to_human,    │
│     drug_safety, vital_sign_record, etc. │
└──────────────────┬───────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
┌─────────┐   ┌─────────┐   ┌─────────┐
│ Care    │   │ Safety  │   │ Equipe  │
│ event   │   │ rules   │   │ humana  │
│ aberto  │   │ checked │   │ (24/7)  │
└─────────┘   └─────────┘   └─────────┘
```

### Stack técnica

| Camada | Tecnologia |
|---|---|
| Backend principal | Python 3.12 + Flask + Gunicorn |
| Workers async | Python + Redis Streams + Resemblyzer |
| Frontend | Next.js 14 + React + Tailwind + shadcn/ui + Radix |
| Database | PostgreSQL 16 + pgvector + pg_trgm |
| Cache + queues | Redis 7 |
| LLM principal | Anthropic Claude Sonnet 4.6 (tool-use) |
| LLM rápido (extract) | Anthropic Haiku 4 |
| Transcrição voz | Deepgram (multi-language, nova-2) |
| TTS | ElevenLabs (vozes brasileiras customizadas) |
| WhatsApp | Evolution API v2 (instâncias por tenant) |
| VoIP | PJSIP + SIP trunking |
| Embeddings vetoriais | text-embedding-004 (Vertex AI) |
| Infra | Docker Compose + Traefik (Let's Encrypt) + Hostinger VPS |
| Observability | structlog + audit log imutável Postgres |

### Componentes-chave do backend

| Componente | Função |
|---|---|
| `webhook_async_routes.py` | Recebe POST do Evolution, valida, publica em Redis Stream |
| `sofia_inbound_worker.py` | Consumer do stream, resolve identidade, chama Sofia |
| `super_sofia_orchestrator.py` | Phase C: orquestra Sofia + sub-agents + memory |
| `sofia_agents/care.py` | Sub-agent pra cuidador identificado |
| `sofia_agents/commercial.py` | Sub-agent pra lead anônimo |
| `sofia_tools.py` | 12+ tools que Sofia pode invocar |
| `identity_resolver.py` | Phone → identidades multi-tenant |
| `voice_biometrics_service.py` | Enroll + verify + identify (Resemblyzer) |
| `safety_queue_executor.py` | Executor da fila de revisão clínica |
| `risk_scoring.py` | Score 0-100 por paciente |
| `checkin_scheduler.py` | Worker de timeline de care events |
| `proactive_caller.py` | Decide quando Sofia liga proativamente |
| `audit_log_writer.py` | Persiste audit imutável |

---

## 4. Personas e fluxos principais

### 👤 Persona 1 — Cuidador profissional (ILPI ou domiciliar)

**Quem é:** técnico de enfermagem ou cuidador formado, atende 5-15 pacientes/dia.
**Canal:** WhatsApp (texto + áudio).
**Identificação:** phone E.164 + (opcional) voiceprint cadastrado.
**Carga típica:** 10-30 relatos/dia.

**Fluxo — relato rotineiro de medicação:**
```
[Cuidador, 14h] "Acabei de dar o losartana da Dona Maria,
                 PA tava 145x88 antes do remédio."

[Sofia, 14h] "Recebi, registrei pra Dona Maria. PA acima
              do alvo individualizado (130x80) — vou marcar
              pra acompanhar nas próximas medições. Algo
              mais sobre ela hoje?"

[Sistema internamente]
  → register_caregiver_report (paciente=Maria, tipo=medication+vital_sign)
  → vital_sign_recorded (SBP=145, DBP=88)
  → classification: attention (PA > alvo individualizado)
  → Se 3 medições seguidas acima → escalate clinical (P2)
```

**Fluxo — emergência (P1):**
```
[Cuidador, 03h] "Seu Antônio tá com dor no peito"

[Sofia, 03h+3s] "🚨 Recebi. Vou acionar a equipe clínica
                  AGORA — alguém vai te chamar em instantes.
                  Se for emergência grave, ligue 192 (SAMU)
                  também."

[Sistema internamente]
  → Pre-check regex detecta "dor no peito" → bypass LLM
  → escalate_to_human_clinical(urgency=P1)
  → Push WhatsApp pra todos plantonistas P1 do tenant
  → handoff_id criado, SLA 5min
```

### 👤 Persona 2 — Familiar responsável

**Quem é:** filho(a), cônjuge, neto(a) que cuida da pessoa idosa.
**Canal:** WhatsApp + portal web.
**Identificação:** phone E.164 + relacionamento declarado no cadastro do paciente.
**Carga típica:** 1-5 mensagens/dia, consulta diária do prontuário.

**Fluxo típico:**
```
[Família] "Mãe falou que tá com fraqueza nas pernas
           desde ontem"

[Sofia] "Anotei. Já temos histórico que ela tem
         neuropatia diabética, então fraqueza nova
         merece atenção. Posso pedir que o(a) cuidador(a)
         observe se piora e te aviso amanhã se virar
         emergência?"

[Sistema]
  → care_event aberto (event_type: weakness)
  → Sofia agenda follow-up automático em 24h
  → Se sem update em 24h → reach out proativo
```

### 👤 Persona 3 — Idoso autônomo (B2C)

**Quem é:** pessoa idosa que cuida de si própria, mora sozinha ou com cônjuge da mesma idade.
**Canal:** WhatsApp (preferencial pra acessibilidade) + portal B2C.
**Identificação:** phone + voiceprint próprio (Sofia trata em primeira pessoa).
**Carga típica:** 3-10 mensagens/dia, principalmente lembretes de medicação.

**Fluxo típico:**
```
[Idoso] "Sofia, esqueci se já tomei o remédio da pressão
         hoje de manhã"

[Sofia] "Oi Dona Maria! Vou conferir aqui... Na sua
         rotina, você toma o losartana às 07h. Você
         confirmou pra mim ontem que tomou, mas hoje
         ainda não recebi confirmação. Quer que eu te
         lembre daqui a meia hora se não me avisar antes?"
```

### 👤 Persona 4 — Equipe clínica (médico/enfermeiro)

**Quem é:** profissional vinculado a um tenant (ILPI, clínica) ou múltiplos (Conselho Científico cross-tenant).
**Canal:** Painel web `care.connectaia.com.br` + WhatsApp pra alertas P1.
**Identificação:** login JWT + role (médico, enfermeiro, etc.).
**Carga típica:** 30min/dia revisando dashboard + atendimento por demanda.

**Fluxo diário:**
1. Abre Dashboard → vê eventos ativos do tenant
2. Filtra por urgência → atende P1 pendentes primeiro
3. Click no evento → vê timeline 30d do paciente + relatos + sinais vitais
4. Resolve ou escala → registra resolution_summary
5. Tudo vira audit log permanente

### 👤 Persona 5 — Gestor de unidade

**Quem é:** coordenador da ILPI / responsável administrativo.
**Canal:** Painel admin tenant.
**Identificação:** role `admin_tenant` (frequentemente acumula com `enfermeiro` ou `medico`).
**Carga típica:** 2h/semana revisando dashboards + 1h/mês compliance.

**Fluxo:**
1. Dashboard cross-tenant ou específico
2. Vê SLA da equipe (% atendidos no prazo)
3. Configura plantonistas, escala, regras clínicas customizadas
4. Acompanha consumo da Sofia (tokens, custo, alertas)
5. Audit log pra compliance (LGPD)

### 👤 Persona 6 — Operador Central ATENT 24/7

**Quem é:** profissional dedicado a atender fila de handoff cross-tenant (modelo terceirizado ConnectaIACare).
**Canal:** Painel Central · ATENT 24/7 + chat embutido.
**Identificação:** role `operador_central`.
**Carga típica:** turnos de 8h, 20-50 handoffs/turno.

**Fluxo:**
1. Login → Heartbeat ativo a cada 5min
2. Painel mostra fila priorizada (P1/P2/P3) cross-tenant
3. Reivindica (claim) handoff → fica vinculado ao operador
4. Atende no chat embutido — pode ligar pro cuidador se preciso
5. Resolve com `outcome_category` + `resolution_summary`
6. SLA tracked por turno + métrica de carga

### 👤 Persona 7 — Super Admin (ConnectaIACare interno)

**Quem é:** Alexandre, time core técnico.
**Canal:** Painel Sistema · Cross-tenant.
**Identificação:** role `super_admin`.

**Capacidades exclusivas:**
- Provisionar/suspender tenants
- Ver Dashboard cross-tenant agregado
- Acessar Sofia Proativa (outbound)
- Configurar regras clínicas master
- Acessar audit log completo
- Trigger manual de jobs (re-enrollment, recompute, etc.)

---

# PARTE II — Guia das Telas

## 5. Grupo Geral (operação diária)

### 5.1 Dashboard (`/`)

**Quem usa:** todos com permission de leitura.
**Função:** visão operacional ao vivo do tenant.

**Componentes visíveis:**

```
┌─────────────────────────────────────────────────┐
│  Dashboard                                       │
│  ─────────                                       │
│                                                  │
│  KPIs (4 cards):                                 │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                │
│  │ 12  │ │  3  │ │  47 │ │ 89% │                │
│  │ ev. │ │ P1  │ │ rel.│ │ SLA │                │
│  │ ativ│ │ abe │ │ 24h │ │ 7d  │                │
│  └─────┘ └─────┘ └─────┘ └─────┘                │
│                                                  │
│  Feed de relatos recentes (auto-refresh 5s):    │
│  [14:32] D. Maria · PA 145x88 (atenção)        │
│  [14:28] Seu Antonio · queda comunicada (urg.)  │
│  [14:15] D. Lúcia · sem intercorrência          │
│                                                  │
│  Eventos abertos por classificação:             │
│  Critical: 0 · Urgent: 3 · Attention: 5 · …    │
└─────────────────────────────────────────────────┘
```

**API consome:** `/api/dashboard/summary`, `/api/listActiveEvents`
**Atualização:** SSR inicial + polling 5s no client.

### 5.2 Alertas Operacionais (`/alertas`)

**Quem usa:** quem tem permission `alerts:read`.
**Função:** triagem de care events abertos esperando ação.

**Componentes:**
- Filtros: classificação (rotina/atenção/urgente/crítico), tenant, paciente, período
- Lista de eventos com:
  - Badge de classificação colorido
  - Timestamp de abertura + idade
  - Resumo da Sofia
  - Botão "Abrir prontuário"
  - Botão "Resolver" inline (sem sair da página)

**Diferente de "Alertas Clínicos":** este painel mostra **care_events** (eventos clínicos abertos). Alertas Clínicos mostra **clinical_alerts** (validações farmacológicas — dose, interação, contraindicação).

### 5.3 Alertas Clínicos (`/alertas/clinicos`)

**Função:** motor de validação farmacológica com lista de alertas pendentes de reconhecimento ou resolução.

**Tipos de alerta:**
- `dose_above_max` — dose acima do máximo recomendado
- `dose_below_min` — dose abaixo do mínimo terapêutico
- `interaction_major` — interação medicamentosa grave
- `interaction_moderate` — interação moderada
- `contraindication_age` — contraindicado pra faixa etária (Beers)
- `cascade_detected` — cascata de prescrição (medicamento A causa efeito colateral, B é prescrito pra tratar esse efeito)
- `cross_validation_missing` — condição declarada sem medicamento esperado

**Ações disponíveis:**
- **Reconhecer** (ack) — médico viu, vai avaliar
- **Resolver** — alterou conduta, alerta fechado
- **Falso positivo** — gera input pra ajustar regra

### 5.4 Relatos (`/reports`)

**Função:** histórico de relatos transcritos.

**Filtros:**
- Por paciente
- Por classificação (4 níveis)
- Por período (1d/7d/30d/custom)
- Por método de identificação do cuidador (voz / phone / manual)

**Cada relato mostra:**
- Áudio original (player embutido)
- Transcrição (Deepgram nova-2 PT-BR)
- Confidence da transcrição
- Entities extraídas (medicamentos, sintomas, sinais vitais)
- Análise da Sofia (resumo + classificação)
- Care event vinculado (link)
- Reporter person type (cuidador / paciente / familiar / desconhecido)

### 5.5 Pacientes (`/patients`)

**Função:** lista + prontuário 360° + cadastro novo.

**Lista:**
- Foto + nome + idade + unidade
- Score ACG resumido
- Última atividade
- Filtro por busca, unidade, severidade

**Botão "Novo Paciente":**
- Modal pequeno: nome + CPF + nascimento (mínimo)
- Cria → redireciona pro Wizard de cadastro completo

**Prontuário 360°** (`/patients/[id]`):

```
┌─────────────────────────────────────────────────┐
│  D. Maria Aparecida Santos, 78 anos              │
│  Casa 1 · Quarto 12 · Care level III             │
│  ────────────────────────────────                │
│                                                  │
│  Hero card:                                      │
│  • Foto + nome + idade + gênero                  │
│  • Score ACG (0-100) com cor por faixa          │
│  • Condições com badge (controlada/descontrol.) │
│  • Alergias em destaque vermelho                │
│  • Cuidador primário + plano ativo              │
│                                                  │
│  Ações: Editar | Cadastro Wizard | Sofia       │
│                                                  │
│  Grid principal (2 col):                        │
│  ┌─────────────────┐  ┌──────────────────┐     │
│  │ Vital Signs Grid│  │ Sofia Insights   │     │
│  │ (últimas 7d)    │  │ (resumos auto)   │     │
│  └─────────────────┘  └──────────────────┘     │
│  ┌─────────────────┐  ┌──────────────────┐     │
│  │ Timeline 30d    │  │ Medication       │     │
│  │ (eventos+meds)  │  │ Timeline +       │     │
│  │                 │  │ Adherence %      │     │
│  └─────────────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────┘
```

### 5.6 Teleconsulta (`/teleconsulta`)

**Função:** dashboard de salas Jitsi com estados:
- Agendadas (próximas)
- Em andamento (ativas agora)
- Documentação pendente (SOAP)
- Assinadas (concluídas)

**Sub-rotas:**
- `/teleconsulta/agendar?patient=X` — agendar nova
- `/consulta/[room]` — sala em si (JWT-gated, público intencional)
- `/teleconsulta/[id]/documentacao` — SOAP pós-call

### 5.7 Sofia Chat (`/sofia`)

**Função:** chat persona-aware. Profissional pode:
- Tirar dúvidas clínicas
- Pedir contexto de um paciente específico (`?patient=X`)
- Simular conversa pra treinamento
- Ver consumo de tokens/mês

**Modelo:** Gemini 3.1 Flash (mais barato que Sonnet pra chat interno).

### 5.8 Chamadas · VoIP (`/comunicacao`)

**3 tabs:**
- **Nova chamada** — escolhe paciente + cenário (playbook) → Sofia liga
- **Em andamento** — chamadas ativas com transcrição ao vivo
- **Histórico** — chamadas concluídas com transcrição + resumo + classificação

**Cenários disponíveis:** vêm de `/admin/governance/scenarios`.

### 5.9 Equipe Clínica (`/equipe`)

**Função:** CRUD de médicos, enfermeiros, cuidadores, técnicos.

**Tabs por papel:**
- Médicos (mostra CRM)
- Enfermeiros (mostra COREN)
- Cuidadores (cuidador_pro)
- Técnicos
- Inativos (histórico)

**Diferente de "Usuários do CRM":** Equipe Clínica é quem **atende** paciente (caregivers table). Usuários do CRM é quem tem **conta no painel** (users table). Podem se sobrepor (médico tem conta + é da equipe).

---

## 6. Grupo Administração do Tenant

### 6.1 Usuários do CRM (`/admin/usuarios`)

**Função:** CRUD de quem tem conta no painel.

**Campos:**
- Nome completo + email
- Papel (super_admin, admin_tenant, medico, enfermeiro, etc.)
- Papéis adicionais (multi-role) — chips
- Perfil customizado (substitui defaults se vinculado)
- Phone (pra recuperação de senha + WhatsApp)
- CRM (médicos) / COREN (enfermeiros)
- Status ativo/inativo

**Permissões:** `users:read`, `users:write`.

### 6.2 Papéis & Permissões (`/admin/perfis`)

**Função:** criar papéis customizados além dos defaults.

**Use cases:**
- "Enfermeiro Sênior" com permissions específicas
- "Familiar Premium" com acesso a dados estendidos
- "Auditor LGPD" só com permission de audit log

**Mecânica:** profile vincula a um user e sobrescreve permissions do role default. Útil pra ILPIs grandes com hierarquias particulares.

### 6.3 Biometria de Voz (`/admin/biometria-voz`)

**Função:** enrollment + cobertura de voiceprints.

**Componentes:**
- **Painel de cobertura** — % de pacientes com voiceprint + % de cuidadores
- **Enrollment manual** — selecionar paciente/cuidador, gravar 3 amostras de 5-10s
- **Histórico de identificações** — log de cada vez que voz foi usada (com score)
- **Re-enrollment alerts** — voiceprints > 90 dias (alerta cor amarelo)

**Tecnologia:** Resemblyzer (encoder 256-dim) + pgvector (similaridade cosine).
**Thresholds:** 0.75 pra 1:1, 0.65 pra 1:N.

### 6.4 Escala de Cuidadores (`/admin/plantoes`)

**Função:** turnos dos cuidadores que atendem pacientes.

**Cada turno:**
- Cuidador (caregiver_id)
- Phone type (personal/shared) — afeta pool de biometria 1:N
- Início + fim
- Pacientes cobertos
- Substituições (se cuidador faltar)

**Painel "Agora":** mostra turno ativo + ausências detectadas.

### 6.5 Fila de Revisão · Safety (`/admin/seguranca/fila-revisao`)

**Função:** ações clínicas críticas esperando aprovação humana.

**Tipos de item:**
- `medication_change` — Sofia sugeriu alteração de medicação (sempre humano)
- `dose_increase` — aumento de dose acima do padrão
- `escalation_to_specialist` — encaminhamento pra especialista
- `clinical_note_added` — nota clínica de IA esperando revisão

**UI:**
- Item com countdown (auto-exec em N minutos se action conservadora)
- Botões: Aprovar / Rejeitar / Pedir mais contexto
- Histórico de circuit breaker (se sistema entrou em modo seguro por taxa alta de erros)

### 6.6 Padrões & Compliance (`/configuracoes`)

**Função:** catálogo READ-ONLY de padrões adotados — vitrine compliance.

**8 grupos:**

1. **Interoperabilidade** — FHIR R4 resources (Patient, Observation, MedicationStatement, AllergyIntolerance, CarePlan)
2. **Codificação** — CID-10 PT-BR (DataSUS), TUSS, CIAP-2
3. **Medicamentos** — ANVISA Bulário, ATC, Beers Criteria AGS 2023
4. **Decisão clínica (CDS)** — diretrizes nacionais (SBC-DBHA 2020, SBD 2024, SBGG)
5. **Escalas** — Katz (ABVD), Lawton (AIVD), MEEM, MMSE-Br, Karnofsky, Norton, Braden
6. **Evidência** — GRADE pra classificar força de recomendações
7. **Compliance** — LGPD, HIPAA mapping, ISO 27001 (parcial)
8. **Identidade + Canais** — fluxo de identificação multi-sinal documentado

**Por que read-only:** é vitrine pra cliente B2B mostrar maturidade. Mudanças requerem PR.

---

## 7. Grupo Governança Clínica

### Sub-grupo Regras

#### 7.1 Regras Clínicas (master) (`/admin/governance/clinical-rules`)

**Função:** CRUD master de regras de validação farmacológica.

**11 tabs:**

1. **Overview** — stats (total regras, ativas, por severidade)
2. **Doses** — limites máximos/mínimos por medicamento + faixa etária
3. **Aliases** — sinônimos de medicamentos ("Captopril" = "Capoten" = "Tensicap")
4. **Interactions** — pares A+B com severidade + descrição
5-11. **Read-only** — view de produção (não-editável)

**Quem edita:** super_admin + admin_tenant (com aprovação Conselho Científico).
**Quem consome:** o motor de Alertas Clínicos.

#### 7.2 Cascatas Farmacológicas (`/admin/governance/cascades`)

**Função:** visualização das cascatas de prescrição A+B+C.

**O que é cascata:** paciente toma medicamento A, A causa efeito colateral X, médico prescreve B pra X, B causa efeito Y, prescreve C pra Y. Quando o problema era simplesmente parar A.

**Painel mostra:**
- Lista de cascatas conhecidas (curadas da literatura)
- Pacientes com padrão suspeito
- Severidade da cascata (low/moderate/high)
- Sugestão de revisão

### Sub-grupo Revisão

#### 7.3 Revisão · Clínica (`/admin/governance/review`)

**Função:** revisão sample-based pelo time interno. Cada review:
- Sample de relatos do dia anterior
- Classificação Sofia
- Box pra clínico marcar concordo/discordo
- Notas de melhoria

#### 7.4 Revisão · Corpus (`/admin/governance/corpus-review`)

**Função:** revisão case-a-case do corpus de classificação (alimenta retraining).

**Tipos de evento revisados:**
- intercorrencia (queda, perda consciência, anafilaxia)
- sintoma_novo (queixa nova sem atribuição a fármaco)
- avaliacao_funcional (ABVD/AIVD)
- evolucao_clinica (update de quadro conhecido)
- evento_adverso_medicamentoso (EAM)
- apoio_emocional (cuidador — vai pra trilha separada)
- + outros

**Fluxo:**
1. Caso aparece com classificação Sofia + LLM
2. Clínico vê todos os campos editáveis
3. Concorda → 1 click
4. Discorda → marca campos diferentes + **motivo obrigatório**
5. Salvo → entra no audit + dataset de retraining

**Important:** todo `apoio_emocional` (relato do cuidador sobre si mesmo) vai pra trilha `caregiver_wellness` separada (PHI separation — não vai pro prontuário do paciente).

#### 7.5 Revisão · Bases Curadas (`/admin/governance/curated-review`)

**Função:** revisão das 3 bases curadas (CID-10, Medicamentos, Cross-validation).

**Status workflow:**
- `draft` — entrada inicial
- `under_review` — clínico marcou pra avaliar
- `approved` — vai pra produção

**3 tabs:**

**Tab CID-10** (150 entries hoje):
- Code + descrição PT-BR + leigos + EN + categoria
- 13 categorias (cardiovascular, endócrino, neurológico, etc.)
- Reviewer notes + reviewed_by

**Tab Medicamentos** (80+):
- Princípio ativo + brand names + match patterns
- Therapeutic classes (ATC)
- Indicações principais
- Notes

**Tab Cross-validation** (8 regras baseline):
- Condition label + CID + match patterns
- Expected therapeutic classes
- Prompt severity (low/medium/high/critical)
- Prompt message (texto exibido ao usuário)
- Response options
- Clinical rationale (justificativa)

### Sub-grupo Sofia

#### 7.6 Cenários da Sofia (`/admin/governance/scenarios`)

**Função:** playbooks VoIP pré-definidos.

**Cada cenário:**
- Nome + descrição + tags
- Prompt do system (instruções Sofia)
- Persona (cuidador-style, médico, formal, casual)
- Voz (ElevenLabs ID)
- Tools habilitadas
- Ações pós-call (criar evento, agendar follow-up)
- Versionamento (cada save cria nova versão)

#### 7.7 Versões de Prompts (`/admin/governance/scenarios/versions`)

**Função:** histórico de versões + diff + rollback.

**Métricas por versão:**
- Taxa de sucesso (call completed)
- Tempo médio
- Tokens consumidos
- Avaliação humana (1-5)

#### 7.8 Testes Sintéticos (`/admin/governance/synthetic-tests`)

**Função:** bateria de cenários sintéticos pra validar regressões.

**Como funciona:**
- Cada teste = par (input, expected_output)
- Roda contra Sofia atual
- Compara classificação + tool calls
- Reporta diff
- Bloqueia deploy se regressão crítica

---

## 8. Grupo Sistema · Cross-tenant

### Sub-grupo Plataforma

#### 8.1 Dashboard cross-tenant (`/admin/system`)

**Função:** visão agregada de TODOS os tenants (super_admin only).

**Mostra:**
- Totais (pacientes, cuidadores, usuários, eventos)
- Eventos 24h
- Eventos abertos
- Série diária últimos 7 dias por classificação
- Top 5 tenants por eventos abertos
- Distribuição de classificação 30 dias

#### 8.2 Tenants (`/admin/system/tenants`)

**Função:** provisioning SaaS.

**CRUD tenant:**
- ID (slug, único — `connectaiacare_demo`, `tecnosenior`, etc.)
- Nome legível
- Tipo (ILPI / clínica / hospital / parceiro / B2C)
- Persona Sofia (ai_name, ai_voice, ai_kickoff_phrase)
- Branding (logo_url, primary_color, accent_color)
- Channels:
  - whatsapp_phone (chip number)
  - whatsapp_evolution_instance (instance name)
  - voice_did (SIP DID)
  - voice_sip_provider
- Integrations enabled (JSON config)
- Active / Suspended

**Sub-rotas:**
- `/admin/system/tenants/new` — wizard de criação
- `/admin/system/tenants/[id]` — detalhe + edit

#### 8.3 Saúde da Plataforma (`/admin/system/health`)

**Função:** uptime, latência, integrações.

**Services monitorados:**
- PostgreSQL (latência query, conexões abertas, locks)
- Redis (memória, comandos/s)
- Evolution API (webhook sync 24h, errors 24h)
- Sofia (tokens consumidos, custo, taxa de erro LLM)
- Deepgram (uptime, latência transcrição)
- ElevenLabs (uptime, latência TTS)
- VoIP gateway (chamadas ativas, falhas)
- Workers (lag do consumer, batch size)

#### 8.4 Risk Score · Pacientes (`/admin/system/health/risk-score`)

**Função:** score 0-100 por paciente baseado em:
- Queixas 7 dias (peso 30%)
- Adesão a medicação (peso 30%)
- Eventos urgent/critical 7 dias (peso 40%)

**Determinístico, sem ML.** Permite explicabilidade total.

**Níveis:**
- `critical` (≥75) — vermelho
- `high` (50-74) — laranja
- `moderate` (25-49) — amarelo
- `low` (<25) — verde

**Ações:**
- Recalcular todos (batch)
- Recomputar baselines individuais (60d histórico)
- Recompute paciente específico
- Ver breakdown drawer (qual sinal puxou o score)

### Sub-grupo Atendimento Humano

#### 8.5 Handoff · Fila (`/admin/system/operations/handoff`)

**Função:** fila de pedidos que Sofia escalou pra humano.

**Cada handoff:**
- Priority (P1/P2/P3)
- Status (pending/claimed/resolved/expired)
- Phone do cuidador
- Reason (acute_symptom_detected, drug_safety_warning_strong, etc.)
- Context preview (últimas 5 mensagens)
- SLA target (5min P1, 30min P2, 2h P3)
- Tenant
- Trace ID

**Ações:**
- Reivindicar (claim) — fica vinculado ao usuário
- Abrir chat — atender com cuidador
- Resolver — outcome_category + resolution_summary

#### 8.6 Central · ATENT 24/7 (`/admin/system/operations/central`)

**Função:** operação cross-tenant priorizada (super_admin + operador_central).

**Painel mostra:**
- Pendentes total
- Em atendimento
- P1 abertos
- SLA estourado (calculado dinamicamente)
- Resolvidos 24h
- Operadores online (heartbeat 5min)

**Tabela:**
- Tipo (clinical/commercial/suporte)
- Prioridade
- Phone
- Razão
- Resumo (truncado, hover pra ver completo)
- Status
- Espera (tempo desde criação)

**Filtros:** tipo, prioridade, tenant, período.

#### 8.7 Plantão Técnico · Contatos P1 (`/admin/system/operations/escalation-contacts`)

**Função:** CRUD de quem recebe push WhatsApp em P1.

**2 tabs:**

**Tab Contatos:**
- Lista de contatos com:
  - Nome + role (chip)
  - Phone (formatado BR)
  - **Schedule** (chips visuais: S/T/Q/Q/S/S/D + 08:00-18:00 + status "ativo agora")
  - Prioridades que recebe (P1/P2/P3 chips)
  - **Última atividade** (badge cor por idade: verde <24h, amarelo 1-7d, cinza >7d)
- Filtro "Mostrar inativos"
- Botão "Novo contato" → modal com nome + phone + role + prioridades + turno

**Tab Saúde do Plantão:**
- SLA Hero card (% P1 reivindicados em <5min últimos 7d, cor por nível)
- 4 stats agregadas
- Mini-gráfico volume P1 últimos 7 dias
- Ranking de carga por contato (top 10 com barras de progresso)
- Alerta de contatos stale (sem atividade > 30 dias)

### Sub-grupo Operações

#### 8.8 Sofia Proativa (`/admin/system/operations/proactive-caller`)

**Função:** Sofia outbound automation.

**Decide DINAMICAMENTE quando ligar baseado em:**
- Risk score do paciente
- Adesão a medicação
- Eventos abertos
- Janela horária preferida do paciente
- Calendário familiar/cuidador

**Painel mostra:**
- Fila de chamadas planejadas próximas 24h
- Histórico 7d com taxa de sucesso
- Override manual (forçar/cancelar uma)

#### 8.9 Comercial · Funil (`/admin/system/operations/comercial/funil`)

**Função:** funil de vendas ConnectaIACare interno.

**Tabs internas:**
- **Funil** — Kanban com prospects → demos → propostas → fechamento
- **Agenda** — calendário de demos agendadas
- **Planos** — catálogo de planos comerciais

#### 8.10 Leads · Lista (legado) (`/admin/system/operations/leads`)

**DEPRECATED** — substituída por Comercial · Funil. Mantida por compatibilidade até migração de histórico.

### Sub-grupo Análise

#### 8.11 Conversas · Replay (`/admin/system/conversations`)

**Função:** replay de conversas Sofia pra auditoria LGPD + análise de qualidade.

**Filtros:**
- Tenant
- Paciente
- Cuidador
- Período
- Sub-agent usado
- Resultado (resolved, escalated, abandoned)

**Cada conversa:** timeline completa de mensagens + tool calls + decisões + tempo total + tokens.

---

## 9. Páginas auxiliares

### 9.1 Login (`/login`)

Email + senha (bcrypt). JWT no cookie `care_token` (HttpOnly, Secure). 401 → redirect com `?next=`.

### 9.2 Cadastro B2C (`/cadastro/*`)

Onboarding público pra idoso solo ou família. Sem login prévio. Captura consentimento LGPD explícito.

### 9.3 Meu Perfil (`/perfil`)

Editar dados pessoais + trocar senha + ver consumo Sofia + revogar consentimentos LGPD.

### 9.4 Portal Paciente (`/meu/[id]`)

PIN-gated (sem login full). Idoso ou familiar acessa via link único com PIN.

### 9.5 Sala Teleconsulta (`/consulta/[room]`)

JWT no link. Sala Jitsi embutida. Gravação opcional (com consentimento).

### 9.6 Pitch / Planos (`/pitch`, `/planos`)

Páginas públicas de marketing. Sem auth.

---

# PARTE III — Sofia em Detalhe

## 10. Anatomia de um turno

Cada vez que um usuário manda mensagem, Sofia executa em sequência:

### Passo 1: Resolve identidade
```python
identity = identity_resolver.resolve(
    phone=normalized_phone,  # E.164 sem +
    tenant_id=tenant_id_from_webhook,
)
# Retorna: List[IdentityMatch] com tenant_id, profile, source, confidence
```

### Passo 2: Carrega CSM (Conversation State Manager)
```python
csm_state = csm.load_or_create(
    tenant_id=tenant_id,
    phone=phone,
    persona=resolved_persona,
)
# Inclui: sessão ativa (TTL 45min), lead_data, pending_question
```

### Passo 3: Extrai dados do user msg
```python
extraction = data_extractor.extract(
    text=inbound_text,
    pending_intent=csm_state.flow_state.pending_question_intent,
    current_lead_data=csm_state.lead_data,
)
# Retorna: data (dict), confidence (0..1)
```

### Passo 4: Pre-check heurístico (sintoma agudo)
```python
acute = _mentions_acute_symptom(inbound_text)
if acute:
    return _handle_acute_symptom(ctx, acute_pattern=acute)
    # → escalate_to_human_clinical(P1) em <3s, BYPASSA LLM
```

### Passo 5: Decisão LLM
```python
decision = router.complete_json(
    task="sofia_chat_tool_decision",
    cacheable_system=_cacheable_system(ctx),
    system=_dynamic_system(ctx),
    user=inbound_text[:1500],
    tools=CARE_TOOLS_SCHEMA,
    tool_choice="auto",
)
# Retorna: {action: "tool"|"text", tool_name, args, text, next_question_intent}
```

### Passo 6: Executa tool (se houver)
```python
if decision.action == "tool":
    result = execute_tool(
        tool_name=decision.tool_name,
        args=sanitized_args,  # injeta IDs do ctx só nos params aceitos
        tenant_id=ctx.tenant.id,
        trace_id=ctx.trace_id,
    )
```

### Passo 7: Persiste + audit + envia resposta
```python
write_audit(action="sofia_agent_turn", ...)
sofia_messages.insert(...)
event_bus.publish(Streams.OUTBOUND, {phone, text, ...})
```

---

## 11. Pre-check de sintomas agudos

Sofia tem **regex pre-check** que dispara em <3s, bypassando LLM, pra casos críticos. Reduz latência em emergência.

### Regex patterns (em `sofia_agents/care.py`):

```python
_ACUTE_SYMPTOM_PATTERNS = [
    # Queda
    r"\bcaiu|caiu\s+do|tombou|despencou\b",

    # Dor
    r"\bdor\s+(forte|aguda|s[úu]bita|no\s+peito|de\s+cabe[çc]a)\b",

    # Não responde
    r"\bn[ãa]o\s+(responde|reage|acorda|fala)\b",

    # Convulsão
    r"\bconvuls|crise|desmaiou|desfaleceu\b",

    # Sangramento
    r"\bsangra|hemorra|v[ôo]mit\w*\s+sangue|fezes\s+pretas\b",

    # Falta de ar
    r"\bfalta\s+de\s+ar|sufoca|n[ãa]o\s+consegue\s+respirar\b",

    # Febre
    r"\bfebre\s+(\d{2,3}|alta|persistente)\b",
]
```

### Validação real (caso Murilo 13/05)

Murilo escreveu "dor no peito" → sistema reagiu em 3 segundos:

```
18:43:38.10  webhook_received
18:43:38.10  identity_resolved (profile=cuidador)
18:43:40.40  clinical_handoff_initiated (P1, reason=acute_symptom_detected:dor no peito)
18:43:40.40  sofia_agent_turn (27ms!)
             text: "Recebi. Vou acionar a equipe clínica AGORA..."
             tool: escalate_to_human_clinical
             handoff_initiated: true
18:43:41.07  outbound_sent (admin push)
18:43:41.58  outbound_sent (resposta cuidador)
```

### Falta cobrir (roadmap)

Patterns que vamos adicionar (validação Henrique + Coord PUC):
- Dor abdominal aguda
- Confusão mental aguda
- Membro inferior pálido/frio (TEP/oclusão)
- Sangramento pós-trauma
- Reação alérgica grave (anafilaxia)
- Hipoglicemia severa
- Crise hipertensiva

---

## 12. Tools disponíveis

12+ tools que Sofia pode invocar. Cada uma com schema JSON validado.

| Tool | O que faz | Quando usar |
|---|---|---|
| `register_caregiver_report` | Cria care_event a partir de relato | Toda vez que cuidador relata algo clinicamente relevante |
| `safety_review_prescriptions` | Valida prescrição contra regras farmacológicas | Quando paciente menciona medicação |
| `escalate_to_human_clinical` | Cria handoff P1/P2/P3 | Sintoma agudo, drug safety high, cuidador pede |
| `vital_sign_record` | Registra PA/HR/temperatura/glicose | Quando vem número estruturado |
| `schedule_followup` | Agenda check-in futuro | Quando precisa acompanhar sintoma |
| `query_patient_context` | Busca prontuário 360° (RAG) | Quando Sofia precisa contexto pra responder |
| `update_lead_data` | Atualiza CSM lead data | Captura nome, idade, condição, etc. |
| `propose_voice_enrollment` | Inicia fluxo enroll de voz | Familiar/cuidador novo não cadastrado |
| `commercial_lead_capture` | Captura lead comercial | Contato pelo fluxo de vendas |
| `commercial_schedule_demo` | Agenda demo | Lead qualificado |
| `tecnosenior_lookup_patient` | Cross-reference parceiro | CPF bate com base Tecnosenior |
| `mcp_google_calendar_*` | Tools do MCP Google (calendário) | Médico quer agendar via Sofia |

### Sanitização de args

Antes de executar a tool, args do LLM são **sanitizados por tool** — injeta IDs do contexto SÓ nos params que a tool aceita. Evita TypeError quando LLM mistura params de tools diferentes.

```python
safe_args = dict(llm_args)
if 'phone' in tool_signature.params:
    safe_args['phone'] = ctx.phone
if 'patient_id' in tool_signature.params:
    safe_args['patient_id'] = ctx.identity_match.patient_id
# ... etc
```

---

## 13. Memória em 4 camadas

```
┌─────────────────────────────────────────────────┐
│  1. In-session (turno atual)                     │
│     • Lead data + pending question               │
│     • Última extração + confidence               │
│     • Stack de tool calls do turno              │
│     • Live no Python, descartada após response  │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  2. Active context cross-channel (TTL 45min)     │
│     • Cuidador começa no WhatsApp,               │
│       troca pra portal, Sofia mantém contexto    │
│     • Redis hash: `sofia:session:{tenant}:{phone}│
│     • Inclui: interactions (últimas 10),         │
│       current_agent, current_stage,              │
│       pending_question_intent                    │
│     • TTL refresh a cada interação              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  3. Per-user persistent (banco)                  │
│     • Preferências: forma de tratamento, idioma  │
│     • Voiceprint                                 │
│     • Histórico de care events                   │
│     • Adherence history                          │
│     • Tabelas: aia_health_patients,              │
│       aia_health_caregivers,                     │
│       aia_health_care_events                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  4. Semantic recall (pgvector)                   │
│     • Episódios similares do mesmo paciente      │
│     • Embeddings 768-dim (text-embedding-004)    │
│     • Query: "queda mês passado com mesmo perfil"│
│     • Retorna top-K por similaridade cosine      │
│     • Tabela: aia_health_sofia_messages          │
│       (com coluna embedding)                     │
└─────────────────────────────────────────────────┘
```

---

## 14. Sub-agents

`get_agent_for(is_anonymous, profile, intent)` decide qual sub-agent processa o turno:

| Sub-agent | Quando | O que faz |
|---|---|---|
| **commercial** | is_anonymous=True OR intent in (interesse_servico, agendar_demo) | Fluxo de vendas: captura lead, qualifica, agenda demo |
| **support** | is_anonymous=True + intent=suporte_cliente | Tira dúvidas administrativas |
| **care** | is_anonymous=False + profile in (cuidador, cuidador_pro) + flag enabled | Fluxo clínico: pre-check + tools clínicas + handoff |
| **passthrough** | Demais identificados ou flag desligada | Pipeline legado (mantém compat) |

Feature flag: `CARE_AGENT_ENABLED=true` (já ON em prod).

---

## 15. Identity Resolver

`identity_resolver.py` — resolve phone E.164 → identidades.

### Ordem de prioridade

1. **`aia_health_users.phone`** (auth, mais forte) — user tem conta
2. **`aia_health_caregivers.phone`** — cuidador cadastrado
3. **`aia_health_patients.proactive_call_phone`** — phone direto do paciente
4. **`aia_health_patients.responsible`** (JSONB) — phone do responsável
5. **`aia_health_phone_history`** — phones secundários conhecidos

### Multi-tenant

Mesmo phone pode aparecer em **2 tenants** (cuidador trabalha em 2 ILPIs). Resolver retorna **ambos**. Sofia decide:
- Se contexto de sessão ativa → mantém o tenant
- Se ambíguo → Sofia pergunta "Você está atendendo em [Tenant A] ou [Tenant B]?"

### Cache

Redis hash com TTL 60s. Invalidado em mudanças (PATCH users/caregivers/patients).

### Retorno

```python
@dataclass
class IdentityMatch:
    tenant_id: str
    profile: str  # 'cuidador_pro', 'familia', 'medico', etc.
    source: str  # 'users', 'caregivers', 'patients.proactive', etc.
    confidence: float  # 1.0 pra exact phone match
    user_id: str | None
    caregiver_id: str | None
    patient_id: str | None
```

---

## 16. Biometria de Voz

### Tecnologia

- **Encoder:** Resemblyzer (50MB, lazy-load no worker)
- **Embedding:** vetor 256-dim float32
- **Similaridade:** cosine via pgvector
- **Pré-processamento:** VAD (Voice Activity Detection) + quality gate (SNR)
- **Migrations:** 003, 050, 052, 059

### Operações

**Enroll** (`enroll(caregiver_id, audio_bytes)`):
1. VAD detecta segmentos de fala
2. Quality gate (SNR > threshold)
3. Resemblyzer extrai embedding
4. INSERT em `aia_health_voice_embeddings`
5. Log de consentimento em `aia_health_voice_consent_log`

**Verify 1:1** (`verify_1to1(caregiver_id, audio_bytes)`):
- Score cosine entre novo embedding e embeddings do caregiver
- Threshold: **0.75** (literatura Resemblyzer)
- Retorna score + accepted (bool)

**Identify 1:N** (`identify_any_1toN(tenant_id, audio_bytes)`):
- Score contra TODOS embeddings do tenant
- Top-1 com score acima de **0.65**
- Retorna identidade + score
- Cache 5min em memória (lista de embeddings agregados por tenant)

### Limites conhecidos

- **Voz idosa varia** (resfriado, prótese dentária, medicação) → roadmap J (re-enrollment 90d)
- **Replay attack** (gravação de alguém falando) → roadmap K (liveness detection)
- **Ground truth ausente** — thresholds vêm da literatura, não calibrados com áudios reais brasileiros (em coleta)

---

# PARTE IV — Manual Operacional (Como fazer X)

## 17. Onboarding de novo tenant

### Pré-requisitos
- Acesso super_admin
- Chip WhatsApp dedicado (linha física pra Evolution API)
- Logo + cores definidos

### Passos

**1. Criar tenant** (`/admin/system/tenants` → Novo)
```yaml
id: cliente_xyz
name: "Cliente XYZ Senior Living"
type: ilpi
ai_name: Sofia
ai_voice: ara  # ElevenLabs ID
ai_kickoff_phrase: "Oi! Eu sou a Sofia da Cliente XYZ..."
logo_url: https://...
primary_color: "#2563eb"
accent_color: "#06b6d4"
```

**2. Provisionar instância Evolution** (via API):
```bash
curl -X POST https://evolution.connectaia.com.br/instance/create \
  -H "apikey: $EVOLUTION_API_KEY" \
  -d '{
    "instanceName": "cliente_xyz",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS",
    "webhook": {
      "url": "https://care.connectaia.com.br/webhook/whatsapp/v2/cliente_xyz",
      "enabled": true,
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

**3. Conectar chip** — escanear QR code com WhatsApp do chip físico.

**4. Atualizar tenant com whatsapp_evolution_instance**:
```sql
UPDATE aia_health_tenants
   SET whatsapp_evolution_instance = 'cliente_xyz',
       whatsapp_phone = '5551XXXXXXXX'
 WHERE id = 'cliente_xyz';
```

**5. Criar 1º admin do tenant** (`/admin/usuarios`):
```yaml
fullName: "Alexandre Henrique"
email: alexandre@clientexyz.com.br
role: admin_tenant
phone: 5551XXXXXXXX
```

**6. Cadastrar plantonistas P1** (`/admin/system/operations/escalation-contacts`).

**7. Testar fluxo end-to-end:**
- Manda mensagem pro número do chip
- Esperado: Sofia responde com persona do tenant
- Check audit log + dashboard

---

## 18. Importação de pacientes em massa

### Opção A — CSV via UI (em roadmap)

### Opção B — REST API (atual)

```bash
curl -X POST https://care.connectaia.com.br/api/admin/patients/import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @patients.json
```

**Schema de cada paciente:**
```json
{
  "full_name": "Maria Aparecida Santos",
  "cpf": "12345678901",
  "birth_date": "1948-03-15",
  "gender": "F",
  "nickname": "Dona Maria",
  "care_unit": "Casa 1",
  "room_number": "12",
  "care_level": "III",
  "conditions": [
    {"name": "Hipertensão", "cid10_code": "I10", "source": "imported_tecnosenior"},
    {"name": "DM2", "cid10_code": "E11", "source": "imported_tecnosenior"}
  ],
  "medications": [
    {"name": "Losartana 50mg", "therapeutic_class": "BRA", "schedule": "1x/dia manhã"},
    {"name": "Metformina 850mg", "therapeutic_class": "biguanida", "schedule": "2x/dia"}
  ],
  "allergies": [{"name": "Penicilina"}],
  "responsible": {
    "name": "João Santos",
    "relationship": "filho",
    "phone": "5551XXXXXXXX"
  },
  "tecnosenior_patient_id": 12345  // se vier de parceiro
}
```

**Retorno:**
```json
{
  "status": "ok",
  "imported": 47,
  "skipped_duplicate_cpf": 3,
  "errors": [
    {"row": 12, "reason": "invalid_birth_date"}
  ]
}
```

### Pós-importação

- Rodar `POST /api/admin/patients/recompute-completeness` pra atualizar `registration_completeness`
- Backfill provenance se foi de string array → objeto array (migration 077 já roda automaticamente)

---

## 19. Cadastro completo de paciente (wizard)

### Quando usar
- Paciente importado mas faltam dados estruturados
- Cadastro novo do zero
- Atualização periódica (idoso passou em consulta nova)

### Fluxo dos 5 passos

**Passo 1 — Quem está informando:**
- Selecionar role: `paciente_b2c` / `familiar_responsavel` / `procurador` / `gestor_unidade` / `enfermeiro` / `medico`
- Se B2C ou familiar: aceitar termo LGPD (captura IP + timestamp + texto exato)

**Passo 2 — Demografia:**
- Nome, CPF (validação dígitos), nascimento, gênero
- Forma de tratamento Sofia
- "Paciente reporta sobre si mesmo" (toggle pra idoso solo)
- Acomodação (unidade + quarto + care level)

**Passo 3 — Condições:**
- Autocomplete CID-10 (subset 150 entries curados)
- Texto livre se não bater
- Severidade + controle por item
- Notas

**Passo 4 — Medicamentos:**
- Lookup de classe terapêutica em tempo real
- "Losartana" → reconhece como BRA + brand names + indicações
- Dose + posologia + notas

**Passo 5 — Revisão:**
- Alergias
- Responsável familiar
- **Cross-validation automática:** condições × medicamentos
  - FA sem anticoagulante → 🔴 crítico
  - DM sem antidiabético → 🟠 importante
  - HAS isolada → 🟡 atenção
- Prompts não-bloqueantes (orientam, não bloqueiam)

### Após finalizar
- `registration_completeness` recalculada
- `active_registration_session_id` setado pra NULL
- Audit log `patient_registration_completed`
- Redireciona pro prontuário 360°

---

## 20. Configurar plantão técnico P1

### Via UI (recomendado)

1. Abrir `/admin/system/operations/escalation-contacts`
2. Click "Novo contato"
3. Preencher:
   - Nome humano
   - Phone WhatsApp (DDI + DDD + número)
   - Role (plantonista_l1, plantonista_l2, medico_responsavel, etc.)
   - Prioridades (default só P1; P2/P3 vira ruído)
   - Turno (default 24/7; custom permite Seg-Sex 08-18, etc.)
4. Salvar

### Via SQL direto (mais rápido)

```sql
INSERT INTO aia_health_tenant_escalation_contacts (
    tenant_id, phone, contact_name, role, priorities
) VALUES (
    'connectaiacare_demo',
    '5551XXXXXXXX',
    'Alexandre Henrique',
    'admin_tenant',
    ARRAY['P1']
);
```

### Validar

1. Mandar "dor no peito" pelo WhatsApp pro chip do tenant
2. Em <5s deve chegar no seu phone:
   ```
   🚨 P1 CLÍNICO
   Cuidador 555199XXXXXXX
   Motivo: acute_symptom_detected:dor no peito
   SLA: 5min. Atender em:
   app.connectaiacare.com.br/admin/system/operations/handoff
   (handoff_id=abc12345...)
   ```

### Rotação de plantonista

```sql
-- Desativar antigo
UPDATE aia_health_tenant_escalation_contacts
   SET active = FALSE,
       deactivated_at = NOW()
 WHERE phone = 'PHONE_ANTIGO' AND active = TRUE;

-- Cadastrar novo (UNIQUE permite porque antigo é inactive)
INSERT INTO aia_health_tenant_escalation_contacts (
    tenant_id, phone, contact_name, role, priorities
) VALUES (...);
```

---

## 21. Criar/aprovar regra clínica curada

### Workflow

1. **Identificar gap** — clínico do Conselho percebe regra faltando (ex: "Beers diz pra evitar anticolinérgico em idoso, mas nossa engine não detecta")
2. **Propor regra** — admin_tenant ou super_admin abre `/admin/governance/clinical-rules`
3. **Criar com status `draft`** — não vai pra produção ainda
4. **Sinalizar `under_review`** — Conselho recebe notificação
5. **Conselho revisa** — concordo / discordo com motivo / sugestão de ajuste
6. **Aprovar** — muda status pra `approved` → entra em produção
7. **Métricas** — dashboard mostra disparos da regra + falsos positivos

### Exemplo prático

Regra: "Cuidado com anticolinérgicos em idoso > 75 anos com Alzheimer"

```sql
INSERT INTO aia_health_disease_medication_expectations (
    condition_label,
    cid10_code,
    condition_match_patterns,
    expected_therapeutic_classes,
    prompt_severity,
    prompt_message,
    clinical_rationale,
    active,
    review_status
) VALUES (
    'Alzheimer + anticolinérgico (Beers)',
    'G30',
    ARRAY['alzheimer', 'demência alzheimer'],
    ARRAY[]::TEXT[],  -- não exige classe; alerta sobre INADEQUADO
    'high',
    'Beers Criteria: anticolinérgicos devem ser evitados em idosos com demência (piora cognição). Verificar prescrição.',
    'AGS Beers 2023, evidência forte (GRADE A). Anticolinérgicos pioram função cognitiva em demência, aumentam delirium.',
    TRUE,
    'under_review'
);
```

Após Conselho aprovar:
```sql
UPDATE aia_health_disease_medication_expectations
   SET review_status = 'approved',
       reviewed_by_user_id = '<uuid-coord-puc>',
       reviewed_at = NOW()
 WHERE id = '<rule-id>';
```

---

## 22. Revisar corpus de classificação

### Workflow do revisor (Henrique, etc.)

1. Abre `/admin/governance/corpus-review`
2. Vê fila de casos a revisar (filtros por evento type, classificação Sofia, severidade)
3. Click num caso → vê:
   - Relato original (transcrição + áudio)
   - Classificação Sofia (event_type + severity + categoria)
   - Resposta da Sofia
4. **Concordo** → 1 click, registra audit
5. **Discordo** → marca campos diferentes (event_type, severity, etc.) + **motivo obrigatório**
6. Salvo → entra no audit + dataset de retraining

### Contadores

- Contador 21/21 (não 21/24 enganoso) — exclui apoio_emocional automaticamente
- Filtro por trilha: clinical / caregiver_wellness

### Trilha separada `caregiver_wellness`

Relatos de **cuidador sobre si mesmo** (tristeza, exaustão, ansiedade) NÃO vão pro prontuário do paciente. Vão pra trilha dedicada `aia_health_caregiver_wellness_reports` com visualização em painel separado (futuro).

---

## 23. Auditar decisão Sofia

### Cenário: "Por que a Sofia classificou esse relato como 'rotina' quando o cuidador disse que paciente caiu?"

### Investigação

**1. Achar o turno via audit log:**
```sql
SELECT created_at, action, payload
FROM aia_health_audit_log
WHERE payload->>'phone_redacted' LIKE '55519****4144'
  AND created_at BETWEEN '2026-05-13 18:00' AND '2026-05-13 19:00'
ORDER BY created_at;
```

**2. Filtrar pelo trace_id do turno suspeito:**
```sql
SELECT created_at, action, payload
FROM aia_health_audit_log
WHERE trace_id = '<uuid-do-turno>'
ORDER BY created_at;
```

Vai mostrar sequência completa:
- `webhook_received`
- `identity_resolved`
- `sofia_agent_turn` (com tools_called, text_preview)
- `clinical_handoff_initiated` (se escalou)
- `outbound_sent`

**3. Olhar conversation_state pra ver contexto:**
```sql
SELECT jsonb_pretty(interactions), flow_state
FROM aia_health_conversation_state
WHERE client_id = '<phone>' AND tenant_id = '<tenant>';
```

**4. Olhar sofia_messages pra ver detalhe da decisão LLM:**
```sql
SELECT role, content, tool_name, tool_input, tool_output, model, tokens_in, tokens_out
FROM aia_health_sofia_messages
WHERE trace_id = '<uuid>'
ORDER BY created_at;
```

**5. Replay da conversa:**
- Painel `/admin/system/conversations` → filtra por phone + período
- Vê timeline completa renderizada

### Se a decisão foi errada

1. Vai pra `/admin/governance/corpus-review`
2. Acha o caso (pode buscar por care_event_id ou trace_id)
3. Marca discordância + motivo
4. Salvo → entra no dataset de melhoria

---

## 24. Atender handoff P1

### Como operador da Central ATENT

1. **Receber push WhatsApp** — chega notificação no seu phone
2. **Abrir Central** — `https://care.connectaia.com.br/admin/system/operations/central`
3. **Login** (se não estiver) — JWT vai pra cookie
4. **Heartbeat ativo** — sistema marca você como "online" a cada 5min
5. **Ver fila** — P1 abertos no topo, com badge de tempo de espera
6. **Reivindicar** (claim) — click no botão; fica vinculado a você
7. **Abrir chat embutido** — vê histórico recente do cuidador + dados do paciente
8. **Atender:**
   - Mandar mensagem de texto
   - Ou ligar pro cuidador (botão "Ligar agora")
   - Ou escalar pra L2 (médico)
9. **Resolver:**
   - Outcome category (encaminhado_hospital / SAMU / falso_alarme / paciente_estavel / etc.)
   - Resolution summary (obrigatório, vai pro prontuário)
10. **Marcar resolved** → SLA tracked

### SLA esperado

- P1: 5min até claim
- P1: 30min até resolved (idealmente)
- P2: 30min claim, 2h resolved
- P3: 2h claim, 24h resolved

---

## 25. Exportar/deletar dados (LGPD)

### Direito de exportação (Art. 18 LGPD)

```bash
curl -X POST https://care.connectaia.com.br/api/me/data-export \
  -H "Authorization: Bearer $USER_TOKEN"
```

Retorna ZIP com:
- Dados pessoais
- Histórico de mensagens
- Care events
- Sinais vitais
- Voiceprints (se aplicável)
- Audit log filtrado pelo user

Async: link de download via email em até 30 dias (LGPD permite até 15d, vamos com 30 pra segurança).

### Direito de deleção (Art. 18)

```bash
curl -X POST https://care.connectaia.com.br/api/me/data-deletion \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"confirm": "DELETAR PERMANENTEMENTE"}'
```

**O que é deletado:**
- Dados pessoais (anonimizados, não removidos — pra manter integridade referencial)
- Voiceprints (DELETE permanente)
- Mensagens (DELETE permanente)
- Consentimentos (mantidos como audit, mas marcados como revoked)

**O que NÃO é deletado:**
- Care events (anonimizados — sem dado pessoal)
- Audit log (immutable por design, LGPD permite pra fins de compliance)
- Dados agregados em métricas (já são anonimizados)

---

## 26. Deploy + rollback

### Fluxo canônico (documentado em `docs/DEPLOY.md`)

```
Local (edit) → git commit + push → GitHub (canônico)
                                       ↓
                            VPS: git pull + rebuild container
```

**Regras absolutas:**
- ❌ NUNCA editar arquivo direto na VPS
- ❌ NUNCA rsync/scp Local → VPS
- ❌ NUNCA `sed -i` na VPS
- ✅ Sempre via git

### Comandos

```bash
# Local
git add <files>
git commit -m "feat/fix: descrição"
git push origin main  # ou via PR + merge

# VPS (script automatiza)
ssh root@72.60.242.245
cd /root/connectaiacare
bash scripts/deploy.sh           # all (api + workers + frontend)
bash scripts/deploy.sh api       # só api + workers
bash scripts/deploy.sh frontend  # só frontend
bash scripts/deploy.sh sofia     # só sofia-service
```

### Script faz automaticamente:
1. `git pull origin main`
2. Detecta mudanças no diff
3. Roda migrations novas (`backend/migrations/*.sql` ordenados)
4. Rebuild containers afetados
5. Health check final (`curl /health`)

### Pegadinha workers

Workers (`sofia-inbound-worker`, `delivery-worker`) compartilham build context com API. Sempre que `REBUILD_API=true`, `REBUILD_WORKERS=true` também — automatizado no `deploy.sh` desde 2026-05-02.

### Rollback

```bash
cd /root/connectaiacare
git log --oneline -5         # pega hash anterior
git reset --hard <hash>      # volta
docker compose up -d --build # rebuild
```

---

# PARTE V — Casos Clínicos Detalhados

## 27. Cenários clínicos detalhados

### Cenário 1 — Cuidador relata medicação dada
**Input:** "Acabei de dar o losartana da D. Maria."
**Sofia detecta:** medicamento (losartana), paciente (Maria), ação (administrado).
**Tools chamadas:** `register_caregiver_report` (event_type=medication_administered), `medication_event_record`.
**Classification:** rotina.
**Output:** "Recebi, registrei. Mais alguma coisa sobre ela hoje?"
**Lifecycle:** care_event status=resolved instantaneamente.

### Cenário 2 — Sinal vital fora do alvo
**Input:** "PA da D. Maria tá 165x95."
**Sofia detecta:** vital sign (PA sistólica/diastólica), paciente, valor numérico.
**Cross-check:** alvo individualizado do paciente é 130x80 (vem da tabela `aia_health_patient_vital_thresholds` se integrado com Tecnosenior, senão fallback SBC-DBHA).
**Classification:** atenção (PA > alvo + 15%).
**Tools:** `vital_sign_record`, `register_caregiver_report` (event_type=vital_sign_alert).
**Output:** "Anotei. PA acima do alvo individualizado. Vou marcar pra acompanhar nas próximas medições."
**Se 3 medições seguidas acima:** escalate clinical P2.

### Cenário 3 — Sintoma agudo (dor no peito)
**Input:** "Seu Antônio tá com dor no peito agora."
**Pre-check:** regex bate `\bdor\s+no\s+peito\b` → BYPASS LLM.
**Tools:** `escalate_to_human_clinical(P1)`.
**Latência:** <3s.
**Output:** "🚨 Recebi. Vou acionar a equipe clínica AGORA. Se for grave, ligue 192 também."
**Audit:** clinical_handoff_initiated, p1_admin_escalation_push (multiple).
**Plantão:** todos plantonistas P1 do tenant recebem push WhatsApp.

### Cenário 4 — Cross-validation: FA sem anticoagulante
**Setup:** D. Maria tem FA no cadastro. Cuidador lista medicamentos atuais, anticoagulante AUSENTE.
**Sofia detecta:** comparação condições × classes esperadas.
**Tools:** `safety_review_prescriptions` retorna alerta crítico.
**Output:** "Atenção: D. Maria tem FA registrada mas não vejo anticoagulante na lista. Risco de AVC isquêmico aumentado. Vou abrir alerta clínico crítico pra revisão médica."
**Lifecycle:** clinical_alert (severity=critical) + care_event escalated P1.

### Cenário 5 — Cuidador pede orientação
**Input:** "Sofia, a D. Maria não quer tomar o remédio hoje. O que faço?"
**Classification:** rotina (não-emergência).
**Tools:** `query_patient_context` (busca histórico de adesão + condições).
**Sofia LLM compõe resposta:**
"Entendo, é comum. Algumas estratégias que funcionam: (1) confirmar com ela se sentiu efeito colateral recente, (2) oferecer o remédio com água gelada ou em meia hora, (3) explicar com paciência por que é importante. Se persistir, marca pra avisar a equipe. Quer que eu agende um follow-up de 2h pra ver como ficou?"

### Cenário 6 — Familiar quer saber do parente
**Input** (família): "Como minha mãe passou hoje?"
**Tools:** `query_patient_context` (agregação últimas 24h).
**Output:**
"Dona Maria passou bem hoje. Tomou todos os 4 medicamentos no horário (cuidador confirmou às 7h, 12h, 18h e 22h). PA medida 2x: 138x82 (12h) e 135x80 (20h) — dentro do alvo. Sem queixas relatadas. Próxima medição de PA programada amanhã 8h. Algo específico que você queria saber?"

### Cenário 7 — Idoso solo precisa de lembrete
**Input** (idoso): "Sofia, esqueci se tomei o remédio."
**Tools:** `query_patient_context` (medication_events últimas 12h).
**Sofia compõe:**
"Oi Dona Maria! Pelo que tenho aqui, você confirmou o losartana ontem às 7h, mas hoje ainda não me avisou. Quer que eu te lembre de tomar agora? Lembre que é importante tomar antes das 9h pra manter o ritmo."

### Cenário 8 — Cuidador no telefone do paciente (cenário 3.1 da policy)
**Setup:** phone bate com paciente. Áudio recebido. Voice identify retorna cuidador conhecido (filho).
**Sofia detecta:** mismatch entre phone owner (paciente) e voice (cuidador).
**Output:** "Olá Maria Silva! Notei que você está usando o telefone do(a) Sr(a). Antônio. Tudo bem com ele(a)? Está acontecendo alguma emergência?"

### Cenário 9 — Drug safety: prescrição arriscada
**Input** (médico): "Vou prescrever amitriptilina 75mg pra D. Maria pela depressão."
**Setup:** D. Maria tem 78 anos.
**Safety check:** Beers Criteria — amitriptilina é anticolinérgico de alto risco em idosos.
**Tools:** `safety_review_prescriptions` retorna severity=warning_strong + categoria=beers_anticholinergic.
**Output:** "⚠️ Atenção, Dr. — amitriptilina é fortemente desaconselhada em idosos pelos Critérios de Beers AGS 2023 (alto risco anticolinérgico, piora cognição, risco de queda). Considerar alternativas como sertralina ou escitalopram. Quer ver o detalhe da evidência?"
**Não bloqueia automaticamente** — médico tem autonomia. Mas cria alerta no histórico + entra na fila de revisão clínica.

### Cenário 10 — Detecção de cascata de prescrição
**Setup:** D. Maria toma furosemida (diurético) + suplemento de potássio + IECA.
**Sofia detecta:** padrão clássico de cascata — furosemida causa hipocalemia, foi prescrito potássio, IECA pode elevar potássio causando hipercalemia.
**Tools:** `safety_review_prescriptions` retorna cascade_detected.
**Output:** "Identifiquei possível cascata de prescrição: furosemida + suplemento potássio + IECA. Risco de oscilação de potássio. Vale revisão médica pra ajustar."
**Lifecycle:** clinical_alert (severity=moderate) + sugere agendar reavaliação.

---

# PARTE VI — Compliance e Segurança

## 28. LGPD por artigo

| Artigo | O que diz | Como atendemos |
|---|---|---|
| **Art. 7** | Bases legais pra tratamento | Consentimento (B2C), execução de contrato (B2B), tutela da saúde (§Art.11) |
| **Art. 8** | Consentimento (forma) | Captura explícita, livre, informada, específica. Texto preservado + versão + IP + timestamp |
| **Art. 9** | Acesso facilitado a info | Portal `/perfil` mostra termos aceitos, finalidade, duração |
| **Art. 11** | Dado biométrico/saúde | Voiceprint só com consentimento explícito; care events com base em tutela da saúde |
| **Art. 13** | Anonimização vs pseudonimização | Audit logs com PII redacted (phone `55519****4144`) |
| **Art. 14** | Direito de acesso (export) | Endpoint `/api/me/data-export` — ZIP com todos dados |
| **Art. 15** | Direito de retificação | UI permite editar dados pessoais |
| **Art. 16** | Direito de eliminação | Endpoint `/api/me/data-deletion` — DELETE de PII, audit fica |
| **Art. 17** | Direito de portabilidade | Export em formato JSON estruturado |
| **Art. 18** | Direito de informação | Portal mostra: quem trata, finalidade, duração, terceiros |
| **Art. 41** | DPO | DPO designado: contato em `/legal/dpo` |
| **Art. 46** | Segurança técnica | Encriptação at-rest + in-transit, RBAC granular, audit imutável |
| **Art. 48** | Comunicação de incidente | Plano documentado, prazo ANPD 72h |
| **Art. 50** | Boas práticas + governança | DPIA atualizado, audit anual interno |

### Bases legais por finalidade

| Finalidade | Base legal | Justificativa |
|---|---|---|
| Care events (clínico) | Tutela da saúde (Art. 11 §2 II.a) | Atendimento de profissional de saúde |
| Voiceprint | Consentimento explícito (Art. 11 §1) | Dado biométrico |
| Cobrança SaaS | Execução de contrato (Art. 7 V) | Cliente B2B |
| Marketing | Consentimento (Art. 7 I) | Opt-in explícito |
| Analytics anonimizado | Legítimo interesse (Art. 7 IX) | Melhoria do produto |

---

## 29. Padrões clínicos adotados

### Terminologia
- **CID-10 PT-BR** (DataSUS) — diagnósticos
- **TUSS** — procedimentos
- **CIAP-2** — atenção primária

### Interoperabilidade
- **FHIR R4** (em roadmap) — resources Patient, Observation, MedicationStatement, AllergyIntolerance, CarePlan, Encounter

### Medicamentos
- **ANVISA Bulário Eletrônico** — base de medicamentos registrados Brasil
- **ATC (Anatomical Therapeutic Chemical)** — classificação OMS
- **Beers Criteria AGS 2023** — medicamentos potencialmente inapropriados em idosos
- **SBGG** — diretrizes geriátricas brasileiras

### Decisão clínica (CDS)
- **SBC DBHA 2020** — hipertensão (alvos pressão por faixa etária + condição)
- **SBD 2024** — diabetes (alvos glicêmicos, A1C, antidiabéticos)
- **SBGG** — fragilidade, polifarmácia, prevenção quedas
- **Critérios STOPP/START** — referência de descontinuação/início de medicamentos em idosos
- **Diretriz Brasileira de Insuficiência Cardíaca** — SBC

### Escalas clínicas
- **Katz (ABVD)** — atividades básicas de vida diária (6 itens)
- **Lawton (AIVD)** — atividades instrumentais (8 itens)
- **MEEM/MMSE-Br** — mini exame mental
- **GDS-15** — depressão geriátrica
- **Karnofsky** — status performance
- **Norton + Braden** — risco úlcera de pressão
- **Morse Fall Scale** — risco de queda
- **CAM** — confusion assessment method (delirium)

### Evidência
- **GRADE** — classifica força de recomendação (A/B/C/D) + qualidade evidência (alto/moderado/baixo/muito baixo)
- Cada regra curada tem `clinical_rationale` + nível GRADE

### Compliance
- **LGPD** (Lei 13.709/2018) — adesão completa
- **HIPAA** (mapping) — pra clientes que queiram exportar pra US
- **ISO 27001** — parcial (controles principais implementados)

---

## 30. Supervisão clínica

### Conselho Científico ConnectaIACare (em formação)

**Composição planejada:**

| Membro | Background | Papel |
|---|---|---|
| **Henrique Bordin** | Biomédico + Farmacêutico (formando final 2026) | Diretor Científico-Clínico (operacional diário) |
| **Coordenadora PUC-RS** | Farmácia/Geriatria | Conselheira — revisão das bases curadas |
| **Geriatra UFRGS** (a convidar) | Geriatria/Medicina | Conselheira — decisões médicas estratégicas |

### Termos (decisão Alexandre 2026-05-10)

**Henrique** (Diretor):
- Equity 3% inicial → até 5%
- Prolabore/salário (R$ 4-8k/mês — biomédico jr healthtech)
- Vesting 4 anos + cliff 1 ano
- Full-time pós-formatura

**Conselheiras** (Coord + Geriatra):
- Equity 0,2% cada
- R$ 0 cash (aposta no projeto)
- 5h/semana
- Compromisso 12 meses
- Vesting 2 anos + cliff 6 meses
- Foco em: prestígio acadêmico + co-autoria papers + network

### O que fazem

- **Revisão das bases curadas** (CIDs, medicamentos, regras cross-validation) antes de irem pra produção
- **Análise mensal** de alertas críticos disparados + falsos positivos
- **Aprovação de novas regras** clínicas master
- **Co-autoria científica** — paper sobre o método

### Sem cliente em uso = momento ideal pra validar

Estamos calibrando bases curadas com revisão clínica intensa **antes** do primeiro cliente em escala. Risco baixo, qualidade alta no go-live.

---

## 31. Plano de resposta a incidente

### Tipos de incidente

| Tipo | Severidade | Resposta inicial |
|---|---|---|
| **Vazamento de dado clínico** | Crítico | DPO acionado em 1h, ANPD em 72h |
| **Decisão Sofia clinicamente errada** | Alto | Revisão clínica imediata, paciente avisado se aplicável |
| **Downtime > 30min** | Alto | Status page atualizada, plantão técnico mobilizado |
| **Bug em produção (não clínico)** | Médio | Rollback se necessário, hotfix prioritário |
| **Falha de integração** | Baixo-Médio | Fallback ativado, fix planejado |

### Workflow de incidente clínico

1. **Detecção** — alerta automático, relato cuidador, ou auditoria
2. **Contenção** — pausar feature/regra se necessário (feature flag)
3. **Investigação** — audit log + replay conversa + análise técnica
4. **Comunicação** — paciente/família afetados em 24h se houve impacto real
5. **Correção** — fix + teste sintético + deploy
6. **Pós-mortem** — documentado em `docs/incidents/` (template)
7. **Aprendizado** — adiciona ao corpus de teste sintético

### Notificação ANPD (LGPD Art. 48)

Casos que requerem:
- Vazamento de dado pessoal
- Acesso não autorizado
- Comprometimento de credenciais

Prazo: **72h** após detecção.

Template em `docs/legal/anpd_incident_template.md`.

---

## 32. Safety Guardrail layer

### Filosofia

> Sofia tem **inteligência** clínica, mas **não autoridade** autônoma. Toda ação clinicamente relevante passa por validação ou aprovação humana.

### Camadas

```
1. Pre-check heurístico (regex)
   └─ Sintoma agudo → handoff P1 imediato (BYPASSA LLM)

2. LLM decision com tools validadas
   └─ Sofia só pode chamar tools whitelisted no schema
   └─ Args sanitizados por tool

3. Tool execution com validação
   └─ safety_review_prescriptions checa contra regras curadas
   └─ Se severity=warning_strong/block → fila de revisão humana

4. Fila de Revisão Safety
   └─ Operações destrutivas (alterar medicação, etc.) sempre humano
   └─ Operações conservadoras: countdown auto-exec
   └─ Circuit breaker se taxa de erro sobe

5. Audit log imutável
   └─ Toda decisão (Sofia + humano) registrada
   └─ Triggers Postgres recusam UPDATE/DELETE
```

### Circuit breaker

Se taxa de erros LLM > threshold em janela de 5min → sistema entra em modo conservador:
- Todas decisões clinicamente relevantes passam por humano
- Notificação pro super_admin
- Logs aumentam verbosity

---

# PARTE VII — Operação 24/7

## 33. Modelo de plantão

```
L1 — Triagem técnica
  Alexandre (ou time core)
  • Confirma se P1 é técnico (bug) ou clínico (real)
  • 24/7 enquanto piloto
  • Push WhatsApp imediato
  • Decide encaminhamento

L2 — Resposta clínica
  Henrique (futuro), médico/enfermeiro de plantão
  • Avalia caso, decide urgência real
  • 9h-22h durante piloto
  • Pode ligar pro cuidador
  • Encaminha pra L3 se médico

L3 — Decisão médica
  Geriatra UFRGS (futura), médico responsável tenant
  • Casos que precisam decisão médica formal
  • Horário comercial
  • Email + WhatsApp

L4 — Emergência absoluta
  SAMU 192
  • Risco iminente de vida
  • 24/7
  • Sofia menciona pro próprio cuidador na resposta
```

### Escalonamento

```
P1 → L1 (5min SLA)
  ├─ Se técnico: resolve no painel
  ├─ Se clínico real → L2 (chama médico/enfermeiro)
  └─ Se grave + sem L2 disponível → ligar SAMU pro cuidador

P2 → L2 (30min SLA)
  └─ Drug safety, queixa nova, sinal vital fora alvo

P3 → L2 ou rotina (2h SLA)
  └─ Esclarecimento, agendamento
```

---

## 34. Central ATENT 24/7

### Visão consolidada cross-tenant

Operador (role `operador_central`) atende fila de **TODOS os tenants** que contratam o serviço ConnectaIACare.

### Dashboard

```
┌──────────────────────────────────────────────────────┐
│  Central · ATENT 24/7                                 │
│                                                       │
│  Pendentes: 4    Em atendimento: 1    P1 abertos: 1  │
│  SLA estourado: 0   Resolvidos 24h: 12               │
│  Operadores online: 2                                │
│                                                       │
│  Filtros: Tipo [Todos] [Operador] [Clínico] [Com.]  │
│           Prioridade [Todas] [P1] [P2] [P3]         │
│                                                       │
│  TIPO     P   PHONE          RAZÃO        ESPERA     │
│  ──────  ─  ────────────  ───────────  ─────────    │
│  clinical P1 555199...4144 acute_sympt  3min ⏰      │
│  commerc. P3 555197...4567 demo_request 2h12min     │
│  ...                                                  │
└──────────────────────────────────────────────────────┘
```

### Heartbeat operador

Operador online é definido por heartbeat nos últimos 5min. Tabela `aia_health_operator_states`:
- last_heartbeat_at
- is_online (bool)
- current_handoff_id (se claimed)
- session_start_at

---

## 35. SLA e métricas

### SLA contratado

| Prioridade | Tempo até claim | Tempo até resolved |
|---|---|---|
| P1 | 5min | 30min |
| P2 | 30min | 2h |
| P3 | 2h | 24h |

### KPIs operacionais

- **% SLA respeitado P1** — alvo ≥ 95%
- **Tempo médio claim P1** — alvo < 3min
- **Tempo médio resolved P1** — alvo < 20min
- **P1 stale > 1h** — alvo = 0
- **% falsos P1** (foi bug, não clínico) — alvo < 5%

### KPIs clínicos

- **Eventos críticos detectados precocemente** vs detectados em consulta seguinte
- **Internações evitadas** (correlação com adesão a recomendações)
- **Cobertura biométrica** — alvo 60% em 90 dias
- **Adesão a medicação** — alvo ≥ 85%

### KPIs financeiros

- **Custo Sofia por paciente/mês** (tokens consumidos)
- **Receita SaaS por tenant**
- **CAC** (custo de aquisição)
- **LTV** (lifetime value)

---

# PARTE VIII — Integração e Parcerias

## 36. Modelo SaaS

### Tipos de tenant

**B2B — ILPI / Senior Living:**
- Licença mensal por faixa de pacientes (até 50, 50-200, 200-500, 500+)
- Variável por uso Sofia (tokens consumidos — pass-through + margem)
- Custo de plantão humano (modelo próprio ou via ConnectaIACare)

**B2B — Clínica geriátrica:**
- Similar a ILPI, mas com pricing diferente (menos pacientes simultâneos, mais consultas)

**B2B2C — Parceiro tecnológico (Tecnosenior):**
- White-label parcial — Sofia com persona deles
- Revenue share por paciente atendido
- Integração bidirecional dados

**B2C — Idoso solo:**
- Plano mensal (R$ X/mês — em definição)
- Inclui Sofia 24/7 + portal + 1 familiar conectado
- Upgrades: mais familiares, teleconsulta, dispositivos

---

## 37. Integração com parceiros

### Tecnosenior (parceria validada 29/04)

- Tecnosenior tem **TotalCare** (dispositivos + plataforma própria pra idosos)
- ConnectaIACare integra **lado conversacional** (WhatsApp + IA + plantão)
- Eles têm **médico de plantão próprio** — roteamento direto
- Compartilhamento bidirecional de dados (consentimento)
- Pilotos: Armindo Trevisan + Cleuza Trevisan
- Tabela: `aia_health_patients.tecnosenior_patient_id` (FK soft)

### Endpoint do parceiro (proposta Matheus)

`GET /api/external/patient/<tecnosenior_id>/vital-thresholds`

Retorna limites individualizados de vitais (PA, glicose, etc.) por paciente, com fonte (SBC genérico vs médico-individualizado).

Documentado em `RESPOSTA_MATHEUS_LIMITES_SAUDE.md`.

### Modelo de integração

```
Parceiro → Webhook ConnectaIACare ← Bidirectional
                ↓
        Patient sync (CPF/ID)
                ↓
        Care events compartilhados
                ↓
        Audit dos dois lados
```

---

## 38. APIs externas

### Endpoints públicos (com token tenant)

**Pacientes:**
- `GET /api/external/patients` — lista
- `POST /api/external/patients/import` — importação batch
- `GET /api/external/patients/<id>` — detalhe
- `PATCH /api/external/patients/<id>` — update

**Care events:**
- `GET /api/external/events/active` — eventos abertos
- `GET /api/external/events/<id>` — detalhe
- `POST /api/external/events/<id>/close` — fechar

**Reports:**
- `GET /api/external/reports` — relatos

**Webhooks outbound** (configurável por tenant):
- `care_event.opened` — novo evento clínico
- `care_event.classification_changed` — escalation
- `care_event.resolved` — fechado
- `clinical_alert.triggered` — alerta drug safety

### Autenticação

Bearer token por tenant, geração via painel admin. Scopes por endpoint.

---

# PARTE IX — Troubleshooting

## 39. Troubleshooting

### Sofia não responde

**Diagnóstico:**
```bash
# 1. Webhook chegou?
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"SELECT created_at, action FROM aia_health_audit_log WHERE created_at > NOW() - INTERVAL '10 minutes' ORDER BY created_at DESC LIMIT 10;\""

# 2. Workers vivos?
ssh root@72.60.242.245 "docker ps --filter name=worker --format '{{.Names}}: {{.Status}}'"

# 3. Lag do consumer?
ssh root@72.60.242.245 "docker exec connectaiacare-redis redis-cli XLEN sofia:inbound"
```

**Soluções:**
- Webhook não chegou → verificar config Evolution + dns
- Workers down → `docker compose restart sofia-inbound-worker-1 sofia-inbound-worker-2`
- Lag alto → escalar workers ou investigar slowdown LLM

### Voz não identificada (1:N retorna None)

**Diagnóstico:**
1. Voz cadastrada? `SELECT COUNT(*) FROM aia_health_voice_embeddings WHERE caregiver_id = '<id>';` (esperado ≥ 3)
2. Score atual? Pegar trace_id + ver audit `voice_identification_attempted`
3. Qualidade do áudio? Threshold de SNR pode estar rejeitando.

**Soluções:**
- Sem voiceprint → propor enrollment via UI
- Score baixo (próximo de 0.65) → re-enrollment (talvez voz mudou)
- SNR baixo → ambiente barulhento, pedir áudio em local mais silencioso

### SLA estourado mostra 0 mas tem itens vencidos

**Causa antiga:** painel usava campo materializado `sla_breached_at` que não era atualizado por job.

**Solução (já em prod):** painel agora calcula dinamicamente `created_at + sla_target_seconds < NOW()`. Fix em commit `c0907dc`.

Se ainda mostrar 0 incorretamente: hard refresh ou verificar deploy aplicado.

### Migration falhou

**Diagnóstico:**
```bash
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"SELECT * FROM aia_health_migrations_applied ORDER BY applied_at DESC LIMIT 5;\""
```

Se migration não está listada mas o arquivo existe → não rodou.

**Solução:**
```bash
ssh root@72.60.242.245 "cd /root/connectaiacare && docker compose exec -T postgres psql -U postgres -d connectaiacare < backend/migrations/<file>.sql"
```

Migrations são idempotentes (`CREATE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).

### Deploy travou

**Diagnóstico:**
- Frontend build Next.js demora 5-10min (normal)
- Se > 15min → ver logs:
```bash
ssh root@72.60.242.245 "docker logs connectaiacare-frontend --tail 100"
```

**Causas comuns:**
- npm install lento (rede)
- Out of memory (frontend build precisa 2GB+)
- pnpm/npm lock desatualizado

### Frontend não carrega (404 em rota nova)

**Causa típica:** rota foi criada local mas frontend ainda não foi rebuildado em prod.

**Solução:** `bash scripts/deploy.sh frontend` na VPS.

### Dashboard cross-tenant erro 500

**Causa histórica (fix em prod):** coluna `classification` renomeada pra `current_classification` + `initial_classification`. Fix em commit `acac7db`.

Se acontecer de novo em outra query: verificar log + atualizar SQL pra `COALESCE(current_classification, initial_classification)`.

### Tooltips do sidebar não aparecem

**Causa:** browser com tradução automática ligada (Google Translate). Quebra labels + bloqueia tooltips.

**Solução:** desativar tradução no Chrome — ⋮ → Configurações → Idiomas → desmarcar "Oferecer traduzir páginas".

---

# PARTE X — Apêndices Técnicos

## 40. Modelo de dados

### Tabelas principais

**Multi-tenant:**
- `aia_health_tenants` — tenants (mãe)
- `aia_health_tenant_config` — config por tenant
- `aia_health_tenant_escalation_contacts` — plantonistas P1 (migration 080)

**Identidade:**
- `aia_health_users` — usuários do CRM (com login)
- `aia_health_caregivers` — equipe clínica que atende
- `aia_health_patients` — pacientes monitorados
- `aia_health_profiles` — perfis customizados (RBAC)
- `aia_health_phone_history` — phones secundários conhecidos

**Voz:**
- `aia_health_voice_embeddings` — voiceprints (vector 256-dim)
- `aia_health_voice_consent_log` — consentimento LGPD Art. 11

**Cuidado clínico:**
- `aia_health_care_events` — eventos clínicos abertos
- `aia_health_reports` — relatos áudio + transcrição
- `aia_health_vital_signs` — sinais vitais
- `aia_health_medication_events` — administrações de medicação
- `aia_health_medication_schedules` — escala de medicação
- `aia_health_clinical_alerts` — alertas drug safety
- `aia_health_clinical_rules` — regras curadas (master)
- `aia_health_drug_cascades` — cascatas de prescrição
- `aia_health_disease_medication_expectations` — cross-validation

**Sofia:**
- `aia_health_sofia_sessions` — sessões CSM
- `aia_health_sofia_messages` — mensagens individuais (com embedding pgvector)
- `aia_health_sofia_audit` — decisões audit
- `aia_health_sofia_active_context` — contexto cross-channel

**Bases curadas:**
- `aia_health_cid10_curated` — CIDs curados
- `aia_health_medication_class_dictionary` — medicamentos curados

**Handoff + operações:**
- `aia_health_human_handoff_queue` — fila de handoff
- `aia_health_operator_states` — heartbeat operadores
- `aia_health_safety_queue` — fila Safety Guardrail

**Audit:**
- `aia_health_audit_log` — log imutável (triggers recusam UPDATE/DELETE)

**Conversation (legado + atual):**
- `aia_health_conversation_state` — CSM state
- `aia_health_conversation_messages` — mensagens conversação
- `aia_health_legacy_conversation_sessions` — sessões legado

### FKs críticas

```
aia_health_reports.caregiver_id      → caregivers.id
aia_health_reports.patient_id        → patients.id
aia_health_care_events.patient_id    → patients.id (NOT NULL)
aia_health_care_events.caregiver_id  → caregivers.id
aia_health_voice_embeddings.caregiver_id → caregivers.id ON DELETE CASCADE
aia_health_voice_embeddings.patient_id   → patients.id ON DELETE CASCADE
aia_health_tenant_escalation_contacts.tenant_id → tenants.id ON DELETE CASCADE
```

---

## 41. Actions canônicas do audit log

Lista exaustiva de actions (use estas strings exatas):

**Inbound:**
- `webhook_received`
- `inbound_received`
- `identity_resolved`
- `tenant_resolved`

**Sofia:**
- `sofia_agent_turn`
- `intent_classified`
- `tool_called`
- `tool_failed`
- `guardrail_decision`

**Outbound:**
- `outbound_sent`
- `outbound_failed`

**Sessão:**
- `session_started`
- `session_closed`
- `session_continued_cross_channel`

**Handoff clínico:**
- `clinical_handoff_initiated`
- `handoff_claimed`
- `handoff_resolved`
- `p1_admin_escalation_push`

**Voz:**
- `voice_enrollment_added`
- `voice_enrollment_failed`
- `voice_enrollment_deleted`
- `voice_identification_attempted`
- `voice_identification_succeeded`
- `voice_identification_failed`
- `identity_resolved` (action genérica)

**Paciente:**
- `patient_created`
- `patient_registration_started`
- `patient_registration_step_saved`
- `patient_registration_completed`
- `patient_section_verified`

**Lead/Commercial:**
- `lead_captured`
- `lead_qualified`
- `lead_converted`
- `lead_lost`

**LGPD:**
- `lgpd_consent_accepted`
- `lgpd_data_export_requested`
- `lgpd_data_deletion_requested`
- `pii_redacted`

**Operacional:**
- `rate_limit_exceeded`
- `quota_exhausted`
- `white_label_override_used`
- `webhook_unknown_instance`

**Escalation contacts (novo):**
- `escalation_contact_created`
- `escalation_contact_updated`
- `escalation_contact_deactivated`

---

## 42. State machines

### Care Event state machine

```
        analyzing
            │
            ▼
        ┌───────┐
        │active │ ───────┐
        └───┬───┘        │
            │            │
    ┌───────┼───────┐    │
    ▼       ▼       ▼    ▼
  resolved expired escalated
```

**States:**
- `analyzing` — recém-criado, Sofia analisando
- `active` — em acompanhamento
- `escalated` — virou handoff humano
- `resolved` — fechado com outcome
- `expired` — passou do prazo sem resolução

**Transições:**
- analyzing → active (Sofia confirmou)
- active → resolved (resposta de equipe + outcome)
- active → escalated (Sofia ou humano subiu prioridade)
- active → expired (24h sem ação)

### Handoff state machine

```
   pending
      │
      ▼ (claim)
   claimed
      │
      ├─→ resolved
      └─→ expired (SLA passou + sem claim)
```

### Registration session state machine

```
   started
      │
      ▼ (save step N)
   in_progress (last_completed_step incrementa)
      │
      ├─→ complete (todos passos OK)
      └─→ abandoned (24h sem ação)
```

---

## 43. Endpoints da API

### Autenticação
- `POST /api/auth/login`
- `POST /api/auth/change-password`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `GET /api/auth/me`

### Pacientes
- `GET /api/patients`
- `POST /api/patients` (novo paciente)
- `GET /api/patients/<id>`
- `PATCH /api/patients/<id>`
- `GET /api/patients/<id>/registration`
- `POST /api/patients/<id>/registration/start`
- `POST /api/patients/<id>/registration/save`
- `POST /api/patients/<id>/registration/complete`
- `POST /api/patients/<id>/verify/<section>`

### Lookups (wizard)
- `GET /api/cid10/search?q=press`
- `GET /api/medication-class/lookup?name=losartana`
- `POST /api/registration/validate`

### Voz
- `POST /api/voice/enroll` (caregiver)
- `GET /api/voice/enrollment/<caregiver_id>`
- `DELETE /api/voice/enrollment/<caregiver_id>`
- `POST /api/voice/patient/enroll`
- `GET /api/voice/patient/enrollment/<patient_id>`
- `DELETE /api/voice/patient/enrollment/<patient_id>`
- `GET /api/voice/coverage`

### Care events
- `GET /api/events/active`
- `GET /api/events/<id>`
- `POST /api/events/<id>/close`
- `GET /api/patients/<patient_id>/events?include_closed=true`

### Reports
- `GET /api/reports`
- `GET /api/reports/<id>`
- `GET /api/reports/<id>/audio`

### Dashboards
- `GET /api/dashboard/summary`
- `GET /api/system/dashboard` (super_admin)

### Tenants (super_admin)
- `GET /api/system/tenants`
- `POST /api/system/tenants`
- `GET /api/system/tenants/<id>`
- `PATCH /api/system/tenants/<id>`
- `POST /api/system/tenants/<id>/suspend`
- `GET /api/system/tenants/<id>/health`

### Escalation contacts (admin_tenant + super_admin)
- `GET /api/admin/tenants/<tid>/escalation-contacts`
- `POST /api/admin/tenants/<tid>/escalation-contacts`
- `PATCH /api/admin/tenants/<tid>/escalation-contacts/<id>`
- `DELETE /api/admin/tenants/<tid>/escalation-contacts/<id>`
- `GET /api/admin/tenants/<tid>/escalation-contacts/health` (dashboard)

### Handoff (operador + admin)
- `GET /api/admin/handoff?status=pending&days=7`
- `POST /api/admin/handoff/<id>/claim`
- `POST /api/admin/handoff/<id>/resolve`
- `GET /api/admin/handoff/stats?days=7`

### Operator
- `GET /api/operator/queue/stats`
- `POST /api/operator/heartbeat`
- `POST /api/operator/claim/<handoff_id>`
- `POST /api/operator/resolve/<handoff_id>`

### Safety queue
- `GET /api/safety/queue`
- `POST /api/safety/queue/<id>/decide`
- `GET /api/safety/circuit-status`

### Risk score
- `GET /api/risk-score/list`
- `POST /api/risk-score/recompute-all`
- `POST /api/risk-score/compute/<patient_id>`
- `POST /api/risk-baseline/recompute-all`
- `POST /api/risk-baseline/compute/<patient_id>`
- `GET /api/risk-baseline/get/<patient_id>`

### Webhook (público)
- `POST /webhook/whatsapp` (legado, redireciona pra v2)
- `POST /webhook/whatsapp/v2/<instance_name>`

### LGPD
- `POST /api/me/data-export`
- `POST /api/me/data-deletion`

---

## 44. Variáveis de ambiente

### Backend (`.env`)

```bash
# Database
DATABASE_URL=postgresql://postgres:xxx@postgres:5432/connectaiacare

# Redis
REDIS_URL=redis://redis:6379/0

# LLMs
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...

# Voz
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...

# WhatsApp
EVOLUTION_API_URL=https://evolution.connectaia.com.br
EVOLUTION_API_KEY=...

# VoIP
VOICE_SIP_PROVIDER_URL=sip:...
VOICE_SIP_USERNAME=...
VOICE_SIP_PASSWORD=...

# Auth
JWT_SECRET=...
JWT_EXPIRY_HOURS=24

# CORS
ALLOWED_ORIGINS=https://care.connectaia.com.br

# Auth enforcement
AUTH_ENFORCE=true

# Feature flags
CARE_AGENT_ENABLED=true
SUPER_SOFIA_ENABLED=true
WEBHOOK_LEGACY_REDIRECT_V2=true
ASYNC_WEBHOOK_ENABLED=true

# Schedulers
ENABLE_SCHEDULER=true
ENABLE_SAFETY_QUEUE_EXECUTOR=true
ENABLE_DOSE_REVALIDATION=true
ENABLE_PROACTIVE_SCHEDULER=true
ENABLE_PROACTIVE_CALLER=true

# Plantão (legado — agora vem da tabela tenant_escalation_contacts)
P1_ESCALATION_PHONES=5551XXXXXXXX  # fallback

# Auto-seed
AUTH_SEED_ON_STARTUP=true

# Production
ENV=production
```

### Frontend (`.env.local`)

```bash
NEXT_PUBLIC_API_URL=https://care.connectaia.com.br
INTERNAL_API_URL=http://api:5055
NEXT_PUBLIC_VAPID_PUBLIC_KEY=...  # quando K (PWA push) for implementado
```

---

## 45. Métricas e KPIs

### Operacionais (dia-a-dia)

| KPI | Cálculo | Alvo |
|---|---|---|
| % SLA P1 respeitado | claimed_under_5min / total_p1 | ≥ 95% |
| Tempo médio claim P1 | AVG(claimed_at - created_at) WHERE priority=P1 | < 3min |
| Tempo médio resolved P1 | AVG(resolved_at - created_at) WHERE priority=P1 | < 20min |
| P1 stale > 1h | COUNT(*) WHERE status=pending AND created_at < NOW() - 1h | 0 |
| Falsos P1 | COUNT(*) WHERE outcome_category='falso_alarme' / total_p1 | < 5% |
| Operadores online | COUNT(*) WHERE last_heartbeat_at > NOW() - 5min | ≥ 1 sempre |

### Clínicos (semanais/mensais)

| KPI | Cálculo | Alvo |
|---|---|---|
| Eventos críticos detectados precocemente | care_events com classification=critical disparados por Sofia / total críticos no período | ≥ 70% |
| Cobertura biométrica | pacientes com voiceprint / total ativos | ≥ 60% em 90d |
| Adesão a medicação | medication_events confirmados / scheduled | ≥ 85% |
| Internações evitadas | (correlação com adesão a recomendações Sofia) | em definição |

### Financeiros (mensais)

| KPI | Cálculo |
|---|---|
| Custo Sofia por paciente/mês | total_tokens × $custo / pacientes_ativos |
| Receita SaaS por tenant | licença mensal + variável Sofia + plantão |
| CAC | custo aquisição cliente |
| LTV | valor por cliente ao longo da vida |
| Margem bruta | (receita - custo_infra - custo_LLM) / receita |

### Qualidade (semanais)

| KPI | Cálculo | Alvo |
|---|---|---|
| Taxa de discordância clínica corpus | discordâncias / total revisado | < 20% |
| Falsos positivos drug_safety | alertas marcados como FP / total alertas | < 15% |
| Tempo médio até revisão corpus | AVG(reviewed_at - created_at) | < 7 dias |
| % regras aprovadas pelo Conselho | approved / proposed | 100% (aprovação obrigatória) |

---

# PARTE XI — Referência

## 46. FAQ

**P: Sofia substitui médico?**
R: Não. Sofia é camada de **triagem e enriquecimento**, não decisão clínica autônoma. Toda ação clinicamente relevante (medicação, escalation, agendamento) passa por revisão humana via Safety Guardrail. Sofia recomenda, humano decide.

**P: E se Sofia errar a classificação?**
R: 3 camadas de proteção:
1. Regras curadas (validadas por médicos) sobrepõem julgamento IA
2. Cuidador tem botão "discordo" em toda interação
3. Casos críticos passam por humano antes de qualquer ação
Erros viram dataset de treinamento via painel de Revisão Corpus.

**P: Como funciona em comparação com outras IAs de saúde?**
R: Diferenças centrais:
- **Hippocratic AI / Sensi.ai**: voice-first, foco em chamadas. Nós usamos **WhatsApp** (canal nativo do brasileiro) + voz como segunda camada.
- **CareYaya / outros**: gerenciamento de cuidadores (HR). Nós focamos em **fluxo clínico** (relato → análise → ação).
- **Diferencial nosso**: bases curadas localmente + Conselho Científico ativo + multi-tenant B2B2C nativo + supervisão humana 24/7 estruturada.

**P: Quanto custa pra operar?**
R: Modelo SaaS com 3 fatores:
- Licenciamento mensal por tenant (faixas de pacientes)
- Variável por interação Sofia (tokens consumidos — pass-through + margem)
- Custo de plantão humano (modelo próprio ou via ConnectaIACare)

**P: LGPD em caso de incidente?**
R: DPO designado, plano de resposta documentado em 72h, audit log permite reconstrução completa. Voiceprint é considerado dado biométrico sensível (Art. 11) — consentimento explícito + texto preservado + direito de deleção total.

**P: Quem é dona da informação?**
R: O **tenant** (ILPI, clínica, família). ConnectaIACare é processadora. Contrato SaaS define termos. Dado anonimizado pode ser usado pra melhorar plataforma se cliente autorizar (opt-in).

**P: Funciona offline?**
R: Cuidador manda áudio offline → quando reconecta, WhatsApp entrega → Sofia processa normalmente. Latência maior, mas relato não se perde. Pra emergência sem internet, WhatsApp não funciona, então protocolo aponta pra SAMU 192 direto.

**P: Como provo eficácia clínica?**
R: Métricas que tracking:
- Eventos críticos detectados precocemente (vs detectados em consulta de rotina seguinte)
- Internações evitadas (correlação com adesão a recomendações Sofia)
- Tempo médio entre sintoma reportado e ação clínica
- Carga reduzida sobre equipe (relatos triados antes de chegar ao médico)
- Co-autoria de paper científico em andamento (Conselho Científico)

**P: Plataforma roda 100% no Brasil?**
R: Infra principal: VPS Hostinger Brasil. LLM (Anthropic + Google) hospedados US — dado clínico passa por eles, mas em conformidade com cláusulas de processamento de dados (DPA Anthropic). Plano futuro: opção de modelo on-premise pra clientes que exigirem.

**P: Posso customizar Sofia pra meu tenant?**
R: Sim. Persona (nome, voz, frase de abertura), branding (logo, cores), prompts (cenários customizados), regras clínicas (em cima das master). Limites: não pode contornar Safety Guardrail.

**P: E se o cliente quer integrar com sistema próprio (FHIR)?**
R: Roadmap FHIR R4 endpoints completos. Hoje: REST API + webhooks. Custom integration possível via consultoria.

**P: Quanto tempo dura um piloto?**
R: 4-6 semanas tipicamente. Começa com 10-20 pacientes, expande conforme tuning + calibração das regras clínicas pro contexto.

**P: Quem treina a Sofia pro meu contexto?**
R: A engine vem com regras curadas universais (Beers, SBC, SBD). Customização local (ex: "essa ILPI tem muitos pacientes com Alzheimer, tunar prompts pra isso") é feita em conjunto durante piloto, com supervisão do Conselho Científico.

---

## 47. Glossário

- **ACG (Adjusted Clinical Groups):** Score de risco clínico baseado em múltiplas dimensões (queixas, eventos, adesão).
- **Active context:** Camada de memória Redis que mantém contexto da Sofia entre canais (WhatsApp ↔ portal ↔ voz).
- **ABVD:** Atividades Básicas de Vida Diária (escala Katz: banho, vestir, transferência, continência, alimentação).
- **AIVD:** Atividades Instrumentais (escala Lawton: telefone, compras, finanças, medicação, etc.).
- **AGS:** American Geriatrics Society (publica Critérios de Beers).
- **ANPD:** Autoridade Nacional de Proteção de Dados (Brasil).
- **ANVISA:** Agência Nacional de Vigilância Sanitária.
- **API REST:** Application Programming Interface estilo REST (HTTP + JSON).
- **ATC:** Anatomical Therapeutic Chemical (classificação OMS de medicamentos).
- **Audit log:** Registro imutável de toda decisão do sistema (compliance LGPD).
- **B2B:** Business-to-Business (cliente é empresa: ILPI, clínica).
- **B2B2C:** Business-to-Business-to-Consumer (parceiro entrega ao consumidor final).
- **B2C:** Business-to-Consumer (cliente é pessoa final: idoso solo).
- **Beers Criteria:** Lista AGS de medicamentos potencialmente inapropriados em idosos.
- **BRA:** Bloqueador do Receptor de Angiotensina (classe de anti-hipertensivos: losartana, valsartana).
- **CAM:** Confusion Assessment Method (escala pra delirium).
- **Care event:** Caso clínico aberto a partir de relato/sintoma, com timeline, status e classificação.
- **Caregiver:** Cuidador (técnico de enfermagem, cuidador formal, cuidador familiar).
- **Care level (I/II/III/IV):** Nível de dependência do paciente.
- **Cascata farmacológica:** Sequência onde medicamento A causa efeito X, prescrevem B pra X, B causa Y, etc.
- **CDS (Clinical Decision Support):** Suporte à decisão clínica baseado em evidência.
- **CID-10:** Classificação Internacional de Doenças (10ª revisão).
- **CIAP-2:** Classificação Internacional de Atenção Primária.
- **Circuit breaker:** Mecanismo que pausa funcionalidade automaticamente se taxa de erro sobe.
- **Cliff (vesting):** Período mínimo antes de equity começar a ser vested.
- **CRM (sistema):** Customer Relationship Management — painel admin pra equipe usar.
- **CRM (médico):** Conselho Regional de Medicina (registro profissional).
- **CSM:** Conversation State Manager (módulo que mantém contexto Sofia).
- **DAR:** Direito de Acesso e Retificação (LGPD).
- **DBHA:** Diretriz Brasileira de Hipertensão Arterial.
- **DPIA:** Data Protection Impact Assessment (avaliação de impacto LGPD).
- **DPO:** Data Protection Officer (encarregado de proteção de dados).
- **DSAR:** Data Subject Access Request (pedido do titular acessar dados).
- **EAM:** Evento Adverso Medicamentoso.
- **E.164:** Padrão internacional de phone (DDI + DDD + número, com +).
- **EER:** Equal Error Rate (métrica de calibração biometria).
- **Embedding:** Vetor numérico que representa semanticamente um texto/áudio.
- **Evolution API:** Gateway open-source pra WhatsApp Web.
- **FA:** Fibrilação Atrial.
- **FAR:** False Accept Rate (taxa de aceite falso em biometria).
- **FHIR:** Fast Healthcare Interoperability Resources (padrão HL7).
- **FRR:** False Reject Rate (taxa de rejeição falsa em biometria).
- **GDS-15:** Geriatric Depression Scale (15 itens).
- **GRADE:** Sistema de classificação de força de recomendação clínica.
- **Handoff:** Transferência de caso pra equipe humana, com prioridade e SLA.
- **Haiku 4:** LLM da Anthropic mais rápido/barato (extração).
- **HAS:** Hipertensão Arterial Sistêmica.
- **HCPA:** Hospital de Clínicas de Porto Alegre.
- **HGT:** Hemoglicoteste (glicemia capilar).
- **HMR:** Hidrocloratiazida (diurético).
- **IAM:** Infarto Agudo do Miocárdio.
- **IC:** Insuficiência Cardíaca (ou Iniciação Científica em contexto acadêmico).
- **IECA:** Inibidor da Enzima Conversora de Angiotensina (anti-hipertensivos: captopril, enalapril).
- **IECAs:** plural de IECA.
- **ILPI:** Instituição de Longa Permanência para Idosos.
- **Intercorrência:** Evento clínico agudo não previsto.
- **JWT:** JSON Web Token (autenticação stateless).
- **Katz:** Escala de ABVD.
- **Lawton:** Escala de AIVD.
- **LGPD:** Lei Geral de Proteção de Dados (Lei 13.709/2018).
- **LID:** Linked ID (identificador WhatsApp Business).
- **LLM:** Large Language Model (Claude, GPT, Gemini, etc.).
- **MCP:** Model Context Protocol (padrão Anthropic pra integração de tools externos).
- **MEEM/MMSE:** Mini-Exame do Estado Mental.
- **Migration:** Script SQL versionado que altera schema do banco.
- **MTTR:** Mean Time To Recovery.
- **Multi-tenant:** Arquitetura que isola dados de cada cliente usando `tenant_id`.
- **Norton:** Escala de risco de úlcera de pressão.
- **OAuth:** Padrão de autorização (Google, etc.).
- **P1/P2/P3:** Prioridades de handoff (5min/30min/2h SLA).
- **PA:** Pressão Arterial.
- **PAS:** Pressão Arterial Sistólica.
- **PAD:** Pressão Arterial Diastólica.
- **PHI:** Protected Health Information (HIPAA US, equivalente LGPD: dado sensível de saúde).
- **PII:** Personally Identifiable Information.
- **pgvector:** Extensão Postgres pra vetores (similaridade semântica).
- **Plantão (Escala de Cuidadores ≠ Plantão Técnico):** 2 conceitos. Escala = turnos cuidadores. Plantão Técnico = quem recebe push P1.
- **Provenance:** Rastreabilidade de origem de cada dado (quem declarou, quando, quem validou).
- **PUC:** Pontifícia Universidade Católica.
- **PWA:** Progressive Web App (web que vira app instalável).
- **RAG:** Retrieval-Augmented Generation (LLM consulta base externa).
- **RBAC:** Role-Based Access Control.
- **Resemblyzer:** Lib Python open-source pra extração de voiceprint.
- **SAMU:** Serviço de Atendimento Móvel de Urgência (192).
- **Safety Guardrail:** Camada que valida ações Sofia contra regras + revisão humana.
- **SBC:** Sociedade Brasileira de Cardiologia.
- **SBD:** Sociedade Brasileira de Diabetes.
- **SBGG:** Sociedade Brasileira de Geriatria e Gerontologia.
- **SCA:** Síndrome Coronariana Aguda.
- **Schedule (escalation):** Janela horária + dias da semana em que contato recebe push.
- **SLA:** Service Level Agreement (compromisso de tempo).
- **SNR:** Signal-to-Noise Ratio (qualidade de áudio).
- **SOAP:** Subjective, Objective, Assessment, Plan (formato de nota clínica).
- **Sonnet 4.6:** LLM da Anthropic usado pela Sofia (tool-use).
- **SSL/TLS:** Encriptação em trânsito.
- **STOPP/START:** Critérios europeus pra descontinuar/iniciar medicamentos em idosos.
- **Stream (Redis):** Estrutura de fila persistente do Redis.
- **Subgroup:** Agrupamento visual dentro de grupo do sidebar.
- **Tenant:** Cliente da plataforma (ILPI, clínica, parceiro, B2C central).
- **TEP:** Tromboembolismo Pulmonar.
- **Tool-use:** Padrão LLM onde modelo chama "ferramentas" backend.
- **TUSS:** Terminologia Unificada da Saúde Suplementar.
- **UFRGS:** Universidade Federal do Rio Grande do Sul.
- **VAD:** Voice Activity Detection.
- **Vesting:** Período de aquisição gradual de equity.
- **Voiceprint:** Embedding vetorial extraído da voz pra biometria.
- **Webhook:** Endpoint que recebe POST de evento externo.
- **Wizard:** Fluxo guiado em N passos.

### Care event types (11 categorias)

- `medication_administered` — medicação dada
- `medication_missed` — medicação esquecida
- `vital_sign_recorded` — sinal vital registrado
- `intercorrencia` — queda, perda consciência, anafilaxia
- `sintoma_novo` — queixa nova sem atribuição a fármaco
- `avaliacao_funcional` — ABVD/AIVD: mobilidade, autonomia
- `evolucao_clinica` — update de quadro JÁ CONHECIDO
- `evento_adverso_medicamentoso` (EAM)
- `apoio_emocional` — cuidador (vai pra trilha separada)
- `caregiver_wellness` — bem-estar cuidador (PHI separation)
- `other`

---

## 48. Roadmap detalhado

### ✅ Concluído (até maio/2026)

**Phase A — Foundation:**
- Multi-tenant schema
- Auth + RBAC + JWT
- Webhook v1 sync

**Phase B — Async + Memory:**
- Webhook v2 async (Redis Streams)
- Sofia inbound worker
- CSM (Conversation State Manager)
- 4 camadas de memória

**Phase C v1 — Sofia básica:**
- Tools básicas (register_report, escalate)
- Sub-agents (commercial, support)

**Phase C v2 — Sofia clínica:**
- Care sub-agent
- Pre-check de sintomas agudos
- Drug safety review
- Cross-validation engine

**Phase D — Operations:**
- Comercial funnel completo
- Operator Central ATENT 24/7
- Handoff queue + claim flow
- Plantão Técnico (multi-tenant)

**Sprint E-H (maio/2026):**
- Sidebar reorganizado com sub-grupos
- Tooltips Radix dark theme
- ConfirmDialog + Toast components
- Coluna "Última atividade" plantonistas
- Dashboard saúde do plantão (SLA + ranking + stale)

### 🔄 Em desenvolvimento (Q3 2026)

- **L** — Onboarding voz via WhatsApp (Sofia conduz enrollment proativo)
- **PWA + push web** (canal redundante pra plantão)
- **Re-enrollment automático voiceprint** (90d trigger)
- **Migração restante** de modais nativos pra useConfirm/useToast (10 páginas)
- **Wizard B2C público** em `/registro` (sem login)

### 📅 Planejado (Q4 2026)

- UI de gestão de roles acumulados (chips multi-role)
- Procurador legal formal com validação cartorial
- FHIR R4 endpoints completos
- Multi-event extraction (relato com 2-3 eventos)
- Dashboard executivo cross-tenant
- Risk score com ML opcional (mantém determinístico como default)

### 🎯 Long-term (2027)

- App mobile nativo (iOS + Android)
- Modelo LLM on-premise opcional (pra clientes regulados)
- Marketplace de integrações
- API GraphQL além de REST
- Voice agent multilíngue (espanhol, inglês — pra clientes BR com expats)

---

## 49. Anexos referenciados

Docs separados que aprofundam tópicos específicos:

| Doc | Sobre |
|---|---|
| `WHATSAPP_INBOUND_IDENTITY_POLICY.md` | 5 cenários de identificação inbound |
| `REVISAO_BASES_CURADAS_HENRIQUE.md` | Guia de revisão clínica das 3 bases |
| `WIZARD_CADASTRO_PACIENTE.md` | 5 passos do wizard |
| `PROPOSTA_PARCERIA_COORDENADORA_PUC.md` | Modelo Conselho Científico |
| `PLANO_PLANTAO_E_MENSAGEM_MURILO.md` | Estrutura operacional plantão |
| `CONFIGURAR_PLANTAO_TENANT.md` | SQL/API pra plantonistas |
| `RESPOSTA_MATHEUS_LIMITES_SAUDE.md` | Integração Tecnosenior |
| `ANALISE_SIDEBAR_2026-05-16.md` | Análise funcional 34 itens |
| `ROADMAP_J_K_L.md` | Próximas evoluções J/K/L |
| `DEPLOY.md` | Fluxo de deploy + rollback |
| `BACKEND_ARCHITECTURE.md` | Mapa de serviços e dependências |
| `FAILOVER_E_MONITORAMENTO_INSTANCIAS.md` | Failover WhatsApp |

---

## Versão e contato

**Manual versão 2.0** · 17 de maio de 2026
**Mantenedor:** Alexandre Henrique + time core ConnectaIACare
**Reportar erro/sugestão:** issue no GitHub `iplayconnect/connectaiacare`

---

# Para a apresentação de quarta

Sugestão de **roteiro de 45-60min**:

| Min | Tópico | Seções do manual |
|---|---|---|
| 0-5 | Boas-vindas + sumário executivo | §1 |
| 5-15 | Problema + solução com exemplos | §2, §3, §4 (3 personas) |
| 15-25 | Demo da plataforma ao vivo | UI walkthrough (§5-§8) |
| 25-30 | Sofia funcionando (caso "dor no peito") | §11 (pre-check) + §27 cenário 3 |
| 30-40 | Diferenciais técnicos + compliance | §28 (LGPD), §30 (Conselho), §32 (Safety Guardrail) |
| 40-50 | Modelo SaaS + integração + parcerias | §36, §37 (caso Tecnosenior) |
| 50-55 | Roadmap + métricas alvo | §48 + §45 |
| 55-60 | Perguntas | §46 (FAQ) ready |

### Pontos fortes pra destacar

✅ **Plataforma rodando agora**, não slideware (`care.connectaia.com.br`)
✅ **Time clínico real validando** (Henrique + Coord PUC + Geriatra UFRGS)
✅ **Multi-tenant desde o dia 1** — pronto pra escalar
✅ **LGPD compliance estruturado** (DPIA, audit imutável, DPO)
✅ **Modelo de operação 24/7 documentado** com SLA + plantão multi-camada
✅ **Diferenciais técnicos únicos**: provenance + cross-validation + multi-sinal + safety guardrail

### Perguntas comuns a antecipar (todas no FAQ)

1. "Sofia substitui médico?" → não, é triagem + enriquecimento
2. "Como provam eficácia?" → métricas + paper em andamento
3. "Quem é dona do dado?" → tenant; ConnectaIACare é processadora
4. "Quanto custa?" → SaaS 3 fatores
5. "Como compara com Hippocratic AI / Sensi.ai?" → diferenças claras
6. "E se errar?" → 3 camadas proteção
7. "LGPD se vazar?" → DPO + 72h ANPD + audit completo
8. "Roda no Brasil?" → infra BR; LLM US com DPA
9. "Customizo Sofia?" → sim, dentro dos limites Safety Guardrail
10. "Quanto dura piloto?" → 4-6 semanas
