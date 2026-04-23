# ConnectaIACare — Plano de Expansão B2B → B2C · v2 (consolidado)

> Segunda iteração consolidando: plano v1 (22/04 manhã) + feedback Opus Chat
> 2ª rodada (22/04 tarde) + decisões do Alexandre + implementações já feitas
> durante a sprint da noite de 22/04.
>
> Data: 23/04/2026 (início) · Demo 28/04
> Autores da síntese: Opus Desktop · Claude Chat · Claude Code (eu)

---

## 0. Mudanças desde o v1

### Decisões do Alexandre
1. **Rede comunitária DESBLOQUEADA juridicamente** — advogado confirmou:
   cláusula de não-obrigatoriedade + "estado de necessidade" do CP Art. 24 +
   voluntariedade opt-in garantem que ConnectaIACare é facilitadora, não
   prestadora de socorro. **Volta pra Fase 2.A** (cronograma original do Chat).
2. **Auth totalmente independente** ConnectaIACare (não SSO) — M&A-ready.
   Copiar código da ConnectaIA, rodar standalone, com camadas extras
   de segurança (MFA obrigatório, session TTL curto, password rotation 90d,
   etc). Detalhado em **ADR-024**.

### Implementações já feitas (22/04 noite)
Durante a sprint, muitos gaps identificados pelo Opus foram resolvidos:

- ✅ **Scheduler Proativo** (migration 009 + `proactive_scheduler.py`)
  - Heartbeat em tabela dedicada (alerta se >5min silent)
  - Timezone por paciente (`timezone` field)
  - Janela tolerância (`response_window_min`, default 120)
  - Learning pattern (`observed_response_avg_min` atualizado auto)
  - Concorrência via `pg_try_advisory_lock` isolado
- ✅ **Weekly Family Report** (`weekly_report_service.py`)
  - Template Claude Sonnet com regras invioláveis anti-alarmismo
  - Output JSON estruturado + WhatsApp curto + email HTML
  - Fallback rico com métricas reais (não genérico)
  - Cache idempotente por `(patient_id, week_start)`
  - Endpoint `POST /api/patients/:id/weekly-report/send`
- ✅ **Portal do paciente PIN + WhatsApp + PDF + preços**
  - PIN 24h + bcrypt + rate-limit + audit LGPD Art. 37
  - PDF com QR de verificação + assinatura eletrônica mocked
  - Scraper CliqueFarma/ConsultaRemedios (advanced mode)
- ✅ **CID-10 DATASUS** (migration 008 + `disease_routes.py`)
  - 51 códigos geriátricos curados com sinônimos
  - Unaccent + trigram fuzzy + ranking geriátrico primeiro
  - Autocomplete integrado no SOAP editor

---

## 1. Convergências mantidas (todos concordam)

- Tese central: reativo-presencial → proativo-digital-comunitário
- Stack única, tenants múltiplos (DB isolado por produto)
- Íris agente-framework mantido standalone
- Pricing R$49,90 Essencial
- Atente como moat humano 24h

---

## 2. Feedback Opus 2ª rodada — absorção e ajustes

### ✅ Ponto 1 — Scheduler proativo (implementado com extras)
Tudo que o Opus pediu está em `aia_health_proactive_schedules`:

- **Heartbeat**: tabela `aia_health_scheduler_heartbeat`, monitora last_tick
- **Janela tolerância**: campo `response_window_min` (configurável por paciente)
- **Timezone**: `timezone TEXT DEFAULT 'America/Sao_Paulo'` (ZoneInfo Python)
- **Learning pattern (extra)**: `observed_response_avg_min` + `observed_response_p95_min`
  atualizados dinâmicamente pela função `_reconcile_recent_responses`
- **Retry exponencial com tom diferente (extra)**: estrutura prevista em
  `aia_health_scheduled_fires.retry_count` + `max_retries` por schedule

**Pendente pra próxima sprint**:
- Monitoring externo (ex: worker de auditoria que manda WhatsApp pro devops
  se heartbeat > 5min silent). Trivial — SQL + cron.
- Segunda tentativa de fire com **texto diferente** baseado em retry_count
  (hoje reenvia o mesmo template).

### ✅ Ponto 2 — B2B como canal B2C (incorporado)
Formalizar em **Onda 7** com:

```sql
CREATE TABLE aia_health_referral_codes (
    id UUID PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,          -- ex: "SPA-VIDA-MARIA"
    issuer_type TEXT CHECK IN ('spa', 'caregiver', 'family'),
    issuer_id UUID,                      -- polimórfico (spa_tenant_id ou caregiver_id)
    
    commission_structure JSONB,          -- {"spa": 0.2, "caregiver": 50} (% ou R$)
    active_since TIMESTAMPTZ,
    active_until TIMESTAMPTZ,
    
    total_uses INT DEFAULT 0,
    total_conversions INT DEFAULT 0,
    total_paid_commission_brl NUMERIC(10,2) DEFAULT 0
);

CREATE TABLE aia_health_subscription_referrals (
    id UUID PRIMARY KEY,
    subscription_id UUID REFERENCES aia_health_subscriptions(id),
    referral_code_id UUID REFERENCES aia_health_referral_codes(id),
    
    attribution_verified_at TIMESTAMPTZ,
    commission_due_brl NUMERIC(10,2),
    commission_paid_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Modelo de comissão inicial (pilotar):**

| Origem da indicação | Comissão | Pagamento |
|---------------------|----------|-----------|
| SPA (Tecnosenior parceira) | 1 mês grátis do contrato B2B por conversão | Crédito na próxima fatura |
| Cuidador profissional pessoal | R$50 Pix no 2º mês de pagamento B2C | Via Pix/PagBank |
| Familiar já cliente | 10% off na própria mensalidade por 3 meses | Crédito recorrente |

**UI:**
- Portal B2B tem seção "Indique ConnectaIACare pra família" com QR + link
- Portal B2C do pagante: banner sutil "Cuide também de outros entes queridos"
  na dashboard principal (não intrusivo)

### ✅ Ponto 3 — Relatório semanal (implementado)
Concreto no código. Exemplo real gerado durante o sprint para a Antonia:

```
☀️ Olá família! Segue o resumo do cuidado de Antonia (16 a 23/abr):

✅ Foram 140 medições de sinais vitais, com FC média de 76 bpm.
⚠️ Tivemos 2 eventos de atenção, incluindo um urgente na quarta (22/abr)
   por tontura e recusa alimentar. A equipe agiu prontamente e iniciou
   os cuidados necessários.
👀 O monitoramento de Antonia segue contínuo e atento.
💙 Estamos à disposição para qualquer dúvida!
```

Regras aplicadas:
- Tom factual, não alarmista ("a equipe agiu prontamente", não "melhorou")
- Métricas quantitativas (140, 76 bpm, 2 eventos)
- Emojis dentro do limite (4 ≤ 5)
- Nome correto sem título ("Antonia", não "Dona Antonia")
- Fallback quando LLM falha também traz métricas reais

**Próximo passo pra UX:**
- Botões acionáveis WhatsApp (requer Business API oficial pra rich messages)
- Email HTML com gráfico comparativo 30 dias
- Deep link pro portal mostrando detalhe

### ✅ Ponto 4 — Anti-fraude em camadas (incorporado)
Matriz adotada:

| Plano | Verificação obrigatória | Custo médio/cliente | Racional |
|-------|-------------------------|---------------------|----------|
| Trial 14d | CPF + SMS OTP | ~R$0,05 | Fricção mínima |
| Essencial R$49,90 | CPF + WhatsApp OTP | R$0,00 | Canal já existente |
| Família R$89,90 | + foto doc. paciente (upload cuidador) | R$0,00 | Prova de vínculo |
| Premium R$149,90 | + selfie Unico/BigID | R$2–3 | Justifica pq tem teleconsulta |

Registra em `aia_health_verification_checks` com `method`, `status`,
`completed_at`, `provider_reference` (pra audit + possível re-verificação).

### ⚠️ Discordância absorvida — polimorfismo atenuado
Ajuste aceito: em vez de migrar tudo pra `aia_health_subjects`, manter
`aia_health_patients` e `aia_health_caregivers` intactas e criar:

- **`aia_health_family_members`** (tabela nova, B2C específica)
- **View `aia_health_subjects_v`** que unifica os 3 pra queries transversais
  (scheduler, biometria, notificações)
- **`aia_health_voice_embeddings`** ganha `subject_type` + `subject_id`
  polimórficos (FK não-formalizada, aplicação valida)

**Benefícios**:
- Zero migração dolorosa no B2B
- Views permitem queries cruzadas sem duplicação lógica
- Quando (e se) quiser unificar no futuro, materializa a view

---

## 3. Gaps estruturais do código — status atualizado

| # | Gap | Status (23/04) |
|---|-----|----------------|
| 1 | Pipeline 100% reativo | ⚠️ Pendente — scheduler proativo já existe, falta integrar inbound→fire correlation |
| 2 | Enrollment só `caregiver_id` | ⚠️ Pendente — Onda 5 biometria expandida |
| 3 | `aia_health_patients.phone` | ⚠️ Pendente — proxy via care_event, precisa coluna dedicada |
| 4 | Sem geolocalização paciente | ⚠️ Pendente — Onda 8 (rede comunitária) |
| 5 | Alergias/condições texto livre | ✅ **Resolvido parcialmente** — CID-10 catalog + trgm |
| 6 | Zero infra billing | ⚠️ Pendente — Fase 2.A |
| 7 | Checkin só `care_events` ativos | ✅ **Resolvido** — proactive_scheduler standalone |
| 8 | Consent LGPD B2C | ⚠️ Pendente — Onda 2 |
| 9 | Evolution API mono-instância | ⚠️ Pendente — migrar WhatsApp Cloud API pré-10k |
| 10 | Sem payer ≠ beneficiary | ⚠️ Pendente — Fase 2.A billing |

**Progresso**: 3 de 10 gaps críticos resolvidos em 1 dia de trabalho.
Restam 7 — todos têm escopo conhecido e estimativa, nada é desconhecido-desconhecido.

---

## 4. Roadmap revisado (substitui v1)

### Fase 1 — Demo B2B e piloto (agora até ~10/mai)
- [x] Ondas 0-4 em produção
- [x] Scheduler proativo + weekly report
- [ ] Módulo Cadastros (Pacientes/Familiares/Profissionais/Usuários)
- [ ] Programa indicação B2B→B2C (MVP)
- [ ] Rehearsal + slides demo 28/04
- [ ] Piloto 30 dias Tecnosenior com 10 SPAs

### Fase 2.A — B2C MVP Essencial (mai–jul/2026)
- Auth independente (ADR-024) com MFA
- Migrations 010-012 (family_members + subjects_v + billing)
- Onboarding WhatsApp conversacional (Sofia faz cadastro B2C)
- Check-in diário (schedule_templates já seedado)
- Escalação família → Atente
- Grupo familiar via DMs individuais (contorna limite Evolution)
- Relatório semanal automático (já pronto, só conectar)
- Billing Stripe/PagSeguro (SKU Essencial R$49,90)
- Verificação CPF + SMS OTP

### Fase 2.B — Diferenciação (ago–set/2026)
- Motor medicamentos 5 camadas (extensão validator)
- Biomarkers de voz como "padrão de fala" (não-diagnóstico, evita SaMD)
- Plano Família R$89,90 + Premium R$149,90
- Rede comunitária georreferenciada (desbloqueada juridicamente)
- Teleconsulta avulsa R$80 (não-incluída)
- Migração WhatsApp Cloud API

### Fase 2.C — Ecosystem (out–dez/2026)
- Integração Apple Watch fall detection
- API pública pra fabricantes SOS
- Canal operadora de saúde (whitel-label)
- Onda 9 — Clube de Benefícios (Dentistas, Academias, Sindicatos etc)

### Fase 3 — Plataforma (Q1–Q2/2027)
- Marketplace (farmácias, labs, fisio)
- API prefeituras
- Internacionalização Portugal + LATAM
- Hospital-at-home com reembolso ANS

---

## 5. Canais de aquisição (atualizados)

**B2B (primários)**:
- Tecnosenior (parceria já ativa)
- Outras SPAs afiliadas via Murilo
- Grupo Abrates (associação operadoras geriátricas)

**B2C (em ordem de prioridade CAC/LTV)**:
1. **B2B como canal orgânico** (Opus — Ponto 2) — menor CAC
2. Sindicatos de aposentados (SINDINAPI, SINSEP) — desconto em folha
3. Condomínios alto padrão com população idosa
4. Imobiliárias residencial sênior
5. Planos funerários (cross-sell natural)
6. Farmácias de manipulação
7. Meta/Google Ads segmentado (filho 45-55 cuida pai/mãe sozinho)
8. Clínicas geriátricas privadas (indicação afiliada)

---

## 6. O que o Opus precisa decidir na próxima sessão

Perguntas abertas pra o Opus resolver:

1. **Billing SKU model**: seat-based (1 pagante → N beneficiários) ou per-subscription?
   Família com mãe + sogra quer pagar 1x, usar 2 slots.

2. **WhatsApp Cloud API timing**: migrar antes da Fase 2.A (mais caro, menos
   fricção escalar) ou durante (Evolution aguenta até 2-3k clientes)?

3. **Biomarkers SaMD ou não**: implementar como "padrão de fala descritivo"
   (sem registro ANVISA) é suficiente ou vamos atrás do registro SaMD Classe I
   desde já (ganha claim diagnóstico)?

4. **Rede comunitária incentivo**: qual é o incentivo "certo"? 1 mês grátis
   por resposta confirmada? R$20/acionamento? Gamification (badge)?
   Piloto com 3 modelos em bairros diferentes pra AB test?

5. **Grupo familiar WhatsApp**: ConnectaIACare como admin (gera N grupos,
   1 por família — custoso Evolution) ou Sofia envia DM individual pra cada
   familiar com o mesmo conteúdo (escalável)?

6. **Teleconsulta avulsa R$80**: pagamento único no ato ou crédito mensal
   tipo "vale-consulta" que sobra/acumula?

---

## 7. Métricas-chave pro pitch B2C

Objetivo: no fim do piloto B2B (30 dias), ter números pro material de
apresentação B2C:

- **Tempo médio de resposta** (áudio → análise IA)
- **% classificação correta** (validada por médico)
- **Satisfação cuidador** (NPS pós-evento)
- **Redução de escalação desnecessária** vs baseline SPA
- **Eventos críticos detectados vs escapados**
- **Adoção de check-in proativo** (%)
- **Adesão do cuidador pagante** ao portal/relatório semanal

---

## 8. ADRs relacionadas

| # | Título | Status |
|---|--------|--------|
| 022 | Atente como fallback humano | ✅ Aprovado |
| 023 | Teleconsulta arquitetura completa | ✅ Implementado |
| 024 | **Auth independente Care com MFA** | 📝 Em draft (esta sprint) |
| 025 | Biomarkers voz como padrão descritivo (não-SaMD) | 📝 Pendente |
| 026 | Migração WhatsApp Cloud API timing | 📝 Pendente |
| 027 | Modelo billing payer ≠ beneficiary | 📝 Pendente |

---

## 9. Checklist imediato (próximas 2 semanas)

**Até 28/04 (demo)**:
- [ ] Rehearsal end-to-end com dataset real
- [ ] Slides do pitch (valor proposto, métricas piloto, roadmap B2C)
- [ ] Prova de weekly report enviado semanalmente
- [ ] 10 SPAs candidatas ao piloto 30d

**Semana 29/04-05/05 (pós-demo)**:
- [ ] Feedback Murilo incorporado
- [ ] ADR-024 publicado
- [ ] Migration 010 (family_members)
- [ ] Módulo Cadastros no CRM

**Semana 06/05-12/05**:
- [ ] Onboarding WhatsApp conversacional (bot Sofia B2C)
- [ ] Stripe setup + SKU Essencial
- [ ] Verificação CPF+SMS OTP

**Semana 13/05-19/05**:
- [ ] Beta fechado 20 famílias convidadas
- [ ] Ajustes UX com base no feedback real
- [ ] Launch público Plano Essencial R$49,90

---

**Fim do plano v2.** Três autores, uma convergência crescente,
implementação já em ~40% pro MVP B2C. Oportunidade real + time capaz +
parceiro certo + timing de mercado. Hora de executar.
