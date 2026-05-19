# Manual da Equipe Clínica — ConnectaIACare

**Pra quem é:** médico(a), enfermeiro(a), farmacêutico(a), biomédico(a) que atua na cadeia de cuidado direto ou de supervisão clínica.

**O que você vai dominar:** plataforma como ferramenta de prática clínica — prontuário longitudinal, triagem inteligente, validação farmacológica, teleconsulta, governança científica.

**Tempo:** 25-30 minutos pra dominar o essencial. Referência permanente depois.

---

## Sumário

1. [Posicionamento da plataforma na sua prática](#1-posicionamento)
2. [Acesso e autenticação](#2-acesso)
3. [Prontuário 360° — leitura clínica](#3-prontuário-360)
4. [Triagem: Alertas Operacionais vs Clínicos](#4-triagem)
5. [Validação farmacológica](#5-validação-farmacológica)
6. [Cross-validation condição × medicação](#6-cross-validation)
7. [Cascatas farmacológicas](#7-cascatas)
8. [Care events e timeline](#8-care-events)
9. [Teleconsulta + SOAP eletrônico](#9-teleconsulta)
10. [Drug Safety Review (fila de revisão)](#10-drug-safety-review)
11. [Revisão Clínica / Corpus / Bases Curadas](#11-revisões)
12. [Sua jornada no Conselho Científico](#12-conselho-científico)
13. [Plantão clínico (L2/L3)](#13-plantão)
14. [Concordar/discordar da Sofia (governança)](#14-governança-sofia)
15. [Compliance + Audit Log próprio](#15-compliance)
16. [Sofia Chat pra apoio diagnóstico](#16-sofia-chat)
17. [Sinais de qualidade da plataforma](#17-sinais-de-qualidade)
18. [FAQ clínica](#18-faq)

---

## 1. Posicionamento

A ConnectaIACare se posiciona como **camada de triagem inteligente e enriquecimento clínico**, **não** como sistema de decisão autônomo.

### Princípios

- **Sofia recomenda, você decide.** Toda ação clínica relevante passa por revisão humana via Safety Guardrail layer.
- **Provenance total** — cada dado clínico carrega quem declarou, quando, e se foi verificado por profissional.
- **Audit imutável** (LGPD Art. 11) — você pode reconstruir qualquer decisão a posteriori.
- **Bases curadas pelo time** — Henrique (biomédico/farmácia) + Conselho Científico (Coord. PUC/Geriatria + Geriatra UFRGS futura).

### Sua autonomia clínica

A plataforma **nunca** sobrescreve sua decisão. Você pode:
- Discordar de qualquer classificação da Sofia
- Prescrever fora de protocolo (com nota clínica)
- Marcar regra como inadequada pro paciente específico
- Pedir revisão de regra que dispara muito falso positivo

Tudo registrado em audit — proteção mútua (sua + paciente + plataforma).

---

## 2. Acesso

### Login

`care.connectaia.com.br/login`

Email + senha. Token JWT em cookie HttpOnly (válido 24h).

### Recuperação de senha

`/forgot-password` — link por email.

### MFA (em roadmap)

Multi-factor authentication via TOTP planejado pra Q3 2026.

### Sua identidade na plataforma

Seu user tem:
- **Role primário** (medico, enfermeiro, etc.)
- **Roles adicionais** (se você acumula — ex: enfermeiro + gestor)
- **Profile customizado** (se sua casa criou) — sobrepõe permissões default
- **CRM** (médicos) ou **COREN** (enfermeiros) — registrado pra auditoria

### Sessão expirada

401 → redirect pra `/login?next=<página>` automático. Você re-logga e volta de onde parou.

---

## 3. Prontuário 360°

`/patients/<id>` — visão completa de um paciente.

### Hero card (topo)

```
┌─────────────────────────────────────────────────┐
│  D. Maria Aparecida Santos, 78 anos             │
│  Casa 1 · Quarto 12 · Care Level III            │
│  ───────────────────────────────────             │
│  Score ACG: 67 (Moderado-Alto)                   │
│                                                  │
│  Condições crônicas:                            │
│  [HAS controlada] [DM2 controlado] [Demência    │
│   leve em controle] [Dislipidemia]              │
│                                                  │
│  🔴 ALERGIAS: Penicilina, AAS                   │
│                                                  │
│  Cuidador primário: Marcos Silva (12 anos)      │
│  Familiar responsável: Ana Santos (filha)       │
└─────────────────────────────────────────────────┘
```

### Vital Signs Grid (últimos 7 dias)

Gráficos mini de:
- PA (sistólica + diastólica + linha do alvo individualizado)
- Glicose
- SpO2
- FC
- Temperatura
- Peso

Cor verde = dentro alvo. Amarelo = atenção. Vermelho = fora alvo.

### Timeline 30 dias

Cronograma vertical com **todos os eventos** ordenados:
- Care events abertos/resolvidos
- Sinais vitais
- Medicações administradas / esquecidas
- Consultas
- Resultados de exames
- Mensagens importantes da família

### Medication Timeline + Adherence

Calendário visual mostrando:
- Doses agendadas (verde se confirmada, vermelho se perdida)
- Adesão % nos últimos 30 dias
- Adesão por medicação (qual tá com problema)

### Sofia Insights

Box que mostra resumos automáticos da Sofia:
- "Adesão de losartana caiu 20% essa semana, investigar"
- "PA média 142x88 acima do alvo, 3 medições seguidas"
- "Sem queixas relatadas, padrão estável"

---

## 4. Triagem

### Alertas Operacionais (`/alertas`)

**Mostra care_events** — eventos clínicos abertos esperando ação.

**Fluxo:**
1. Filtra por classificação (rotina/atenção/urgente/crítico)
2. Abre evento → lê resumo + contexto
3. **Resolve inline** (sem sair da página) com outcome_category + summary
   - Cuidado iniciado
   - Encaminhado hospital
   - Transferido
   - Sem intercorrência
   - Falso alarme
   - Paciente estável
   - Outro

### Alertas Clínicos (`/alertas/clinicos`)

**Mostra clinical_alerts** — validações farmacológicas (dose, interação, contraindicação).

**Tipos:**
- `dose_above_max` — dose acima do máximo recomendado
- `dose_below_min` — dose abaixo do mínimo terapêutico
- `interaction_major` — interação medicamentosa grave
- `interaction_moderate` — interação moderada
- `contraindication_age` — contraindicado por idade (Beers)
- `cascade_detected` — cascata de prescrição detectada
- `cross_validation_missing` — condição declarada sem medicamento esperado

**Ações:**
- **Reconhecer (ack)** — você viu, vai avaliar (alerta fica histórico mas sai da fila ativa)
- **Resolver** — alterou conduta clínica, alerta fechado com nota
- **Marcar falso positivo** — gera input pra ajustar regra

---

## 5. Validação farmacológica

A engine de validação roda **automaticamente** quando:
- Nova medicação é prescrita / cadastrada
- Sinal vital é registrado (validação contextual)
- Cuidador relata efeito colateral

### Tipos de validação

#### Doses
- Confronta com `dose_limit_max` / `dose_limit_min` por medicamento + faixa etária
- Alerta se dose prescrita estiver fora

#### Interações
- Pares A+B no banco de interações curadas
- Severidade: minor / moderate / major
- Mostra mecanismo + recomendação

#### Contraindicações Beers
- Lista AGS 2023 (Beers Criteria) — medicamentos potencialmente inapropriados em idosos (PIM)
- Categorias:
  - Anticolinérgicos (piora cognição)
  - Benzodiazepínicos longa ação (queda)
  - AINEs (úlcera, IR)
  - Etc.

### Regras curadas pelo time

Ver detalhes em `/admin/governance/clinical-rules`. Você pode propor nova regra via:
1. Aba "Doses" / "Aliases" / "Interactions"
2. Click "Nova regra"
3. Preenche + status `draft`
4. Conselho Científico revisa
5. Aprovado → vai pra produção

---

## 6. Cross-validation

### O conceito

Pra cada **condição declarada** do paciente, esperamos uma **classe terapêutica** correspondente. Se ausente → alerta.

### Regras baseline (curadas pelo time)

| Condição | Classe esperada | Severidade se ausente |
|---|---|---|
| Fibrilação Atrial | Anticoagulante (warfarina, DOACs) | 🔴 Crítica (AVC anual 5-7%) |
| Diabetes Mellitus | Antidiabético oral ou insulina | 🟠 Importante |
| Insuficiência Cardíaca | IECA/BRA + betabloqueador | 🟠 Importante |
| Hipotireoidismo | Reposição hormonal (levotiroxina) | 🟡 Sugestão |
| Hipertensão | Anti-hipertensivo (qualquer classe) | 🟡 Atenção (se sem nenhum) |
| DAC | Antiagregante (AAS) + estatina | 🟠 Importante |
| DPOC | Broncodilatador (LABA/LAMA) | 🟡 Atenção |
| Asma | Broncodilatador + corticoide inalatório | 🟡 Atenção |

### Quando aparece o alerta

- No wizard de cadastro (passo 5)
- No Alertas Clínicos
- Quando médico atualiza medicação e remove classe esperada
- Em consulta de rotina (revalidação periódica)

### Como tratar

- **Concordo com Sofia** → ajustar prescrição (incluir classe esperada)
- **Discordo** (paciente não tem clearance pra essa classe, ex. anticoagulante em paciente com risco hemorrágico alto) → registra justificativa, alerta vira "dispensado" mas fica no audit

---

## 7. Cascatas farmacológicas

### O que é

Sequência A → B → C onde:
- Paciente toma medicamento A
- A causa efeito colateral X
- Médico prescreve B pra tratar X (mas X é causado por A, não por doença nova)
- B pode ter próprio efeito Y → cascata continua

### Exemplo clássico

```
1. Paciente toma:
   • Furosemida (diurético) — pra IC

2. Furosemida causa:
   • Hipocalemia (potássio baixo)

3. Médico prescreve:
   • Suplemento de potássio

4. Paciente também toma:
   • Enalapril (IECA) — pra IC

5. IECA + suplemento de potássio →
   RISCO de hipercalemia

→ Cascata detectada: precisa ajustar
```

### Painel `/admin/governance/cascades`

Read-only — mostra cascatas curadas da literatura. Pacientes com padrão suspeito são listados pra revisão.

---

## 8. Care events

### O que é

`care_event` = caso clínico aberto a partir de relato/sintoma. **Unidade de trabalho clínico** da plataforma.

### State machine

```
analyzing → active → resolved
                  ↘ escalated
                  ↘ expired (24h sem ação)
```

### Cada care_event tem

- `id` (UUID + human_id sequencial)
- `tenant_id` + `patient_id` + `caregiver_id`
- `caregiver_phone` (quem relatou)
- `event_type` (medication_administered, vital_sign_recorded, intercorrencia, etc.)
- `initial_classification` (rotina/atenção/urgente/crítico)
- `current_classification` (atualizada se escalou)
- `context` (JSONB com detalhes específicos)
- `summary` (texto gerado pela Sofia)
- `reasoning` (raciocínio clínico Sofia)
- `opened_at`, `pattern_analyzed_at`, `first_escalation_at`, `last_check_in_at`, `resolved_at`, `expires_at`
- `closed_by`, `closed_reason`, `closure_notes`

### Como fechar

Pelo `/alertas` ou pelo prontuário:
1. Click evento
2. Click "Resolver"
3. Escolher `closed_reason`:
   - cuidado_iniciado
   - encaminhado_hospital
   - transferido
   - sem_intercorrencia
   - falso_alarme
   - paciente_estavel
   - expirou_sem_feedback
   - obito
   - outro
4. Escreve `closure_notes` (obrigatório se outro)
5. Salvo → fica no histórico, sai da fila

---

## 9. Teleconsulta + SOAP

### Fluxo

1. **Agendamento** (`/teleconsulta/agendar?patient=<id>`)
   - Escolhe paciente
   - Define horário
   - Configura sala Jitsi
   - Convida cuidador / familiar opcional

2. **Na hora**: dashboard mostra "Em andamento"
   - Click "Entrar na sala"
   - Sala Jitsi embutida no domínio próprio
   - Gravação opcional (com consentimento)

3. **Pós-consulta**: documentação SOAP
   - **S**ubjective: queixa principal + HMA
   - **O**bjective: exame físico, sinais vitais
   - **A**ssessment: diagnóstico/avaliação
   - **P**lan: conduta + prescrição + retorno
   - Assinatura digital (CRM)
   - Salvo no prontuário + audit

### Sofia ajuda

- **Antes**: Sofia prepara resumo do paciente (últimos 30 dias + score ACG + medicações)
- **Durante**: você pode pedir contexto adicional ("Sofia, última vez que essa paciente teve febre?")
- **Depois**: Sofia gera draft do SOAP baseado na transcrição da chamada → você revisa/edita/assina

---

## 10. Drug Safety Review

`/admin/seguranca/fila-revisao` — fila de ações clínicas críticas esperando aprovação humana.

### Tipos de item

| Tipo | O que é | Auto-exec? |
|---|---|---|
| `medication_change` | Sofia sugeriu alterar prescrição | ❌ NUNCA — sempre humano |
| `dose_increase` | Aumento de dose acima do padrão | ❌ NUNCA |
| `escalation_to_specialist` | Encaminhamento pra especialista | ✅ Após 1h sem revisão |
| `clinical_note_added` | Nota clínica de IA esperando revisão | ✅ Após 4h sem revisão |
| `medication_reminder_added` | Lembrete novo de medicação | ✅ Após 30min |

### Fluxo

1. Item entra na fila com countdown visível
2. Você abre, lê justificativa da Sofia + contexto
3. **Decide:**
   - ✅ **Aprovar** — ação executa
   - ❌ **Rejeitar** — ação não executa, fica registrado
   - ⏸ **Pedir mais contexto** — Sofia provê informação adicional
4. Circuit breaker monitora taxa de aprovação — se cair muito, sistema entra em modo conservador

---

## 11. Revisões

### `/admin/governance/review` — Revisão Clínica

Revisão **sample-based** pelo time interno. Cada review:
- Sample de 5-10 relatos do dia anterior
- Classificação Sofia visível
- Box pra você marcar concordo/discordo
- Notas de melhoria

### `/admin/governance/corpus-review` — Revisão Corpus

Revisão **case-a-case** que alimenta dataset de retraining.

**Por que importa:** suas correções viram melhoria do modelo. Errou? Você marca o certo e a Sofia "aprende" pro futuro.

**Workflow:**
1. Caso aparece com classificação atual + sugestão LLM
2. Você concorda (1 click) ou discorda
3. Se discorda, marca:
   - Event type correto
   - Severidade correta
   - Categoria correta
   - **Motivo obrigatório** (texto livre)
4. Salvo → audit + dataset

**Trilha separada `caregiver_wellness`:** relatos de cuidador sobre si mesmo (tristeza, exaustão) NÃO vão pro prontuário do paciente. Vão pra trilha dedicada pra gestor de pessoas acompanhar bem-estar da equipe.

### `/admin/governance/curated-review` — Bases Curadas

Revisão das 3 bases que alimentam a plataforma:

**Tab CID-10** (150 entries hoje):
- Code + descrição PT-BR + leigos + EN + categoria
- 13 categorias (cardiovascular, endócrino, neurológico, etc.)
- Você marca como `draft` / `under_review` / `approved`

**Tab Medicamentos** (80+):
- Princípio ativo + brand names + match patterns
- Therapeutic classes (ATC)
- Indicações principais

**Tab Cross-validation** (8 regras baseline):
- Condition label + CID + match patterns
- Expected therapeutic classes
- Prompt severity + prompt message + clinical rationale

**Importante:** sem **aprovação do Conselho Científico**, regra **não vai pra produção**. Você é a barreira de qualidade.

---

## 12. Conselho Científico

Se você é membro do Conselho Científico ConnectaIACare (Coord. PUC, Geriatra UFRGS, ou outros futuros):

### Suas atribuições

1. **Aprovação final** de bases curadas antes de irem pra produção
2. **Revisão mensal** de alertas críticos disparados + falsos positivos
3. **Definição de novas regras** com base em literatura clínica
4. **Co-autoria** em papers científicos

### Cadência

- **Quinzenal** — reunião de 1h30 com time (sincronização)
- **Mensal** — análise de tendências (async ~3h)
- **Trimestral** — workshop de validação científica (2h)
- **Semestral** — retrospectiva + roadmap papers (2h)
- **Anual** — renovação formal + atualização institucional

### Equity / remuneração

- 0,2% equity por pessoa (vesting 2 anos + cliff 6 meses)
- Sem cash recorrente (aposta no projeto)
- Co-autoria em papers científicos (alvo: 3 papers em 18 meses)
- Bolsa IC orientada por você possível

Detalhes em `PROPOSTA_PARCERIA_COORDENADORA_PUC.md`.

---

## 13. Plantão

### Modelo multi-camada

| Camada | Quem | Quando |
|---|---|---|
| **L1 — Triagem técnica** | Plantonista (Alexandre/time core ou da casa) | Confirma se P1 é técnico (bug) ou clínico (real). 24/7 durante piloto. |
| **L2 — Resposta clínica** | Você (médico/enfermeiro de plantão) | Avalia caso real, decide urgência. 9-22h durante piloto. |
| **L3 — Decisão médica** | Geriatra responsável | Casos que precisam decisão médica formal. Horário comercial. |
| **L4 — Emergência absoluta** | SAMU 192 | Risco iminente de vida. 24/7. |

### Como entrar de plantão

Se você é configurado(a) como plantonista P1 do seu tenant (cadastrado em `/admin/system/operations/escalation-contacts`):

1. **Recebe push WhatsApp** quando P1 entra na fila do tenant
2. Mensagem inclui:
   - Phone do cuidador
   - Razão (sintoma agudo, drug safety, etc.)
   - SLA (5min)
   - Link direto pro painel de handoff

3. **Abre Central** (`/admin/system/operations/central`)
4. **Reivindica** (claim) — fica vinculado a você
5. **Atende** no chat embutido
6. **Resolve** com outcome + nota

### SLA esperado

- P1: claim em 5min, resolved em 30min
- P2: claim em 30min, resolved em 2h
- P3: claim em 2h, resolved em 24h

### Dashboard saúde do plantão

`/admin/system/operations/escalation-contacts` tab **Saúde do Plantão**:
- % SLA respeitado últimos 7d
- Volume diário
- Ranking de carga (você vê quanto recebeu)
- Alertas de contato stale (sem atividade > 30d)

---

## 14. Governança Sofia

### Concordar/discordar

Toda decisão Sofia (classificação, tool chamada, resposta) **pode ser questionada**.

**Onde marcar:**
- `/admin/governance/corpus-review` — revisão case-a-case
- Inline em qualquer care_event (botão "Discordar")
- Audit log permite identificar trace_id e contestar

### Quando suas correções viram regra

- Pattern repetido (5+ discordâncias do mesmo tipo) → flag pro Conselho
- Conselho avalia → atualiza regra master OU adiciona nova
- Regra entra `under_review` → testes sintéticos → `approved` → produção

### Você pode propor regra do zero

`/admin/governance/clinical-rules` → "Nova regra"

Preenche:
- Tipo (dose/alias/interaction/etc.)
- Detalhe clínico
- Justificativa (com referência)
- Severidade sugerida
- Categoria

Vai pra `draft`. Marca `under_review` quando quiser que Conselho avalie.

---

## 15. Compliance

### LGPD por artigo (resumo)

Implementação no [`PLATAFORMA.md §28`](PLATAFORMA.md). Pontos chave pra você:

| Artigo | O que você precisa saber |
|---|---|
| **Art. 11** | Você está tratando dado sensível de saúde — autorização contratual + tutela da saúde |
| **Art. 13** | PII (CPF, phone) é redactada em audit logs públicos |
| **Art. 14** | Paciente pode pedir export — você atende quando recebe demanda |
| **Art. 16** | Paciente pode pedir deleção — você processa via fluxo interno |
| **Art. 41** | DPO da plataforma é designado — você não precisa ser o DPO da casa, mas pode consultá-lo |

### Seu audit log

Tudo que você faz na plataforma fica registrado:
- Quando logou
- Que paciente viu
- Que evento resolveu
- Que prescrição aprovou
- Que regra mudou

**Importante:** isso te **protege** legalmente também. Em caso de questionamento, audit log mostra exatamente o que você decidiu e por quê.

### Acesso ao audit pessoal

`/perfil` → "Meu audit" — você vê apenas as ações suas, sem outras.

---

## 16. Sofia Chat

`/sofia` — chat com a Sofia pra **apoio diagnóstico**, não relato.

### O que você pode pedir

**Apoio diagnóstico:**
> "Sofia, paciente 78 anos, mulher, DM2, refere tontura ao levantar. PA sentada 130x80, em pé 100x65. Hipóteses?"

Sofia responde com base em literatura:
- Hipotensão ortostática (alta probabilidade)
- Distúrbios vestibulares
- Anemia
- Etc. + recomendação de investigação

**Lookup rápido:**
> "Dose máxima de losartana em paciente com TFG 35?"

> "Vacinas indicadas em idoso > 65 anos?"

**Síntese de paciente:**
> "Resume Dona Maria, ID 12345, últimas 4 semanas"

Sofia consulta prontuário e retorna síntese.

**Treinamento:**
> "Simula uma conversa onde sou cuidador e relato dor no peito de paciente"

Sofia faz roleplay pra você treinar resposta.

### NÃO é

- Substituto de avaliação clínica
- Diagnóstico (responsabilidade médica)
- Receita

Use como ferramenta de apoio — decisão clínica é sua.

---

## 17. Sinais de qualidade da plataforma

### O que indica plataforma saudável

✅ SLA P1 ≥ 95% últimos 30 dias
✅ Taxa de falso positivo drug_safety < 15%
✅ Taxa de discordância clínica corpus < 20%
✅ Cobertura biométrica ≥ 60% pacientes
✅ Adesão medicação média ≥ 85%

### O que indica problema

❌ Sofia respondendo lento (> 20s) → infraestrutura
❌ Muitos falsos P1 → regras precisam calibração
❌ Cuidador reclama de Sofia "burra" → bases curadas precisam reforço
❌ Equipe ignora alertas → fadiga de alerta, repriorizar

### Como reportar

`/admin/system/operations/central` ou direto pro super_admin via Sofia Chat ou contato no Manual.

---

## 18. FAQ

### "Posso prescrever fora de protocolo?"
Sim. Autonomia médica preservada. Sofia alerta, você decide com nota clínica justificando.

### "E se eu errar uma prescrição?"
Audit te protege. Plataforma ALERTA antes (drug safety + cross-validation). Se você ignorou alerta + justificou, audit mostra que houve aviso e sua decisão consciente.

### "Sofia pode prescrever sozinha?"
NÃO. Toda prescrição passa por médico. Sofia ajuda a estruturar pedido mas não emite receita.

### "E se cuidador relatar algo grave que vejo só horas depois?"
Sistema escalou pra plantão clínico imediato. Você fica sabendo via audit. Se o plantão respondeu, ação foi tomada. Se ninguém respondeu (gap operacional), audit também registra.

### "Como integrar com sistema próprio (FHIR, HL7)?"
APIs REST hoje + FHIR R4 em roadmap Q4 2026. Conversar com time técnico pra customização.

### "Posso usar telemedicina pela plataforma sem CRM ativo?"
Não. Compliance CFM exige CRM válido. Validação ativa.

### "Preciso de consentimento explícito do paciente pra usar plataforma?"
Pra B2B (paciente da ILPI/clínica), tutela da saúde cobre. Pra B2C (idoso direto), consentimento explícito obrigatório.

### "Como participar do Conselho Científico?"
Conversa direta com ConnectaIACare. Modelo descrito em `PROPOSTA_PARCERIA_COORDENADORA_PUC.md`.

### "Quem treina a Sofia clinicamente?"
Conselho Científico aprova regras. Engineering implementa. Você revisa via Corpus Review. Ciclo contínuo.

### "Tem responsabilidade civil minha pelo que a Sofia faz?"
Se você seguir a sugestão da Sofia sem julgamento próprio: responsabilidade compartilhada (sua decisão final + plataforma). Se você discordar da Sofia e fizer diferente: sua decisão. Audit protege.

### "Como exportar dados de um paciente pra outro sistema?"
`/admin/system/operations/...` → Export → JSON ou FHIR (quando disponível).

### "E em caso de óbito do paciente?"
Você marca evento como `obito`. Plataforma mantém prontuário arquivado (LGPD permite por tempo legal de prontuário médico — 20 anos).

### "Posso recomendar plataforma pra colega?"
Sim, especialmente outras casas/clínicas com perfil similar. Programa de indicação em planejamento.

---

## 🩺 Suas decisões clínicas, melhor estruturadas

A ConnectaIACare existe pra te dar **mais contexto** e **menos sobrecarga operacional**, pra você focar no que importa: **decisão clínica de qualidade**.

Qualquer feedback é bem-vindo — pra Sofia melhorar, pra plataforma melhorar.

Bom trabalho.
