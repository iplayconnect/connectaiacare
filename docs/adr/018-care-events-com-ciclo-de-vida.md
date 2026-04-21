# ADR-018: Modelo de Care Events com ciclo de vida clínico completo

- **Date**: 2026-04-20
- **Status**: Accepted
- **Deciders**: Alexandre (ConnectaIA), com input do Murilo (Tecnosenior)
- **Tags**: domain-model, state-machine, orchestration, clinical-protocol
- **Supersedes**: [ADR-017](017-sessao-conversacional-persistente.md)

## Context and Problem Statement

ADR-017 introduziu a noção de "sessão conversacional persistente" — uma única sessão ativa por cuidador, preservando contexto entre mensagens. Ao testar o modelo com cenário real de SPA (1 cuidador atendendo 10-20 idosos), ficaram claras três insuficiências:

1. **Escopo da sessão é ambíguo**: o que é "uma sessão"? Uma conversa sobre Dona Maria ou toda a interação do cuidador? Se o cuidador falar de 3 pacientes num intervalo de 20 minutos, seria 1 sessão ou 3? Sem resposta clara, o sistema adivinha mal.

2. **Falta ciclo clínico real**: o cuidado não é "conversa" — é um **evento clínico** com início, desenvolvimento, escalação e encerramento categorizado (cuidado iniciado, encaminhado, falso alarme, etc). Sessão conversacional é um conceito técnico; evento clínico é o objeto que o médico e o gestor querem ver no dashboard.

3. **Protocolos temporais não cabem em "sessão"**: o cuidado real tem SLAs temporais — aos +5min rodar análise de padrão histórico, aos +10min pingar o cuidador, aos +30min decidir encerrar, com escalação hierárquica se sem resposta em N minutos. Esse **workflow** não é uma "sessão" — é uma **máquina de estados temporal** que precisa de scheduler, persistência dedicada, e auditoria clara.

A visão articulada pelo Murilo (Tecnosenior) consolidou: *"cada evento tem início, meio e fim, passa por etapas com personas diferentes (cuidador, enfermagem, família), e precisa aparecer no dashboard como um item clínico, não como uma conversa técnica"*.

## Decision Drivers

- **Modelo mental clínico**: o objeto de interesse no dashboard e relatórios é o **evento** (uma queda, uma dispneia, uma recusa alimentar), não a conversa
- **Múltiplos eventos paralelos**: um cuidador pode ter 3 eventos abertos simultâneamente (3 pacientes diferentes em situações diferentes)
- **Timeline temporal**: ações agendadas (pattern analysis, check-in, closure) precisam de scheduler robusto independente de thread HTTP
- **Escalação hierárquica**: SLA + canal + fallback por nível (central → enfermeira → médico → família 1/2/3) precisa ser auditável
- **Encerramento categorizado**: desfecho (cuidado iniciado, encaminhado, falso alarme, óbito, etc) alimenta relatórios operacionais
- **Integração com sistemas mestres**: quando evento fecha, sincronizar anotação estruturada no TotalCare (ADR-019)
- **Multi-tenant**: timings e políticas de escalação configuráveis por SPA/ILPI

## Considered Options

- **Option A**: Manter ADR-017 (sessão conversacional única)
- **Option B**: Sessões conversacionais múltiplas paralelas (sem conceito de "evento")
- **Option C**: Introduzir entidade **Care Event** como objeto clínico de primeira classe, com ciclo de vida, sub-entidades (check-ins, escalações) e scheduler temporal (escolhida)
- **Option D**: Case Management full-feature tipo PerfectServe (overkill pro MVP)

## Decision Outcome

Chosen option: **Option C — Care Event como objeto central de domínio**.

### Modelo de dados

```
aia_health_care_events             (entidade central)
    ├─ aia_health_care_event_checkins    (scheduler de ações temporais)
    └─ aia_health_escalation_log         (trilha de notificações hierárquicas)

aia_health_reports                 (relato individual)
    └─ care_event_id (FK)          (N relatos por 1 evento em follow-ups)

aia_health_tenant_config           (timings + escalation_policy por tenant)
```

### Máquina de estados do CareEvent

```
    [novo áudio, cuidador-paciente ainda não confirmado]
            │
            ▼
       analyzing   ──── (texto do cuidador SIM)
            │
            ▼
      awaiting_ack  (resumo enviado, aguarda leitura)
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
pattern_          escalating   (classification >= urgent)
analyzed            │
    │               │
    └───────┬───────┘
            │
            ▼
 awaiting_status_update  (check-in proativo enviado)
            │
    ┌───────┴────────┐
    │                │
    ▼                ▼
 resolved         expired
 (manual)         (TTL sem feedback)
```

### Múltiplos eventos paralelos

Constraint UNIQUE parcial permite **1 evento ativo por (tenant, cuidador, paciente)** mas múltiplos pares cuidador-paciente podem coexistir:

```sql
CREATE UNIQUE INDEX idx_care_events_unique_active
    ON aia_health_care_events(tenant_id, caregiver_phone, patient_id)
    WHERE status NOT IN ('resolved', 'expired');
```

Assim cuidador pode ter simultaneamente: queda da Dona Maria (#0009), dispneia do Seu João (#0010), recusa alimentar do Seu Pedro (#0011). Cada qual com sua timeline e escalação independentes.

### Timeline temporal (SLAs)

Ao abrir evento, três check-ins são agendados (`aia_health_care_event_checkins`):

| Kind | Quando | Ação |
|---|---|---|
| `pattern_analysis` | +5 min (critical: +3min) | Busca padrões históricos do paciente (ADR-021 pattern detection) |
| `status_update` | +10 min (critical: +8min) | "Como [paciente] está agora?" — pergunta ao cuidador |
| `closure_check` | +30 min (critical: +45min) | Se sem atividade recente → expira; senão reagenda |

Valores são **defaults do tenant_config** e podem ser sobrescritos por classificação via JSONB `timings`.

### Escalação hierárquica

Quando `classification ∈ {urgent, critical}`, o pipeline dispara imediatamente escalação institucional (central, enfermagem, médico) em paralelo via Evolution WhatsApp. Se ninguém responder em `escalation_level1_wait_min`, o scheduler agenda e dispara família nível 1, depois 2, depois 3 — cada nível com `escalation_levelN_wait_min`. Ver ADR-020 para detalhes.

Cada notificação é registrada em `aia_health_escalation_log` com:
- `target_role`: central | nurse | doctor | family_1 | family_2 | family_3
- `channel`: whatsapp | voice | sms
- `status`: queued → sent → delivered → read → responded | no_answer | failed
- Timestamps de cada transição + `response_summary`

### Encerramento categorizado

Endpoint `POST /api/events/:id/close` aceita um de 9 motivos:
`cuidado_iniciado | encaminhado_hospital | transferido | sem_intercorrencia | falso_alarme | paciente_estavel | expirou_sem_feedback | obito | outro` + observações livres.

Ao encerrar, o sistema:
1. Grava `closed_by`, `closed_reason`, `closure_notes`, `resolved_at`
2. Chama MedMonitor API (ADR-019) para criar `care-note` no TotalCare com o conteúdo estruturado do evento
3. Remove evento do feed de ativos no dashboard
4. Mantém visível na timeline do paciente individual para histórico

### Positive Consequences

- **Objeto clínico claro**: dashboard fica trivial — lista eventos abertos, timeline do paciente, distribuição por classificação
- **Auditoria precisa**: cada escalação, check-in, mensagem vira linha em tabela com timestamps — compliance-ready
- **Multi-paciente paralelo sem ambiguidade**: cuidador real funciona como cuidador real
- **Scheduler desacoplado**: thread background com `pg_try_advisory_lock` roda sem bloquear HTTP
- **Encerramento estruturado**: motivos enum alimentam relatórios operacionais (quantos falsos alarmes/semana, etc)
- **TotalCare sincronizado**: cada evento encerrado vira anotação oficial no sistema mestre
- **Tenants configuram protocolo**: Tecnosenior pode ter SLA diferente de Amparo sem deploy

### Negative Consequences

- **Mais complexidade que ADR-017**: 4 tabelas novas, 7 novos serviços Python
- **State machine com 7 estados**: mais testes necessários, mais caminhos possíveis
- **Pipeline depende de scheduler funcionando**: se scheduler morrer, check-ins param (mitigado: advisory lock + healthcheck)
- **Timings configuráveis exigem UI de admin** (fica pra pós-demo — por hora é via SQL direto)

## Pros and Cons of the Options

### Option A — Sessão única (ADR-017) ❌ Superseded

- ✅ Simples
- ❌ Não modela N pacientes por cuidador
- ❌ Sem SLA temporal
- ❌ Sem escalação hierárquica auditável

### Option B — Sessões múltiplas paralelas ❌

- ✅ Resolve ambiguidade de paciente
- ❌ Ainda é "sessão técnica", não evento clínico
- ❌ Sem encerramento categorizado
- ❌ Sem scheduler temporal

### Option C — Care Event como objeto de domínio ✅ Chosen

- ✅ Modela realidade clínica
- ✅ Timeline auditável
- ✅ Escalação real + encerramento categorizado
- ✅ Multi-tenant configurável
- ❌ Mais código + mais testes

### Option D — Case Management full-feature ❌

- ✅ Completude máxima
- ❌ Overkill pra MVP — mais de 6 meses de desenvolvimento
- ❌ Curva de adoção do cuidador
- ❌ Esconde valor-chave (IA + proatividade)

## Implementation — migration 005

Nova tabela central + 3 auxiliares + 2 coluna em `aia_health_reports`:

```sql
-- Central
CREATE TABLE aia_health_care_events (
    id UUID, human_id SERIAL, tenant_id TEXT,
    patient_id UUID FK, caregiver_phone TEXT, caregiver_id UUID FK,
    initial_classification, current_classification TEXT CHECK,
    event_type TEXT, event_tags TEXT[],
    status TEXT CHECK IN ('analyzing'|'awaiting_ack'|'pattern_analyzed'|
                          'escalating'|'awaiting_status_update'|'resolved'|'expired'),
    context JSONB,
    summary TEXT, reasoning TEXT,
    opened_at, pattern_analyzed_at, first_escalation_at,
    last_check_in_at, resolved_at TIMESTAMPTZ,
    closed_by TEXT, closed_reason TEXT CHECK, closure_notes TEXT,
    expires_at TIMESTAMPTZ,
    initial_report_id UUID FK
);

-- Scheduler
CREATE TABLE aia_health_care_event_checkins (
    event_id UUID FK, kind TEXT CHECK,
    scheduled_for, sent_at TIMESTAMPTZ,
    channel TEXT, message_sent TEXT,
    response_received_at, response_text, response_classification,
    status TEXT CHECK IN ('scheduled'|'sent'|'responded'|'skipped'|'failed')
);

-- Trilha de escalação
CREATE TABLE aia_health_escalation_log (
    event_id UUID FK,
    target_role TEXT CHECK, target_name, target_phone,
    channel TEXT, message_content, status TEXT CHECK,
    sent_at, delivered_at, read_at, responded_at,
    response_summary, external_ref
);

-- Config por tenant
CREATE TABLE aia_health_tenant_config (
    tenant_id PK,
    central_phone, nurse_phone, doctor_phone, ...,
    pattern_analysis_after_min, check_in_after_min, closure_decision_after_min,
    escalation_level1_wait_min, level2, level3,
    timings JSONB,           -- overrides por classificação
    escalation_policy JSONB, -- quais roles pra cada classificação
    features JSONB           -- feature flags
);

-- Relatos ligam a eventos + ganham embedding semântico
ALTER TABLE aia_health_reports
    ADD COLUMN care_event_id UUID FK,
    ADD COLUMN embedding vector(768);  -- pgvector HNSW para pattern detection
```

### Serviços

- `care_event_service.py` — CRUD + transições de estado + scheduler de check-ins + trilha de escalações
- `tenant_config_service.py` — cache de timings/policy/contatos (TTL 60s)
- `pattern_detection_service.py` — 3 camadas combinadas (tag count, pgvector semântico, severity progression)
- `escalation_service.py` — orquestra níveis hierárquicos via Evolution + Sofia Voice (ADR-020)
- `checkin_scheduler.py` — thread daemon com `pg_try_advisory_lock` (single-writer entre workers Gunicorn)
- `medmonitor_client.py` — cliente TotalCare API (ADR-019)

### Endpoints REST

- `GET /api/events/active` — dashboard principal
- `GET /api/events/:id` — detalhe + timeline + escalações + check-ins
- `POST /api/events/:id/close` — encerramento + sync TotalCare
- `GET /api/patients/:id/events` — timeline por paciente (ativos + histórico)

## When to Revisit

- Se cuidadores relatarem que eventos "grudam" depois do desfecho → revisar TTLs + auto-close por inatividade
- Se SLAs fixos (5/10/30 min) mostrarem-se inadequados pra casos específicos → adicionar "prolongamento manual"
- Se chegarmos a 200+ eventos ativos simultâneos por tenant → migrar scheduler pra RQ/Celery ao invés de thread daemon
- Se integração TotalCare apresentar race conditions no sync → adicionar outbox pattern + retry com idempotência

## Links

- [migration 005](../../backend/migrations/005_care_events.sql)
- [care_event_service](../../backend/src/services/care_event_service.py)
- [pattern_detection_service](../../backend/src/services/pattern_detection_service.py)
- [escalation_service](../../backend/src/services/escalation_service.py)
- [checkin_scheduler](../../backend/src/services/checkin_scheduler.py)
- [tenant_config_service](../../backend/src/services/tenant_config_service.py)
- [pipeline refactor](../../backend/src/handlers/pipeline.py)
- [ADR-017 (superseded)](017-sessao-conversacional-persistente.md)
- [ADR-019 integração MedMonitor](019-integracao-medmonitor-totalcare.md)
- [ADR-020 escalação hierárquica](020-escalacao-hierarquica-evolution-sofia.md)
