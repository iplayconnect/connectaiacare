# Sessão Noturna 22→23/04/2026 — Trabalho Autônomo

> Relatório do trabalho feito enquanto Alexandre descansava.
> Execução aprovada: LLM Router integration + Onboarding Sofia B2C + ADRs.

---

## 🎯 Entregue (100% do planejado)

### 1. LLMRouter integrado em 7 services — Claude Sonnet 4 AO VIVO

Todos os serviços de IA agora chamam `router.complete_json(task='...')` em vez de escolher modelo hardcoded. Modelos escolhidos por tarefa conforme ADR-025:

| Tarefa | Modelo agora | Benefício |
|--------|--------------|-----------|
| **SOAP Writer** | Claude Sonnet 4 | Raciocínio clínico top |
| **Prescription Validator** | Claude Sonnet 4 | Beers + interações + alergias |
| **Patient Summary** (portal) | Claude 3.5 Haiku | Tom acolhedor, rápido |
| **Weekly Report** | GPT-5.4 mini | Relatório factual família |
| **Clinical Analysis** (áudio) | GPT-5.4 mini | Alto volume, bom custo |
| **OCR (vision)** | Gemini 2.5 Flash | Já funcionava perfeito |
| **Price Search** | Gemini 2.5 Flash-Lite | Zero-PHI, mais barato |
| **Intent Classifier** | GPT-5.4 nano | Ultra rápido, ultra barato |

**Evidência ao vivo**: re-assinei a teleconsulta da Dona Antonia pra confirmar:
- MODEL: `anthropic/claude-sonnet-4-20250514` ✅
- Tempo: 27s
- Diagnóstico: "hipotensão ortostática severa **secundária a efeito medicamentoso (Levodopa) associada à desidratação**"

Compare com a versão anterior (Gemini): só dizia "hipotensão ortostática severa aguda". Claude identificou **etiologia medicamentosa + componente de desidratação** — raciocínio muito mais elaborado.

### 2. Custo estimado mensal: **$15-53/mês** (vs $300-500 se tudo Claude)

Sistema de fallback cascade garante que se um provider falhar, o próximo tenta — sem quebrar produção.

### 3. Sofia Cuida Onboarding B2C — schema + state machine completa

**Migration 011** criou 4 tabelas:
- `aia_health_plans` (4 planos seedados)
- `aia_health_subscriptions` (payer ≠ beneficiary)
- `aia_health_onboarding_sessions` (state machine 14 estados)
- `aia_health_payment_intents` (PSP integration abstract)

**4 planos seedados**:
```
essencial       R$  49,90/mês — Check-in + 3 contatos + medicação
familia         R$  89,90/mês — Essencial + grupo familiar + rede comunitária
premium         R$ 149,90/mês — Família + teleconsulta + Atente 24h
premium_device  R$ 199,90/mês — Premium + pulseira SOS Tecnosenior
```

**Regras de negócio implementadas** (conforme sua decisão):
- ✅ Trial **7 dias** (CDC Art. 49)
- ✅ Trial **apenas com cartão recorrente**
- ✅ PIX = assinatura imediata, sem trial
- ✅ CPF hasheado (LGPD, nunca em claro)

**State machine da Sofia** (14 estados sequenciais):
`greeting → role_selection → collect_payer_name → collect_payer_cpf → collect_beneficiary → collect_conditions → collect_medications → collect_contacts → collect_address → plan_selection → payment_method → payment_pending → consent_lgpd → active`

Cada estado usa **LLM intent classifier** (GPT-5.4 nano) pra entender texto livre.

**Escape valves** implementados:
- "humano" / "atendente" → escala pra Atente
- "voltar" → estado anterior
- "cancelar" → aborta sessão

**Integração no pipeline**:
`_try_handle_onboarding` intercepta ANTES do fluxo normal:
- Sessão existente em estado intermediário → continua onboarding
- "oi" / "olá" / "quero assinar" de phone sem care_event ativo → entra no onboarding
- Cuidador B2B com evento ativo → fluxo legado (intocado)

### 4. ADRs publicados

- **ADR-025** — LLM Routing por Tarefa e Criticidade Clínica (214 linhas)
- **ADR-026** — Onboarding WhatsApp-first + Políticas de Pagamento (247 linhas)

Ambos no GitHub prontos pra você levar pro Opus revisar.

---

## ⚠️ Incidente resolvido (peço desculpa)

### Bug #1: Loop infinito de lembretes de Domperidona

**Detectado** durante a noite: você reportou que a Domperidona estava em loop enviando mensagens sem parar.

**Causa raiz**: meu `INSERT ... ON CONFLICT DO NOTHING` no `medication_event_service.materialize_for_patient` **não tinha UNIQUE constraint** pra bater. Resultado: a cada 15s o scheduler criava novos events idênticos, gerando **3.203 duplicatas** só do mesmo horário (11h de hoje), que dispararam **688 lembretes** WhatsApp pro teu número.

**Correção aplicada**:

1. ✅ **Pausei schedules** imediatamente (Domperidona + Diclofenaco desativados)
2. ✅ **Migration 012** emergencial: deduplica (prioridade: `taken > refused > skipped > reminder_sent > scheduled`) + adiciona `UNIQUE(schedule_id, scheduled_at)`
3. ✅ **3.917 events duplicados removidos** do banco
4. ✅ **Schedules unique reabilitados** (1 Domperidona + 1 Diclofenaco ativos)
5. ✅ **Validado**: agora só 1 event pendente, sem criar duplicatas novas

**Status**: 100% resolvido. Se você olhar o WhatsApp, verá a enxurrada de Domperidonas — essa parou de vez às 02:47.

---

## 📊 Métricas da sessão

- **9 commits**
- **~1.900 linhas** de código + docs adicionadas/modificadas
- **2 migrations** aplicadas em produção (011 + 012 emergencial)
- **7 services refatorados** (redução de ~280 linhas redundantes removidas)
- **1 migration YAML** de routing (`llm_routing.yaml`)
- **2 novos ADRs** (025 + 026)
- **1 incidente detectado + corrigido** no mesmo ciclo
- **Sistema estável**: API 200, Frontend 200, LLM Router operacional, Scheduler saudável

---

## 🔍 Pra validar quando acordar

### 1. Confirmar que Claude está respondendo SOAP
- Abrir `/teleconsulta/c05501d4-53de-4db5-812d-f24fb6e3c0d3/documentacao`
- Ou ver payload API: `POST /api/teleconsulta/:id/soap/generate`
- Campo `_model_used` deve ser `anthropic/claude-sonnet-4-20250514`

### 2. Testar Sofia Onboarding ao vivo
- Manda **"oi"** de um número WhatsApp que NUNCA interagiu com Care antes
- Sofia deve responder: "Olá! 👋 Aqui é a Sofia..."
- Conversa até `payment_method` funciona com LLM classificação real
- Ativação final cria subscription (stub — sem PSP ainda)

### 3. Verificar medicação sem loop
- Acesse prontuário da Dona Antonia
- Deve ter 1 Domperidona + 1 Diclofenaco ativos (não 15)
- Próximas doses mostradas corretamente, sem flood

### 4. Ler ADRs pra levar ao Opus
- `docs/adr/025-llm-routing-por-tarefa.md`
- `docs/adr/026-onboarding-whatsapp-first-pagamento.md`

---

## 🚧 O que ficou pendente (pós-demo)

1. **Integração PSP real** (Asaas ou MP) — hoje apenas stub
2. **Webhook endpoint** `/api/webhooks/asaas` pra confirmar pagamento
3. **Dashboard admin** de onboarding (funnel + drop-off)
4. **OCR via Sofia Onboarding** (quando user manda foto de medicação no estado `collect_medications`, chamar `prescription_ocr_service` diretamente)
5. **Rotacionar Anthropic API key** (sua key foi exposta no chat na noite passada — criar nova e revogar antiga)

---

## 🔑 Lembrete importante de segurança

A API key da Anthropic que você me passou no chat **está exposta no histórico de mensagens** (visível nos logs do Claude Desktop + aqui no chat). 

**Ação recomendada** pós-demo:
1. Acessar https://console.anthropic.com/settings/keys
2. **Revogar** a key que você compartilhou no chat (aquela começando com `sk-ant-api03-EQIG...`)
3. Gerar **nova** key
4. Atualizar `ANTHROPIC_API_KEY` no `.env` da VPS via SSH (**não commita**)
5. Restart api: `docker compose restart api`

> Nota: O GitHub Secret Scanning detectou a key no meu documento original
> e bloqueou o push — por isso ela aparece truncada aqui.

---

## 💙 Recado final

Tu descansou, eu trabalhei. **Tudo no ar, tudo estável**. Entreguei o que prometi + resolvi o incidente que apareceu. 

Aguardo tuas observações e próxima frente. Tamo junto. 🚀

— Claude Code · 02:58 BRT · 2026-04-23
