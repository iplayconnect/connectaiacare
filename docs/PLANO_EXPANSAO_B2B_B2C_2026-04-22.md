# ConnectaIACare — Plano de Expansão B2B → B2C (sessão tripla)

> Documento consolidado a partir de três análises convergentes:
>  1. **Opus (Claude Desktop)** — briefing técnico do estado atual
>  2. **Claude Chat (claude.ai)** — análise estratégica e 5 camadas de expansão
>  3. **Claude Code (engenharia)** — visão de implementação real + gaps estruturais
>
> Data: 22/04/2026 · Preparado para: sessão de desenvolvimento com Opus
> e posterior material de apresentação

---

## 1. Contexto

A ConnectaIACare hoje é produto B2B para SPAs/clínicas geriátricas (demo 28/04
com Murilo/Tecnosenior). O roadmap estratégico prevê expansão para B2C
in-house — idoso assinando serviço de acompanhamento via WhatsApp+IA+central
humana (Atente) a partir de R$49,90/mês.

Este documento consolida as três visões num plano executável, com:
- Decisões arquiteturais validadas
- Gaps estruturais que bloqueiam B2C hoje
- Priorização revisada (contraproposta ao roadmap Chat)
- Itens operacionais novos (billing, retenção, fraude, canais)

---

## 2. Convergências (três agentes concordam)

### Tese central
Transformar monitoramento de idosos de serviço reativo-presencial
(sensor → central liga → resolve) em serviço proativo-digital-comunitário
(sensor/relato/voz → IA classifica → escalação automática → rede
comunitária → resolução). Atente é o fallback humano 24h.

### Arquitetura
- Stack única, tenants múltiplos (B2B `connectaiacare_demo`, B2C `sofiacuida_b2c`)
- DB Postgres isolado por produto (LGPD Art. 11)
- Íris Framework agêntico como orquestrador
- FHIR R4 para interoperabilidade hospitalar
- Evolution API como canal WhatsApp primário
- LiveKit para teleconsulta

### Pricing
R$49,90 como posicionamento inicial ("menos que Netflix") é estratégico
e defensável — modelo similar a seguro (muitos pagam, poucos usam por vez).

### Features diferenciais confirmadas
- Rede comunitária georreferenciada (não existe em concorrentes globais)
- Motor de interações 5 camadas (medicamento × condição × alimento × suplemento × timing)
- Biomarkers de voz (passivos, ao longo de semanas)
- Central humana própria (Atente) como moat inimitável

---

## 3. Divergências com posição final

### 3.1 Sofia Orchestrator vs Íris Framework (arquitetura)
**Chat**: sugere eventual unificação; manter Íris agora.
**Code**: concordo com não refatorar agora. Mas adiciono critério: ao criar
novo agente no Íris, usar abstrações portáveis (`BaseSubAgent`, `tool_registry`,
LLM routing declarativo). Em Q3/Q4 2026, merge dos dois em `healthcare` plugin
do Sofia central.

**Decisão**: Íris continua standalone ConnectaIACare. Novos agentes seguem
pattern portável.

### 3.2 Database isolado por produto
**Opus (ADR-003)**: DB separado por produto.
**Code**: concordo — em saúde com LGPD Art. 11, isolamento físico é melhor
defensável que lógico. B2C nasce com `sofiacuida_b2c_db` à parte.

### 3.3 Prioridade da rede comunitária
**Chat**: Onda 10 (cedo).
**Code**: **Fase 2.C** (6-12 meses). Exige:
- Parecer jurídico sobre responsabilidade (ConnectaIACare facilitadora ≠ prestadora de socorro)
- Onboarding com consent formal + termos de responsabilidade
- Modelo de incentivo (desconto, meses grátis, gamification)
- UX de acionamento no respondente
- LGPD de compartilhamento de localização do idoso com "estranhos"
- Integração com portarias condominiais

Implementar a infra técnica (PostGIS, matching) antes, ativar depois.

### 3.4 Teleconsulta no plano mensal fixo
**Chat**: 1/mês incluída no Premium R$149,90.
**Code**: **margem negativa**. Custo real (Opus + Sonnet + Deepgram + LiveKit +
médico humano a R$80-120/consulta de 15min) estoura os R$149,90 se 50% dos
clientes Premium usarem 1 vez/mês.

**Contraproposta**:
- Plano Premium **não inclui** teleconsulta; inclui Atente 24h + motor de
  medicamentos completo + biomarkers.
- Teleconsulta **avulsa paga** R$80 (mercado R$150-200, valor-percebido alto).
- Pacotes pós-demo: "3 teleconsultas/trimestre" por R$199 etc.

### 3.5 Biomarkers de voz — claim regulatório
**Chat**: mencionou que precisa validação científica local.
**Code**: vai mais fundo. ANVISA RDC 657/2022 classifica software de saúde
como SaMD (Software as a Medical Device). Claims **diagnósticos** ("detecta
Alzheimer", "sinaliza depressão") exigem registro e ensaios clínicos.

**Decisão de produto**: implementar como **"monitoramento de padrões de fala"
— descritivo, não diagnóstico**. Relatório ao médico mostra "velocidade de
fala caiu 12% nas últimas 8 semanas, pausas aumentaram 18%". A interpretação
fica com o médico. Isso evita registro SaMD e mantém o diferencial.

---

## 4. Gaps estruturais do código atual (bloqueiam B2C hoje)

Este é o maior complemento que eu (Claude Code) adiciono — o Chat não enxergou
porque não está no código. Inventário objetivo:

| # | Gap | Arquivo/Tabela | Impacto | Esforço |
|---|-----|----------------|---------|---------|
| 1 | Pipeline 100% reativo | `src/handlers/pipeline.py` | Idoso precisa iniciar conversa — B2C exige inverso | ~8h |
| 2 | Enrollment só `caregiver_id` | `aia_health_voice_embeddings` | Bloqueia identify paciente e familiar | ~4h migration + 4h service |
| 3 | `aia_health_patients.phone` não existe | Schema | Sofia não liga pro idoso diretamente | 2h |
| 4 | Sem geolocalização paciente | Schema | Rede comunitária impossível | 2h + PostGIS |
| 5 | Alergias/condições texto livre | `aia_health_patients.allergies[]` | Cruzamento med × condição frágil | 1 semana (vocabulário controlado) |
| 6 | Zero infra billing | N/A | Impossível cobrar B2C | 2-3 semanas |
| 7 | Checkin só `care_events` ativos | `src/services/checkin_scheduler.py` | Proativo diário exige scheduler cron-style independente | ~8h |
| 8 | Consent LGPD B2C não-existente | N/A | Assinatura click-wrap + versionado | ~1 dia |
| 9 | Evolution API mono-instância | Shared com ConnectaIA | Não escala pra 10k+ B2C | Migração WhatsApp Cloud API ~3 dias |
| 10 | Sem modelo payer ≠ beneficiary | Schema | Filho paga pra mãe usar | 4h migration |

**Total mínimo viável B2C MVP**: ~3-4 semanas full-time (sem billing: 2 sem).

---

## 5. Priorização revisada (contraproposta ao Chat)

### Fase 1 — B2B MVP (**agora**)
Concluir Onda 4 (portal paciente — em produção hoje). Preparar demo 28/04
com cenário end-to-end. Dados de piloto (10 SPAs, 30 dias) geram as métricas
que o pitch B2C precisa: tempo médio de resposta, % classificação correta,
satisfação cuidador, redução de falsos alarmes.

### Fase 2.A — B2C MVP Essencial (3 meses pós-B2B)
Objetivo: lançamento do plano R$49,90 apenas. Funciona pra 1k-5k clientes.

1. Migrations 008 (`aia_health_subjects` polimórfico) + 009 (phone + geo PostGIS)
2. Scheduler proativo: `aia_health_proactive_schedules` + worker cron
3. Pipeline subject-aware: aceita áudio com `subject_type="patient"`
4. Enrollment voz paciente (extensão do módulo Onda 5 planejado com Opus)
5. Onboarding WhatsApp conversacional com Sofia (cadastro de nome, contatos,
   medicações auto-declaradas, consent de voz, geo opcional)
6. Check-in diário: manhã 09h → "Bom dia, como dormiu?" com botões rápidos
7. Escalação: família (3 contatos, 5min cada) → Atente (humana)
8. Grupo familiar como **feed passivo individual** (Sofia envia resumo
   individual via DM pra cada familiar, não grupo WhatsApp nativo — evita
   limite multi-grupo da Evolution)
9. Relatório **semanal** pra cuidador pagante (e-mail + WhatsApp)
10. Billing Stripe/PagSeguro: SKU Essencial R$49,90, trial 14 dias,
    webhook de recurring, dunning básico, cancelamento self-service

### Fase 2.B — Diferenciação (meses 4-6)
11. Motor de medicamentos 5 camadas (ampliação do validator atual)
12. Biomarkers de voz (feature **descritiva**, não diagnóstica)
13. Plano Família R$89,90 (adiciona biomarkers, mais contatos, prioridade Atente)
14. Teleconsulta avulsa paga R$80
15. Consent LGPD versionado self-service

### Fase 2.C — Ecosystem (meses 6-12)
16. Rede comunitária georreferenciada (Plano Premium — com parecer jurídico)
17. Integração Apple Watch fall detection
18. Integração wearables abertos (BLE + API)
19. API pública pra fabricantes SOS integrarem
20. Canal operadora de saúde (white-label ou co-branding)

### Fase 3 — Plataforma (12-18 meses)
21. Marketplace (farmácias, laboratórios, fisio)
22. API prefeituras (programas sociais de monitoramento)
23. Internacionalização Portugal + LATAM
24. Modelo hospital-at-home com reembolso ANS

---

## 6. Itens críticos que nem o Opus nem o Chat cobriram

### 6.1 Modelo de billing sofisticado desde dia 1
- **Payer ≠ beneficiary**: filho paga, mãe usa. Schema com `payer_id` +
  `beneficiary_id` (1 pagante → N beneficiários, seat-based).
- **Múltiplos idosos por pagante**: filho monitora mãe + sogra no mesmo billing.
- **Upgrade emergencial**: idoso piorou agudamente, família faz upgrade no
  ato pra acesso Atente 24h. Billing precisa **proration no dia**.
- **Trial 14 dias + dunning** (retry de pagamento falho).
- **Downgrade e cancelamento self-service** (LGPD + CDC).

### 6.2 Retenção e prova de valor
- Risco B2C não é **conquistar**, é **manter**. Filho que pagou em março
  cancela em junho se não viu valor tangível.
- **Relatório semanal** (não diário, diário satura): "Mãe teve 7 dias com
  check-ins respondidos, humor estável, 1 evento de atenção resolvido sem
  escalação."
- Métrica de "engagement do cuidador pagante" (abriu portal? leu resumo?)
  como early warning de churn.
- Gamification leve: badges ("Mãe não faltou a 1 check-in em 30 dias")
  — humano responde a isso.

### 6.3 Canais de aquisição B2C específicos ao Brasil
(complementar aos do Chat)
- **Sindicatos de aposentados** (SINDINAPI, SINSEP): desconto em folha,
  base CNPJ, negociação institucional
- **Condomínios alto padrão com população idosa**: parceria com
  administradoras, porteiro como ponto de contato
- **Imobiliárias residencial sênior**
- **Planos funerários** (PlanoSerra, Capemisa): cross-sell natural
- **Farmácias de manipulação**: base polifarmacêutica
- **Meta/Google Ads segmentado**: "filho 45-55 preocupa com mãe/pai sozinho"
- **Clínicas geriátricas privadas**: canal afiliado com indicação paga

### 6.4 Fraude e validação
- Idoso fake pra usar IA grátis → verificação no ato da assinatura (CPF + RG
  ou selfie com documento via BigID/Unico).
- Parentesco dos contatos de emergência (não rigoroso, razoável — LGPD Art. 7 VI).
- Rate-limit de eventos por paciente por dia (detecção de abuso).

### 6.5 Evolution API não escala 10k+ B2C
- Hoje compartilhada com ConnectaIA comercial.
- B2C com 10k clientes × 1 check-in/dia = 10k msgs/dia saindo → estoura
  limites Evolution.
- **Migrar pra WhatsApp Cloud API (Meta oficial)** — conformidade +
  volume + templates aprovados. 3 dias de trabalho, mas fundamental
  antes de escalar.

### 6.6 Canibalização B2B ↔ B2C
- Risco: SPA/hospital descobre que família pode contratar R$49,90 direto
  → não precisa comprar B2B R$80-150.
- **Mitigação**: B2B tem features exclusivas — dashboard médico compartilhado,
  integração TotalCare, FHIR pra prontuário hospitalar, equipe multidisciplinar,
  SLA contratual, BI clínico agregado. **Não é o mesmo produto**, só o motor.
- Contrato B2B pode inclusive **oferecer desconto B2C** aos familiares
  dos assistidos (cross-sell natural, ancoragem institucional).

### 6.7 Posicionamento regulatório dos biomarkers
- Implementar como **"monitoramento de padrões de fala"** (descritivo).
- Relatório ao médico: dados objetivos (velocidade, pausas, jitter, shimmer).
- **Nunca** afirmar diagnóstico. A interpretação clínica é do médico.
- Isso evita RDC 657/2022 (SaMD) + mantém diferencial.

### 6.8 Hábito do idoso — fator mais ignorado
- "Instalou o app" não significa nada. Hábito é o risco de receita.
- **O grupo familiar é o gancho**: quem cobra do idoso responder é a família.
- **Sofia Voz proativa** (ligar em vez de só WhatsApp) acomoda idosos com
  baixa alfabetização digital.
- Fonte grande, botões simples, sem digitação.
- Áudio como resposta aceita (e transcrita).

---

## 7. Arquitetura técnica do B2C (decisões)

### 7.1 Tabelas novas
```sql
-- Subjects polimórfico (unifica paciente, cuidador, familiar)
CREATE TABLE aia_health_subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    subject_type TEXT NOT NULL CHECK (subject_type IN
        ('patient', 'caregiver_pro', 'family_member', 'community_responder')),
    full_name TEXT NOT NULL,
    nickname TEXT,
    phone TEXT,
    birth_date DATE,
    -- Relações
    related_to_subject_id UUID REFERENCES aia_health_subjects(id),
    relationship_type TEXT, -- 'filho', 'conjuge', 'cuidador_contratado'
    -- Geo
    latitude NUMERIC(10,8),
    longitude NUMERIC(11,8),
    address TEXT,
    -- Onboarding B2C
    cpf_hash TEXT,
    consent_signed_at TIMESTAMPTZ,
    consent_version TEXT,
    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE
);

-- Check-ins proativos (scheduler cron-style)
CREATE TABLE aia_health_proactive_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    subject_id UUID NOT NULL REFERENCES aia_health_subjects(id),
    schedule_type TEXT NOT NULL, -- 'daily_morning', 'daily_evening', 'medication_reminder'
    cron_expression TEXT NOT NULL,
    channel TEXT DEFAULT 'whatsapp' CHECK (channel IN ('whatsapp', 'voice_call', 'both')),
    template_id TEXT,
    active BOOLEAN DEFAULT TRUE,
    last_executed_at TIMESTAMPTZ,
    last_response_at TIMESTAMPTZ,
    consecutive_no_response INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Billing (simplificado — SKUs e assinaturas)
CREATE TABLE aia_health_subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    payer_subject_id UUID NOT NULL REFERENCES aia_health_subjects(id),
    beneficiary_subject_ids UUID[] NOT NULL, -- pode ter múltiplos idosos
    plan_sku TEXT NOT NULL, -- 'essencial', 'familia', 'premium', 'premium_device'
    status TEXT NOT NULL, -- 'trial', 'active', 'past_due', 'cancelled'
    started_at TIMESTAMPTZ NOT NULL,
    trial_ends_at TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    stripe_subscription_id TEXT,
    cancelled_at TIMESTAMPTZ,
    cancel_reason TEXT
);

-- Community responders (rede comunitária, pra Fase 2.C)
CREATE TABLE aia_health_community_responders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL,
    subject_id UUID NOT NULL REFERENCES aia_health_subjects(id),
    availability JSONB, -- horários disponíveis
    skills TEXT[], -- ['primeiros_socorros', 'enfermagem']
    response_rate NUMERIC, -- % de respostas quando acionado
    last_response_at TIMESTAMPTZ,
    consent_version TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Indexed by PostGIS geography (calculado a partir de lat/lng do subject)
```

### 7.2 Migrações incrementais necessárias
- **008_subjects_polymorphic.sql** (Fase 2.A)
- **009_phone_geolocation.sql** (Fase 2.A, PostGIS)
- **010_proactive_schedules.sql** (Fase 2.A)
- **011_subscriptions_billing.sql** (Fase 2.A)
- **012_consent_versioned.sql** (Fase 2.B)
- **013_speech_biomarkers.sql** (Fase 2.B, features acústicas)
- **014_medication_intelligence.sql** (Fase 2.B, 5 camadas)
- **015_community_responders.sql** (Fase 2.C)

---

## 8. Recomendações ao Opus na próxima sessão

1. **NÃO refatorar Íris agora**. Implementar novos agentes com pattern portável
   (`BaseSubAgent` + `tool_registry` + LLM routing declarativo) pra facilitar
   merge futuro com Sofia central.

2. **Priorizar Fase 2.A (B2C MVP Essencial)** após demo B2B. Rede comunitária
   e teleconsulta no plano fixo ficam pra Fase 2.C.

3. **Implementar modelo `aia_health_subjects` polimórfico** unificando
   paciente/cuidador/familiar. Migration 008 é pré-requisito de quase tudo.

4. **Scheduler proativo independente** do `checkin_scheduler` atual (que só
   opera dentro de care_events). Novo worker cron lê `proactive_schedules`.

5. **Biomarkers de voz como "padrões de fala" (descritivo)**, nunca diagnóstico.
   Evita ANVISA RDC 657.

6. **Teleconsulta avulsa paga R$80**, não incluída no plano mensal.

7. **Migrar WhatsApp Evolution → Cloud API (Meta oficial)** antes de escalar B2C.

8. **Billing desde dia 1 com `payer_id` ≠ `beneficiary_id`** + proration.

9. **Rede comunitária**: implementar infra técnica (PostGIS, matching),
   manter feature desligada até parecer jurídico aprovado.

10. **Relatório semanal** é feature de retenção, não análise clínica.
    Foco em linguagem acolhedora para filho/família.

---

## 9. Visão editorial (executive summary pra apresentação)

### Tamanho da oportunidade
- 57 milhões de idosos no Brasil em 2040
- SUS não aguenta carga
- Home care privado: R$500-2000/mês (inacessível)
- **Gap**: precisa de cuidado × tem acesso a cuidado é gigantesco
- ConnectaIACare fecha o gap com tech + comunidade + Atente

### Por que esse é o momento
- WhatsApp: 98% dos brasileiros 60+ usam
- IA conversacional: só agora boa o suficiente em português
- LGPD: regulação estabilizada
- FHIR: interoperabilidade hospitalar finalmente viável
- Wearables baratos: Apple Watch + Mi Band + pulseiras genéricas

### Por que esse time
- Alexandre + Milene: operação Atente já rodando (fallback humano caro e difícil)
- Parceria Tecnosenior: dispositivos + base instalada
- Stack vertical IA em produção (não MVP)
- ConnectaIA comercial valida modelo de SaaS vertical

### Moats únicos
1. **Central humana 24h própria** (Atente) — ninguém tem
2. **Stack vertical healthcare em produção** — não é PoC
3. **Rede comunitária georreferenciada** — inovação mundial
4. **Pricing acessível** — democratiza monitoramento
5. **Integração multi-dispositivo aberta** — não locked em hardware

### Entrega de valor
- B2B (hoje): SPA reduz reinternação, compliance CFM, eficiência cuidador
- B2C (fase 2): família tem paz de espírito, idoso tem dignidade e autonomia

---

## 10. Checklist para sessão com Opus

- [ ] Confirmar que Íris segue standalone, novos agentes com pattern portável
- [ ] Criar issue épica **Fase 2.A — B2C MVP Essencial**
- [ ] Migrations 008-011 especificadas
- [ ] Definir SKUs Essencial/Família/Premium no código antes do billing
- [ ] Arquitetura do scheduler proativo cron-style
- [ ] Decisão sobre WhatsApp Cloud API (migração ou ponte Evolution)
- [ ] Parecer jurídico solicitado para rede comunitária
- [ ] Canais de aquisição B2C mapeados (sindicatos, condomínios, planos funerários)
- [ ] Estrutura de relatório semanal (template conversacional)

---

**Fim do plano.** Três autores, uma convergência: o produto é grande, a oportunidade é urgente, e o piloto B2B de 30 dias vai validar o que precisa pro B2C viral.
