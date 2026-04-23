# Pitch — Esteira Visual de Credibilidade Técnica

> **Posicionamento**: slides que rodam ANTES da demo ao vivo pra estabelecer
> "isso não é MVP de startup, é infraestrutura de saúde pronta."
>
> **Formato**: 6 slides densos visualmente (30-45s cada, 3-4 min total).
> **Handoff pra Opus Design**: este documento é spec visual — ele transforma em HTML.
>
> **Timing na apresentação**:
>   - Slide 3-4 (contexto do produto) → estes 6 slides (credibilidade técnica)
>   - Depois → demo ao vivo da plataforma (Alexandre narra)

---

## 🎬 Slide T1 — "Não começamos ontem"

**Headline**: **Infraestrutura pronta para escala regulatória do dia 1.**

**Visual central**: timeline horizontal com 4 marcos:

```
COMMIT 0              HOJE                    6 MESES              18 MESES
   ●                    ●                         ○                    ○
Multi-tenant    331 testes          FHIR export ativo     HIPAA / GDPR
Multi-locale    13 migrations       SOC 2 audit           LatAm 3 países
                7 ADRs publicados   ISO 13485 roadmap     US compliance
```

**Side cards (3 números grandes):**
- **331** testes automatizados verdes
- **13** migrações de schema versionadas
- **7** decisões arquiteturais formalizadas (ADRs)

**Subtexto pequeno**: "Cada linha de código revisada, cada decisão documentada, cada mudança rastreável."

---

## 🎬 Slide T2 — "Compliance como base, não como adendo"

**Headline**: **4 marcos regulatórios brasileiros embutidos na arquitetura.**

**Layout**: grid 2×2 de cards, cada card com emoji + norma + 1 linha de implementação:

```
┌─────────────────────────────────┬─────────────────────────────────┐
│  🛡️  LGPD                        │  ⚕️  CFM 2.314/2022              │
│  Lei 13.709/2018                 │  Telemedicina + IA em saúde      │
│  ─────────                       │  ─────────                       │
│  • Criptografia fim-a-fim        │  • IA nunca diagnostica          │
│  • Consent versionado            │  • IA nunca prescreve            │
│  • Audit chain imutável          │  • Constituição Sofia no prompt  │
│  • DPO nomeado + ANPD-ready      │  • Médicos CRM ativo             │
├─────────────────────────────────┼─────────────────────────────────┤
│  👴  Estatuto do Idoso           │  🛒  CDC                         │
│  Lei 10.741/2003                 │  Lei 8.078/1990                  │
│  ─────────                       │  ─────────                       │
│  • Detector de elder abuse       │  • 7 dias arrependimento         │
│  • Escala Disque 100 em <60s     │  • Zero fidelidade               │
│  • Autonomia do idoso preservada │  • Cancelamento livre             │
│  • Payer ≠ beneficiary           │  • Preço transparente            │
└─────────────────────────────────┴─────────────────────────────────┘
```

**Badge no canto**: **"ANVISA RDC 657/2022 — Classe B"** (SaMD software clínico de apoio).

**Subtexto**: "Quando a norma muda, mudamos 1 configuração. Não refatoramos sistema."

---

## 🎬 Slide T3 — "Preparados pra falar a língua da saúde global"

**Headline**: **FHIR HL7 é nosso padrão interno, não um adaptador.**

**Visual principal**: diagrama de arquitetura com seta de mapeamento:

```
┌──────────────────────────┐         ┌──────────────────────────┐
│   Schema ConnectaIACare  │    →    │        FHIR R4           │
├──────────────────────────┤         ├──────────────────────────┤
│ aia_health_patients      │    →    │ Patient                  │
│ aia_health_caregivers    │    →    │ Practitioner             │
│ aia_health_vital_signs   │    →    │ Observation (LOINC)      │
│ aia_health_reports       │    →    │ Observation + Communic.  │
│ aia_health_care_events   │    →    │ Encounter (virtual)      │
│ aia_health_medication_*  │    →    │ Medication* (RxNorm)     │
│ aia_health_teleconsulta  │    →    │ Encounter + DocumentRef  │
└──────────────────────────┘         └──────────────────────────┘
```

**Linha central grande**: **"LOINC-aligned desde commit zero · SNOMED-CT em onda C · CID-10 importado"**

**3 selos à direita**:
- ✅ **Exportador FHIR $everything** — roadmap Q3/2026
- ✅ **Terminologias**: LOINC · CID-10 · SNOMED BR · RxNorm
- ✅ **Integração TASY / Philips / Unimed** — FHIR bridge pronta

---

## 🎬 Slide T4 — "Pronto pra LatAm, Europa e EUA"

**Headline**: **Uma plataforma, múltiplas jurisdições.**

**Visual**: mapa-múndi com **pins coloridos por readiness level**:

```
  🇧🇷 Brasil              — 100% ativo (produção)
  🇦🇷 Argentina           — 95% ready (Lei 25.326 + GDPR-adequated)
  🇲🇽 México              — 90% ready (LFPDPPP ≈ LGPD)
  🇨🇴 Colômbia            — 90% ready (Lei 1581)
  🇨🇱 Chile               — 85% ready (Lei 19.628 modernização)
  🇵🇹 Portugal / 🇪🇺 UE    — 75% ready (GDPR 90% overlap LGPD)
  🇺🇸 EUA                 — 60% ready (HIPAA estrutural, falta SOC 2)
```

**Grid de 4 features na base**:

```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│  🌐 Multi-tenant │  🗣️  Multi-locale │  💱 Multi-moeda  │  📍 Data resid.  │
│  desde dia 1     │  BCP-47 + ICU    │  ISO 4217        │  por região     │
│  (ADR-010)       │  (ADR-011)       │  BRL·MXN·USD·EUR │  (BR/EU/US)     │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

**Subtexto forte**: **"8-12 semanas pra lançar em novo país. Sem refatoração."**

---

## 🎬 Slide T5 — "Vendor-agnostic por design"

**Headline**: **Nunca reféns de fornecedor de IA.**

**Visual**: diagrama de router com flechas de fallback:

```
             ┌─────────────────────┐
             │  LLM Router         │
             │  (por tarefa)       │
             └──────────┬──────────┘
                        │
        ┌───────────────┼───────────────┬─────────────┐
        ▼               ▼               ▼             ▼
    ┌────────┐    ┌────────┐    ┌─────────┐   ┌────────┐
    │ Claude │    │ OpenAI │    │ Gemini  │   │ Deep-  │
    │ Sonnet │    │ GPT-5.4│    │ 2.5     │   │ Seek   │
    └───┬────┘    └───┬────┘    └────┬────┘   └────────┘
        │             │              │
      SOAP         Weekly       Visão (OCR)
   Clínico       Report       Price search
   Rx Valid.    Intent Cls.    Embedding

   ──fallback──▶  ──fallback──▶  ──fallback──▶
```

**3 proposições de valor**:
- **Custo otimizado por tarefa** — tarefa simples usa modelo barato, tarefa crítica usa modelo top
- **Fallback cascade** — 1 provedor cai, outro entra, usuário nem percebe
- **Migração em 1 config** — troca YAML, restart container, zero code change

**Número destacado**: **$15-53/mês** custo real LLM atual (vs $300-500/mês se tudo Claude)

---

## 🎬 Slide T6 — "Integrações: o que já pluga hoje"

**Headline**: **Ecossistema aberto — já conversamos com tudo que importa.**

**Visual**: hub central "ConnectaIACare" com **rosas de integração** em 4 categorias:

```
                    ┌──────── AFERIÇÃO ─────────┐
                    │                           │
                    │  🎤 Deepgram (STT pt-BR) │
                    │  🔊 ElevenLabs (TTS)     │
                    │  🎙️  Resemblyzer (bio voz)│
                    │  ⌚ Apple Health         │
                    │  🟢 Android Health       │
                    │  📟 Tecnosenior IoT      │
                    │  🏥 MedMonitor           │
                    │                           │
                    └───────────────────────────┘
                                 │
┌───── CANAIS ──────┐           │           ┌─── INSTITUCIONAL ──┐
│                   │           │           │                    │
│  💬 WhatsApp      │           │           │  🚨 CVV 188        │
│  🔊 Alexa (Q4)    │ ──── ConnectaIACare ──┤  📞 Disque 100     │
│  📞 Voice (Q4)    │                       │  🚑 SAMU 192       │
│  🌐 Web           │                       │  ⚕️  CFM            │
│                   │           │           │                    │
└───────────────────┘           │           └────────────────────┘
                                 │
                    ┌──── COMPLEMENTARES ───────┐
                    │                           │
                    │  💳 Asaas + MP (PSP)     │
                    │  📹 LiveKit WebRTC       │
                    │  🗺️  Google Workspace    │
                    │  🔐 Anthropic + OpenAI   │
                    │                           │
                    └───────────────────────────┘
```

**Selo inferior**: **"FHIR HL7 bridge ativa pra operadoras de saúde, ILPIs, hospitais, SUS (roadmap 2027)"**

---

## 🎬 Slide T7 (opcional, se tiver tempo) — "Porque isso importa"

**Headline animada, 1 frase**: **"Não é sobre IA. É sobre cuidado com infraestrutura séria o suficiente pra sustentar 10 milhões de idosos."**

**Visual**: número crescente animado 31M → 57M (idosos no BR 2025 → 2040).

**Callout em negrito**: **"O mercado vai dobrar. A tecnologia tem que estar pronta antes."**

**Transição pra demo**: "Agora deixa eu te mostrar isso funcionando."

---

## 📋 Instruções pro Opus Design

### Timing e ritmo
- Cada slide: 30-45s de narração (Alexandre)
- Total: ~4 min antes da demo ao vivo
- Animações rápidas (fade-up, count-up números) — nunca lentas
- Evitar transições exóticas — foco no conteúdo

### Design system
- Reusar **glass-card + accent-gradient** do design system existente
- Slide T2 grid 2×2 de compliance: **glass-card + border colorida por norma**
- Slide T3 diagrama de mapeamento: **linhas em accent-gradient animadas** (flecha preenchendo)
- Slide T4 mapa-múndi: **SVG com pins pulsando** (intensidade = readiness level)
- Slide T5 router LLM: **animação de fallback cascata** (provedor principal verde → seta avança pro fallback laranja → usuário fica verde)
- Slide T6 hub: **radial layout** com ConnectaIACare no centro e 4 clusters orbitando
- Slide T7: **number counter animado** 31M → 57M em 2s

### Tom visual
- Denso mas respiravel (muitos itens, mas cada um com espaço)
- Menos palavras nos slides, mais palavras na narração
- Se a frase couber em 5 palavras, usa 5 palavras, não 15
- Emoji contido — só onde agrega (compliance marcos, categorias)

### Opcional pra wow extra
- Último slide T7 com **contra-regressivo animado** saindo do número "57M idosos em 2040" → aparece UI da plataforma → Alexandre emenda com demo ao vivo

---

## 🗂️ Arquivos relacionados

- **`docs/PITCH_TECH_READINESS.md`** — versão texto densa (anexo/FAQ pro pitch)
- **`docs/PITCH_DECK.md`** — deck principal (slides 1-10 de produto)
- **`exploracoes/html/pitch-tech-slides.html`** ← Design publica aqui
