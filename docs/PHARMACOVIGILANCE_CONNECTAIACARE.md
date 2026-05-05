# Sistema de Farmacovigilância — ConnectaIACare

**Documento técnico-clínico | Maio 2026**
**Destinatário primário:** referência clínica do projeto + potenciais parceiros acadêmicos (Faculdade de Farmácia PUC/RS)
**Confidencialidade:** restrito — descrever em alto nível em apresentações externas

---

## 1. Sumário executivo

A ConnectaIACare é uma plataforma SaaS B2B de assistência clínica integrada com IA, focada em cuidado domiciliar geriátrico. O **módulo de farmacovigilância** é uma das 14 dimensões do motor clínico — responsável por detectar riscos farmacológicos em tempo real durante prescrição, agendamento e relato de cuidador.

Este documento descreve a arquitetura técnica, cobertura atual de dados clínicos, fontes utilizadas, e oportunidades de pesquisa/colaboração.

---

## 2. Arquitetura técnica

### 2.1 Camadas

```
┌────────────────────────────────────────────────────────────────────┐
│ APRESENTAÇÃO                                                       │
│  • Sofia (LLM agent: WhatsApp + voz Grok)                          │
│  • UI admin /admin/governance/clinical-rules (CRUD curador)        │
│  • API mobile/web (medication_routes, teleconsulta_routes)         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ ORQUESTRAÇÃO (drug_safety_service — wrapper alto-nível)            │
│  • evaluate_prescription(med, dose, patient)                        │
│  • safety_review_prescriptions([meds], patient)                     │
│  • detect_cascades_for_patient(patient_id)                         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ MOTORES CANÔNICOS                                                  │
│                                                                    │
│  dose_validator.validate()        cascade_detector.detect_cascades()│
│  ─────────────────────────        ──────────────────────────────── │
│  11 checks integrados              Padrões A+C / A+B+C             │
│  ↓ Cobertura ↓                     com supressão por                │
│                                    contraindicação real            │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE BASE (Postgres + pgvector)                               │
│  9 tabelas especializadas — fontes curadas múltiplas               │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 11 Checks integrados em `dose_validator.validate()`

| # | Check | Fonte primária |
|---|---|---|
| 1 | Alergia (princípio + classe terapêutica + cross-reactivity) | Anvisa + bibliografia |
| 2 | Terapia duplicada (mesma classe / sinergia indesejada) | classes terapêuticas curadas |
| 3 | Polifarmácia (≥5 meds = critério OMS) | OMS + Beers 2023 |
| 4 | Janela terapêutica estreita | Stockley's Drug Interactions |
| 5 | Interações drug-drug + **distanciamento temporal** | Stockley's, Lexicomp, Beers, FDA |
| 6 | Contraindicações por condição clínica (ICD/CID) | Beers 2023 + Anvisa |
| 7 | Carga anticolinérgica (escala ACB) | Anticholinergic Cognitive Burden Scale |
| 8 | Risco de queda | STOPP/START 2023 |
| 9 | Ajuste renal (Cockcroft-Gault implementado) | KDIGO + bula Anvisa |
| 10 | Ajuste hepático | Child-Pugh + bibliografia |
| 11 | Restrições por sinais vitais (PA, FC, glicemia recentes) | manual curado + diretrizes BR |

### 2.3 Cobertura atual (snapshot maio/2026)

| Domínio | Quantidade |
|---|---|
| Drugs únicos cobertos | **142** |
| Princípios ativos com dose limit (≥60 anos) | **151** |
| Interações drug-drug ativas | **93** |
| Drugs com burden anticolinérgico (ACB) | **51** verified |
| Drugs com risco de queda (STOPP) | **38** |
| Ajustes renais cadastrados | **45** |
| Ajustes hepáticos | **166** |
| Aliases (brand → genérico BR) | **109** |
| Cascatas de prescrição (A+C / A+B+C) | **10** |
| Drugs com `food_warning` | subset das 93 interações |
| Interações com `time_separation_minutes` | subset das 93 interações |

**Severidades modeladas**: `block`, `warning_strong`, `warning`, `info` (dose_validator)
+ `contraindicated`, `major`, `moderate`, `minor` (interactions/cascades).

### 2.4 Fontes curadas

| Source | Uso principal | Volume |
|---|---|---|
| **Beers Criteria 2023** (American Geriatrics Society) | dose_avoid_in_elderly + interactions críticas | 16+ flags + 31 interactions |
| **Bulário Anvisa** | dose limits BR + brand→genérico | 129 dose_limits + 109 aliases |
| **Stockley's Drug Interactions** | interactions + time_separation | 15 |
| **Lexicomp** (referência pública) | interactions | 26 |
| **FDA** | interactions + black box warnings | 11 + 2 |
| **SBGG** (Sociedade Brasileira de Geriatria e Gerontologia) | dose_limits BR-específicos | 2 |
| **STOPP 2023** (European Group on Inappropriate Prescriptions in Elderly) | fall_risk scoring | 38 drugs |
| **Anticholinergic Cognitive Burden Scale (ACB)** | escala 0-3 burden | 51 drugs |
| **Curadoria manual** | gaps + ajustes contextuais | distribuída |

---

## 3. Casos clínicos cobertos hoje

### Exemplos de detecções automáticas

**Triple Whammy renal** — IECA/BRA + Tiazídico + AINE
- Detecção: 3 interações cadastradas (Enalapril+Ibuprofeno, Losartana+Ibuprofeno, HCTZ+Ibuprofeno)
- Severidade: `major`
- Recomendação clínica: substituir AINE por paracetamol; monitorar creatinina semanal

**Síndrome serotoninérgica** — ISRS + tramadol
- Detecção: Sertralina+Tramadol, Fluoxetina+Tramadol
- Severidade: `major`
- Onset: rapid (<24h)
- Recomendação: dipirona/paracetamol como alternativa

**Depressão respiratória** — benzodiazepínico + opioide (FDA black box 2016)
- Detecção: Diazepam/Clonazepam + Tramadol/Codeína
- Severidade: `major`
- Recomendação: doses mínimas + monitoração + naloxona disponível

**Toxicidade digitálica** — Digoxina + Amiodarona
- Detecção pharmacokinetic (CYP3A4)
- Recomendação: reduzir dose digoxina 50% ao iniciar amiodarona; nível sérico em 1 sem e 1 mês

**Burden anticolinérgico** (Beers + ACB)
- Sistema soma scores ACB de todos os meds ativos do paciente
- Alerta automático quando soma ≥3 (risco cognitivo significativo)
- Casos comuns: Difenidramina (3) + Oxibutinina (3) + Amitriptilina (3) = 9 → bloqueio

### Particularidades brasileiras endereçadas

- **Bulário Anvisa em PT-BR** — nomes comerciais + genéricos
- **Distanciamento temporal** com `time_separation_minutes` (ex: levotiroxina precisa intervalo de Ca/Fe — modelado)
- **`food_warning`** — interações com alimentos (varfarina+vitamina K, IMAO+tiramina)
- **SBGG-aligned** dose limits onde diretrizes brasileiras divergem das americanas
- **Cascatas de prescrição** — antipsicótico → parkinsonismo → levodopa (cadeia "iatrogenia mascarada")

---

## 4. Workflow de governança clínica

### 4.1 Status de revisão por entry

Cada flag/interaction tem `review_status`:
- `verified` — revisado clinicamente, pronto pra produção
- `pending` — aguarda revisão
- `auto_generated` — gerado por automação (precisa human-in-the-loop)

Hoje: 100% verified (status default), mas **assinatura clínica formal pendente** — gap operacional.

### 4.2 Interface de governança

**`/admin/governance/clinical-rules`** — UI Next.js permitindo:
- CRUD de dose_limits (adicionar drug + dose máxima geriátrica)
- Editar interactions (severity, mechanism, recommendation, time_separation)
- Gerenciar aliases (mapeamento brand→genérico)
- Configurar contraindications por condição
- Cadastrar renal/hepatic adjustments

**`/admin/governance/corpus-review`** — fila de relatos clínicos pra classificação humana
- Cada caso: relato livre + sugestão IA + 8 categorias clínicas + 4 severidades
- 24 cases pendentes hoje aguardando revisor

### 4.3 Audit trail
Todas mudanças em regras clínicas geram event em `aia_health_audit_chain` (LGPD/CFM-compliant) — quem mudou o quê e quando.

---

## 5. Limitações reconhecidas

1. **Cobertura não-exaustiva**: 142 drugs ≠ todos os medicamentos disponíveis no BR. Sistema possui mecanismo de gap-tracking automático (registra drugs perguntados mas não cadastrados pra priorização).

2. **Validação clínica formal pendente**: dataset foi curado por desenvolvedores + curadoria manual baseada em fontes públicas. Carece de **assinatura de farmacêutico habilitado** revisando entry-by-entry — esse é o ponto que motiva conversa com PUC/RS.

3. **Dependência de bula**: dose limits e interactions são derivados de bibliografia pública. Para uso clínico oficial, ainda recomenda-se conferência com bula atualizada Anvisa.

4. **Sem conexão direta com prontuário externo**: integração com sistemas hospitalares (HL7/FHIR) está em roadmap mas não implementada.

5. **Modelo de IA generativo (Sofia) é separado do motor clínico**: motor é determinístico (regras), Sofia consulta o motor mas não substitui suas decisões. Se motor diz `block`, Sofia NÃO sugere o medicamento.

---

## 6. Oportunidades de pesquisa e colaboração acadêmica

### Para um departamento/coordenadoria de Farmácia (ex: PUC/RS):

#### 6.1 Validação clínica do dataset
- Revisão sistemática das 142 drugs + 93 interações + 151 dose limits
- Possível co-autoria em paper de validação ("Implementação de farmacovigilância automatizada para cuidado domiciliar geriátrico no Brasil — validação de knowledge graph")

#### 6.2 Expansão de cobertura
- Curadoria de drugs prevalentes em cuidado domiciliar BR ainda não cobertos
- Estudo de prevalência de polifarmácia nos pacientes piloto

#### 6.3 Estudos clínicos derivados
- Análise retrospectiva de alertas gerados vs desfechos clínicos
- Validação prospectiva: comparar adesão e segurança de pacientes em domicílio com/sem sistema
- Tese/dissertação possível: "Knowledge graph farmacológico e redução de eventos adversos em cuidado domiciliar de idosos"

#### 6.4 Educação continuada
- Dataset pode alimentar treinamentos de cuidadores e farmacêuticos
- Casos clínicos do `corpus-review` podem virar material didático

#### 6.5 Estágio/residência
- Estudantes de farmácia podem rotacionar como **revisores clínicos** do sistema (workflow já implementado em `/admin/governance/corpus-review`)
- Experiência hands-on com farmacovigilância digital + LGPD + telesaúde

### Vantagens potenciais pra parceria PUC/RS

- **Acesso a dado real**: piloto ConnectaIACare em produção (anonimizado, com consent LGPD)
- **Infraestrutura técnica pronta**: não precisa construir nada — só revisar/curar
- **Pesquisa publicável**: temas de fronteira (IA + farmacovigilância + saúde digital BR)
- **Selo institucional**: dataset com assinatura farmacêutica acadêmica = credibilidade pra contratos B2B enterprise

### O que ConnectaIACare oferece em retorno

- Ambiente real de estudo + dados anonimizados
- Co-autoria em papers
- Possível bolsa/remuneração pra revisores clínicos sistemáticos
- Integração curricular (estágio supervisionado)
- Visibilidade pública do trabalho da coordenadoria

---

## 7. Perfil técnico do sistema (alto nível)

- **Backend**: Python (Flask + Postgres + pgvector + Redis)
- **Frontend**: Next.js 14 + TypeScript
- **IA**:
  - LLM principal: Anthropic Claude (Sonnet/Haiku) + Google Gemini Vertex AI
  - Embeddings: text-embedding-005 (Vertex)
  - Voz: Grok Voice Realtime + biometria Resemblyzer
- **Compliance**: LGPD-compliant (consent log, audit chain), Vertex AI residency configurable
- **Multi-tenant**: SaaS B2B com isolamento por tenant
- **Integrações**: WhatsApp (Evolution API), Google Workspace (MCP), VoIP PJSIP

## 8. Contato

Para conversa inicial sobre parceria:
- Coordenação técnica: Alexandre (CEO/founder ConnectaIACare)
- Referência clínica do projeto: Henrique Bordin (admin tenant)

---

*Documento gerado em maio/2026. Versionado em git: `docs/PHARMACOVIGILANCE_CONNECTAIACARE.md`*
