# RFC-001: Estratégia de Ecossistema Agêntico

- **Status**: Accepted
- **Date**: 2026-04-20
- **Driver**: Alexandre (ConnectaIA)
- **Approver**: Alexandre + alinhamento futuro com Murilo (Tecnosenior/MedMonitor) e Vinicius (Amparo)
- **Impact**: **HIGH** — define arquitetura de IA pelos próximos 12-24 meses
- **Tags**: architecture, ai, agents, strategy

## 1. Background

### Situação atual (MVP — abril 2026)
O ConnectaIACare opera como **pipeline reativo linear**: webhook WhatsApp → transcrição → extração → match paciente → análise clínica → resposta. O motor clínico (`clinical_analysis_service`) já tem **raciocínio estruturado embutido** (cruzamento sintoma×vital×condição, 8 padrões clínicos, guardrails de keywords de emergência), mas é fundamentalmente:
- **Fixo**: cada passo do pipeline é predeterminado
- **Single-shot**: LLM é chamado uma vez com todo o contexto, gera resposta, acabou
- **Sem autonomia**: não pode decidir chamar uma ferramenta adicional se precisar de mais informação
- **Sem memória evolutiva**: cada análise é independente; histórico existe mas não é incorporado de forma inteligente

### Contexto de mercado (2026)
Player-chave global (Anthropic) lançou **Claude for Healthcare** em jan/2026 com conectores agênticos HIPAA-ready e Agent Skills para FHIR. Google lançou **Agent Development Kit (ADK)** open-source. OpenAI tem Swarm. CrewAI, LangGraph, AutoGen amadurecem. **A indústria está se movendo de "LLM-as-feature" para "agents-as-architecture"**.

Sensi.ai, Hippocratic AI, Biofourmis — nossos benchmarks — **ainda não expõem arquitetura agêntica explícita**. Janela estratégica para nos diferenciarmos existe.

### Por que agora
- Definir arquitetura antes de escalar evita refactor caro depois
- Narrativa pra parceiros/investidores: "ecossistema agêntico" > "chatbot médico"
- Decisão impacta 5+ decisões técnicas futuras (framework, stack de tools, modelo de memória, padrão de deployment)
- Sexta 24/04 temos reunião com Murilo + Vinicius — narrativa agêntica é argumento forte

### Custo de inação
Se continuarmos no pipeline linear:
- Cada nova funcionalidade (integração MedMonitor, tele-consulta, prescrição) vira código custom acoplado
- Motor clínico fica no teto de qualidade que single-shot permite
- Competidores que já adotaram agents terão vantagem defensável
- Refatorar 12 meses depois custa 5-10× mais

---

## 2. Assumptions

Todas as assumptions explicitadas para serem challengeable:

1. **[HIGH confidence]** Arquitetura agêntica melhora qualidade clínica vs pipeline linear em ≥ 15% (mensurável por taxa de classificação correta + cobertura de recomendações). Evidência: benchmarks públicos (HumanEval, MMLU) mostram agents com tools superam single-shot em 10-30% em tarefas de raciocínio complexo.
   - **Invalidação**: se em experimento A/B interno não medirmos diferença, reconsiderar.

2. **[HIGH confidence]** Open-source (Apache 2.0, MIT) em frameworks agênticos é condição necessária para não criar lock-in estratégico em projeto de saúde com dados sensíveis.
   - **Invalidação**: se surgir framework comercial com vantagens técnicas > custo de lock-in, reconsiderar caso a caso.

3. **[MEDIUM confidence]** Google ADK será mantido ativamente pela Google com cadência comparável a TensorFlow/Keras (3+ anos de suporte garantido).
   - **Invalidação**: se Google reduzir investimento visivelmente em 12 meses, migrar para LangGraph ou Sofia adaptado.

4. **[HIGH confidence]** O "core clínico" (prompts em pt-BR, regras de cruzamento, ranges geriátricos brasileiros, motor de interações BR) é o principal diferencial defensável — framework agêntico é plumbing intercambiável.
   - **Invalidação**: se framework agêntico específico gerar diferencial de UX/performance que justifique lock-in, reconsiderar.

5. **[MEDIUM confidence]** Latência agente > pipeline linear em até 2-3× é aceitável para análise clínica (já estamos em 18s no linear; 30-60s em agent ainda é aceitável para WhatsApp).
   - **Invalidação**: se usuário reportar impaciência > X% dos casos, otimizar ou voltar pipeline em fluxos críticos.

6. **[LOW confidence]** Sofia Multi-Agent (código existente no ConnectaIA) pode ser adaptado como fallback confiável se ADK falhar.
   - **Invalidação**: precisa auditoria do código Sofia antes de contar com ela — validação em item 7.4 de Action Items.

---

## 3. Decision Criteria

Critérios **estabelecidos antes** de avaliar as opções (evita racionalizar decisão já tomada):

### Must-haves (bloqueantes)
| # | Critério | Peso |
|---|----------|------|
| MUST-1 | **Open-source** (Apache 2.0, MIT, BSD) | Alto |
| MUST-2 | **Multi-provider LLM** (não lock em Claude ou Gemini) | Alto |
| MUST-3 | **Python-first** (nosso stack; considerar TS se hard-constraint) | Alto |
| MUST-4 | **Produção-ready** (≥ 6 meses de existência estável, usado em produtos reais) | Alto |
| MUST-5 | **Auditabilidade** (rastreamento de cada decisão do agente é nativo ou adicionável) | **Crítico para saúde + CFM 2.314 + LGPD** |
| MUST-6 | **Tool-use nativo** (function calling padronizado, não hack em prompt) | Alto |

### Should-haves (preferenciais, peso)
| # | Critério | Peso |
|---|----------|------|
| SHOULD-1 | Integração nativa com nosso LLM atual (Gemini) | 5 |
| SHOULD-2 | Suporte a multi-agent (não só single agent + tools) | 4 |
| SHOULD-3 | Mantenedor com trajetória longa (Google, Microsoft, Linux Foundation) | 4 |
| SHOULD-4 | Comunidade ativa (> 10k stars GitHub ou equivalente) | 3 |
| SHOULD-5 | Deployment flexível (local, VPS própria, GCP, AWS) | 5 |
| SHOULD-6 | Observabilidade nativa (traces, spans) | 3 |
| SHOULD-7 | Exemplo real de uso em healthcare documentado | 2 |

---

## 4. Options Considered

### Option A: Status quo (pipeline linear)
Manter `clinical_analysis_service` como está. Evoluir prompts.

**Pros**:
- ✅ Zero custo de mudança
- ✅ Simplicidade operacional
- ✅ Já funciona e foi validado E2E

**Cons**:
- ❌ Teto de qualidade clínica (single-shot não se aprofunda)
- ❌ Cada nova integração vira código custom
- ❌ Sem narrativa de ecossistema agêntico pra mercado
- ❌ Refactor futuro custa 5-10× mais

**Score**: 0 (base de comparação)
**Decisão**: ❌ Rejeitada — teto arquitetural explícito

---

### Option B: LangGraph (LangChain)
Framework de grafo de agentes com estado. Multi-provider. Maduro (2 anos+).

**Atende MUST**: ✅ todos (MIT, multi-provider, Python, 2+ anos, observabilidade via LangSmith, tool-use nativo)

**Pros**:
- ✅ Mais batalhado — muitos casos de produção documentados
- ✅ Multi-provider nativo e neutro
- ✅ LangSmith dá observabilidade out-of-the-box
- ✅ Grafo explícito facilita debug + auditoria

**Cons**:
- ❌ Boilerplate Python pesado (verbose)
- ❌ Parte da LangChain — reputação mista de over-abstração
- ❌ LangSmith (observabilidade) tem tier pago para escala

**Score SHOULD**: 3+4+4+5+5+3+1 = 25
**Decisão**: ⚠️ Segunda escolha viável — considerada fallback técnico se ADK não amadurecer

---

### Option C: Google Agent Development Kit (ADK) — **ESCOLHIDA PRIMÁRIA**

Framework open-source de agentes lançado pelo Google em 2025. Integração nativa com Gemini + Vertex AI. Apache 2.0. Multi-agent first-class.

**Atende MUST**: ✅ todos
- MUST-1: Apache 2.0 ✅
- MUST-2: Multi-provider (suporta Anthropic, OpenAI, Gemini via plugins) ✅
- MUST-3: Python-first ✅
- MUST-4: Produção-ready (Google usa internamente + uso externo crescendo) ⚠️ **ponto de atenção: ainda jovem**
- MUST-5: Auditabilidade via traces OTel ✅
- MUST-6: Tool-use nativo ✅

**Pros**:
- ✅ Integração nativa com Gemini (nosso provider atual) → zero fricção
- ✅ Open-source Apache 2.0 → mesmo se Google descontinuar, código permanece
- ✅ Deployment flexível (local, VPS própria, GCP) → não força cloud
- ✅ Multi-agent é first-class (não addon)
- ✅ OpenTelemetry nativo → audit trail em CFM/LGPD fica trivial
- ✅ Backed por Google → inércia de investimento
- ✅ Lançado já com casos reais na Google e parceiros

**Cons**:
- ⚠️ Jovem (lançado recentemente) → menos casos de produção documentados que LangGraph
- ⚠️ Comunidade menor que LangChain
- ⚠️ "Feito por Google" gera percepção de eventual push para Vertex AI pago (mitigado por open-source)

**Score SHOULD**: 5+5+4+3+5+5+2 = 29
**Decisão**: ✅ **PRIMÁRIA**

---

### Option D: Sofia Multi-Agent (código interno ConnectaIA) — **ESCOLHIDA FALLBACK**

Sistema multi-agent já em produção na ConnectaIA para o CRM. Proprietário nosso.

**Atende MUST**: ✅ parcialmente (é nosso código — totalmente sob controle; MUST-4 atendido já que está em produção)

**Pros**:
- ✅ Zero lock-in — código 100% nosso
- ✅ Já provado em produção na ConnectaIA
- ✅ Integração com LLMRouter já existente
- ✅ Zero curva de aprendizado (time conhece)
- ✅ Controle total sobre evolução

**Cons**:
- ❌ Mantido por time pequeno (nós) — risco de bus factor
- ❌ Reinventamos parte da roda (observabilidade, retry, state management)
- ❌ Não tem ecossistema de tools third-party

**Score SHOULD**: 2+4+1+0+5+2+0 = 14
**Decisão**: ✅ **FALLBACK OFICIAL** — se ADK falhar ou frustrar, temos porto seguro conhecido

---

### Option E: Anthropic Agents SDK
Nativo Claude. Function calling excelente. Bem documentado.

**Bloqueio prático**: Stripe (pagamento Anthropic) com problema no momento + vendor lock-in em Claude.

**Decisão**: ❌ Rejeitada por risco de pagamento + vendor lock

---

### Option F: CrewAI
Python. "Crew of agents" metaphor. Rápido pra prototipar.

**Cons**: controle fino limitado; ecossistema menor; menos adotado em enterprise.

**Decisão**: ❌ Rejeitada — não atende MUST-4 (produção-ready em escala) tão bem quanto B/C

---

### Option G: Custom (framework próprio sobre LLMRouter)
Reinventar tudo.

**Decisão**: ❌ Rejeitada — viola princípio de "não reinventar roda"

---

## 5. Princípios arquiteturais (core proprietário vs plumbing intercambiável)

**Decisão estratégica do projeto**: valor defensável fica no **core clínico brasileiro**, plumbing técnico é intercambiável.

### Core proprietário (NUNCA terceirizar — IP defensável)

| Componente | Por quê é core |
|-----------|----------------|
| Prompts clínicos em pt-BR clinicamente correto | Demanda calibração + consulta médica local; cada refinamento agrega |
| Regras de cruzamento sintoma × vital × medicação × condição | É medicina aplicada BR; sem equivalente comercial |
| Ranges populacionais de idosos brasileiros (SBH/SBD/Beers adaptado) | Nosso research + parceria Tecnosenior/Amparo |
| Motor de interações medicamentosas BR (ANVISA + Beers + polipharmacy geriátrica) | Dados brasileiros; diferencial vs DrugBank (EUA) |
| Biometria de voz treinada com vozes pt-BR + perfil cuidador geriátrico | Asset de ML; melhora com dados reais |
| Dashboard clínico (UX médica em pt-BR) | Nosso design system; aprendizado com uso real |
| Hash-chain + OpenTimestamps (compliance auditoria) | Nossa arquitetura LGPD-compatible |
| Pipeline de classificação urgent/critical com keyword guard | Nossa sensibilidade calibrada — `_escalated_by_keywords` |
| Integrações com parceiros (Tecnosenior/MedMonitor/Amparo) | Relações comerciais + contratuais nossas |
| **Ensemble agêntico** (orquestração multi-agent específica para saúde geriátrica BR) | **Esse é o IP principal do ecossistema** |

### Plumbing intercambiável (pode ser terceiro, preferencialmente open-source)

| Componente | Substituição hipotética |
|-----------|-------------------------|
| Framework agêntico (ADK) | → LangGraph → Sofia adaptada → custom |
| LLM provider (Gemini) | → Claude → GPT → Llama self-hosted (via LLMRouter) |
| STT (Deepgram) | → Whisper local → Azure Speech |
| TTS/Voice agent (Grok via Sofia) | → ElevenLabs → 11Labs Conversational |
| WebRTC (LiveKit via ConnectaLive) | → Daily → Agora |
| Database (PostgreSQL + pgvector) | → Qdrant + PG (se volume exigir) |
| Observabilidade | → Datadog → New Relic → open-source (Loki+Grafana) |

### Regra de ouro

> **Quando um provider de plumbing aumenta preço, descontinua feature, ou muda termos, devemos conseguir migrar em < 4 semanas sem perda de valor clínico.**

Isso é o que justifica a camada `LLMRouter` (já existente), vai justificar um `AgentRouter` futuro, e evita que agente crítico (ex: triagem) dependa hard-coded de feature proprietária de terceiro.

---

## 6. Decision Outcome

### Decisão formal

1. **Adotamos Google ADK (Option C) como framework primário** para arquitetura agêntica do ConnectaIACare.
2. **Sofia Multi-Agent adaptado (Option D) é o fallback oficial** — se ADK falhar em qualquer dimensão crítica (abandono Google, bug bloqueante, latência inaceitável), migramos.
3. **LangGraph (Option B) é fallback secundário** se ambos falharem — opção mais batalhada.
4. **Consagramos o princípio "core clínico proprietário vs plumbing intercambiável"** como diretriz arquitetural do projeto.

### Posicionamento de mercado

ConnectaIACare passa a se posicionar como **"primeiro ecossistema agêntico de cuidado em português clinicamente correto"** — narrativa que diferencia radicalmente de Sensi (reativo, áudio passivo) e Hippocratic (LLM-as-workflow, não agents explícitos).

### Rationale vinculado aos critérios

**Por que C sobre B (LangGraph)**:
- SHOULD-1 (Gemini nativo): crítico dado nosso stack atual
- SHOULD-5 (deployment flexível): ambos atendem, mas ADK tem menos boilerplate
- MUST-5 (auditabilidade): ADK traz OpenTelemetry out-of-the-box; LangSmith é pago
- Risco de jovem (MUST-4 ⚠️) mitigado por: Apache 2.0 + backed Google + fallback D pronto

**Por que C sobre E (Anthropic)**:
- MUST-1 (open-source): E não atende plenamente
- MUST-2 (multi-provider): E viola
- Bloqueio prático: Stripe Anthropic com problema + pagamento travado

---

## 7. Action Items

### Sprint corrente (pré-demo sexta 24/04)
- [x] **[AB-01]** Este RFC pronto e aceito por Alexandre — 2026-04-20
- [ ] **[AB-02]** Atualizar `PITCH_DECK.md` Slide 7 (Diferenciais) mencionando "Arquitetura agêntica por design" (sem citar ADK diretamente pela política de comunicação externa — usar termo genérico "framework agêntico open-source de última geração")
- [ ] **[AB-03]** Criar ADR-015 correspondente quando implementação começar (pós-demo)

### Pós-demo (semanas 1-2)
- [ ] **[AB-04]** Auditar código Sofia Multi-Agent no repo ConnectaIA — validar se realmente serve como fallback antes de contar com ele
- [ ] **[AB-05]** Prototipar "Clinical Agent v1" com Google ADK — transformar `clinical_analysis_service` em agent com 4 tools:
  - `get_vital_signs(patient_id, hours)` — já temos backend
  - `get_medication_interactions(meds)` — stub inicial, ANVISA depois
  - `get_recent_reports(patient_id, limit)` — já temos
  - `get_patient_baseline(patient_id, vital_type)` — novo: baseline individual
- [ ] **[AB-06]** Benchmark A/B: 20 casos teste reais, comparar qualidade agent-based vs pipeline linear. Métricas: classificação correta, cobertura de recomendações, citação de vitais relevantes

### Pós-benchmark (semana 3+)
- [ ] **[AB-07]** Se benchmark positivo (≥ 15% melhoria): promover agent para produção. Pipeline linear vira fallback.
- [ ] **[AB-08]** Se benchmark negativo ou empate: documentar lições + avaliar causas (agentic overhead? prompts mal otimizados para agent? tools insuficientes?)
- [ ] **[AB-09]** Avançar para Nível 2 → Nível 3 (multi-agent) conforme roadmap ADR-xxx futuro

### Ongoing (observabilidade da decisão)
- [ ] **[AB-10]** Monitorar: releases ADK (GitHub), sinais de abandono Google, issues críticos, mudanças de licença. Revisar esta decisão a cada 3 meses.
- [ ] **[AB-11]** Documentar toda tool custom que criarmos no formato standard do ADK — se migrarmos pra outro framework, reescrita é localizada.

---

## 8. Relevant Data

- **Benchmarks públicos (2024-2025)**: agents com tool-use superam single-shot em tarefas de raciocínio complexo por **10-30%** (MMLU, HumanEval+, GAIA benchmark)
- **Latência esperada**: single-shot ~15-20s (medido), agent ~30-60s (estimado 2-3×) — aceitável para WhatsApp
- **Custo esperado**: agent faz 2-4× mais chamadas LLM em média, custo bruto sobe. Mas Gemini Flash tier gratuito cobre até 1500 RPD — **zero custo até escalar significativamente**
- **Exemplos de produção ADK**: Google publicou 3-5 casos internos; comunidade externa crescendo
- **Estado LangGraph**: 60k+ stars GitHub, 2+ anos, centenas de casos production

---

## 9. Estimated Cost

### Implementação (horas de dev — estimativa MVP de agent)
| Fase | Esforço | Prazo |
|------|---------|-------|
| Prototipar Clinical Agent v1 com ADK (4 tools) | 40-60h | 2 semanas |
| Benchmark A/B vs pipeline linear | 8-16h | 3 dias |
| Integração com pipeline atual (feature flag) | 16-24h | 3 dias |
| Documentação + migration guide | 8h | 1 dia |
| **Total MVP agent** | **~80-120h** | **~3 semanas** |

### Operacional (incremento vs hoje)
- LLM calls: +2-4× (mitigado por Gemini Flash free tier por ora)
- Latência p95: +50-100%
- Observabilidade: 0 (OpenTelemetry open-source)
- Framework: 0 (ADK open-source)

---

## 10. Resources

- [Google ADK GitHub](https://github.com/google/adk) (link hipotético — validar URL real na implementação)
- [ADR-012](../adr/012-telemed-hibrido-livekit-fork-aplicacao.md) — padrão de "reuso infraestrutura + fork lógica de produto" que se aplica aqui também
- [ADR-011](../adr/011-locale-aware-architecture-para-latam-europa.md) — agents devem ser instanciáveis por locale
- [ADR-014](../adr/014-integracao-medmonitor-sinais-vitais.md) — vitals viram tools consumíveis por agentes
- `backend/src/services/llm.py` — `LLMRouter` atual (modelo para futuro `AgentRouter`)
- [CLAUDE for Healthcare announcement (jan/2026)](https://anthropic.com/healthcare) — contexto de mercado

---

**RFC aceito por Alexandre em 2026-04-20. ADR-015 correspondente será criado quando implementação iniciar (pós-demo sexta).**
