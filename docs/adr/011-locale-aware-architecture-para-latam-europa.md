# ADR-011: Arquitetura locale-aware desde o dia 1 (LATAM + Europa)

- **Date**: 2026-04-19
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: architecture, i18n, compliance, internationalization

## Context and Problem Statement

Estratégia comercial do ConnectaIACare prevê expansão:
1. **Brasil (Q2-Q3 2026)** — Tecnosenior + Amparo + Grupo Vita → Português
2. **LATAM (Q4 2026 - Q2 2027)** — Argentina, Chile, México, Colômbia → Espanhol (variantes por país)
3. **Europa (2027+)** — Portugal, Espanha, Reino Unido, Alemanha → Português Europeu, Espanhol Europeu, Inglês, Alemão

Hoje o código está **hard-coded pt-BR** em todos os lugares: prompts, mensagens WhatsApp, labels de classificação, config Deepgram, labels do dashboard. Precisamos decidir **agora** se:
- Preparar arquitetura locale-aware desde o dia 1 (custo médio agora, zero retrabalho depois)
- Ou manter pt-BR puro no MVP e internacionalizar quando precisar (custo baixo agora, retrabalho alto depois)

## Decision Drivers

- **Custo de retrabalho**: i18n retroativo em 30+ arquivos + schema migrations + prompt templating + compliance é tipicamente 5-10× o custo de preparar upfront
- **Compliance varia por país, não por idioma**: Brasil (LGPD), Argentina (Ley 25.326), México (LFPDPPP), Chile (Ley 19.628), UE (GDPR, muito mais rígido que LGPD). `locale = language + country` é o conceito certo, não só idioma
- **Dados clínicos variam por país**: códigos ICD-10 são universais, mas nomes comerciais de medicamentos, dosagens, e normas de prescrição variam
- **Deepgram suporta nativamente**: `pt-BR`, `es`, `en-US`, `en-GB`, `it`, `fr`, `de` — sem esforço adicional
- **Resemblyzer é language-agnostic**: embeddings de voz funcionam independente do idioma falado
- **Prompts Claude**: modelos Anthropic funcionam bem em português e espanhol; inglês é default; outras línguas precisam de tuning
- **Regulatory AI**: CFM 2.314/2022 (Brasil) vs normas espanholas vs GDPR AI Act (EU 2024) — arquitetura deve suportar matriz de controles por país
- **Time-to-market**: MVP ainda é pt-BR only, mas a **estrutura de código** permite expansão sem refactor

## Considered Options

- **Option A**: pt-BR puro agora, i18n reativo quando precisar
- **Option B**: Arquitetura locale-aware com pt-BR como único locale ativo no MVP (escolhida)
- **Option C**: Full i18n com múltiplos locales ativos no dia 1

## Decision Outcome

Chosen option: **Option B — Arquitetura locale-aware desde o dia 1, pt-BR como único locale ativo no MVP, expansão incremental LATAM 2026 → Europa 2027**, porque o custo incremental é baixo (~10% de esforço) e evita refactor massivo. Implementação é incremental: estrutura agora, conteúdo traduzido depois.

### Positive Consequences

- **Zero retrabalho estrutural** quando ativar novo locale — só adicionar conteúdo traduzido
- **Compliance matrix por país** já modelada desde o início
- **Data model preparado**: cada registro sabe seu locale de origem
- **Prompts template-driven**: modelo claro para tradução profissional (não auto-translate)
- **GDPR ready**: quando entrar na Europa, já temos estrutura para controles mais rígidos
- **Onboarding de tenants internacionais** vira questão de conteúdo, não de código

### Negative Consequences

- ~10% esforço adicional no desenvolvimento inicial (tradução via chaves, não strings inline)
- Disciplina constante: novo código deve respeitar o padrão
- Prompts templatizados são ligeiramente mais verbosos (mas mais testáveis)
- Dashboard precisa de biblioteca de i18n (`next-intl`) mesmo com 1 locale ativo

## Pros and Cons of the Options

### Option A — pt-BR puro, i18n reativo ❌

- ✅ MVP 10% mais rápido
- ❌ Refactor futuro em 30+ arquivos
- ❌ Schema migrations complexas (adicionar `locale` em N tabelas já populadas)
- ❌ Prompts hard-coded exigem re-escrita total
- ❌ Compliance matrix retroativa é pesadelo

### Option B — Locale-aware, pt-BR único ativo ✅ Chosen

- ✅ Estrutura preparada, expansão incremental
- ✅ Custo upfront pequeno
- ✅ Ativação de novo locale = trabalho de conteúdo, não de código
- ❌ +10% esforço inicial
- ❌ Disciplina constante

### Option C — Full i18n com múltiplos locales ativos

- ✅ Pronto para qualquer mercado no dia 1
- ❌ Custos de tradução profissional de conteúdo clínico antes de ter clientes
- ❌ Testes e QA multiplicados por N locales
- ❌ Divergência de comportamento esperado (o que rola em pt-BR é fonte de verdade?)

## Design Decisions

### 1. Modelo de dados — adicionar `locale` em tabelas que contêm texto ou dependem de país

```sql
-- Proposta (a implementar em migration futura):

-- Tenant ganha locale default + country (regulatory profile)
ALTER TABLE aia_health_tenants  -- tabela a criar
    ADD COLUMN locale TEXT NOT NULL DEFAULT 'pt-BR',
    ADD COLUMN country TEXT NOT NULL DEFAULT 'BR',
    ADD COLUMN regulatory_profile TEXT NOT NULL DEFAULT 'lgpd_cfm_anvisa';

-- Paciente pode ter locale preferido (para futuro de comunicação direta)
ALTER TABLE aia_health_patients
    ADD COLUMN preferred_locale TEXT DEFAULT 'pt-BR';

-- Relato guarda o locale em que foi feito (útil para análise retroativa)
ALTER TABLE aia_health_reports
    ADD COLUMN locale TEXT NOT NULL DEFAULT 'pt-BR';
```

### 2. Prompts templatizados por locale

Arquivo `src/prompts/clinical_analysis.py` evolui de:
```python
SYSTEM_PROMPT = """Você é um assistente..."""
```

Para:
```python
SYSTEM_PROMPTS = {
    "pt-BR": """Você é um assistente de enfermagem geriátrica...""",
    "es-AR": """Eres un asistente de enfermería geriátrica...""",  # quando ativar
    "en-GB": """You are a geriatric nursing assistant...""",       # quando ativar
}

def get_system_prompt(locale: str = "pt-BR") -> str:
    return SYSTEM_PROMPTS.get(locale, SYSTEM_PROMPTS["pt-BR"])
```

Tradução de prompt clínico é tarefa de **especialista médico nativo** no idioma — não usar tradução automática.

### 3. Deepgram — config por locale

```python
DEEPGRAM_LANG = {
    "pt-BR": "pt-BR",
    "es-AR": "es",
    "es-MX": "es",
    "en-GB": "en-GB",
    "en-US": "en-US",
    "it-IT": "it",
    "de-DE": "de",
}
```

### 4. Classification labels por locale

```python
CLASSIFICATION_LABELS = {
    "pt-BR": {"routine": "ROTINA", "attention": "ATENÇÃO", "urgent": "URGENTE", "critical": "CRÍTICO"},
    "es-AR": {"routine": "RUTINA", "attention": "ATENCIÓN", "urgent": "URGENTE", "critical": "CRÍTICO"},
    "en-GB": {"routine": "ROUTINE", "attention": "ATTENTION", "urgent": "URGENT", "critical": "CRITICAL"},
}
```

### 5. Regulatory matrix por país

```python
# backend/config/compliance.py (a criar)
REGULATORY_PROFILES = {
    "BR": {
        "data_protection": "lgpd",
        "medical_regulator": "cfm_2314_2022",
        "device_regulator": "anvisa",
        "retention_policy": {"audio_raw": 90, "transcription": -1, "audit": 1825},  # dias, -1 = indefinido
        "consent_base": "art_11_paragraph_2_ii_f",
        "data_residency": "br",
    },
    "AR": {
        "data_protection": "ley_25326",
        "medical_regulator": "ansm",
        "device_regulator": "anmat",
        "retention_policy": {"audio_raw": 60, "transcription": -1, "audit": 1825},
        "data_residency": "ar",  # ou eu se autorizado
    },
    "ES": {
        "data_protection": "gdpr_lopdgdd",
        "medical_regulator": "cgmge",
        "device_regulator": "aemps",
        "retention_policy": {"audio_raw": 30, "transcription": -1, "audit": 1825},
        "data_residency": "eu",
    },
    # ...
}
```

### 6. Frontend i18n

- Biblioteca: `next-intl` (App Router compatível)
- Estrutura: `messages/pt-BR.json`, `messages/es-AR.json`, etc.
- Routing: sem prefixo de locale no MVP (1 locale); adicionar `[locale]/...` quando expandir

### 7. Detecção de locale

Ordem de precedência:
1. Explicit: parâmetro na request ou header `Accept-Language`
2. User profile: `preferred_locale` do paciente/cuidador
3. Tenant default: `locale` do tenant
4. Fallback: `pt-BR`

## Implementação faseada

| Fase | Quando | Entrega |
|------|--------|---------|
| **Fase 0 — Estrutural** | Próxima sprint (P1) | Migrations adicionando colunas `locale`, `country`; prompts em dict com 1 entrada; função `get_prompt(locale)`; regulatory matrix BR |
| **Fase 1 — LATAM piloto** | Q4 2026 | Ativar `es-AR`: tradução de prompts (com especialista médico argentino), classification labels, mensagens WhatsApp, regulatory profile Argentina |
| **Fase 2 — LATAM expansão** | Q1-Q2 2027 | `es-MX`, `es-CL`, `es-CO`: reuso de tradução `es-AR` com adaptações locais |
| **Fase 3 — Europa piloto** | Q3 2027 | `pt-PT`, `es-ES`: variantes europeias do português/espanhol. GDPR compliance implementada |
| **Fase 4 — Europa expansão** | 2028 | `en-GB`, `de-DE`, `it-IT`, `fr-FR`: línguas novas com modelos clínicos específicos |

## When to Revisit

- Se Tecnosenior quiser expansão Argentina/Chile antes de 2027 — adiantar Fase 1
- Se houver parceria com rede hospitalar espanhola — adiantar Fase 3
- Se a Anthropic lançar modelos multi-locale nativos que simplifiquem prompts (ex: "Claude pt" vs "Claude es") — revisitar arquitetura de prompts
- Se aparecer requisito de variante regional que não prevemos (ex: `pt-AO` Angolano para expansão africana)

## Non-goals (explicit)

- **NÃO fazer tradução automática de conteúdo clínico** — risco de erro médico. Tradução é sempre humano-revisada.
- **NÃO detectar idioma do áudio em tempo real no MVP** — locale é config do tenant/paciente; expansão futura.
- **NÃO internacionalizar documentação interna** (esta ADR, CLAUDE.md, etc.) — continuam em pt-BR, são para time interno.

## Links

- Documentação: [INFRASTRUCTURE.md](../../INFRASTRUCTURE.md) — seção de i18n a adicionar
- Relacionado: [ADR-010](010-multi-tenant-desde-o-dia-1.md) — multi-tenant + locale é o modelo completo
- Referência externa: [next-intl](https://next-intl-docs.vercel.app/), [GDPR vs LGPD comparison](https://gdpr.eu/what-is-gdpr/)
