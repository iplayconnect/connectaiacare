# Consolidação Panel LLM — Análise comparativa Gemini × GPT × Grok

**Data**: 2026-04-28
**Estudo de origem**: `docs/estudo_classificacao_inputs_cuidadores.md`
**Respostas brutas**: `docs/panel_llm_respostas.md`

---

## 1. Resumo executivo (TL;DR)

| Aspecto | Vencedor | Por quê |
|---------|----------|---------|
| Resposta estruturada Q1-Q12 | **Gemini** | Único que seguiu o formato; deu pra comparar item a item |
| Visão arquitetural | **GPT** | Pipeline de 7 camadas + multimodalidade + eventos compostos |
| Profundidade prática real | **Grok** | Fase 2 cobriu persona + fallback + tenant/plantão + celular compartilhado/pessoal — insights que viram código |
| Prompt zero-shot funcional | **Gemini** > Grok > GPT | Gemini com few-shot completo PT-BR; Grok com estrutura JSON; GPT não escreveu |
| Furos concretos no plano | **Gemini** | Apontou 3 reais (temporal, multi-paciente, alucinação de unidades). GPT e Grok deixaram passar |
| Case real de mercado | **Gemini** | Único que citou (Sensi.ai) |

**Veredito**: nenhum dos 3 sozinho — **a soma é o produto certo**.

---

## 2. Convergências (3 concordam)

Tudo abaixo é **decisão consensual**, pode implementar sem mais
debate:

1. **Reduzir taxonomia top-level** — Gemini sugere "12 backend / 6
   UI", GPT sugere "25-30 eventos", Grok sugere "8 classes".
   Direção comum: enxugar antes de implementar.

2. **Híbrido determinístico + LLM** — todos batem que regex
   fast-path para emergência é mandatório. LLM só quando ambíguo.
   GPT chega a falar "70% resolve sem IA pesada".

3. **Schema híbrido (hub + tabelas tipadas)** — todos os 3
   concordam com a proposta original do estudo.

4. **Confirmação seletiva, não universal** — Gemini ("híbrida —
   ativa só em crítico ou confidence<0.7"), Grok ("fallback quando
   confidence<75%"), GPT (não falou explicitamente, mas o pipeline
   dele depende disso).

5. **Multi-label, não single-label** — todos concordam que
   mensagem real é multi-tópico.

6. **Baseline por paciente é fundamental** — todos citam contexto
   individual. **Já temos** via `aia_health_patient_baselines`
   (migration 041).

---

## 3. Divergências reais (precisam decisão)

### 3.1 Quantas classes top-level?

| LLM | Sugestão | Justificativa |
|-----|----------|---------------|
| Gemini | 12 backend / 6 UI | Granularidade no banco, simplicidade na UI |
| GPT | 25-30 eventos | Lista mais flat, sem hierarquia |
| Grok | 8 (com fusões explícitas) | Custo/risco menor, escala melhor |

**Recomendação**: ficar com **8 classes do Grok** (mais defensível
operacionalmente). Mantém Aferições / Eventos Agudos / Medicação /
Alimentação / Eliminações / Comportamental / Cuidados Físicos /
Operacional. Emergência como flag transversal.

> Nossa taxonomia original tinha redundância identificada pelos 3:
> Pele(7) + Higiene(8) → "Cuidados Físicos"; Estoque(9) +
> Solicitações(10) + Equipe(11) + Eventos sociais(12) →
> "Operacional".

### 3.2 Pipeline: 4 etapas (Grok) ou 7 camadas (GPT)?

**Grok (4 etapas)** é mais aderente ao que temos hoje. **GPT (7
camadas)** acrescenta `normalização` e `enriquecimento contextual`
explicitos — bom mas pode esperar fase 2.

**Recomendação**: começar com Grok (4) + adicionar campo
`explanation` no output (sugestão do GPT). Camada de normalização
do GPT vira útil quando integrarmos sensor/câmera.

### 3.3 Multi-tópico em 1 áudio: split ou multi-label?

| LLM | Posição |
|-----|---------|
| Gemini | Opção B — split em N care_events com `parent_id` |
| GPT | Implícito — multi-label no event |
| Grok | Não tocou diretamente |

**Recomendação**: começar com **multi-label** (mais simples). Se
analytics precisar separar, adicionar `parent_event_id` depois.

---

## 4. Insights únicos que devem entrar no projeto

### 4.1 Do Gemini (3 furos críticos)

1. **Ambiguidade temporal** — "agora há pouco" pode ser 10min ou
   4h. Capturar `sent_at` do WhatsApp + LLM extrair referência
   relativa pro gráfico de tendências.
2. **Múltiplos pacientes em 1 áudio** — "A Dona Maria tomou o
   remédio mas o Seu José tá agitado". Precisa **NER por
   patient_id antes da classificação**.
3. **Alucinação de unidades** — "PA 12 por 8" → 120/80; "está com
   38" → febre, não idade. Precisa **post-processor determinístico
   Python** validando range biológico antes de salvar.

### 4.2 Do GPT (3 estruturais)

1. **Multimodalidade desde o pipeline** — normalização aceita
   sensor/câmera/log/áudio. Vale ter o contrato pronto pra futuro.
2. **Eventos compostos** — "baixa alimentação + apatia → risco
   maior". Multi-label conjugado, regra que combina signals.
3. **Campo `explanation` no output** — Sofia explicaria o porquê
   da classificação. Vira valor pro auditor clínico.

### 4.3 Do Grok (4 práticos — os mais valiosos)

1. **Fallback híbrido humano+usuário** — pergunta opção fechada
   primeiro pro usuário (8s timeout), escalate pro cuidador se
   falhar. Texto da pergunta crítico: "É dor no peito? Sim ou
   não" (não "foi isso que você quis dizer?").

2. **3 personas com prompts distintos** — Paciente / Cuidador /
   Familiar. Travado na conversa após identificação.

3. **Biometria + plantão = pool reduzido** — em vez de 1:N contra
   todos os cuidadores do tenant, restringir ao pool do plantão
   atual (3-4 vozes). Acerto sobe muito. Bonus: troca de plantão
   resolvida via fallback de pergunta.

4. **Celular compartilhado vs pessoal** — campo novo `phone_type`
   por número. Compartilhado desativa biometria e força "com quem
   falo + sobre qual paciente". Pessoal usa biometria normal.

---

## 5. Implicações na arquitetura ATUAL (o que precisa mudar)

### 5.1 Schema (migrations novas)

```sql
-- A. phone_type por número de WhatsApp (Insight 4.3.4)
ALTER TABLE aia_health_caregivers
    ADD COLUMN phone_type TEXT
    CHECK (phone_type IN ('personal','shared','unknown'))
    DEFAULT 'unknown';

CREATE TABLE aia_health_shift_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    caregiver_id UUID REFERENCES aia_health_caregivers(id),
    shift_name TEXT NOT NULL,           -- 'morning'/'afternoon'/'night'
    starts_at TIME NOT NULL,
    ends_at TIME NOT NULL,
    weekdays INT[] NOT NULL,            -- [1..7] dias da semana
    active BOOLEAN NOT NULL DEFAULT TRUE
);

-- B. Override temporário de plantão (cobrindo colega)
CREATE TABLE aia_health_shift_overrides (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    caregiver_id UUID REFERENCES aia_health_caregivers(id),
    shift_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- C. Tabelas tipadas por classe (Insight do estudo + 8 classes do Grok)
-- (a criar: aia_health_eliminations, aia_health_inventory_consumption,
--  aia_health_service_requests, aia_health_behavior_logs, etc.)
```

### 5.2 Service de classificação

`backend/src/services/input_classifier_service.py` (novo) — pipeline
em 4 etapas:

```python
def classify_input(transcription: str, tenant_id: str,
                   patient_id: str | None = None) -> dict:
    # Etapa 1: regex fast-path emergency
    # Etapa 2: LLM zero-shot multi-label (8 classes)
    # Etapa 3: extração estruturada por classe (paralelo se >1 label)
    # Etapa 4: post-processor determinístico (validação de unidades)
    return {
        "classes": [...],
        "severity": ...,
        "extracted": {...},
        "explanation": "...",       # do GPT
        "confidence": ...,
        "needs_clarification": ...,
    }
```

### 5.3 Voice biometrics — encaixe com plantão (Insight 4.3.3)

Já temos o serviço; falta:

1. Reduzir pool de busca de `tenant_id` para `tenant_id +
   active_shift_caregivers` quando áudio chega.
2. Detectar `phone_type='shared'` e desativar biometria para esses
   números (ou forçar pergunta).
3. Implementar fallback "você é X, Y ou Z?" quando biometria não
   bate dentro do plantão.

### 5.4 Persona detection + prompt switching (Insight 4.3.2)

`sofia-service/src/persona_resolver.py` (novo) — entrada áudio,
saída `{persona: paciente|cuidador|familiar, confidence, source:
biometria|pergunta_explicita}`. Sofia carrega prompt diferente
por persona, persona trava por sessão.

### 5.5 NER + post-processor (Insights 4.1.2 e 4.1.3)

Antes da classificação top-level:
1. **NER de nome de paciente** — busca `aia_health_patients` por
   nome citado. Se >1 nome → split em care_events distintos.
2. **Pós-processor de unidades** — após LLM extrair `pa_sistolica:
   12`, valida range. Se fora de [40, 250] mmHg → flag erro,
   não salva.

---

## 6. Roadmap consolidado (proposta)

### Fase 0 — Decisões de produto (essa semana)
- [ ] Você confirma: 8 classes top-level (Grok) ou manter 12?
- [ ] Lista de gírias regionais por tenant — quem cura?
- [ ] Cadastro de plantões + phone_type — UI manual ou import?

### Fase 1 — Foundations (~1 semana)
- [ ] Migration: phone_type + shift_schedules + shift_overrides
- [ ] Migration: tabelas tipadas por classe (8 classes)
- [ ] `input_classifier_service.py` esqueleto + regex fast-path
- [ ] Prompt zero-shot v1 (combinação Gemini + Grok)
- [ ] Post-processor determinístico de unidades

### Fase 2 — Persona + biometria (~1 semana)
- [ ] `persona_resolver.py` com biometria + plantão + fallback
- [ ] 3 system prompts distintos (paciente / cuidador / familiar)
- [ ] Frontend admin: cadastrar plantões + phone_type
- [ ] Lógica "shared phone" desativa biometria

### Fase 3 — Fallback híbrido (~3 dias)
- [ ] Confidence threshold + flow de pergunta-confirmação
- [ ] Texto exato das perguntas por cenário
- [ ] Escalation pra cuidador com contexto rico

### Fase 4 — NER + multi-paciente (~3 dias)
- [ ] NER de nomes de paciente em uma mensagem
- [ ] Split em N care_events com `parent_event_id`

### Fase 5 — Validação real (~2 semanas)
- [ ] Coletar 100 áudios reais do lar carente que você visita
  hoje
- [ ] Rotular manualmente (você + Henrique, ou só o Alexandre)
- [ ] Medir taxa de acerto, latência, custo
- [ ] Iterar prompt + thresholds

**Total**: ~5 semanas pra ter algo robusto rodando em 1 ILPI piloto.

---

## 7. O que NÃO vai entrar (deixar pra depois)

- **Paralinguagem (tom de voz emocional)** — todos os 3 LLMs
  recomendaram esperar. Custo-latência não justifica ganho marginal.
- **NER multimodal (sensor + câmera)** — GPT defendeu, mas hoje só
  temos WhatsApp. Volta quando integrarmos câmera de queda.
- **Eventos compostos automatizados** — começar com classes simples
  + multi-label. Composição vira regra explícita por evento depois.
- **Glossário regional por região (NE, Sul)** — começar com PT-BR
  geral + few-shot. Regional vira parametrização por tenant
  conforme erros aparecem.

---

## 8. Decisões pendentes pra você

Antes de eu começar a implementação Fase 1, preciso de 3 OK:

1. **Taxonomia: 8 classes do Grok ou manter 12?**
   - Recomendo 8.

2. **Biometria com plantão: implementar agora ou só após panel
   completo?**
   - Recomendo agora — encaixa direto no que já fizemos
   (`aia_health_voice_embeddings`) e resolve cenário real do lar
   que você vai visitar.

3. **Coleta de áudios reais hoje no lar carente:**
   - Vale gravar 5-10 áudios reais (com consentimento) pra termos
   amostra inicial pra validar prompt v1?
