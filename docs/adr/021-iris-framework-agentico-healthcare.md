# ADR-021: Íris — Framework agêntico próprio, workflow-first, healthcare-specific

- **Date**: 2026-04-21
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA), com input do Murilo (Tecnosenior) sobre visão estratégica
- **Tags**: architecture, agents, orchestration, framework, healthcare
- **Relates to**: [RFC-001](../rfc/001-estrategia-ecossistema-agentico.md) (estratégia agêntica), [ADR-018](018-care-events-com-ciclo-de-vida.md) (care events)

## Context and Problem Statement

O ConnectaIACare começou como MVP focado em **relato geriátrico via WhatsApp**. O pipeline atual (`src/handlers/pipeline.py`, ~680 linhas) resolve esse caso específico bem: transcrição → identificação de paciente → análise clínica → escalação hierárquica → timeline temporal.

Mas a **visão estratégica** articulada pelo Murilo (2026-04-20) e ratificada pelo Alexandre expande isso drasticamente:

> *"A vertical da saúde tende a crescer muito rápido — parcerias sendo costuradas. Foco em geriatria, clínicas, hospitais, medicina do trabalho. A plataforma vai ganhar VOIP próprio, telemedicina, prescrição eletrônica, assinaturas, várias integrações."*

Se vamos ter:

- 🩺 **Geriatria** — protocolo atual (MVP) com escalação familiar
- 🏥 **Clínicas/hospitais** — fluxos de consulta agendada + prescrição + retorno
- 🏭 **Medicina do trabalho** — triagem NR-7, ASO, atestados, PPRA
- 📞 **Telemedicina** — pré-consulta + consulta + prescrição + follow-up
- 💊 **Prescrição segura** — interação medicamentosa + alergias + posologia
- 💰 **Assinaturas** — billing + uso + upgrade
- 📡 **Integrações múltiplas** — TotalCare (já), futuras: Vidaas, PrescribeRx, ANS APIs

…o pipeline.py monolítico **não escala**. Cada novo vertical seria +500 linhas de lógica enredada ao código geriátrico. Sem isolamento, sem testes evolutivos, sem policy-per-tenant, sem audit trail estrutural.

Precisamos decidir **qual framework de orquestração agêntica adotar** (ou construir) para suportar esse crescimento com:

- **Isolamento entre workflows** (um evento geriátrico não toca código de telemedicina)
- **Reuso de agentes** (o mesmo `contact_agent` serve geriatria e telemed)
- **Scheduler temporal nativo** (SLAs em minutos, não request-response)
- **Audit trail imutável** (compliance CFM + LGPD Art. 11)
- **Evals em CI** (regressão clínica detectada automaticamente)
- **Claude-first** (nosso stack é Anthropic; Gemini é provider secundário)

## Decision Drivers

- **Independência arquitetural**: ConnectaIACare vai pra VPS dedicada (decisão de 2026-04-21). Framework não pode depender de runtime compartilhado com BBMD.
- **Crescimento rápido**: dos atuais 45 pacientes (Tecnosenior) pra 500+ em 3-6 meses conforme parcerias. Orquestrador precisa suportar 100x sem refactor.
- **Verticais radicalmente diferentes**: protocolo geriátrico (observacional + escalação familiar) é oposto de protocolo hospitalar (consulta agendada + prescrição).
- **Compliance escopada**: auditoria CFM precisa olhar apenas nosso código, não acoplamento com outros produtos.
- **Manutenção por time futuro**: dev que entrar depois precisa aprender 1 framework simples, não 3 (LangChain + ADK + interno).
- **Observabilidade**: cada transição de estado, chamada LLM, invocação de tool precisa ser rastreável individualmente.
- **Evals como cidadão de primeira classe**: testes de regressão clínica precisam rodar em CI toda PR.

## Considered Options

- **Option A**: Continuar com `pipeline.py` e adicionar novos verticais nele
- **Option B**: Adotar Google ADK (framework proprietário Google)
- **Option C**: Adotar LangGraph (LangChain) como orquestrador
- **Option D**: Reutilizar Sofia Orchestrator (produto ConnectaIA Comercial) como multi-tenant
- **Option E**: Construir framework próprio enxuto, Claude-first, healthcare-specific — **"Íris"** (escolhida)

## Decision Outcome

Chosen option: **Option E — Íris, framework agêntico próprio**.

### Nome

**Íris** — mensageira entre os deuses e os humanos na mitologia grega. Metáfora clínica:

- Orquestra a comunicação entre cuidador → paciente → enfermagem → médico → família
- Curto (4 letras), fácil de falar, paralelismo com "Sofia" sem colidir com o produto comercial
- Feminino acolhedor (tom adequado a cuidado geriátrico/clínico)
- Forte pra logotipo: "Íris, a orquestradora clínica do ConnectaIACare"

### Princípios de design

1. **Workflow-first, não chat-first** — cada caso de uso é uma máquina de estados finita (Finite State Machine), não uma "conversa livre". Geriatria=workflow A, Telemed=workflow B, Prescrição=workflow C.

2. **Agentes são funções Python tipadas** — Pydantic in, Pydantic out. Testáveis isoladamente. Troca de modelo trivial. Sem herança de classes gigantes.

3. **Tools são registradas centralmente** — registry único, namespaces por domínio (`clinical.*`, `contact.*`, `documentation.*`). Agentes declaram o que podem usar.

4. **Scheduler é primeiro-classe** — transições temporais (t+5min, t+10min) são declaradas no workflow, não montadas à mão com cron.

5. **Audit trail embutido** — toda transição de estado + toda chamada LLM + todo output → `aia_health_audit_chain` (hash-chain imutável que já temos, ADR-008).

6. **Policy por tenant via YAML** — workflows ativos, timings, LLMs, feature flags configuráveis sem deploy.

7. **Claude-first, multi-provider via interface** — modelo default Claude Sonnet/Opus, fallback Gemini/OpenAI via abstração. Sem lock-in vendor.

8. **Evals em CI** — cada agente tem fixtures YAML + asserts + regressão automática em GitHub Actions.

### Arquitetura

```
backend/src/iris/                    ← framework (~1000 linhas Python)
├── core.py                          # Workflow, State, Agent, Tool, Runtime
├── workflow.py                      # @workflow decorator + state transitions
├── agent.py                         # @agent decorator + Pydantic I/O
├── tool_registry.py                 # registry central
├── scheduler.py                     # integração com checkin_scheduler
├── audit.py                         # hash-chain + structured logging
├── policy.py                        # carrega tenant_config YAML
├── llm.py                           # multi-provider abstraction
└── evals.py                         # fixtures + asserts + regression

backend/src/workflows/               ← casos de uso (1 arquivo por vertical)
├── geriatric_incident.py            # MVP atual → refatorado pra Íris
├── telemedicine_consultation.py     # futuro Q2
├── prescription_safety.py           # futuro Q2
├── occupational_triage.py           # futuro Q3
└── clinical_followup.py             # futuro

backend/src/agents/                  ← agentes reutilizáveis por domínio
├── clinical/
│   ├── triage.py                    # classificação clínica (usado em múltiplos workflows)
│   ├── pattern_detector.py          # detecção de padrões históricos (já temos)
│   ├── drug_safety.py               # interações + alergias + posologia
│   └── summary_writer.py            # resumo clínico (usado em prescrição, followup, etc)
├── contact/
│   ├── whatsapp_sender.py           # adapta mensagem ao papel (cuidador/médico/família)
│   ├── voice_caller.py              # Sofia Voice para ligações
│   └── ack_watcher.py               # detecta resposta/leitura
└── documentation/
    ├── fhir_generator.py            # gera recurso FHIR R4
    ├── prescription_writer.py       # gera receita SNGPC-compatible
    └── audit_logger.py              # hash-chain append

backend/tools/                       ← operações concretas
├── clinical/
│   ├── check_vitals.py              # consulta MedMonitor
│   ├── check_medications.py         # consulta base de medicamentos
│   └── fetch_history.py             # últimos N relatos
└── external/
    ├── medmonitor_api.py            # TotalCare (existing)
    ├── prescribe_rx.py              # futuro
    └── vidaas_sign.py               # assinatura digital médica
```

### Anatomia de um Workflow (exemplo: geriatric_incident)

```python
# backend/src/workflows/geriatric_incident.py
from iris import workflow, state, transition, agent
from iris.agents.clinical import triage_agent, pattern_detector
from iris.agents.contact import whatsapp_sender, voice_caller

@workflow(
    name="geriatric_incident",
    version="1.0",
    verticals=["geriatric"],   # aparece só em tenants geriátricos
)
class GeriatricIncident:
    """Protocolo de incidente clínico em idoso via relato de cuidador."""

    initial_state = "analyzing"

    # Estados declarados
    states = [
        state("analyzing"),
        state("awaiting_ack", on_enter="send_analysis_summary"),
        state("escalating", on_enter="dispatch_institutional"),
        state("pattern_analyzed"),
        state("awaiting_status_update", on_enter="send_status_check_in"),
        state("resolved", terminal=True),
        state("expired", terminal=True),
    ]

    # Transições
    @transition("analyzing -> awaiting_ack")
    async def on_analysis_complete(self, ctx):
        result = await triage_agent.run(
            transcript=ctx.transcription,
            patient=ctx.patient,
            history=ctx.history,
        )
        ctx.classification = result.classification
        ctx.summary = result.summary

    @transition("awaiting_ack -> escalating", when="classification in {urgent, critical}")
    async def on_escalation_needed(self, ctx):
        # Scheduler dispara paralelo imediato + cascata família
        ...

    # Agendamento temporal
    @scheduled(after_minutes=5, kind="pattern_analysis")
    async def pattern_check(self, ctx):
        result = await pattern_detector.run(
            patient_id=ctx.patient.id,
            current_transcript=ctx.transcription,
        )
        if result.has_pattern and result.suggested_classification:
            # Re-classifica e re-escala se padrão histórico exige
            await self.transition_to("escalating", reason=result.headline)

    @scheduled(after_minutes=10, kind="status_update")
    async def status_ping(self, ctx):
        await whatsapp_sender.run(
            to=ctx.caregiver_phone,
            template="status_check_in",
            patient_name=ctx.patient.nickname,
        )

    @scheduled(after_minutes=30, kind="closure_check")
    async def maybe_close(self, ctx):
        if ctx.last_activity_at > 15*60:
            await self.transition_to("expired")
```

### Anatomia de um Agent (exemplo: triage)

```python
# backend/src/agents/clinical/triage.py
from pydantic import BaseModel, Field
from iris import agent
from iris.tools import clinical

class TriageInput(BaseModel):
    transcript: str
    patient: dict  # schema de paciente
    history: list[dict]
    vitals_last_24h: str | None = None

class TriageOutput(BaseModel):
    classification: Literal["routine", "attention", "urgent", "critical"]
    summary: str
    reasoning: str
    symptoms_new: list[dict]
    alerts: list[dict]
    vital_signs_concerning: list[dict] = Field(default_factory=list)
    needs_medical_attention: bool
    tags: list[str] = Field(default_factory=list)

@agent(
    name="triage",
    model="claude-sonnet-4",            # default
    fallback_models=["gemini-2.5-flash"],
    tools=[clinical.fetch_vitals, clinical.check_medications],
    sla_seconds=8,
    max_tokens=4096,
    temperature=0.1,
)
async def triage_agent(input: TriageInput) -> TriageOutput:
    """Classifica evento clínico. Ver prompt_clinical_analysis.md."""
    # Implementação: Íris runtime resolve model + tool calls + validation + retries
    ...
```

### Anatomia de uma Tool

```python
# backend/tools/clinical/fetch_vitals.py
from iris import tool

@tool(
    name="clinical.fetch_vitals",
    description="Retorna sinais vitais do paciente nas últimas N horas",
    rate_limit_per_minute=60,
    requires_permission="clinical.read",
)
async def fetch_vitals(patient_id: str, hours: int = 24) -> str:
    """Consulta MedMonitor ou cache local. Retorna texto formatado pro prompt."""
    ...
```

### Policy por tenant (YAML)

```yaml
# tenants/connectaiacare_tecnosenior.yaml
tenant_id: connectaiacare_tecnosenior
name: Tecnosenior
verticals: [geriatric]   # só workflows desse vertical

workflows:
  geriatric_incident:
    enabled: true
    version: "1.0"
    timings:
      critical:
        pattern_analysis_after_min: 3
        check_in_after_min: 5
        closure_decision_after_min: 45
      urgent:
        pattern_analysis_after_min: 3
        check_in_after_min: 8
        closure_decision_after_min: 45

agents:
  triage:
    model: claude-opus-4       # premium pra saúde
    fallback_on_timeout: escalate_human
  pattern_detector:
    model: claude-sonnet-4
  whatsapp_sender:
    model: claude-haiku-4      # suficiente pra formatar mensagem
  voice_caller:
    provider: sofia_voice_ultravox

escalation_policy:
  critical: [central, nurse, doctor, family_1, family_2, family_3]
  urgent:   [central, nurse, family_1]
  attention:[central]
  routine:  []

features:
  pattern_detection: true
  proactive_checkin: true
  sofia_voice_calls: true
  medmonitor_integration: true

compliance:
  regulated_industry: health
  data_retention_years: 20
  audit_trail: hash_chain
  phi_encryption: true
  cfm_compliant: true
```

### Positive Consequences

- **Domínio clínico explícito no código** — workflows modelam protocolos reais, não abstrações genéricas
- **Adicionar vertical = 1 arquivo** em `workflows/` + talvez 2-3 agentes novos. Sem refactor do core.
- **Agentes são unidades testáveis** — fixtures YAML + `pytest` + asserts sobre output Pydantic. Regressão clínica é detectável.
- **Troca de modelo por agente** — decisão de custo/qualidade granular. `triage_agent` pode usar Opus em tenant premium, Sonnet em tenant economy.
- **Audit trail embutido** — compliance CFM + LGPD Art. 11 como cidadão de primeira classe, não afterthought.
- **Claude-first reduz atrito** — nosso time já domina Claude, docs Anthropic são referência, MCP nativo.
- **Zero lock-in** — Python puro, Pydantic, sem framework pesado. Mudar pra LangGraph no futuro é refatorar, não migrar ecossistema.
- **Controle sobre performance** — async nativo, sem overhead de abstrações genéricas de LangChain.
- **Evolução independente** — ConnectaIACare pode iterar diário, ConnectaIA SaaS mantém release semanal estável. Zero acoplamento.
- **Nome forte** — "Íris" vira marca da orquestradora clínica. Diferenciada de "Sofia" comercial.

### Negative Consequences

- **Construir framework tem custo** — ~1000 linhas iniciais + testes + docs. Tempo estimado: 2-4 semanas de esforço focado.
- **Não tem community** — bugs que a gente descobre primeiro. Mitigação: base simples e bem testada, evita superfície grande.
- **Menos "baterias incluídas"** — nem todos os helpers/integrações existem em framework próprio que existem em LangGraph. Mitigação: adicionar conforme necessidade.
- **Time de 1 pessoa** — se Alexandre sair, ninguém conhece o framework. Mitigação: docs + ADRs + testes extensivos. Framework simples (800-1000 linhas) é aprendível em 1-2 dias por dev sênior.
- **Risco de reinventar mal** — tentação de resolver problemas que frameworks existentes já resolveram. Mitigação: estudar LangGraph + ADK como referência antes de implementar cada módulo.

## Pros and Cons of the Options

### Option A — Continuar com `pipeline.py` monolítico ❌

- ✅ Zero retrabalho imediato
- ❌ Cada vertical novo = +500 linhas no mesmo arquivo → dívida técnica crescente
- ❌ Testes isolados impossíveis
- ❌ Policy hardcoded
- ❌ Não modela workflows reais

### Option B — Google ADK ❌

- ✅ ParallelAgent/SequentialAgent elegantes
- ❌ Gemini-first — debugging, docs, ecossistema assumem Gemini
- ❌ Framework novo, breaking changes frequentes
- ❌ Lock-in em Google Cloud pra otimizações
- ❌ Claude via LiteLLM funciona mas é segundo-cidadão

### Option C — LangGraph ❌

- ✅ State machine nativa, popular em healthcare
- ✅ Multi-provider maduro
- ❌ Dependência pesada (LangChain ecosystem)
- ❌ Abstrações genéricas — não entende "evento de cuidado"
- ❌ Audit trail, compliance, scheduler temporal são add-ons
- ❌ Debugging complexo em erros (stack trace passa por 5 camadas)

### Option D — Sofia Orchestrator multi-tenant ❌

- ✅ Reusa código já em produção
- ❌ **Contradiz decisão de independência** (VPS dedicada, compliance escopada)
- ❌ Sofia é classify→dispatch→synthesize (request-response), não state machine temporal
- ❌ Acopla release cadence: BBMD semanal vs ConnectaIACare diário
- ❌ Auditoria CFM cobriria código comercial também
- ❌ Escala horizontal conflita (SDR batch vs paciente crítico)

### Option E — Íris (framework próprio) ✅ Chosen

- ✅ Design específico pra healthcare clinical workflows
- ✅ Zero dependência framework
- ✅ Claude-first alinhado com stack
- ✅ Audit trail + compliance nativos
- ✅ Adicionar vertical = 1 arquivo
- ✅ Evals em CI como primeira classe
- ❌ Custo de construir (~2-4 semanas)
- ❌ Sem community (compensado por simplicidade)

## Implementation — Roadmap gradual

**Princípio: nunca quebrar o MVP atual durante a construção.** Íris nasce ao lado do `pipeline.py`, e a migração é gradual workflow-por-workflow.

### Fase 1 · Fundação (1 semana) — Q2 2026

- [ ] Criar `src/iris/` com core (Workflow, State, Agent, Tool, Runtime)
- [ ] Implementar `@workflow` e `@agent` decorators com validação Pydantic
- [ ] Tool registry com namespacing
- [ ] Integração com `checkin_scheduler` existente (ADR-018)
- [ ] Audit hook conectado ao hash-chain (ADR-008)
- [ ] Policy loader de YAML (tenant_config)
- [ ] LLM abstraction (Claude + Gemini + OpenAI)
- [ ] Testes unitários básicos + fixtures YAML
- [ ] Documentação interna (`docs/iris/README.md`)

### Fase 2 · Migrar geriatric_incident (1 semana) — Q2 2026

- [ ] Refatorar lógica atual do `pipeline.py` em `workflows/geriatric_incident.py` usando Íris
- [ ] Extrair agentes: `triage`, `pattern_detector`, `whatsapp_sender`, `voice_caller`, `followup_responder`
- [ ] Deploy paralelo: flag `USE_IRIS=false` mantém pipeline legado; `USE_IRIS=true` usa Íris
- [ ] Rodar em sombra por 48h (logs comparativos)
- [ ] Cutover: `USE_IRIS=true` default; legado deprecated
- [ ] Remover `pipeline.py` legado após 1 semana sem regressão

### Fase 3 · Evals em CI (1 semana) — Q2/Q3 2026

- [ ] Suite de fixtures clínicas YAML (30-50 casos cobrindo critical/urgent/attention/routine + edge cases de polimedicação, desidratação, dispneia etc)
- [ ] Asserts sobre classificação, raciocínio, escalação
- [ ] GitHub Actions rodando em toda PR
- [ ] Regressão clínica documentada + changelog quando muda

### Fase 4 · Novos workflows (progressivo) — Q2-Q4 2026

Conforme parcerias:

- [ ] `telemedicine_consultation.py` — consulta agendada + prescrição
- [ ] `prescription_safety.py` — validação de interação + alergia + posologia
- [ ] `clinical_followup.py` — acompanhamento pós-consulta
- [ ] `occupational_triage.py` — medicina do trabalho

Cada workflow:
- 1 arquivo + reutiliza agentes existentes
- YAML de tenant específico
- Evals em CI antes do deploy

### Fase 5 · Dashboard evolui (pós MVP, gradual)

- [ ] Filtros por workflow ativo no tenant
- [ ] Timeline estruturada com agentes invocados (não só mensagens)
- [ ] Dashboard de evals (qualidade clínica por vertical)
- [ ] Admin UI pra editar tenant YAML (hoje é SQL direto)

## When to Revisit

- **Se Íris ficar >3000 linhas** → sinal de que estamos reinventando LangGraph. Avaliar migração.
- **Se time crescer >3 devs** → considerar adotar framework maduro pra reduzir custo de onboarding.
- **Se precisarmos de GraphQL federation / complex streaming** → LangGraph ou Modal provavelmente cobrem melhor.
- **Se regulação de IA no Brasil (PL 2.338/2023) exigir características específicas** → revalidar se Íris cumpre ou se precisa adotar framework com certificação formal.
- **Se clientes enterprise exigirem integração com orquestrador deles** (improvável em geriatria, possível em hospitalar) → avaliar exposição de Íris como API pra chamar externamente.

## Links

- [pipeline.py atual](../../backend/src/handlers/pipeline.py) — a ser refatorado
- [ADR-018 Care Events](018-care-events-com-ciclo-de-vida.md) — modelo de dados que Íris orquestra
- [ADR-008 Hash-chain OpenTimestamps](008-hash-chain-opentimestamps-em-vez-de-blockchain.md) — audit trail que Íris usa
- [ADR-019 Integração MedMonitor](019-integracao-medmonitor-totalcare.md) — fonte das tools clínicas
- [ADR-020 Escalação hierárquica](020-escalacao-hierarquica-evolution-sofia.md) — exemplo de workflow temporal
- [RFC-001 Estratégia agêntica](../rfc/001-estrategia-ecossistema-agentico.md) — contexto estratégico
- [Google ADK](https://google.github.io/adk-docs/) — referência de design
- [LangGraph](https://langchain-ai.github.io/langgraph/) — referência de state machine
- [MADR template](https://adr.github.io/madr/)
