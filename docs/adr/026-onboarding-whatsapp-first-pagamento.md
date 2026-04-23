# ADR-026 — Onboarding WhatsApp-first + Políticas de Pagamento

**Status**: Aceito (implementado 23/04/2026 — stub sem PSP real)  
**Decisores**: Alexandre (CEO), Claude Code (engenharia)

---

## Contexto

O produto B2C da ConnectaIACare ("Sofia Cuida") se destina a famílias brasileiras que cuidam de idosos em casa. Perfil:

- **Decisor/pagante**: filho(a) 40-60 anos, smartphone Android, WhatsApp multiusado
- **Usuário final**: idoso 65+, muitas vezes com baixa alfabetização digital
- **Contexto emocional**: angústia, urgência, sobrecarga — não há paciência para onboarding longo

Análise competitiva: **100% dos concorrentes** (Hippocratic, Sensi, Lyfegen) exigem:
1. Download de app
2. Cadastro via formulário web
3. Múltiplas confirmações por e-mail
4. Cartão digitado com teclado numérico

Isso é barreira de entrada impeditiva pro nosso público.

**Hipótese central**: cada passo fora do WhatsApp reduz conversão em ~15-25% (dados setor fintech BR).

---

## Decisão

**Todo o onboarding B2C acontece dentro do WhatsApp, conduzido pela assistente Sofia. Única exceção: clique único em link de pagamento seguro (cartão/PIX).**

Arquitetura:

```
User manda "oi" no WhatsApp da Sofia
   ↓
Sofia conduz state machine de 14 estados (aia_health_onboarding_sessions)
   ↓
Coleta progressiva:
   nome pagante → CPF → nome/idade idoso → condições → medicações
   → contatos emergência → endereço → plano → pagamento → consent LGPD
   ↓
Gera link PSP (Asaas/MP) — user clica, preenche cartão, volta
   ↓
Sofia ativa subscription + envia confirmação
   ↓
9h da manhã seguinte: primeiro check-in começa
```

Implementação em `src/services/sofia_onboarding_service.py` (state machine) + schema `aia_health_onboarding_sessions` + `aia_health_subscriptions` + `aia_health_payment_intents` + `aia_health_plans` (migration 011).

---

## Políticas de negócio

### Trial

- **7 dias de teste grátis** — CDC Art. 49 (direito de arrependimento em compras à distância)
- **Apenas com cartão recorrente** — PIX não permite trial
- **Cancelamento simples**: user manda "cancelar" no chat, Sofia executa com confirmação
- Trial rastreado em `aia_health_subscriptions.trial_started_at` + `trial_ends_at`

### Métodos de pagamento

**Cartão de crédito** (recomendado pelo sistema):
- Experiência: link clicável → página do PSP → user preenche cartão → volta pro WhatsApp
- Trial 7 dias grátis
- Recorrência automática mensal
- Dunning automático em caso de recusa: sistema tenta 3x em dias diferentes antes de suspender

**PIX**:
- Experiência: Sofia envia QR code + copia-cola no WhatsApp
- **Assinatura começa no primeiro pagamento** — sem trial
- Cobrança mensal: todo mês Sofia envia QR novo 3 dias antes do vencimento
- Se falta no prazo: tolerância de 3 dias, depois suspensão
- Risco: abandono por esquecer de pagar. Mitigação: 3 lembretes escalados (chat + ligação Sofia + ligação Atente)

### Verificação anti-fraude tier-based (ADR-025)

| Plano | Verificação obrigatória | Custo/cliente |
|-------|-------------------------|---------------|
| Trial 14d | CPF + WhatsApp OTP | R$0,05 |
| Essencial R$49,90 | CPF + WhatsApp OTP | R$0 |
| Família R$89,90 | + foto doc. paciente (upload cuidador) | R$0 |
| Premium R$149,90 | + selfie Unico/BigID | R$2-3 |
| Premium+Device R$199,90 | + selfie Unico + verificação endereço | R$3-5 |

CPF sempre validado via hash SHA-256 (LGPD — nunca armazenado em claro).

### Payer ≠ Beneficiary (polimorfismo)

Schema `aia_health_subscriptions` tem:
- `payer_subject_type` + `payer_subject_id` (quem paga)
- `beneficiary_patient_ids[]` (N idosos monitorados)

Caso de uso real: filho paga e monitora mãe + sogra + pai. 1 subscription, 3 beneficiaries (limitado pelo plano — Essencial=1, Família=2, Premium=2).

### Cancelamento e retenção

- **Self-service via WhatsApp**: user digita "cancelar" → Sofia confirma + pergunta motivo + cancela
- Motivos coletados em `aia_health_subscriptions.cancellation_reason` pra análise de churn
- **Downgrade disponível**: user digita "mudar pra essencial" → ajuste de plano no próximo ciclo
- **Upgrade emergencial**: idoso piorou, filho quer Atente 24h agora → upgrade imediato com proration

### LGPD + Consent

- Consent versionado (`consent_version` + `consent_signed_at`)
- Opcional: `consent_audio_hash` — áudio do user aceitando ("Eu, João Silva, autorizo...")
- Direito ao esquecimento: user digita "apagar meus dados" → scrub 30 dias
- Audit completo em `aia_health_onboarding_sessions.funnel_step_times`

---

## State machine — detalhes

14 estados sequenciais com permissão de voltar:

| Estado | Sofia pergunta | Coleta |
|--------|----------------|--------|
| `greeting` | "Olá! Aqui é a Sofia..." | nada (apenas saúda) |
| `role_selection` | "Pra você mesma ou ente querido?" | `role` |
| `collect_payer_name` | "Nome completo do pagante" | `payer.full_name` |
| `collect_payer_cpf` | "CPF do pagante" | `payer.cpf_hash` |
| `collect_beneficiary` | "Nome e idade do idoso" | `beneficiary.{full_name, age}` |
| `collect_conditions` | "Problemas de saúde conhecidos" | `beneficiary.conditions_raw` |
| `collect_medications` | "Medicações (texto ou foto)" | `beneficiary.medications_raw` ou OCR |
| `collect_contacts` | "Contatos de emergência" | `contacts[]` |
| `collect_address` | "CEP onde mora" | `address_raw` |
| `plan_selection` | "Qual plano? (1-4)" | `plan_sku` |
| `payment_method` | "Cartão ou PIX?" | `payment_method` |
| `payment_pending` | Envia link/QR, aguarda | PSP webhook / confirmação manual |
| `consent_lgpd` | "Aceita os termos?" | `consent_signed_at` |
| `active` | "Tudo ativado! 🎉" | — |

Estados terminais: `active` (sucesso), `abandoned` (>48h sem interação), `rejected` (não aceitou LGPD, CPF inválido, etc).

### Escape valves

- `"humano"` / `"atendente"` / `"falar com alguém"` → escala pra Atente 24h
- `"voltar"` / `"corrigir"` → volta 1 estado
- `"cancelar"` → aborta e arquiva sessão

### Inteligência da Sofia

Cada estado tem um **intent classifier** via LLM (`task='intent_classifier'` → GPT-5.4 nano).

Exemplo: em `plan_selection`, user pode responder:
- "1" → essencial
- "famila" → familia (matcha mesmo com erro)
- "o mais barato" → essencial
- "me explica mais" → show detalhes + re-ask
- "tanto faz" → pedir clarificação

---

## Integração PSP

### Provider escolhido: Asaas (primeiro)

Motivos:
- API brasileira, documentação em português
- PIX + cartão + boleto nativos
- **Split de comissão** nativo — crucial pro programa de indicação B2B→B2C (ADR-026 complementar)
- Webhook robusto
- Preço competitivo (~R$2 fixo/transação PIX, 2,99% cartão)

### Secundário: Mercado Pago (fallback)

- Volume maior, confiança de marca
- Usado quando Asaas der problema (alternativa operacional)

### Interface do nosso lado

```python
# Abstração em aia_health_payment_intents
psp_provider:    'asaas' | 'mercadopago'
psp_intent_id:   id no provider
psp_checkout_url: link que Sofia envia pro user
psp_qr_code:     base64 PNG do QR PIX
psp_copy_paste:  texto copia-cola PIX
webhook_events:  JSONB com histórico
```

Implementação do `asaas_client.py` e `mercadopago_client.py` — pendente, será feita quando chegarmos em billing real (Fase 2.A).

---

## Decisões descartadas

### A. Onboarding por site + WhatsApp como notificação
- **Descartado**: cada step fora do WhatsApp = perda de conversão

### B. Formulário único com link mestre
- **Descartado**: idoso não navega bem em form longo no mobile

### C. Video call de onboarding
- **Descartado**: fricção alta, exige agendamento

### D. App nativo iOS/Android
- **Descartado**: download da App Store reduz conversão em 70%+ em B2C saúde

### E. WhatsApp Business API (Meta oficial) vs Evolution API
- **Temporariamente mantido Evolution** (o que já usamos)
- **Futuro**: migrar pra WhatsApp Cloud API quando volume justificar — templates oficiais, melhor deliverability, botões ricos nativos

---

## Evidência (em produção após esta sessão)

**Schema migrado**: 4 planos seedados
```
essencial       | Sofia Cuida Essencial             |  49.90
familia         | Sofia Cuida Família               |  89.90
premium         | Sofia Cuida Premium               | 149.90
premium_device  | Sofia Cuida Premium + Dispositivo | 199.90
```

**State machine ativa** — `sofia_onboarding_service.py` pronto pra intercept de "oi" em phone novo.

**Próximo passo** (Fase 2.A pós-demo):
- [ ] Implementar `asaas_client.py` real
- [ ] Webhook endpoint `/api/webhooks/asaas`
- [ ] Tela de auditoria admin (quantas onboardings em cada estado, funnel)
- [ ] Testes de carga (quantas sessões simultâneas o worker suporta)
- [ ] A/B test de mensagens da Sofia (tom, comprimento, emoji density)

---

## Métricas-chave pra acompanhar

- **Conversão greeting → active**: meta 30%+ (setor: 15-25%)
- **Tempo médio greeting → active**: meta <15 min
- **Estados com maior drop**: identificar os 2 piores e A/B test
- **CAC atribuído por canal de indicação** (programa B2B→B2C)
- **Churn em 30/60/90 dias**
- **NPS do cuidador pagante** (pergunta automática no 7º dia de trial)

---

## Referências

- ADR-024 — Auth independente Care
- ADR-025 — LLM Routing por Tarefa (intent_classifier usado aqui)
- Plano v2 (`PLANO_EXPANSAO_B2B_B2C_v2_2026-04-22.md`)
- Programa de Indicação B2B→B2C (`PROGRAMA_INDICACAO_B2B_B2C.md`)
- CDC Art. 49 (direito de arrependimento)
- LGPD Art. 11 (dado sensível de saúde) + Art. 37 (registro de operações)
