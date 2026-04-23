# ADR-025 — LLM Routing por Tarefa e Criticidade Clínica

**Status**: Aceito (implementado 23/04/2026)  
**Decisores**: Alexandre (CEO), Claude Code (engenharia)

---

## Contexto

Durante a implementação do módulo de medicação (Blocos 1-5, 22-23/04), observamos que o backend da Care usava um **único LLM para tudo** (default: Gemini 2.5 Flash configurado via `LLM_PROVIDER=gemini`). Isso criou 3 problemas:

1. **Gemini Vision falhava ao identificar caixas de medicamento** — JSON truncado por `max_tokens` e parsing errático. Corrigimos, mas foi indicador de que o modelo não é ideal pra todas tarefas.
2. **Alexandre (CEO) não sabia que o sistema estava em Gemini** — ele contratou "Claude" e ficou sabendo só quando perguntou. Falta de transparência inaceitável em contexto clínico.
3. **Qualidade clínica variável** — o SOAP writer e o prescription validator, tarefas de **alta criticidade clínica**, rodavam em Gemini Flash (modelo genérico). Claude Sonnet tem benchmarks superiores em raciocínio clínico (MedQA, USMLE) e precisava ser o modelo default nessas tarefas.

Por outro lado, usar Claude Sonnet 4 em TUDO era caro demais:

- Claude Sonnet 4: $3/1M input, $15/1M output
- Gemini 2.5 Flash: $0.30/$2.50  
- **~10x mais caro**

Pra MVP com margem apertada (Essencial R$49,90), calibrar por tarefa importa.

---

## Decisão

**Implementar um LLM Router que escolhe modelo por tarefa, baseado em criticidade clínica, volume esperado, necessidade de vision, e custo.**

Arquitetura:

```
src/services/llm_router.py
├── Lê config/llm_routing.yaml
├── Por task: primary + fallbacks[] + params
├── Tenta primary → se falha, cai em fallbacks em ordem
├── Suporta 4 providers: Anthropic / OpenAI / Gemini / DeepSeek
└── Vision quando supports_vision=true no catálogo
```

Interface única pros services:

```python
router.complete_json(
    task="soap_writer",
    system=SYSTEM_PROMPT,
    user=payload,
    image_b64=optional,
)
```

O service **não escolhe modelo** — só declara a task. Trocar de modelo = editar YAML + restart API.

---

## Mapeamento atual de tasks (ponto-a-ponto)

| Task | Primary | Fallbacks | Criticidade | Custo estim. |
|------|---------|-----------|-------------|--------------|
| `soap_writer` | **Claude Sonnet 4** | Claude Haiku → GPT-5.4 mini | Alta (clínico crítico) | $3-15/mês |
| `prescription_validator` | **Claude Sonnet 4** | GPT-5.4 mini → Gemini 2.5 Flash | Alta | $4-12/mês |
| `clinical_analysis` | GPT-5.4 mini | Claude Haiku → Gemini 2.5 Flash | Alta (alto volume) | $5-25/mês |
| `patient_summary` | **Claude 3.5 Haiku** | GPT-5.4 mini → Gemini 2.5 Flash | Média (tom acolhedor) | $1-4/mês |
| `weekly_report` | GPT-5.4 mini | Gemini 2.5 Flash-Lite → Claude Haiku | Média | $0.5-2/mês |
| `prescription_ocr` | **Gemini 2.5 Flash** (vision) | Claude Sonnet 4 Vision → GPT-5.4 mini | Alta (ocr clínico) | $0.5-3/mês |
| `price_search_extraction` | Gemini 2.5 Flash-Lite | DeepSeek Chat → GPT-5.4 nano | Baixa (zero-PHI) | $0.3-1/mês |
| `intent_classifier` | GPT-5.4 nano | Gemini Flash-Lite | Baixa | $0.2-1/mês |
| `followup_answer` | GPT-5.4 mini | Gemini 2.5 Flash | Média | - |

**Total estimado**: **$15-65/mês** pra volume B2B (100 pacientes).

---

## Princípios de decisão

### 1. Criticidade clínica define mínimo de qualidade
- SOAP, Validator, OCR → **Claude ou Gemini** (nada de DeepSeek/nano)
- Alucinação = incidente clínico potencialmente grave

### 2. Vision nativa > Vision adaptada
- Gemini 2.5 Flash tem vision nativa a $0.30/1M — **mais barato que Claude em vision**
- Para OCR de medicação, vale o trade-off

### 3. DeepSeek apenas em tarefas ZERO-PHI
- Tarefas que recebem dados identificáveis de pacientes **não passam por servidor chinês**
- LGPD Art. 33 (transferência internacional) + data sovereignty
- DeepSeek hoje aparece APENAS no fallback de `price_search_extraction` (nome de remédio + HTML de farmácia, sem nome de paciente)

### 4. Fallback cascade garante disponibilidade
- Se primary fora do ar ou sem quota → próximo da lista tenta
- Services NÃO precisam saber que houve fallback — `_model_used` é registrado

### 5. Configuração por YAML, não código
- Trocar de modelo sem redeploy
- Útil quando sair GPT-5.5 ou Claude Opus novo

---

## Compliance e segurança

### LGPD
- Todo prompt LLM é considerado "tratamento de dado" (Art. 5º X)
- Registramos `_model_used` em logs → audit trail
- Não é PHI passa pra provider fora do Brasil **exceto** os com adequação:
  - ✅ OpenAI (DPA + SCCs)
  - ✅ Anthropic (DPA + SCCs)
  - ✅ Google (DPA + SCCs)
  - 🚨 DeepSeek (China — adequação não-demonstrada, evitar)

### Keys
- ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY em `.env` do servidor
- **Nunca commitar** em código
- Rotação documentada em checklist de segurança

### Cost tracking
- Campo `input_cost_per_1m` e `output_cost_per_1m` no catálogo de models
- Preparado pra expandir com `aia_health_llm_usage` (trabalho futuro)

---

## Decisões descartadas

### A. Usar tudo Claude Sonnet 4 (conservador)
- **Custo**: $300-500/mês só pro MVP
- **Descartado**: margem Essencial R$49,90 inviável

### B. Usar tudo Gemini 2.5 Flash (barato)
- **Custo**: $15-25/mês
- **Descartado**: bug inicial no OCR mostrou que Gemini não é uniforme em qualidade; SOAP tinha raciocínio clínico mais raso

### C. Usar DeepSeek em tudo (muito barato)
- **Custo**: <$10/mês
- **Descartado**: compliance LGPD (China) + sem vision

### D. LiteLLM proxy reutilizado da ConnectaIA
- Opção avaliada pra centralizar
- **Descartado**: quebra isolamento M&A-ready (ADR-001, ADR-003). Care deve ser ativo standalone quando vendida.
- Futuro: se ConnectaIA for fundida/vendida junto, unificamos

### E. GLM-OCR (Zhipu AI, China) self-hosted
- Open-source Apache 2.0, #1 em OmniDocBench
- **Descartado pra MVP**: complexidade (GPU VPS); pode voltar quando escala justificar

---

## Evidência da mudança

### Antes (Gemini pra tudo)
```
"MODEL: gemini-2.5-flash"
"PRIMARY_HYP: Hipotensão ortostática severa aguda"
```

### Depois (Claude Sonnet 4 em SOAP)
```
"MODEL: anthropic/claude-sonnet-4-20250514 | PROVIDER: anthropic | MS: 27158"
"PRIMARY_HYP: hipotensão ortostática severa secundária a efeito 
 medicamentoso (Levodopa) associada à desidratação"
```

O raciocínio clínico é visivelmente mais elaborado (identifica etiologia medicamentosa + desidratação como componente).

---

## Próximos passos

- [ ] `aia_health_llm_usage` table pra cost tracking granular
- [ ] Dashboard "LLM spend" por task/tenant
- [ ] A/B test: Gemini 3.1 Flash-Lite vs 2.5 Flash em OCR (quando preview estabilizar)
- [ ] Modo degraded: se todas APIs fora, usa cache/fallback offline
- [ ] Integração com **GLM-OCR self-hosted** quando volume OCR >10k/mês (economicamente justifica)

---

## Referências

- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [Claude pricing](https://docs.anthropic.com/en/docs/about-claude/pricing)
- ADR-001 — Stack isolada da ConnectaIA
- ADR-003 — Postgres separado (mesmo princípio de isolamento aplica a LLM)
- ADR-024 — Auth independente Care (argumentação M&A-ready)
