# Sofia — Plataforma Clínica ConnectaIACare

> **Apresentação técnica para revisão farmacológica**
> Material para profissional clínico-farmacológico sênior · ConnectaIACare © 2026
> Conteúdo confidencial · uso restrito

---

> **Para o time de Design:** este documento está estruturado como deck de slides (cada `## SLIDE N` = uma lâmina). Cada slide tem:
> - **Título** (`## SLIDE N — título`)
> - **Conteúdo visível** (bullets curtos pra slide)
> - **Notas do palestrante** (texto longo entre `> `)
>
> Sugestão visual: fundo escuro (consistente com produto), cores de destaque ciano/teal. Tabelas usar tipografia monoespaçada nos princípios ativos. Diagramas das 12 dimensões e da arquitetura podem ser ilustrações limpas estilo "engenharia clínica".
>
> **Convenção de status nos slides:**
> - ✅ produção · 🟡 finalização · 🔵 roadmap próximo · 🟣 visão futura

---

## SLIDE 1 — Capa

**Sofia — Plataforma Clínica**

Apresentação técnica para revisão farmacológica sênior

ConnectaIACare · 2026

> **Speaker notes:**
> Agradecer pelo tempo. Esta apresentação dura ~30-40 minutos e cobre toda a plataforma Sofia — motor clínico, canais de entrada, sistemas de inteligência, segurança, regulatório e roadmap. O objetivo é receber feedback técnico farmacológico e discutir possível colaboração formal.

---

## SLIDE 2 — Quem somos

ConnectaIACare é uma plataforma de **assistência inteligente conversacional** para idosos e pacientes crônicos no Brasil.

- Multi-canal: WhatsApp · chat web · voz no app · ligação telefônica direta · teleconsulta integrada
- Multi-persona: paciente · cuidador · familiar · enfermagem · médico · admin
- Núcleo: **Sofia**, IA conversacional com motor clínico determinístico
- B2C (idoso individual) + B2B (casa geriátrica · clínica · hospital)

> **Speaker notes:**
> Não somos chatbot genérico nem app de wellness. Somos camada de relacionamento clínico contínuo entre o paciente e a equipe responsável. A diferença para outras IAs em saúde é que a Sofia tem inteligência mas não tem autoridade clínica — toda decisão passa por humano. Hoje vou mostrar tudo o que a plataforma faz hoje, separando claramente o que está em produção, o que está em finalização e o que está no roadmap.

---

## SLIDE 3 — O problema clínico

**Polifarmácia geriátrica brasileira:**

- Idoso 65+ usa em média 5-7 medicações simultâneas
- 25-30% das readmissões hospitalares evitáveis tem causa farmacológica
- Cascatas de prescrição (drug A → efeito → drug B inadequada) afetam até 1/3 dos idosos
- Beers 2023, STOPP/START, KDIGO, Child-Pugh — diretrizes pouco aplicadas em escala
- Acompanhamento longitudinal pós-alta: dependente de equipe humana 24/7 → custo proibitivo

**A questão:** como aplicar essas diretrizes em **toda interação clínica**, não apenas em consultas geriátricas especializadas?

> **Speaker notes:**
> Estamos resolvendo o "elephant in the room" da prescrição em geriatria: o conhecimento clínico existe (Beers, STOPP/START, KDIGO), mas na prática só é aplicado quando o paciente vai num geriatra. Pra demais 90% das interações — pronto-socorro, clínico geral, especialistas focais — esse conhecimento fica de fora. Sofia tenta ser um "geriatra de bolso" disponível 24/7 pra qualquer profissional, e um "cuidador atento" pro paciente.

---

## SLIDE 4 — Sofia: arquitetura geral

```
┌─────────────────────────────────────────────────────────┐
│              CANAIS DE ENTRADA (multimodais)              │
│  WhatsApp · Chat · Voz browser · Ligação · Teleconsulta │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│              SOFIA (LLM conversacional)                   │
│  Persona ajustada · Tools · Memória 4 camadas             │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│              MOTOR DETERMINÍSTICO (12+1 dim)              │
│  Validação clínica em código · Sem alucinação            │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│              SAFETY GUARDRAIL LAYER                       │
│  Decide: executa · enfileira · escala · bloqueia         │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Audit chain LGPD · Fila de revisão · Equipe humana      │
└─────────────────────────────────────────────────────────┘
```

> **Speaker notes:**
> Esse é o macro-mapa. Cada camada vai ser explicada nos próximos slides. A IA generativa cuida da conversa. O MOTOR CLÍNICO é código nativo Python — nada de LLM, nada de "alucinação possível". Beers AVOID em demência é uma regra que retorna em 200ms, sempre igual, auditável, versionada.

---

## SLIDE 5 — Canais de entrada (1/2)

| Canal | Status | Capacidades |
|---|---|---|
| **WhatsApp Business** | ✅ produção | Texto · áudio · foto (OCR) · botões interativos · grupo familiar |
| **Chat web/app** | ✅ produção | Texto · upload arquivo · 16 tools clínicas |
| **Voz no browser** | ✅ produção | Speech-to-speech state-of-the-art (PT-BR) · interrupção em tempo real |
| **Ligação telefônica** | ✅ produção | Outbound · cenário por persona · interrupção · transcrição automática |
| **Teleconsulta integrada** | 🟡 finalização | Módulo próprio · vídeo · prescrição digital · finalização estruturada |
| **Inbound calls** | 🔵 roadmap próximo | Sofia atende · roteador por caller_id |
| **WhatsApp Calling** | 🟣 visão futura | Outbound via Meta Business API |

> **Speaker notes:**
> WhatsApp é canal de primeira classe — 90%+ dos brasileiros usam diariamente. Pra idoso, frequentemente é o ÚNICO app digital. Operamos via WhatsApp Business API homologada com Meta, criptografia ponta-a-ponta nativa, integradores certificados com servidores brasileiros. Pra ligação telefônica direta usamos infraestrutura SIP própria (PJSIP) com voz speech-to-speech state-of-the-art.

---

## SLIDE 6 — Canais de entrada (2/2): WhatsApp em detalhe

Idoso brasileiro frequentemente não digita bem. WhatsApp permite:

| Entrada | Processamento | Saída clínica |
|---|---|---|
| **Áudio do WhatsApp** (30s falando) | Transcrição STT + estruturação clínica | Sintoma identificado · severidade · registro no prontuário · escalação se urgente |
| **Foto da receita médica** | OCR (visão multimodal) | Princípios ativos extraídos · confronto com prescrição registrada · alerta de discrepância **antes da primeira dose** |
| **Foto da bula** | OCR + reasoning | Explicação em linguagem simples da seção relevante |
| **Foto da embalagem** | OCR | Princípio ativo · dose · lote · validade |
| **Foto de exame laboratorial** | OCR estruturado | Hb · creatinina · etc · alerta automático se valor crítico |
| **Foto de lesão / ferida / edema** | Visão multimodal | Observação clínica gerada · NÃO diagnóstico |
| **Foto do display de aparelho** (oxímetro · glicosímetro · pressão) | OCR | Valor extraído · registrado · alerta se fora de faixa |

✅ **OCR clínico em produção** · ✅ **análise visual em produção**

> **Speaker notes:**
> Esse slide costuma impressionar. O caso de uso "OCR de receita = detector de erro de medicação ANTES da primeira dose" é dos mais valiosos — paciente sai do hospital, fotografa receita ao chegar em casa, Sofia confronta com prescrição registrada, se farmácia entregou medicação errada (ou paciente está olhando receita anterior misturada) Sofia escala antes de o paciente tomar dose errada. Isso captura erro de medicação no momento certo.

---

## SLIDE 7 — Biometria de voz + biomarcadores vocais

Em healthcare, **saber com certeza quem está do outro lado da linha não é detalhe — é segurança clínica.**

**Biometria de voz** ✅ produção:
- Cada usuário cadastrado tem voiceprint registrado (vetor matemático, não áudio cru)
- Em ligação, identifica nos primeiros segundos se é o paciente, esposa, neta, cuidador
- Persona adapta automaticamente: paciente → tom calmo · familiar → técnico permitido
- LGPD: TCLE específico para dado biométrico sensível (Art. 11)

**Biomarcadores vocais** 🟣 fase de estudo:
- Análise quantitativa: jitter · shimmer · ritmo · prosódia · fluência
- Detecção precoce de: desidratação aguda · descompensação cardíaca · quadros depressivos · declínio cognitivo
- Literatura: Mayo Clinic + MIT Voice Foundation 2023-2025
- Quando ativado: gera **observação clínica** (não diagnóstico) → equipe avalia

> **Speaker notes:**
> Quando a Sofia liga pra Sr. José pós-IAM e quem atende é a esposa, neta, ou cuidadora informal, o conteúdo da conversa muda completamente: confidencialidade LGPD, validade do dado clínico relatado, roteamento da escalação. Biometria de voz protege contra vazamento e marca explicitamente "informação relatada por terceiro" no prontuário. Biomarcadores vocais são fase de estudo — ainda em pesquisa, mas a base técnica (gravação + STT) já está pronta. Essa é uma área onde gostaria seu input clínico.

---

## SLIDE 8 — Teleconsulta integrada 🟡

**Não é Doctoralia. É módulo próprio integrado ao prontuário.**

```
Sofia identifica necessidade clínica → propõe teleconsulta
                  ↓
         Paciente aceita via WhatsApp
                  ↓
       Link único (zero fricção · sem app)
                  ↓
   Médico VITA com tela dividida:
   ┌──────────────┬─────────────────┐
   │ Vídeo paciente│ Prontuário cheio │
   │              │ + Risk Score      │
   │              │ + Histórico Sofia │
   │              │ + Motor 12 dim    │
   └──────────────┴─────────────────┘
                  ↓
   Transcrição em tempo real (STT)
   Sofia atua como secretária clínica
                  ↓
   FINALIZAÇÃO (5 ações automáticas):
   1. Prescrição digital com assinatura
   2. Atestado · encaminhamento
   3. Plano terapêutico atualizado
   4. Motor 12 dim valida nova prescrição
   5. Audit chain criptográfica
                  ↓
   Sofia retoma acompanhamento com plano novo
```

> **Speaker notes:**
> Esse é um dos diferenciais estratégicos. Plataformas de telemedicina marketplace (Doctoralia, Conexa) tiram o paciente do ecossistema do hospital. Nosso módulo de teleconsulta mantém o paciente DENTRO do parceiro: equipe clínica do hospital atende, prescrição vai pro prontuário do hospital, receita gerada fica com o hospital. Quando médico finaliza consulta, motor de 12 dimensões VALIDA a nova prescrição automaticamente. Status: em finalização — disponível pra piloto VITA.

---

## SLIDE 9 — Motor clínico: 12 dimensões

Todo input de medicação é validado simultaneamente em:

```
1.  Dose máxima diária              7. Contraindicações por condição clínica
2.  Critérios de Beers 2023         8. ACB Score (anticolinérgico)
3.  Alergias + reações cruzadas     9. Fall Risk Score
4.  Duplicidade terapêutica         10. Ajuste renal (Cockcroft-Gault + KDIGO)
5.  Polifarmácia                    11. Ajuste hepático (Child-Pugh A/B/C)
6.  Interações med×med              12. Constraints de sinais vitais
```

**+ Dimensão 13: Cascatas de prescrição** ✅ (slide 13)

Saída estruturada em ~200ms. Cada dimensão é uma tabela versionada no banco com fonte citada.

> **Speaker notes:**
> Esse é o coração técnico. Diferente de outras soluções que usam LLM pra "raciocinar" sobre interações (e às vezes erram), nós temos REGRAS DETERMINÍSTICAS em código. Cada dimensão é uma tabela no PostgreSQL com fonte citada — Beers 2023, FDA labels, ANVISA Bulário, Stockley's, KDIGO 2024. Quando atualizamos uma regra, todas as prescrições ativas no sistema são re-validadas semanalmente.

---

## SLIDE 10 — Detalhe: dim 1-4

| Dim | Tabela | Exemplo |
|---|---|---|
| 1. Dose máxima | `aia_health_drug_dose_limits` | Olanzapina: 20 mg/dia (ANVISA bulário) |
| 2. Beers 2023 | `aia_health_drug_beers` | Olanzapina: AVOID em demência (FDA Box warning — aumenta mortalidade + AVC) |
| 3. Alergia/reações cruzadas | `aia_health_allergy_crossreactivity` | Penicilina ↔ todos β-lactâmicos · sulfa ↔ probenecida · AAS ↔ AINEs |
| 4. Duplicidade terapêutica | Detecção por classe + por princípio | Sertralina + escitalopram = duplicação SSRI |

> **Speaker notes:**
> Beers 2023 atualizado completo. Quando médico prescreve, motor compara com lista AVOID e lista CAUTION. Distinguimos "AVOID em qualquer idoso" de "AVOID em condição específica" (demência, history of falls, IRC, etc). Isso é crítico — Beers é contextual, não só lista preta.

---

## SLIDE 11 — Detalhe: dim 5-8

| Dim | Tabela | Exemplo |
|---|---|---|
| 5. Polifarmácia | Threshold ≥5 medicamentos com peso por classe | Idoso com 8 meds + 2 anticolinérgicos = high score |
| 6. Interações med×med | `aia_health_drug_interactions` (40 pares + classes) | Ciprofloxacino + amiodarona = QT longo (AVOID) |
| 7. Contraindicações por condição | `aia_health_drug_contraindications` (CID-10) | Risperidona + Parkinson G20 = AVOID antagonismo D2 |
| 8. ACB Score | `aia_health_drug_anticholinergic_burden` | Amitriptilina ACB 3 + oxibutinina ACB 3 = total 6 (alto risco cognitivo) |

> **Speaker notes:**
> Detalhe importante na dimensão 6: temos **interações mitigáveis por espaçamento de horário**, não só "evitar". Levotiroxina + carbonato de cálcio = espaçar 4h, não evitar. ACB Score é cumulativo (escala Boustani) — soma ≥3 = alto risco cognitivo (associado com declínio, delirium, queda).

---

## SLIDE 12 — Detalhe: dim 9-12

| Dim | Tabela | Exemplo |
|---|---|---|
| 9. Fall Risk Score | `aia_health_drug_fall_risk` (por classe) | BZD score 2, BCCa di-hidropiridínico score 1, antipsicótico atípico score 1 |
| 10. Ajuste renal | `aia_health_drug_renal_adjustments` (4 faixas ClCr) | Metformina: ClCr<30 = AVOID; <45 = max 1g/dia |
| 11. Ajuste hepático | `aia_health_drug_hepatic_adjustments` (Child A/B/C) | Olanzapina: Child A monitor, B reduce 50%, C avoid |
| 12. Constraints de vitais | `aia_health_drug_vital_constraints` | Anlodipino + PA<110 = warning hipotensão |

> **Speaker notes:**
> Cockcroft-Gault aplicado pra calcular ClCr — usado em decisão clínica em vez de creatinina pura, porque idoso pode ter creatinina "normal" mas TFG real baixa por sarcopenia. Constraints de vitais permite Sofia avisar quando dose existente perde adequação (ex: paciente em uso de anlodipino chega com PA 100/60 — alerta automático).

---

## SLIDE 13 — Dimensão 13: Cascatas de prescrição ✅

8 cascatas codificadas (Beers 2023 + STOPP/START + Rochon BMJ 2017):

| # | Cascata | Severidade |
|---|---|---|
| 1 | Triple Whammy (AINE + IECA/BRA + Diurético) → IRA aguda | major |
| 2 | HAS induzida por AINE → anti-hipertensivo | moderate |
| 3 | BCCa-DHP → edema → diurético (ineficaz) | moderate |
| 4 | Antipsicótico + antiparkinsoniano (paradoxal) | major |
| 5 | Metoclopramida → discinesia tardia | major |
| 6 | IBP crônico + suplementos B12/Cálcio | minor |
| 7 | Anticolinérgico + laxante crônico | moderate |
| 8 | Corticoide → hiperglicemia → antidiabético | moderate |

**Exclusões clínicas codificadas** (paciente com Parkinson real é excluído da cascata 4, etc).

> **Speaker notes:**
> Cascatas é onde o motor sai do "validador de prescrição individual" e vira "auditor de regime terapêutico". Cada cascata tem padrão A+C ou A+B+C, com regras de exclusão (ex: paciente com Parkinson G20/G21 não dispara cascata 4 porque antiparkinsoniano é tratamento real, não cascata). Ainda há cascatas que considero adicionar — diurético tiazídico→hiperuricemia→alopurinol, beta-bloqueador→bradicardia, opioide→constipação→laxante (separada de anticolinérgico). Quero seu input sobre quais valem prioridade.

---

## SLIDE 14 — Cobertura atual: 48 princípios ativos × 14 classes

```
Anti-hipertensivos (7)        Antipsicóticos (4)
  losartana, enalapril,         haloperidol, risperidona,
  anlodipino, propranolol,      quetiapina, olanzapina
  atenolol, metoprolol,
  carvedilol                   Antiparkinsonianos (3)
                                 levodopa+carbidopa,
Antidiabéticos (5)               pramipexol, ropinirol
  metformina, glibenclamida,
  gliclazida, empagliflozina,  Antieméticos (2)
  dapagliflozina                 metoclopramida, ondansetrona

Antiplaq./Anticoag. (6)        Antibióticos (5)
  AAS, clopidogrel,              amoxicilina, amoxi+clavulanato,
  varfarina, rivaroxabana,       azitromicina, ciprofloxacino,
  apixabana, dabigatrana         sulfa+trimetoprima

Estatinas (3) | IBPs (3) | Antidepressivos (4) | Hipnóticos (4)
Outros: paracetamol, dipirona, AINEs, alendronato, levotiroxina, carbonato Ca
```

**Cobertura: 70-80% da prescrição geriátrica brasileira.**
🔵 **Roadmap próximo:** 80 princípios ativos (~95% cobertura).

> **Speaker notes:**
> Esses 48 cobrem o que vejo prescrito 80% das vezes em prontuário geriátrico real. Faltam: BCCa não-DHP (verapamil, diltiazem), inibidores colinesterase (donepezila, rivastigmina, galantamina, memantina), insulinas, broncodilatadores inalatórios, corticoides sistêmicos, opioides (tramadol, codeína, morfina), anticonvulsivantes (gabapentina, pregabalina, valproato). É exatamente nesse ponto que sua expertise pode acelerar nossa expansão.

---

## SLIDE 15 — Validação automática semanal ✅

Toda semana o motor **re-roda** todas as prescrições ativas no banco contra a versão atual das 13 dimensões.

**Por quê:**
- Nova interação descoberta → ontem segura, hoje insegura
- Atualização de Beers → fármaco passa a ser AVOID
- Mudança de função renal do paciente → dose anterior virou inadequada
- Cascata recém-codificada → identifica padrões já existentes

Achados vão pra fila de revisão clínica (`aia_health_action_review_queue`) com severidade calibrada.

> **Speaker notes:**
> Esse é um ponto que diferencia. A maioria dos sistemas "valida na hora da prescrição e esquece". Nós re-validamos semanalmente. Quando Beers 2023 saiu nova versão, em uma semana todos os pacientes ativos tinham suas prescrições re-cruzadas. Achados ficam na fila pra equipe clínica revisar e decidir — não modificamos prescrição automaticamente.

---

## SLIDE 16 — Memória: 4 camadas ✅

Sofia se diferencia de chatbot porque **lembra**:

| Camada | Função | Detalhes |
|---|---|---|
| 1. Conversa atual | Últimas 30 mensagens da sessão | Padrão LLM |
| 2. Cross-canal | 45 min cross-channel | Chat às 8h é lembrado na ligação às 8h30 |
| 3. Perfil persistente | Resumo + facts JSONB por usuário | Re-extraído a cada 20 msgs · LGPD opt-in |
| 4. Recall semântico | pgvector 768d HNSW | Busca verbatim em 90 dias |

**+ Recall cross-paciente anonimizado** ✅ (slide 18)
**+ Memória coletiva cross-tenant** ✅ (insights agregados anônimos pra calibrar regras)

> **Speaker notes:**
> A memória habilita Sofia a notar padrões longitudinais. Idoso que teve 3 quedas em 5 dias — memória detecta padrão e classifica como urgente, mesmo cada queda isolada parecendo "rotina". Recall semântico é VERBATIM (não resumo) — médico pergunta "lembra que comentei sobre dor lombar do Sr Antônio em fevereiro?" e Sofia traz a mensagem exata, com timestamp e canal de origem.

---

## SLIDE 17 — Risk Score por paciente ✅

**Fase 1: Score 0-100 baseado em sinais determinísticos**

```
Sinal 1: Frequência de queixas registradas (últimos 7d)
Sinal 2: Adesão à medicação (% confirmadas vs planejadas, 7d)
Sinal 3: Eventos urgent/critical (últimos 7d)

→ Score 0-100 · level: low · moderate · high · critical
```

**Fase 2: Baseline individual** ✅
- Cada paciente comparado contra **ele mesmo** (median + MAD robusto)
- João (DPOC) com baseline 5 queixas/sem = normal pra ele
- Maria (geral) que pulou de 1 → 3 queixas = ALERTA mesmo abaixo do threshold absoluto
- Z-score robusto detecta desvio individual

**Combined score** = max(threshold absoluto, threshold + bônus baseline)

> **Speaker notes:**
> Risk Score é a "espinha dorsal" da priorização. Hoje em produção identificou 2 pacientes críticos automaticamente que estavam invisíveis no painel humano. Fase 2 (baseline individual) é a evolução conceitual — em vez de regra "5 queixas = high", compara cada paciente com seu próprio padrão. Mais sensível, mais personalizado.

---

## SLIDE 18 — Proactive Caller ✅

**Sofia decide DINAMICAMENTE quando ligar**, não por cron estático.

Tick a cada 5min, avalia cada paciente ativo:

```
Score de gatilho (0-100):
  + risk_level critical → 60 pts
  + risk_level high → 35 pts
  + missed_doses 24h ≥ 3 → 40 pts
  + open_urgent_events ≥ 2 → 35 pts
  + gap > 48h sem contato → 15 pts
  - gap < 4h (acabou de ligar) → -100 pts (block)

Threshold default: 50 pts
```

**Respeita:** janela horária do paciente · DND · circuit breaker do Safety Guardrail · scenario configurável por tenant

✅ Em produção. Cada decisão (will_call OR skip) fica auditável em `aia_health_proactive_call_decisions`.

> **Speaker notes:**
> Diferente do scheduler estático ("8h30 todo dia"). Aqui a Sofia decide: "Helena com risk score 85, baseline alto, esta semana já 4 queixas → ligo agora pra checar". Configurável por paciente: janela horária, DND, intervalo mínimo entre ligações. Toda decisão registrada pra auditoria — incluindo skip com razão (fora janela, score baixo, etc).

---

## SLIDE 19 — Recall semântico cross-paciente ✅

Médico pergunta: *"que outros pacientes tiveram esse mesmo padrão de queda?"*

Sofia busca semanticamente em **todos os pacientes** do tenant, retornando matches anonimizados:

```json
{
  "matches": [
    {
      "anonymized_patient_id": "anon-a3f72b1c",  // hash + salt único por query
      "channel": "voice",
      "content": "[PACIENTE] disse que caiu na sala [DATA]",  // PII redacted
      "similarity": 0.847,
      "days_ago": 3
    }
  ],
  "unique_patients": 7
}
```

**RBAC:** restrito a medico · enfermeiro · admin (cuidador/família/paciente recebem `persona_not_allowed`)
**PII redaction:** nome paciente · telefone · email · CPF · datas → tokens
**Salt único por query:** mesmo paciente NÃO é re-identificável entre buscas

> **Speaker notes:**
> Esse recurso permite reflexão sobre padrões coletivos sem expor identidade individual. Profissional pode perguntar "já vimos esse tipo de queixa antes?" e receber 10 snippets anonimizados pra raciocinar. Salt único por query: se profissional fizer 10 buscas, o mesmo paciente aparece com IDs DIFERENTES — não dá pra cross-referenciar fora do contexto da query.

---

## SLIDE 20 — Versionamento de prompts dos cenários ✅

5 cenários de ligação Sofia em produção, cada um editável sem release:

| Cenário | Persona | Quando dispara |
|---|---|---|
| paciente_checkin_matinal | paciente B2C | 8h-9h diário · mais Proactive Caller dinâmico |
| cuidador_retorno_relato | cuidador profissional | Atualizar status de relato em aberto |
| familiar_aviso_evento | familiar | Avisar sobre evento clínico (queda, febre) — tom anti-pânico |
| paciente_enrollment_outbound | paciente novo | Onboarding leve |
| comercial_outbound_lead | lead comercial | Qualificar + agendar demo |

**Workflow de versionamento** ✅:
```
draft → testing → published → archived
```
- Admin edita prompt em DRAFT
- Testa contra "golden dataset" (10 conversas-tipo por cenário)
- Promove pra PUBLISHED → arquiva versão anterior automaticamente
- Audit chain registra cada promoção

> **Speaker notes:**
> Cada cenário tem ~7-15 KB de prompt com regras anti-pânico, anti-diagnóstico, RBAC LGPD. Admin edita via interface dedicada `/admin/cenarios-sofia`. Mudanças entram em vigor na próxima ligação, sem release de código. Versionamento traz auditabilidade — toda promoção pra produção é registrada com user_id e timestamp.

---

## SLIDE 21 — Tools clínicas da Sofia ✅

Sofia pode chamar **16 tools** durante conversa (chat ou voz). Disponibilidade depende de persona:

```
Clínicas (medico, enfermeiro, admin):
  query_drug_rules            check_drug_interaction
  check_medication_safety     list_beers_avoid_in_condition
  query_clinical_guidelines   recall_semantic_cross_patient

Pacientes/cuidadores/família:
  get_patient_summary         list_medication_schedules
  get_patient_vitals          create_care_event (Safety Guardrail)
  schedule_teleconsulta       escalate_to_attendant (Safety Guardrail)
  recall_semantic             get_my_subscription
```

Cada tool tem:
- Description: Sofia entende quando chamar
- Parameters: schema validado
- Allowed personas: RBAC nativo
- Safety Guardrail integration: tools de ação clínica passam pelo router

> **Speaker notes:**
> Esse slide mostra que Sofia não é "LLM falando solto". Ela tem ferramentas estruturadas. Quando médico pergunta "é seguro 0,5 mg risperidona pra Dona Helena com demência?", Sofia chama `check_medication_safety` automaticamente. O motor retorna o output estruturado em ~200ms. Sofia traduz pra linguagem natural, sempre com disclaimer.

---

## SLIDE 22 — Safety Guardrail Layer ✅

> **Princípio:** Sofia tem inteligência. Sofia NÃO tem autoridade.

Toda ação clínica passa por router determinístico que decide entre 5 destinos:

| Ação | Comportamento |
|---|---|
| **Informativa** (responder dose máxima) | Executa direto + disclaimer |
| **Registrar histórico** (gravar queixa) | Salva no banco · notifica se severity ≥ atenção |
| **Convocar atendente** | Vai pra fila · humano aprova |
| **Emergência real-time** (paciente fala "dor no peito") | Bypass · escala imediato + 192 + família |
| **Modificar prescrição** | **BLOQUEADO** (precisa médico responsável formal) |

**Circuit breaker:** auto-pausa tenant se >5% queue rate em 5 min.

> **Speaker notes:**
> Esse é o slide regulatorialmente mais importante. CFM 2.314/2022 e a nova 2.454/2026 são bem claras: IA pode informar, sugerir, escalar — não pode diagnosticar nem prescrever. Nosso Safety Guardrail é a tradução técnica desse princípio. "Modificar prescrição" está hard-coded como bloqueado. Outras ações passam por médico humano antes de afetar o paciente.

---

## SLIDE 23 — Audit chain criptográfica LGPD ✅

Toda ação sensível registrada em chain de hash SHA-256:
- Acesso a dados clínicos
- Edição de regras do motor
- Promoção de versão de prompt
- Execução de tool com Safety Guardrail
- Decisão clínica do médico durante teleconsulta

**Inviolável:** qualquer adulteração retroativa é detectável computacionalmente (cada hash inclui hash anterior).

**LGPD compliance:**
- Privacy by design
- Minimização de dados (só o necessário)
- TCLE específico Art. 11 (saúde + biometria)
- DPA com hospitais parceiros (controlador vs operador)
- Direitos do titular: exportação · exclusão a qualquer momento

> **Speaker notes:**
> Audit chain criptográfica é diferencial pra auditorias de hospitais e órgãos reguladores. Cada bloco (linha) referencia o hash do bloco anterior. Se alguém tentar editar um log retroativamente, a chain quebra e o sistema sinaliza. Padrão equivalente a blockchain interna mas sem custo de descentralização.

---

## SLIDE 24 — Fontes citadas no motor

Cada regra tem fonte e referência:

```
beers_2023        — American Geriatrics Society 2023 update
fda               — FDA labels (Box warnings, dose limits)
anvisa            — Bulário Eletrônico ANVISA
kdigo             — KDIGO Clinical Practice Guideline 2024
stockleys         — Stockley's Drug Interactions
lexicomp          — Lexicomp clinical references
stopp_start_v2    — STOPP/START Criteria v2 (Ireland)
rochon_bmj_2017   — Rochon RJ et al, BMJ 2017;359:j5251 (cascades)
manual            — curadoria interna documentada
```

Confidence score por regra (0-1). Audit chain criptográfica registra mudanças.

> **Speaker notes:**
> Esse é o slide pra mostrar rigor metodológico. Cada linha do banco tem source + source_ref + confidence. Quando audit interno ou externo perguntar "de onde veio essa regra?", o sistema responde em segundos. Confidence < 0.7 = manual review obrigatório antes de promover.

---

## SLIDE 25 — Posicionamento regulatório

| Frente | Status | Roadmap |
|---|---|---|
| **CFM 2.314/2022 + 2.454/2026** | Conformidade preventiva (médico responsável designado, comitê IA estabelecido) | Formalizar comitê com geriatra externo |
| **ANVISA SaMD** | Operando como ferramenta de apoio (até 1k pacientes) | Registro Classe IIa em 2026/2027 |
| **LGPD** | Privacy by design + audit chain criptográfico SHA-256 | DPA com hospitais parceiros |
| **CRF/Farmacêutico Responsável** | Em formalização | **Aqui é onde sua possível colaboração entra** |

> **Speaker notes:**
> Pra registrar como SaMD (Software como Dispositivo Médico) Classe IIa na ANVISA precisamos de farmacêutico responsável técnico formal. Esse é um dos pontos onde gostaria de explorar se você teria interesse em compor o time clínico — seja como consultor, seja como RT formal quando for o momento. Não decisão hoje, mas quero deixar a porta aberta.

---

## SLIDE 26 — Validação científica em curso

**Golden dataset interno:**
- 10 conversas-tipo por cenário de ligação (5 cenários ativos = 50 testes)
- Validação manual de saídas clínicas críticas
- Versionamento de prompts (draft → testing → published)

**Parcerias acadêmicas (em formação):**
- Universidades de Farmácia para revisão por pares
- Co-publicação de resultados após 100+ pacientes acompanhados

**Métricas tracking:**
- Falsos positivos (Sofia escalou e era irrelevante)
- Falsos negativos críticos (paciente teve evento, Sofia não captou)
- Tempo até captura de sintoma novo
- NPS profissional (Sofia ajuda ou atrapalha?)
- Taxa de adesão a recomendações clínicas

> **Speaker notes:**
> Reconhecemos publicamente que validação científica formal está APENAS COMEÇANDO. Não fingimos ter robustez de Hippocratic AI ou Sensi.ai (que tem estudos de não-inferioridade vs enfermagem em larga escala). Nosso momento é construir essa base — uma das razões pra trazer expertise sênior pra dentro.

---

## SLIDE 27 — Status: produção × roadmap (matriz visual)

| Capacidade | Status |
|---|---|
| Chat texto · 16 tools clínicas | ✅ |
| Voz no browser (speech-to-speech) | ✅ |
| Ligação telefônica outbound (PJSIP) | ✅ |
| WhatsApp Business: texto + áudio + mídia | ✅ |
| OCR clínico (receita, bula, exame, embalagem) | ✅ |
| Análise visual de lesão / display de aparelho | ✅ |
| Biometria de voz — identificação interlocutor | ✅ |
| Motor 12 dimensões · 48 fármacos | ✅ |
| Cascatas de prescrição (dim 13) · 8 cascatas | ✅ |
| Memória 4 camadas + cross-canal + recall semântico | ✅ |
| Memória coletiva anonimizada cross-tenant | ✅ |
| Safety Guardrail Layer + circuit breaker | ✅ |
| Audit chain LGPD criptográfica | ✅ |
| Risk Score por paciente (Fase 1 + Baseline Fase 2) | ✅ |
| Proactive Caller (Sofia decide quando ligar) | ✅ |
| Recall semântico cross-paciente anonimizado | ✅ |
| Versionamento de prompts cenários | ✅ |
| 5 cenários de ligação editáveis sem release | ✅ |
| Validação automática semanal do motor | ✅ |
| Teleconsulta integrada (módulo próprio) | 🟡 |
| Cobertura motor 48 → 80 fármacos | 🔵 |
| Inbound calls (Sofia atende) | 🔵 |
| LiveKit Cloud + SIP trunk Flux | 🔵 |
| WhatsApp Calling outbound (Meta API) | 🟣 |
| Biomarcadores vocais (jitter/shimmer/prosódia) | 🟣 |
| STOPP/START como camada complementar a Beers | 🟣 |
| Detecção longitudinal de padrões cognitivos | 🟣 |
| Plano "Cuidado Sem Limites" B2C massivo | 🟣 |

**Legenda:** ✅ produção · 🟡 finalização · 🔵 roadmap próximo · 🟣 visão futura

> **Speaker notes:**
> Esse slide é importante porque traduz com transparência o que está pronto vs o que está vindo. Não inventamos features. Tudo o que está em ✅ você pode testar HOJE. 🟡 está na reta final. 🔵 estamos codificando. 🟣 é visão estratégica que depende de dados/pesquisa.

---

## SLIDE 28 — Roadmap clínico expandido

**Próximas 8-12 semanas (🔵):**
- Cobertura motor 48 → 80 princípios ativos
- Mais cascatas (tiazídico→hiperuricemia, beta-blq→bradicardia, opioide→constipação)
- STOPP/START como camada complementar a Beers
- LiveKit Cloud + SIP trunk redundante (resiliência)
- Inbound calls (Sofia atende)

**3-6 meses (🟣):**
- Biomarcadores vocais (jitter, shimmer, prosódia)
- Detecção longitudinal de padrões cognitivos
- Recall semântico cross-tenant (insights coletivos com diferential privacy)
- WhatsApp Calling outbound nativo (Meta API)
- Imagem multimodal: análise visual avançada de lesão/ferida com follow-up temporal

**6-12 meses (🟣):**
- Plano "Cuidado Sem Limites" B2C massivo (Dona Helena scenario)
- Federated learning entre tenants
- ANVISA SaMD Classe IIa formalizado
- Co-publicação científica (100+ pacientes acompanhados)

> **Speaker notes:**
> Tudo o que está em 🔵 e 🟣 depende de validação clínica. Especialmente cobertura de fármacos, cascatas adicionais, biomarcadores. Quanto mais rápido tivermos input clínico sênior, mais rápido sai do roadmap pra produção.

---

## SLIDE 29 — Onde sua expertise pode entrar

**Imediato — auditoria do que já temos:**

1. Revisão crítica das regras codificadas pra cada um dos 48 princípios ativos
2. Revisão dos 5 cenários de ligação (anti-pânico, anti-diagnóstico, RBAC LGPD)
3. Validação das 8 cascatas de prescrição
4. Revisão dos thresholds de Risk Score (ACB, fall risk, polifarmácia)

**Curto prazo — expansão:**

5. Priorização de quais 30 fármacos faltantes mais importam em geriatria brasileira
6. Codificação clínica desses 30 (formato YAML simplificado — ~30 min/lote de 5 fármacos)
7. STOPP/START Brasil (vs Beers americana) — vale somar?
8. Cascatas adicionais a considerar
9. Biomarcadores vocais — quais sinais valem priorizar pra detectar?

**Médio prazo — frente clínica do produto:**

10. Comitê de governança IA (CFM)
11. Farmacêutico Responsável Técnico (ANVISA SaMD)
12. Co-publicação científica quando atingirmos 100+ pacientes
13. Calibração de regras com dados reais quando volume escalar

> **Speaker notes:**
> Esse é o "ask" da apresentação. Não estamos pedindo decisão hoje. Quero entender qual desses tópicos mais te interessa, qual você teria largura de banda pra contribuir, e se faria sentido formalizar a relação (consultoria, RT, co-autoria, ou participação no comitê).

---

## SLIDE 30 — O que NÃO somos

Pra calibrar expectativa:

| O que somos | O que NÃO somos |
|---|---|
| Sistema de apoio à decisão clínica | Substituto de avaliação clínica |
| Validador determinístico de regras conhecidas | Descobridor de novas regras farmacológicas |
| Plataforma de relacionamento longitudinal | Plataforma de prontuário único |
| Co-piloto de profissional | Médico/farmacêutico |
| Engenharia clínica em PT-BR nativo | Versão localizada de produto americano |

**A Sofia não diagnostica, não prescreve, não decide.** Ela informa, lembra, escala, escuta, gera observação clínica.

> **Speaker notes:**
> Calibração honesta. Sabemos onde acaba nossa fronteira. Não estamos resolvendo "fazer geriatria automaticamente" — estamos resolvendo "tornar o conhecimento geriátrico aplicável em escala em qualquer interação". A diferença é importante.

---

## SLIDE 31 — Equipe

**Alexandre Veras** — CEO + Engenharia
20+ anos em arquitetura de plataformas SaaS escaláveis. Construtor da ConnectaIA (automação comercial em produção há 5 anos).

**Henrique Bordin** — Líder Clínico-Farmacológico
Biomédico. Formando em Farmácia (2026). Líder atual da expansão clínica do motor.

**[Vaga: Farmacêutico Sênior]** — RT formal pra ANVISA SaMD + comitê de governança IA + revisão de regras existentes + curadoria de expansão.

> **Speaker notes:**
> Aqui apresento o time atual e o gap. Henrique está fazendo um trabalho excelente mas reconhecemos que pra registrar ANVISA Classe IIa precisamos de RT com mais experiência clínica. É exatamente esse o slot que estamos discutindo com você.

---

## SLIDE 32 — Próximos passos

**Se houver interesse em colaboração:**

1. **Reunião de aprofundamento (1h):** demo ao vivo da Sofia + walkthrough do motor + perguntas técnicas
2. **Acesso a documentação técnica:** dicionário das 13 dimensões + tabelas SQL + fontes citadas
3. **Definir formato:** consultoria honorária · participação no comitê IA · RT formal · co-autoria científica
4. **NDA padrão** (se ainda não assinado)

**Se preferir só feedback pontual:**

1. Lê o checklist de revisão (anexo) e devolve por email/WhatsApp
2. Compartilha sua opinião sobre os 30 fármacos prioritários e regras críticas que você acharia importantes adicionar/corrigir

**Sem pressão pra decidir hoje. Estamos em construção.**

> **Speaker notes:**
> Slide de fechamento. Deixar claro que o leque é amplo — desde feedback pontual até envolvimento profundo. A pessoa decide o nível de imersão. Importante: NDA antes de qualquer documentação interna profunda.

---

## SLIDE 33 — Contato

**Alexandre Veras**
CEO, ConnectaIACare
alexandre@connectaia.com.br

**Material complementar (mediante NDA):**
- Documentação técnica do motor (13 dimensões + cascatas + risk score)
- Lista completa de 48 princípios ativos com regras codificadas
- Dump anonimizado da fila de revisão (exemplos reais de saídas clínicas)
- Acesso ao painel admin de regras clínicas
- Demo guiada de 20 min ao vivo da Sofia

> **Speaker notes:**
> Encerramento. Agradeço atenção. Disponível pra responder dúvidas agora ou seguir por email. Se tiver interesse em ver a Sofia em ação, posso fazer demo guiada de 20 min em outra sessão.

---

# Anexos para o Design

## A1. Diagrama de arquitetura sugerido (slide 4 ou 22)

```
┌──────────────────────────────────────────────────┐
│ Profissional / Paciente / Familiar               │
│       (chat / voz / WhatsApp / ligação)           │
└─────────────────┬────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────┐
│  Sofia (LLM conversacional)                       │
│  Detecta intenção · Gera resposta · Chama tools  │
│  Persona ajustada · Memória 4 camadas             │
└─────────────────┬────────────────────────────────┘
                  │ chama tool clínica
                  ▼
┌──────────────────────────────────────────────────┐
│  MOTOR DETERMINÍSTICO (12+1 dimensões)            │
│   ┌──────────────┬───────────────┬─────────────┐ │
│   │ Dose máx     │ Beers 2023    │ Alergias    │ │
│   │ Duplicidade  │ Polifarmácia  │ Interações  │ │
│   │ Contraindic. │ ACB Score     │ Fall Risk   │ │
│   │ Renal KDIGO  │ Hepática Pugh │ Vitais      │ │
│   │              │ Cascatas (13) │             │ │
│   └──────────────┴───────────────┴─────────────┘ │
└─────────────────┬────────────────────────────────┘
                  │ output estruturado
                  ▼
┌──────────────────────────────────────────────────┐
│  Safety Guardrail Layer                           │
│  Decide: executa | enfileira | escala | bloqueia │
└─────────────────┬────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────┐
│  Audit chain LGPD + fila de revisão clínica       │
└──────────────────────────────────────────────────┘
```

## A2. Diagrama da Teleconsulta (slide 8)

```
                    SOFIA detecta necessidade
                            ↓
                    Propõe teleconsulta
                            ↓
                    Paciente aceita (WhatsApp)
                            ↓
                    Link único → navegador
                            ↓
            ┌──────────────────────────────────┐
            │  TELA DO MÉDICO (split screen)    │
            ├─────────────┬────────────────────┤
            │   Vídeo      │ Prontuário        │
            │   paciente   │ + Risk Score      │
            │              │ + Histórico Sofia │
            │              │ + Motor 12 dim    │
            └─────────────┴────────────────────┘
                            ↓
                    STT em tempo real
                    Sofia = secretária clínica
                            ↓
            ┌──────────────────────────────────┐
            │       FINALIZAÇÃO (5 ações)       │
            │ 1. Prescrição digital (assinatura) │
            │ 2. Atestado · encaminhamento      │
            │ 3. Plano terapêutico atualizado    │
            │ 4. Motor 12 dim valida nova rec    │
            │ 5. Audit chain criptográfica       │
            └──────────────────────────────────┘
                            ↓
                    Sofia retoma com plano novo
```

## A3. Paleta de cores sugerida (consistente com produto)

- Fundo escuro: `#0a0e1a` ou similar (slate-950)
- Primary: ciano `#31e1ff` ou teal `#14b8a6`
- Texto: branco `#f8fafc`
- Secundário: cinza `#94a3b8`
- Destaque crítico: vermelho `#ef4444`
- Destaque atenção: laranja `#fb923c`
- Destaque aprovação: verde `#10b981`
- Status badges: ✅ verde · 🟡 amarelo · 🔵 azul · 🟣 roxo

## A4. Tipografia sugerida

- Títulos: Inter Bold ou Geist Bold
- Corpo: Inter Regular
- Código/tabelas técnicas: JetBrains Mono ou IBM Plex Mono

## A5. Notas finais para Design

1. **Preferir tabela > lista de bullets** sempre que houver dado técnico (slides 5, 10-12, 14, 16, 27 são exemplos)
2. **Speaker notes** vão na seção de notas do PowerPoint/Keynote — não devem aparecer no slide
3. **Diagramas (slides 4, 8, A1, A2)** merecem ilustração caprichada — esses são os "wow" técnicos do deck
4. **Logos**: ConnectaIACare na capa + rodapé discreto
5. **Numeração de slides** discreta (canto inferior direito)
6. **Slide 27** (matriz produção/roadmap) é o pico de informação — pode merecer 2 slides se ficar muito denso
7. **Cores de status** consistentes através do deck (✅ ✅ verde sempre, etc)

---

ConnectaIACare © 2026
