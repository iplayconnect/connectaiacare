# ADR-014: Integração MedMonitor + modelo de dados de sinais vitais

- **Date**: 2026-04-20
- **Status**: Accepted (estrutura) + Proposed (integração real)
- **Deciders**: Alexandre (ConnectaIA)
- **Tags**: architecture, integration, vital-signs, fhir, medmonitor

## Context and Problem Statement

O ConnectaIACare tem 4 parceiros formais (ConnectaIA + Tecnosenior + MedMonitor + Amparo). MedMonitor é o parceiro técnico que provê **dispositivos clínicos homologados de aferição de sinais vitais** — oximetro, esfigmomanômetro, glicosímetro, termômetro, balança. Segundo www.medmonitor.com.br, os parâmetros principais são: **pressão arterial, glicose, oximetria, temperatura, frequência cardíaca e outros**.

Precisamos decidir **agora** o modelo de dados + arquitetura de ingestão, porque:
1. O Prontuário longitudinal (sendo desenhado pelo Claude Design) precisa exibir vital signs
2. O motor de análise clínica (`clinical_analysis.py`) precisa cruzar sintomas com vitals recentes para gerar alertas mais precisos
3. Mock data atual não tem vitals — precisamos seed para demo de sexta

## Decision Drivers

- **Compatibilidade FHIR R4 desde o dia 1**: futuras integrações com hospitais (Fase 3 INTEGRA) exigem FHIR. Os códigos LOINC de cada tipo de medição devem estar no modelo de dados
- **Isolamento lógico**: ingestão de vitals não pode acoplar-se a provedor específico (MedMonitor hoje, Apple Health amanhã, manual sempre)
- **Classificação automática**: toda medição precisa de status (routine/attention/urgent/critical) baseado em ranges — para alertas proativos + visualização
- **Ranges adaptáveis por paciente**: idoso com DPOC crônico tem SpO₂ baseline diferente; diabético sob insulina tem alvo de glicemia diferente
- **Mock realista**: demo de sexta precisa de valores críveis (PA alta em hipertensos, glicemia alta em diabéticos, SpO₂ baixa em DPOC)
- **Prontuário-first**: UX prioritária é a **visão longitudinal** para médico, não tempo-real 24/7 (isso é Fase 2 posterior)

## Considered Options

- **Option A**: Tabela única `aia_health_vital_signs` com coluna `vital_type` discriminando, classificação por ranges tabulares adaptáveis (escolhida)
- **Option B**: Uma tabela por tipo (`aia_health_blood_pressure`, `aia_health_heart_rate`, etc.) — mais explícito mas muitas tabelas
- **Option C**: JSONB genérico `aia_health_observations` tipo FHIR Observation raw — máxima flexibilidade, pouco queryable
- **Option D**: TimescaleDB hypertable dedicada — otimização de time-series real

## Decision Outcome

Chosen option: **Option A — tabela única discriminada por `vital_type`** com enum de tipos, códigos LOINC embutidos, ranges em tabela separada (paciente-específica ou populacional default).

### Positive Consequences

- **Schema simples e queryable** — um index compound `(patient_id, vital_type, measured_at)` resolve 95% das queries
- **FHIR-ready**: cada linha mapeia 1:1 para uma `FHIR Observation` (campo `loinc_code` já embutido)
- **Classificação centralizada**: status é calculado no momento da inserção via ranges da tabela `aia_health_vital_ranges` — UI não recalcula
- **Ranges adaptáveis**: um paciente pode ter seu range específico (sobrescreve default populacional)
- **Mock data rico**: procedimento PL/pgSQL na migration 004 gera 7 dias × 8 pacientes × ~1200 medições realistas por condição

### Negative Consequences

- **Pressão arterial composite**: decidimos guardar PA em 1 linha (campos `value_numeric` = sistólica, `value_secondary` = diastólica, `vital_type` = `blood_pressure_composite`). Alternativa seria 2 linhas separadas. Optamos composite para manter atomicidade clínica (PA sempre é par).
- **Não otimizado para time-series massivo**: se chegarmos a milhões de medições contínuas (SpO₂ 1Hz de wearable), TimescaleDB vira necessário. Hoje volume é baixo: ~3 medições × 6 tipos × 50 pacientes = ~900/dia por tenant, totalmente OK em PostgreSQL normal.
- **Sem validação cross-field**: composite PA permite sistólica < diastólica (impossível clinicamente). Aceito — validação fica na camada de app, não no banco.

## Arquitetura de ingestão

```
┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│  MedMonitor │   │ Apple Health │   │ Dashboard   │
│  dispositivo│   │ / wearables  │   │ (manual)    │
└──────┬──────┘   └──────┬───────┘   └──────┬──────┘
       │ webhook/pull   │ FHIR sync        │ POST /vitals
       │ (Fase 2)       │ (Fase 3)         │ (agora)
       └────────┬───────┴──────────────────┘
                │
                ▼
     ┌──────────────────────────────┐
     │ vital_signs_service          │
     │  ingest() → classify() → save│
     └──────────────┬───────────────┘
                    │
                    ▼
     ┌──────────────────────────────┐
     │ aia_health_vital_signs       │
     │ + classificação automática   │
     │ + loinc_code preenchido      │
     └──────────────┬───────────────┘
                    │
        ┌───────────┴──────────────┐
        ▼                          ▼
┌───────────────┐          ┌──────────────────┐
│ Prontuário UI │          │ Análise IA       │
│ (timeline)    │          │ (cruza com relato│
│               │          │  do cuidador)    │
└───────────────┘          └──────────────────┘
```

## Roadmap de integração

### Fase atual (MVP — demo sexta 24/04)
- ✅ Schema criado (migration 004)
- ✅ 7 dias de mock por paciente com valores realistas por condição
- ✅ Service + endpoints: `GET /api/patients/{id}/vitals/summary` e `GET /api/patients/{id}/vitals?type=&days=`
- ✅ Ranges populacionais idoso (SBH/SBD) seeded
- 🎨 UI no Prontuário longitudinal (Claude Design em curso, spec em `docs/DESIGN_BRIEF.md` §5.1)

### Fase 1.5 (pós-demo, 2-3 semanas)
- Endpoint `POST /api/patients/{id}/vitals` para entrada manual (enfermagem digita direto no dashboard)
- Validação cross-field (PA sistólica > diastólica, SpO₂ ≤ 100, etc.)
- Motor de análise: quando houver vital crítico nas últimas 24h, incluir no contexto do prompt clínico
- Tabela `aia_health_vital_ranges` per-patient UI (médico define thresholds custom)

### Fase 2 — MONITOR (Q3 2026)
- **Webhook MedMonitor** quando dispositivo sync → chama `POST /api/integrations/medmonitor/vitals`
- Autenticação HMAC do webhook (shared secret negociado com Murilo/MedMonitor)
- Mapping de dispositivos MedMonitor → tipos/unidades canônicos
- Histórico de device_id para auditoria LGPD

### Fase 3 — INTEGRA (Q3-Q4 2027)
- Export FHIR R4: endpoint `/fhir/Patient/{id}/Observation` retornando bundle FHIR standard
- Importação FHIR: recebemos Observations de hospitais (Vita) via integração
- Apple Health / Android Health Connect import (Claude for Healthcare connectors?)

## Integração com motor de análise IA (crítico)

O prompt `clinical_analysis.py` será atualizado na Fase 1.5 para incluir:

```
<vital_signs_last_24h>
PA: 155/95 mmHg · attention (média 7d 138/85) · trend ↗
FC: 88 bpm · routine
SpO₂: 91% · urgent (paciente DPOC baseline 92; hoje 91 com queda de 3 pontos)
Temperatura: 38.2°C · urgent
</vital_signs_last_24h>
```

Isso permite ao LLM cruzar sintomas do relato com dados objetivos recentes. Ex: cuidador diz "dispneia leve", mas SpO₂ está 89% — urgência real mais alta do que o relato isolado sugeriria.

## When to Revisit

- Se volume exceder ~5k medições/dia por tenant → avaliar TimescaleDB hypertable
- Quando MedMonitor expuser API oficial → implementar webhook Fase 2
- Quando Apple Health/Google Health Connect virarem prioridade (Claude for Healthcare path) → adicionar source `wearable` com mapping FHIR
- Se surgirem parâmetros novos (ex: ECG) que exijam modelagem diferente (waveform) → tabela dedicada

## Links

- Migration: [004_vital_signs.sql](../../backend/migrations/004_vital_signs.sql)
- Serviço: [vital_signs_service.py](../../backend/src/services/vital_signs_service.py)
- Design spec: [DESIGN_BRIEF.md §5.1](../DESIGN_BRIEF.md)
- Relacionado: [ADR-011](011-locale-aware-architecture-para-latam-europa.md) — unidades variam por locale (Europa usa mmol/L para glicemia)
- Referências regulatórias: SBH 2020, SBD 2023, Beers Criteria 2023
