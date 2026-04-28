# Integração Tecnosenior — Care Notes / Addendums

**Status**: análise + arquitetura proposta. Não implementado.
**Data**: 2026-04-28
**Origem**: API de care_notes documentada por Matheus (Tecnosenior)
em `docs/tecnosenior_care_notes_api.md`.

---

## 1. Objetivo

Devolver para a plataforma TotalCare (Tecnosenior) as anotações de
cuidado geradas a partir de relatos que cuidadores fazem via
WhatsApp para a Sofia. Hoje o relato vive só no nosso lado; com a
integração, ele passa a aparecer no prontuário da Tecnosenior em
tempo quase-real.

**Arquitetura pretendida**: outbound webhook do nosso lado para a
API REST deles, com fila + retry + idempotência. ConnectaIACare
permanece como fonte primária; TotalCare recebe espelhamento.

---

## 2. Mapeamento de modelos

### 2.1 Tabela de equivalências

| Tecnosenior | ConnectaIACare | Notas |
|-------------|----------------|-------|
| `CareNote` | `aia_health_care_events` (1 linha) | Hub do evento clínico |
| `CareNote.status` (OPEN/CLOSED) | `care_events.status` | Mapping abaixo |
| `CareNote.content` | concat dos textos do `aia_health_reports` ligados | "Relato completo" |
| `CareNote.content_resume` | `care_events.summary` | Resumo da Sofia |
| `CareAddendum` | cada `aia_health_reports` extra do mesmo evento | 1 addendum por mensagem follow-up |
| `caretaker` (int) | `aia_health_caregivers.id` (UUID) | Precisa mapping numérico — ver §3 |
| `patient` (int) | `aia_health_patients.id` (UUID) | Idem |
| `occurred_at` (ISO) | `reports.created_at` ou `care_events.opened_at` | Timestamp do relato real |
| `source` ("AGENT") | forçado pelo servidor deles | Não enviar |

### 2.2 Mapping de status

A Tecnosenior tem só `OPEN` / `CLOSED`. A gente tem 7 estados
(`analyzing` → `awaiting_ack` → `pattern_analyzed` → `escalating` →
`awaiting_status_update` → `resolved` / `expired`).

Regra de tradução:

| `care_events.status` | TotalCare `CareNote.status` |
|----------------------|-----------------------------|
| analyzing | OPEN |
| awaiting_ack | OPEN |
| pattern_analyzed | OPEN |
| escalating | OPEN |
| awaiting_status_update | OPEN |
| resolved | CLOSED (com `closed_reason` no content_resume) |
| expired | CLOSED (com nota "expirou sem feedback") |

### 2.3 Quando criar / atualizar / fechar

```
[care_event nasce]
  ↓
  status=analyzing → POST /agent/care-notes/ (status=OPEN)
                      [guardar carenote_id retornado]
  ↓
[care_event recebe novo aia_health_reports]
  ↓
  POST /agent/care-notes/{id}/addendums/  (status=OPEN)
  ↓
[care_event vai para resolved/expired]
  ↓
  POST /agent/care-notes/{id}/addendums/ com status=CLOSED
                      [content do addendum = "Encerrado: <closed_reason>"]
```

---

## 3. Lacuna crítica — IDs numéricos

A API da Tecnosenior usa `caretaker: int` e `patient: int`. A gente
usa UUID. **Sem mapping não dá pra integrar**.

### 3.1 Opções

**A. Eles enriquecem nosso schema** — Tecnosenior fornece um arquivo
com `(uuid_paciente_nosso, id_paciente_deles)` e a gente importa.

**B. Eles batem por outro identificador** — CPF do paciente, telefone
do cuidador, ou nome+data_nascimento. Match probabilístico do lado
deles.

**C. Tecnosenior cria dois IDs** — usuário cadastrado nos dois lados,
guardamos ambos no nosso DB.

### 3.2 Recomendação

**Opção C** com migração nova:

```sql
ALTER TABLE aia_health_patients
    ADD COLUMN tecnosenior_patient_id INTEGER UNIQUE;
ALTER TABLE aia_health_caregivers
    ADD COLUMN tecnosenior_caretaker_id INTEGER UNIQUE;

CREATE INDEX idx_patients_tecnosenior_id
    ON aia_health_patients(tecnosenior_patient_id)
    WHERE tecnosenior_patient_id IS NOT NULL;
```

População inicial: enquanto não temos mapping, paciente sem
`tecnosenior_patient_id` = não sincroniza. Painel admin mostra alerta
"sincronização pendente". Conforme Matheus envia o mapping, a gente
preenche.

**Pergunta para Matheus**: vocês expõem um endpoint
`GET /agent/patients/?cpf=X` ou `GET /agent/caretakers/?phone=X` que
retorna o ID interno deles? Isso fecha o mapping sem precisar de
arquivo manual.

---

## 4. Schema novo proposto

### 4.1 Tabela de outbound sync

```sql
CREATE TABLE aia_health_tecnosenior_sync (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    care_event_id UUID NOT NULL REFERENCES aia_health_care_events(id)
        ON DELETE CASCADE,

    -- ID retornado pela Tecnosenior na criação
    tecnosenior_carenote_id INTEGER UNIQUE,

    -- Espelho local do estado deles
    tecnosenior_status TEXT CHECK (tecnosenior_status IN ('OPEN', 'CLOSED')),
    closed_at_remote TIMESTAMPTZ,

    -- Sincronização
    last_synced_at TIMESTAMPTZ,
    last_sync_attempt_at TIMESTAMPTZ,
    sync_error TEXT,
    retry_count INT NOT NULL DEFAULT 0,

    -- Idempotência (caso a chamada falhe e a gente não tenha o ID retornado)
    idempotency_key TEXT UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tecnosenior_sync_pending
    ON aia_health_tecnosenior_sync(last_sync_attempt_at NULLS FIRST)
    WHERE sync_error IS NOT NULL OR last_synced_at IS NULL;
```

### 4.2 Tabela de outbound addendums

```sql
CREATE TABLE aia_health_tecnosenior_addendums (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    care_event_id UUID NOT NULL REFERENCES aia_health_care_events(id)
        ON DELETE CASCADE,
    report_id UUID REFERENCES aia_health_reports(id) ON DELETE SET NULL,

    tecnosenior_carenote_id INTEGER NOT NULL,
    tecnosenior_addendum_id INTEGER UNIQUE,  -- preenchido após POST

    content TEXT NOT NULL,
    content_resume TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    closes_note BOOLEAN NOT NULL DEFAULT FALSE,

    last_synced_at TIMESTAMPTZ,
    sync_error TEXT,
    retry_count INT NOT NULL DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tecnosenior_add_pending
    ON aia_health_tecnosenior_addendums(care_event_id, occurred_at)
    WHERE last_synced_at IS NULL;
```

---

## 5. Service `tecnosenior_sync_service.py`

### 5.1 Métodos principais

```python
class TecnoseniorSyncService:
    def sync_care_event(self, care_event_id: str) -> dict:
        """Cria ou atualiza CareNote remota a partir do evento local.

        Lógica:
          - Se sync_row não existe → POST /agent/care-notes/
          - Se já existe + status local mudou → POST addendum (CLOSED)
          - Se já existe + novo report → POST addendum
        """

    def sync_report(self, report_id: str) -> dict:
        """Sincroniza um aia_health_reports específico como addendum.

        Usado quando recebemos novo follow-up dentro de evento já
        sincronizado. Decide se vira o último addendum (CLOSED) ou
        addendum normal (OPEN).
        """

    def retry_failed(self, max_retries: int = 5) -> int:
        """Worker periódico re-tenta sync_error com backoff.

        Backoff: 1min, 5min, 30min, 2h, 12h.
        """

    def get_status(self, care_event_id: str) -> dict:
        """Estado da sincronização — usado pelo painel admin."""
```

### 5.2 Idempotência

A API da Tecnosenior **não menciona idempotency-key**. Estratégia
do nosso lado:

- Antes de cada POST, gravar `aia_health_tecnosenior_sync` com
  `idempotency_key = uuid4()` no nosso DB.
- Se POST tiver timeout ou falha de rede, marca `sync_error` com
  o erro. Worker tenta de novo na próxima janela.
- Se resposta voltar com `id`, gravamos `tecnosenior_carenote_id`
  e marcamos sucesso.

**Risco**: se POST chega no servidor deles e a resposta se perde no
caminho, a gente vai duplicar na próxima tentativa. Mitigação: pedir
pra Matheus expor um `GET /agent/care-notes/?idempotency_key=X` ou
aceitar header `Idempotency-Key`. Sem isso, há janela pequena de
duplicidade.

### 5.3 Tracker de eventos

Hook em `aia_health_care_events`:

- INSERT → enfileira sync_create
- UPDATE quando `status` muda → enfileira sync_status_change
- FK do `aia_health_reports.event_id` quando novo report → enfileira
  sync_addendum

Implementação: PostgreSQL trigger que insere em
`aia_health_tecnosenior_sync_queue` (Redis com BullMQ-equivalente
em Python ou tabela PG simples) + worker assíncrono em
voice-call-service ou container dedicado.

---

## 6. Cenários da Tecnosenior na nossa realidade

| Cenário deles | Quando cabe na ConnectaIACare |
|---------------|-------------------------------|
| 1. One-off CLOSED | Cuidador manda 1 áudio único, evento resolve em 1 mensagem (raro mas existe — "PA 120/80 do seu João, sem queixas" e pronto) |
| 2. Streaming (POST + N addendums + close) | **Padrão**: cuidador inicia relato, follow-ups chegam, evento se resolve depois de minutos/horas |
| 3. Bulk OPEN | Quando recebemos áudio multi-tópico (5 informações em 30s) e queremos enviar 1 nota com 5 addendums atômicos, mas evento ainda OPEN |
| 4. Bulk CLOSED | **Backfill**: importação retroativa de eventos antigos, ou consolidação no fim do plantão de cuidador |

**Decisão**: começar com modo Streaming (Cenário 2) como default,
porque é o que mais espelha o ciclo de care_event natural. Bulk só
pra retroativo.

---

## 7. Tratamento de erros

### 7.1 Mapping com erros da Tecnosenior

| Erro deles | Causa nossa | Ação |
|------------|-------------|------|
| `Patient does not belong to this organization` | `patient_id` errado ou paciente sem `tecnosenior_patient_id` | Não retentar; flag em painel admin pra mapping manual |
| `Cannot add addendum: care note is not open` | A gente acha que tá OPEN, mas Tecnosenior fechou (ou alguém fechou no painel deles) | `GET /agent/care-notes/{id}/`, atualizar nosso espelho, marcar como dessincronizado |
| `Addendum occurred_at must be greater than parent's` | `occurred_at` retroativo | Ajustar para `>= parent.occurred_at`. Logar warning |
| Timeout / 5xx | Rede, indisponibilidade | Backoff + retry |

### 7.2 CareNote órfã

Se nosso evento expirou mas não conseguimos fechar lado deles, fica
órfã. Worker detecta e envia addendum-CLOSED com
`content: "Evento expirado sem feedback do cuidador. Encerramento
automático."`

---

## 8. UI / painel admin

Adicionar em `/admin/integracoes/tecnosenior`:

- Status geral: % sincronizado, fila pendente, erros últimos 24h.
- Tabela: `care_event_id ↔ tecnosenior_carenote_id ↔ status` com
  filtro por erro.
- Botão "Resincronizar agora" pra um evento específico.
- Tabela de pacientes/cuidadores **sem** `tecnosenior_id`
  (pendência de mapping).

Sidebar: "Integrações → Tecnosenior" sob admin.

---

## 9. Perguntas abertas para Matheus

Antes de implementar:

1. **Idempotency-Key** — vocês aceitam header `Idempotency-Key`
   ou ele é silenciosamente ignorado?

2. **Mapeamento UUID ↔ ID numérico** — vocês têm endpoint pra
   buscar `caretaker_id` por telefone ou CPF? Ou faz mais sentido
   trocarmos um arquivo CSV inicial?

3. **Webhook reverso** — caso a CareNote seja editada/fechada no
   painel deles (humano da TotalCare resolveu manualmente),
   vocês mandam webhook pra gente atualizar o espelho?

4. **Limite de rate** — quantos requests/min suportam por API key?
   Em pico de plantão noturno temos picos de 30-50 relatos/min.

5. **Authentication** — API key estática no header? Bearer token?
   Tem rotação?

6. **CareNote `content`** — preferem que enviemos transcrição literal
   ou já o resumo da Sofia? (A doc separa `content` de
   `content_resume`, sugerindo que o full vai em content.)

7. **`closed_reason`** — vocês têm enum próprio ou aceitam string
   livre? A gente tem 8 valores em
   `aia_health_care_events.closed_reason`.

8. **Anexos** — áudios e imagens. A API só fala em texto. Vocês
   suportam attachment URL futuramente, ou tudo vai em texto?

---

## 10. Roadmap de implementação

**Fase 0 — Decisões + perguntas com Matheus** (1 conversa, ~30 min)
- Resolver as 8 perguntas da §9.
- Decidir Opção A/B/C de mapping (§3).

**Fase 1 — Schema + service básico** (~1 dia)
- Migration: tabelas tecnosenior_sync + addendums + colunas
  `tecnosenior_*_id` em patients/caregivers.
- `tecnosenior_sync_service.py` com métodos principais.
- Endpoint admin `/api/integrations/tecnosenior/status`.

**Fase 2 — Worker + retry + UI** (~1 dia)
- Worker periódico chama `retry_failed`.
- Painel `/admin/integracoes/tecnosenior`.
- Smoke test em ambiente de homologação da Tecnosenior.

**Fase 3 — Hooks automáticos** (~1 dia)
- Trigger PG ou hook no service quando care_event muda.
- Sincronização end-to-end (relato chega → addendum sai).
- Testes E2E.

**Fase 4 — Webhook reverso (se aplicável)** (~0.5 dia)
- Endpoint pra receber updates da Tecnosenior.

**Total**: ~3.5 dias de eng se as decisões da §9 estiverem fechadas.
