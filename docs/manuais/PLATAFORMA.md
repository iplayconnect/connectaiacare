# Manual ConnectaIACare

**Versão:** 1.0 · 2026-05-17
**Audiência:** Parceiros comerciais, equipe interna, equipe clínica em onboarding
**Última atualização técnica:** sidebar reorganizado + dashboard saúde do plantão (sprint E-H)

---

## 📑 Sumário

1. [Sumário executivo](#1-sumário-executivo) — 1 página, leia primeiro
2. [O que é a ConnectaIACare](#2-o-que-é-a-connectaiacare)
3. [Personas e fluxos principais](#3-personas-e-fluxos-principais)
4. [Recursos por área funcional](#4-recursos-por-área-funcional)
5. [Como a Sofia funciona](#5-como-a-sofia-funciona)
6. [Diferenciais técnicos](#6-diferenciais-técnicos)
7. [Compliance + Segurança Clínica](#7-compliance--segurança-clínica)
8. [Modelo de operação 24/7](#8-modelo-de-operação-247)
9. [Integração com parceiros (parceiro integrador, ILPIs)](#9-integração-com-parceiros)
10. [Roadmap e estado atual](#10-roadmap-e-estado-atual)
11. [FAQ](#11-faq)
12. [Glossário](#12-glossário)

---

## 1. Sumário executivo

**ConnectaIACare** é uma plataforma SaaS que conecta a **Sofia** (IA conversacional clinicamente supervisionada) com a equipe humana de cuidado, dentro de um modelo de **operação 24/7 multi-camada**.

### O problema que resolve

Cuidado de idosos hoje é fragmentado:
- **Cuidador relata sintoma** por WhatsApp/áudio → ninguém estrutura → equipe perde sinais críticos
- **Família quer saber como o paciente está** → ninguém responde até a próxima visita médica
- **Médico precisa de contexto** → não tem prontuário longitudinal, depende de memória do cuidador
- **ILPI quer escalar** → não tem como atender 100 famílias com 5 funcionários

A consequência: **eventos clínicos perdidos**, retrabalho, judicialização, custo alto, satisfação baixa.

### Como resolvemos

3 camadas que trabalham juntas:

1. **Sofia (IA)** recebe relatos por WhatsApp/voz, classifica clinicamente (rotina/atenção/urgente/crítico), responde com tom apropriado e abre **care events** estruturados no prontuário.

2. **Safety Guardrail** valida cada ação clínica da IA contra:
   - CIDs curados pelo nosso time
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
| Pre-check de sintomas agudos (P1) | ✅ regex + LLM bypass em 27ms |
| Fila de handoff humano 24/7 | ✅ com SLA + push WhatsApp P1 |
| Bases curadas (CID-10, medicamentos, cross-validation) | ✅ + painel de revisão pra clínicos |
| Pacientes em piloto | parceiro integrador validado · 200+ importados |
| Equipe clínica de validação | Henrique Bordin (Biomédico + Farmácia) · Coord. PUC (Farmácia Geriátrica) · Geriatra UFRGS (em convite) |

### Próximas entregas (Q3 2026)

- Onboarding de voz via WhatsApp (Sofia conduz enrollment)
- PWA + push web (canal redundante pra plantão)
- Re-enrollment automático de voiceprint (90d)
- Wizard B2C público em `/registro` (sem login)

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
| **Parceiro tecnológico** (parceiro integrador, etc.) | Integra dados de prontuário próprio + recebe enriquecimento da Sofia. |

### Arquitetura conceitual

```
   ┌──────────────────────────────────────────┐
   │   Cuidador / Familiar / Paciente B2C     │
   │   "PA tá 140x90, ele dormiu mal"         │
   └──────────────────┬───────────────────────┘
                      │ WhatsApp (texto/áudio)
                      ▼
   ┌──────────────────────────────────────────┐
   │   Evolution API (gateway WhatsApp)       │
   └──────────────────┬───────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────┐
   │   Webhook v2 async (Redis Streams)       │
   │   • Resolve tenant (instância → tenant)  │
   │   • Idempotência por message_id          │
   └──────────────────┬───────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────┐
   │   sofia-inbound-worker                   │
   │   • Identity resolver (phone E.164)      │
   │   • Voice biometrics (1:N opcional)      │
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
   │   • Tools: register_caregiver_report,    │
   │     safety_review, escalate_to_human,    │
   │     drug_safety, ...                     │
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

---

## 3. Personas e fluxos principais

### 👤 Persona 1 — Cuidador profissional (ILPI ou domiciliar)

**Quem é:** técnico de enfermagem ou cuidador formado, atende 5-15 pacientes/dia.
**Canal:** WhatsApp (texto + áudio).
**Identificação:** phone E.164 + (opcional) voiceprint cadastrado.

**Fluxo típico — relato rotineiro:**
```
[Cuidador, 14h] "Acabei de dar o losartana da Dona Maria,
                 PA tava 145x88 antes do remédio."

[Sofia, 14h] "Recebi, registrei pra Dona Maria.
              PA acima do alvo (130x80) — vou marcar
              pra acompanhar nas próximas medições.
              Algo mais sobre ela hoje?"

[Sofia internamente]
  → register_caregiver_report (paciente: Maria, tipo: medication+vital_sign)
  → vital_sign_recorded (SBP=145, DBP=88)
  → classification: attention (PA > alvo individualizado)
  → Se 3 medições seguidas acima → escalate clinical (P2)
```

**Fluxo típico — emergência:**
```
[Cuidador, 03h] "Seu Antônio tá com dor no peito"

[Sofia, 03h+3s] "🚨 Recebi. Vou acionar a equipe clínica AGORA —
                  alguém vai te chamar em instantes. Se for
                  emergência grave, ligue 192 (SAMU) também."

[Sistema internamente]
  → Pre-check regex detecta "dor no peito" → bypass LLM
  → escalate_to_human_clinical(urgency=P1)
  → Push WhatsApp pra todos plantonistas P1 do tenant
  → handoff_id criado, SLA 5min
```

### 👤 Persona 2 — Familiar responsável

**Quem é:** filho(a), cônjuge, neto(a) que cuida da pessoa idosa.
**Canal:** WhatsApp + portal web (pra ver prontuário).
**Identificação:** phone E.164 + relacionamento declarado no cadastro do paciente.

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

**Fluxo diário:**
1. Dashboard cross-tenant ou específico
2. Vê SLA da equipe (% atendidos no prazo)
3. Configura plantonistas, escala, regras clínicas customizadas
4. Acompanha consumo da Sofia (tokens, custo, alertas)
5. Audit log pra compliance (LGPD)

---

## 4. Recursos por área funcional

Estrutura do painel — 4 grupos no menu lateral:

### 🟦 Geral (operação diária)
| Recurso | O que faz |
|---|---|
| **Dashboard** | Visão ao vivo: eventos ativos, KPIs, feed de relatos |
| **Alertas Operacionais** | Care events abertos esperando triagem |
| **Alertas Clínicos** | Motor de validação farmacológica (doses, interações) |
| **Relatos** | Histórico transcrito de áudios dos cuidadores |
| **Pacientes** | Lista + prontuário 360° + cadastro wizard de 5 passos |
| **Teleconsulta** | Salas Jitsi pra consulta com SOAP eletrônico |
| **Sofia Chat** | Chat persona-aware (tira dúvidas, simula conversas) |
| **Chamadas · VoIP** | Hub de ligações (nova/ativa/histórico transcrito) |
| **Equipe Clínica** | Médicos, enfermeiros, cuidadores, técnicos (tabs por papel) |

### 🟧 Administração do Tenant (configuração + segurança)
| Recurso | O que faz |
|---|---|
| **Usuários do CRM** | Quem tem conta no painel (≠ Equipe Clínica) |
| **Papéis & Permissões** | Crie papéis customizados além dos defaults |
| **Biometria de Voz** | Enrollment de voiceprints + cobertura por unidade |
| **Escala de Cuidadores** | Turnos dos cuidadores (quem está agora, futura) |
| **Fila de Revisão · Safety** | Ações clínicas críticas esperando aprovação humana |
| **Padrões & Compliance** | Catálogo read-only dos padrões adotados (FHIR, CID-10, escalas) |

### 🟪 Governança Clínica (revisão, regras, prompts)

**Sub-grupo Regras:**
- Regras Clínicas (master) — CRUD de doses, aliases, interações
- Cascatas Farmacológicas — visualização das cascatas A+C, A+B+C

**Sub-grupo Revisão:**
- Revisão · Clínica — sample-based pelo time interno
- Revisão · Corpus — case-a-case do corpus de classificação (com LLM)
- Revisão · Bases Curadas — CID-10, medicamentos, cross-validation (Henrique + PUC)

**Sub-grupo Sofia:**
- Cenários da Sofia — playbooks VoIP (prompts, voz, tools)
- Versões de Prompts — diff + rollback
- Testes Sintéticos — bateria pra validar regressões

### 🟩 Sistema · Cross-tenant (super_admin)

**Sub-grupo Plataforma:**
- Dashboard cross-tenant — agregado de todos os tenants
- Tenants — provisioning SaaS
- Saúde da Plataforma — uptime, latência, integrações

**Sub-grupo Indicadores Clínicos:**
- Risk Score · Pacientes — score 0-100 por paciente (queixas 7d + adesão + eventos urgent)

**Sub-grupo Atendimento Humano:**
- Handoff · Fila — pedidos que Sofia escalou
- Central · ATENT 24/7 — operação cross-tenant priorizada (P1/P2/P3)
- Plantão Técnico · Contatos P1 — quem recebe push WhatsApp em P1

**Sub-grupo Operações:**
- Sofia Proativa — outbound de check-in
- Comercial · Funil — vendas ConnectaIACare
- Leads · Lista (legado) — DEPRECATED

**Sub-grupo Análise:**
- Conversas · Replay — replay Sofia pra auditoria LGPD

---

## 5. Como a Sofia funciona

### Anatomia de um turno

Cada vez que um usuário manda mensagem, Sofia executa em sequência:

```
1. Resolve identidade (Identity Resolver)
   ├─ Phone E.164 → users / caregivers / patients / responsible
   ├─ Multi-tenant aware (mesmo phone em 2 ILPIs → escolhe ativo)
   └─ Voice biometrics opcional (1:N pra confirmar quem fala)

2. Carrega contexto (CSM — Conversation State Manager)
   ├─ Sessão ativa (Redis, TTL 45min)
   ├─ Lead data acumulado
   ├─ Pending question (se Sofia perguntou e está esperando resposta)
   └─ Active context cross-channel (WhatsApp ↔ portal ↔ chat ↔ voz)

3. Pre-check heurístico (latência baixa em emergência)
   ├─ Sintoma agudo? (regex: dor no peito, falta de ar, queda, etc.)
   │  → SIM: escalate_to_human_clinical(P1) em <3s, BYPASSA LLM
   └─ Continua se NÃO

4. Decisão LLM (Sonnet 4.6 + tool-use)
   ├─ Classifica intent
   ├─ Escolhe tool ou texto livre
   └─ Tools disponíveis (12+): register_caregiver_report,
      safety_review, escalate_to_human_clinical,
      vital_sign_record, schedule_followup, …

5. Executa tool (se houver) com sanitização de args

6. Persiste no DB + audit_log

7. Envia resposta via Evolution API
```

### Tipos de classificação clínica

A Sofia classifica relatos em 4 níveis (cor + ação):

| Nível | Cor | Exemplo | Ação |
|---|---|---|---|
| **Rotina** | Verde | "Tomou losartana 8h" | Registra, sem alerta |
| **Atenção** | Amarelo | "PA 145x90, alvo é 130x80" | Cria care_event, segue acompanhamento |
| **Urgente** | Laranja | "Vomitou 2x noite, fica fraca" | Notifica enfermeiro tenant em 30min |
| **Crítico (P1)** | Vermelho | "Dor no peito agora" | Push WhatsApp todos plantonistas em 5min + SAMU mencionado |

### Memória da Sofia (4 camadas)

```
1. In-session (turno atual)
   └─ Lead data + pending question + última extração

2. Active context cross-channel (45min)
   └─ Cuidador começa WhatsApp, troca pra portal,
      Sofia mantém contexto

3. Per-user persistent
   └─ Preferências (forma de tratamento, idioma),
      voiceprint, histórico de care events

4. Semantic recall (pgvector)
   └─ Episódios similares anteriores do mesmo paciente
      ("queda mês passado tinha esse mesmo padrão")
```

---

## 6. Diferenciais técnicos

### 1. Multi-tenant nativo desde o dia 1

Tabela `aia_health_tenants` é a mãe — todos os outros dados (pacientes, cuidadores, relatos, eventos) têm `tenant_id` obrigatório. Isolamento por default (LGPD). Cada tenant tem:
- Persona própria da IA (nome, voz, frase de abertura)
- Whatsapp_evolution_instance dedicado
- Branding (logo, cores primária/accent)
- Integrações configuráveis (parceiro integrador, FHIR endpoint, etc.)

### 2. Provenance por dado clínico

Cada item de condição/medicamento/alergia carrega:
```json
{
  "name": "Hipertensão arterial",
  "cid10_code": "I10",
  "source": "family_declared",
  "declared_at": "2026-05-11T14:32:00Z",
  "declared_by_user_id": "uuid",
  "verified_by_clinician_at": null,
  "verified_by_user_id": null
}
```

Quando o(a) enfermeiro(a)/médico(a) **valida**, os campos `verified_by_*` são preenchidos. UI mostra selo verde "Validado por clínico" — diferencia palpite familiar de confirmação profissional num relance.

### 3. Cross-validation farmacológica curada

Engine própria que checa: **se paciente tem condição X, esperamos classe medicamentosa Y nas medicações declaradas.**

Exemplos baseline curados:
- **Fibrilação atrial** sem anticoagulante → **crítico** (risco anual AVC 5-7%)
- **Diabetes Mellitus** sem antidiabético oral/insulina → **importante**
- **Insuficiência cardíaca** sem IECA/BRA → **importante**
- **Hipotireoidismo** sem reposição → **sugestão**

Regras são **curadas e aprovadas por equipe clínica** (Henrique + Coord PUC) antes de irem pra produção. Painel dedicado `/admin/governance/curated-review`.

### 4. Identificação multi-sinal

Phone é fonte de verdade primária. Voice biometrics é camada adicional:

| Cenário | Comportamento |
|---|---|
| Phone desconhecido | Encaminha pro fluxo comercial/suporte (NÃO tenta voz) |
| Phone cadastrado + voz bate | Identidade direta, fluxo normal |
| Cuidador no celular do paciente (voz bate com pessoa do círculo) | Sofia confirma emergência: "Notei que você está usando o telefone de [paciente]. Está acontecendo algo?" |
| Tenant ambíguo (phone em 2 ILPIs) | Sofia pergunta em qual atua agora |
| Familiar novo no celular dele próprio | Sofia propõe enrollment via WhatsApp |

Documentado em `WHATSAPP_INBOUND_IDENTITY_POLICY.md`.

### 5. Safety Guardrail layer

Sofia tem **inteligência mas não autoridade** clínica autônoma. Toda ação considerada arriscada (medicação fora de protocolo, contraindicação detectada, etc.) entra em **fila de revisão humana** com:
- Countdown de auto-execução (ações conservadoras executam após N min sem revisão)
- Bloqueio total pra ações destrutivas (sempre requer humano)
- Circuit breaker se taxa de erro sobe

### 6. Audit log imutável (LGPD Art. 11)

Tabela `aia_health_audit_log` é append-only (triggers Postgres recusam UPDATE/DELETE). Cada decisão clínica registra:
- Trace ID (correlação E2E)
- Tenant + usuário + role
- Action canônica (lista de 20+ ações padronizadas)
- Payload (PII redactada)
- IP + user agent

Permite reconstruir QUALQUER decisão pra auditoria regulatória ou judicial.

---

## 7. Compliance + Segurança Clínica

### LGPD (Lei Geral de Proteção de Dados)

| Requisito | Como atendemos |
|---|---|
| **Art. 7 — Bases legais** | Consentimento (B2C), execução de contrato (B2B), tutela da saúde (Art. 11 §2) |
| **Art. 11 — Dado sensível biométrico** | Voiceprint só com consentimento explícito + texto exato preservado + versão do termo |
| **Art. 18 — Direitos do titular** | Endpoints `/api/me/data-export` (LGPD 14) e `/api/me/data-deletion` (LGPD 15) |
| **Art. 46 — Segurança** | Encriptação at-rest + in-transit, audit log imutável, RBAC granular |
| **Anexo (Tratamento por agente IA)** | Sofia documentada como "agente de tratamento" no DPIA — todas decisões auditáveis |

### Padrões clínicos adotados

Catálogo completo no painel **"Padrões & Compliance"** (vitrine read-only):

- **Terminologia:** CID-10 (DataSUS PT-BR), TUSS, CIAP-2
- **Interoperabilidade:** FHIR R4 (resources Patient, Observation, MedicationStatement, AllergyIntolerance, CarePlan)
- **Medicamentos:** ANVISA Bulário Eletrônico + classes ATC + critérios de Beers AGS 2023
- **Escalas clínicas:** Katz (ABVD), Lawton (AIVD), MEEM, MMSE-Br, Karnofsky, Norton, Braden
- **Evidência:** GRADE pra classificar força de recomendações nas regras curadas
- **Diretrizes nacionais:** SBC-DBHA 2020 (pressão), SBD 2024 (diabetes), SBGG (geriatria)

### Supervisão clínica humana

Time formal de validação:
- **Henrique Bordin** — Biomédico + Farmacêutico (formando final 2026) — referência operacional clínica
- **Coordenadora PUC-RS** (Farmácia/Geriatria) — Conselho Científico (em formação)
- **Geriatra UFRGS** (a convidar) — Conselho Científico (segunda fase)

Estrutura formal em `PROPOSTA_PARCERIA_COORDENADORA_PUC.md`. Tudo que vai pra produção em **bases curadas** (CIDs, medicamentos, regras) passa por aprovação deles.

---

## 8. Modelo de operação 24/7

### Camadas de plantão

```
L1 — Triagem técnica (Alexandre / time core)
  └─ Confirma se P1 é técnico (bug) ou clínico (real)
  └─ 24/7 enquanto piloto
  └─ Push WhatsApp imediato
  └─ Decide encaminhamento

L2 — Resposta clínica (Henrique / enfermeiro)
  └─ Avalia caso, decide urgência real
  └─ 9h-22h durante piloto
  └─ Pode ligar pro cuidador

L3 — Decisão médica (Geriatra UFRGS futura)
  └─ Casos que precisam decisão médica formal
  └─ Horário comercial
  └─ Email + WhatsApp

L4 — Emergência absoluta (SAMU 192)
  └─ Risco iminente de vida
  └─ 24/7
  └─ Mensagem padrão pro próprio cuidador
```

### Fila Central · ATENT 24/7

Painel dedicado mostra:
- **Pendentes** por prioridade (P1/P2/P3)
- **SLA estourado** (calculado dinamicamente: `created_at + sla_seconds < NOW()`)
- **Operadores online** (heartbeat 5min)
- **Filtros por tipo** (clinical / commercial / suporte)

Operadores reivindicam (claim) → atendem no chat embutido → marcam resolved com nota de resolução.

### Plantão Técnico · Contatos P1

Sistema parametrizado por **tenant** (multi-tenant ready):
- Cada tenant cadastra seus plantonistas no painel
- Por contato: phone WhatsApp, role, prioridades (P1/P2/P3), schedule opcional (turnos)
- Push automático quando P1 entra no tenant
- Dashboard de saúde do plantão:
  - **SLA 7d** (% reivindicados em <5min)
  - **Volume diário** (mini-gráfico)
  - **Ranking de carga** por contato
  - **Stale alerta** (contatos sem push há >30d — sinal de número morto)

---

## 9. Integração com parceiros

### Como uma ILPI/parceiro entra na plataforma

1. **Onboarding técnico** (1-2 dias):
   - Criar tenant no painel super_admin
   - Provisionar instância Evolution dedicada (chip WhatsApp próprio)
   - Configurar branding (logo, cores, persona Sofia)
   - Importar pacientes (CSV ou API REST)

2. **Onboarding clínico** (1 semana):
   - Cadastrar equipe (médicos, enfermeiros, cuidadores)
   - Cadastrar plantonistas P1
   - Definir escala de cuidadores
   - Treinar 2-3 pessoas-chave na UI

3. **Piloto** (4-6 semanas):
   - Começa com 10-20 pacientes
   - Acompanhamento próximo + tuning
   - Calibração de regras clínicas pro contexto
   - Validação de SLA real

4. **Operação plena**:
   - Roll-out pra 100% dos pacientes
   - SLA de 95% P1 atendidos em <5min
   - Reuniões mensais de retrospectiva

### Integração técnica disponível

| Tipo | Endpoint | Quando usar |
|---|---|---|
| **REST API** | `/api/external/*` (com token tenant) | Importação batch de pacientes, sincronização de prontuário |
| **Webhook outbound** | Receber notificação de care_events | Quando parceiro tem sistema próprio que precisa saber |
| **FHIR R4** | `/api/fhir/*` (em roadmap) | Sistemas hospitalares que falam FHIR |
| **Limites custom de vitais** | `GET /patient/<id>/vital-thresholds` (parceiro integrador) | Parceiro define limites individualizados, Sofia consome |

### Caso real: parceria com parceiro integrador

- parceiro integrador tem produto **TotalCare** (cuidado de idosos em casa via dispositivos)
- ConnectaIACare integra **lado conversacional** (WhatsApp + IA + plantão)
- Eles têm **médico de plantão próprio** — nossa plataforma roteia direto pra fila deles
- Compartilhamento bidirecional de dados de paciente (com consentimento)
- Piloto validado em 29/04 com pacientes Armindo + Cleuza Trevisan

---

## 10. Roadmap e estado atual

### ✅ Em produção (maio/2026)

- Multi-tenant + provisioning SaaS
- Sofia conversacional Phase C v2 (CSM + memory layers)
- Pre-check de sintomas agudos (regex + bypass LLM)
- Tools de Sofia (12+: register_report, safety_review, escalate, etc.)
- Engine de cross-validation farmacológica (8 regras baseline)
- Bases curadas: CID-10 (150), medicamentos (80+), interações
- Painel de revisão pra clínicos
- Wizard de cadastro completo do paciente (5 passos)
- Fila de handoff humano + Central ATENT 24/7
- Plantão Técnico · Contatos P1 (multi-tenant, com schedule)
- Dashboard de saúde do plantão (SLA + ranking + stale alerta)
- Biometria de voz (caregiver + patient) com consentimento LGPD
- Spec WhatsApp Inbound Identity Policy (5 cenários)

### 🔄 Em desenvolvimento (Q3 2026)

- **Onboarding voz via WhatsApp** — Sofia conduz enrollment proativo (L do roadmap)
- **PWA + push web** — canal redundante pra plantão (K)
- **Re-enrollment automático voiceprint** — 90d trigger (J)
- **Migração modais custom** restante (10 páginas)

### 📅 Planejado (Q4 2026)

- Wizard B2C público em `/registro` (sem login)
- UI de gestão de roles acumulados (chips)
- Procurador legal formal com validação cartorial
- FHIR R4 endpoints completos
- Multi-event extraction (relato com 2-3 eventos simultâneos)

### 🎯 Métricas operacionais (alvos)

| Métrica | Alvo |
|---|---|
| Tempo até claim P1 | < 5min (SLA contratado) |
| Tempo até resolved P1 | < 30min |
| % P1 com resposta humana | 100% |
| Falsos P1 (foi bug, não clínico) | < 5% |
| Cobertura biométrica | 60% em 90 dias |
| % regras curadas aprovadas pelo Conselho | 100% |
| Uptime plataforma | 99.5% |

---

## 11. FAQ

**P: Sofia substitui médico?**
R: **Não.** Sofia é uma camada de **triagem e enriquecimento**, não decisão clínica autônoma. Toda ação clinicamente relevante (medicação, escalation, agendamento de procedimento) passa por revisão humana via Safety Guardrail. Sofia recomenda, humano decide.

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

---

## 12. Glossário

- **Care event**: caso clínico aberto a partir de relato/sintoma, com timeline, status (analyzing/active/resolved) e classificação.
- **CSM (Conversation State Manager)**: módulo que mantém contexto da Sofia entre turnos e canais (WhatsApp ↔ portal ↔ voz).
- **Handoff**: transferência de caso pra equipe humana, com prioridade (P1/P2/P3) e SLA.
- **Multi-tenant**: arquitetura que isola dados de cada cliente (ILPI/clínica) usando `tenant_id` em todas tabelas.
- **P1 / P2 / P3**: prioridades de handoff. P1 = crítico/SLA 5min, P2 = atenção/SLA 30min, P3 = rotina/SLA 2h.
- **PII**: Personally Identifiable Information — dado pessoal identificável, redactado em audit logs.
- **Plantão (Escala de Cuidadores ≠ Plantão Técnico)**: 2 conceitos distintos. Escala = turnos dos cuidadores. Plantão Técnico = quem recebe push P1.
- **Provenance**: rastreabilidade de origem de cada dado clínico (quem declarou, quando, quem validou).
- **RBAC**: Role-Based Access Control — permissões baseadas em papel (role).
- **Safety Guardrail**: camada que valida ações da Sofia contra regras clínicas + revisão humana.
- **Sofia**: persona IA conversacional da plataforma. Personalizável por tenant.
- **Subgroup**: agrupamento visual dentro de um grupo do sidebar (ex: "Atendimento Humano" dentro de Sistema).
- **Tenant**: cliente da plataforma — pode ser ILPI, clínica, hospital, parceiro tecnológico ou B2C central.
- **Tool-use**: padrão LLM onde modelo chama "ferramentas" (funções backend) ao invés de responder texto.
- **Voiceprint**: embedding vetorial extraído da voz pra identificação biométrica (Resemblyzer + pgvector).
- **Care event types** (11 categorias):
  - `medication_administered`, `medication_missed`
  - `vital_sign_recorded`
  - `intercorrencia` (queda, perda consciência, anafilaxia)
  - `sintoma_novo` (queixa nova sem atribuição a fármaco)
  - `avaliacao_funcional` (ABVD/AIVD: mobilidade, autonomia)
  - `evolucao_clinica` (update de quadro conhecido)
  - `evento_adverso_medicamentoso` (EAM)
  - `apoio_emocional` (cuidador — tristeza, exaustão)
  - `caregiver_wellness` (bem-estar separado do prontuário paciente)
  - `other`

---

## 📎 Anexos referenciados (docs separados)

| Doc | Sobre o quê |
|---|---|
| `WHATSAPP_INBOUND_IDENTITY_POLICY.md` | 5 cenários de identificação inbound com regras exatas |
| `REVISAO_BASES_CURADAS_HENRIQUE.md` | Guia pra revisão clínica das 3 bases curadas |
| `WIZARD_CADASTRO_PACIENTE.md` | 5 passos do wizard explicados |
| `PROPOSTA_PARCERIA_COORDENADORA_PUC.md` | Modelo de Conselho Científico |
| `PLANO_PLANTAO_E_MENSAGEM_MURILO.md` | Estrutura operacional do plantão |
| `CONFIGURAR_PLANTAO_TENANT.md` | Como cadastrar plantonistas via SQL/API |
| `RESPOSTA_MATHEUS_LIMITES_SAUDE.md` | Integração com limites custom parceiro integrador |
| `ANALISE_SIDEBAR_2026-05-16.md` | Análise funcional dos 34 itens de menu |
| `ROADMAP_J_K_L.md` | Próximas 3 evoluções com spec |

---

## Histórico de versões

| Versão | Data | Mudanças |
|---|---|---|
| 1.0 | 2026-05-17 | Versão inicial. Cobre estado pós-sprint E-H (sidebar reorganizado + escalation health) |

---

**Para a apresentação de quarta:**

O documento inteiro é denso (~30 páginas). Pra o parceiro comercial, sugiro abordar nesta ordem:

1. **Sumário executivo** (página 1) — 5min
2. **Personas e fluxos** (seção 3) — 10min com exemplos do Murilo
3. **Diferenciais técnicos** (seção 6) — 5min destacando provenance + cross-validation + multi-tenant
4. **Compliance** (seção 7) — 5min se for cliente saúde institucional
5. **Casos de uso e integração** (seções 9 + 10) — 10min mostrando piloto parceiro integrador + roadmap

Total: **35-40min de apresentação + tempo de perguntas.**

Pontos fortes pra destacar:
- ✅ Plataforma rodando, não slideware
- ✅ Time clínico real validando (Henrique + Coord PUC)
- ✅ Multi-tenant desde o dia 1
- ✅ LGPD compliance estruturado
- ✅ Modelo de operação 24/7 documentado

Pontos a antecipar (perguntas comuns):
- "Sofia substitui médico?" → seção FAQ
- "Como medem eficácia?" → seção FAQ + Métricas no roadmap
- "Quem é dona do dado?" → seção FAQ
- "Quanto custa?" → seção FAQ (modelo SaaS 3 fatores)
- "E se errar?" → 3 camadas de proteção descritas
