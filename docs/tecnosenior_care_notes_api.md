# Tecnosenior — API de Care Notes (agente externo)

**Origem**: documento enviado por Matheus (Tecnosenior) sobre como
integrar a Sofia/ConnectaIACare como agente externo emitindo
anotações de cuidado pra plataforma deles.

**Data recebido**: 2026-04-28

---

## 1. Contexto

API permite que o agente externo (Sofia/ConnectaIACare) crie e
atualize anotações de cuidado (care notes) na plataforma TotalCare.

**Conceitos:**

- **CareNote** — anotação principal. Tem conteúdo próprio (`content`
  + `content_resume`), `caretaker` autor, `patient` alvo, e `status`
  (`OPEN` ou `CLOSED`).
- **CareAddendum** — adição/continuação a uma CareNote. Só pode ser
  adicionada enquanto a CareNote estiver `OPEN`.
- **status** — controla se a CareNote ainda recebe addendums (OPEN)
  ou já foi finalizada (CLOSED). CareNote `CLOSED` não aceita
  mais addendums.

### 1.1 Endpoints

| Método | Path | Função |
|--------|------|--------|
| POST | `/agent/care-notes/` | Cria CareNote simples (sem addendums) |
| POST | `/agent/care-notes/bulk/` | Cria CareNote + addendums atômico |
| POST | `/agent/care-notes/{id}/addendums/` | Adiciona addendum em CareNote OPEN |

**Importante**: campo `source` é forçado para `"AGENT"` pelo servidor.
Não enviar.

---

## 2. Cenários de uso

### 2.1 One-off (uma anotação rápida, sem addendums)

Caretaker faz procedimento curto, descreve tudo em uma única
anotação. Usa endpoint simples com `status: CLOSED`.

```
POST /agent/care-notes/
{
  "caretaker": 12,
  "patient": 7,
  "content": "Aferição de pressão arterial. PA 120x80 mmHg. Sem queixas.",
  "content_resume": "Aferição de PA 120x80, sem queixas.",
  "occurred_at": "2026-04-27T14:00:00Z",
  "status": "CLOSED"
}
```

Total: 1 chamada. Status final: CLOSED.

### 2.2 Streaming (criar OPEN + addendums conforme interação)

Agente abre CareNote no início + posta addendums conforme cuidador
relata pelo WhatsApp. Último addendum vem com `status: CLOSED`.

**Passo 1** — abrir CareNote:
```
POST /agent/care-notes/
{
  "caretaker": 12, "patient": 7,
  "content": "Início da visita. Aferição inicial.",
  "content_resume": "Início da visita.",
  "occurred_at": "2026-04-27T14:00:00Z",
  "status": "OPEN"
}
→ 201 { "id": 432, ..., "status": "OPEN" }
```

**Passo 2** — adicionar addendums (N vezes):
```
POST /agent/care-notes/432/addendums/
{
  "content": "PA 120x80 mmHg.",
  "content_resume": "PA normal.",
  "occurred_at": "2026-04-27T14:05:00Z"
}
```

**Passo 3** — último addendum com `status: CLOSED`:
```
POST /agent/care-notes/432/addendums/
{
  "content": "Visita encerrada. Paciente estável.",
  "content_resume": "Encerrada, estável.",
  "occurred_at": "2026-04-27T14:30:00Z",
  "status": "CLOSED"
}
```

CareNote 432 fica CLOSED, não aceita mais addendums. Campo `status`
do addendum é só sinal — ele NÃO é gravado, apenas dispara fechamento.

Total: 1 (criar) + N (addendums, último com close).

### 2.3 Bulk OPEN (envia nota + buffer, mas continua adicionando)

Agente acumulou buffer de addendums e quer enviar de uma vez, mas
interação não acabou. Usa `bulk/` com `status: OPEN`.

```
POST /agent/care-notes/bulk/
{
  "caretaker": 12, "patient": 7,
  "content": "Início da visita.",
  "content_resume": "Início da visita.",
  "occurred_at": "2026-04-27T14:00:00Z",
  "status": "OPEN",
  "addendums": [
    { "content": "PA 120x80 mmHg.", ... "occurred_at": "...:05Z" },
    { "content": "Tontura leve.", ... "occurred_at": "...:15Z" },
    { "content": "Tontura cessou.", ... "occurred_at": "...:20Z" }
  ]
}
→ 201 { "id": 433, "status": "OPEN", "addendums": [{id:902},...] }
```

Continua com `POST /agent/care-notes/433/addendums/` normal.

### 2.4 Bulk CLOSED (interação completa em buffer, fecha de uma vez)

Agente já tem tudo em buffer. Uma única chamada bulk com
`status: CLOSED`.

```
POST /agent/care-notes/bulk/
{
  "caretaker": 12, "patient": 7,
  "content": "...", "content_resume": "...",
  "occurred_at": "...", "status": "CLOSED",
  "addendums": [
    { "content": "PA 120x80...", ... },
    { "content": "Tontura leve...", ... },
    { "content": "Tontura cessou...", ... },
    { "content": "Encerrada, estável.", ... }
  ]
}
→ 201 { "id": 434, "status": "CLOSED", "closed_at": "...:31:02Z", ... }
```

Total: 1 chamada. Atômico: se 1 addendum falha, NADA é gravado.

---

## 3. Tratamento de erros

Toda falha de validação retorna **HTTP 400**. Em todos os endpoints,
incluindo bulk (atômico), 400 = nada salvo.

### 3.1 Erros comuns

**Caretaker/paciente não pertence à organização**:
```
400 { "patient": ["Patient does not belong to this organization."] }
```

**Tentar addendum em CareNote CLOSED**:
```
400 { "care_note": ["Cannot add addendum: care note is not open."] }
```

**Bulk: addendum com `occurred_at` < CareNote pai**:
```
400 { "addendums": { "2": {
  "occurred_at": ["Addendum occurred_at must be greater than or
                   equal to the parent note's occurred_at."]
} } }
```

**Campo obrigatório ausente em addendum do bulk**:
```
400 { "addendums": [
  {}, { "content_resume": ["This field is required."] }, {}, {}
] }
```

### 3.2 Recuperação por cenário

| Cenário | Comportamento em falha | Recuperação |
|---------|------------------------|-------------|
| **One-off** | Nada criado | Corrige payload, reenvia |
| **Streaming**: addendum N falhou | CareNote + addendums anteriores já gravados; só o N falhou | Corrige addendum N, POST de novo. `GET /agent/care-notes/{id}/` para ver estado |
| **Bulk OPEN** falhou | Nada criado (atômico) | Corrige payload todo, reenvia |
| **Bulk CLOSED** falhou | Nada criado | Idem |

### 3.3 CareNote órfã (agente travou com nota OPEN)

Sem rotina automática de fechamento. Soluções:

- `GET /agent/care-notes/?caretaker={id}` — listar notas do caretaker
- Adicionar último addendum com `status: CLOSED` para fechar:
  `"interação interrompida"`

---

## 4. Restrições importantes

### 4.1 Misturar fluxos

- **Bulk só serve para CRIAR.** Não existe "bulk add addendums".
  Após criar, addendums adicionais são via `/addendums/` (1 por vez).
- **Não é possível reabrir CLOSED.** Pra "continuar", criar nova
  CareNote.
- **Não é possível UPDATE de conteúdo.** Sem PATCH/PUT. Erros são
  corrigidos com novo addendum tipo "correção: ...".

### 4.2 Timestamps

- **Bulk** valida `occurred_at` de cada addendum >= CareNote pai.
- Não valida ordem entre addendums (servidor ordena por
  `occurred_at` na leitura).
- **Endpoint single** (`/addendums/`) NÃO valida `occurred_at` contra
  pai. Confiar no agente, evitar futuro/anterior ao início.

---

## 5. Notas para integração

- API key escopa o agente a uma organização. Caretaker/patient IDs
  precisam ser dessa organização.
- `occurred_at` é o timestamp clínico real do evento (não o do
  registro). Crítico pra ordenação cronológica.
- `content_resume` é separado de `content` — sugere que TotalCare
  exibe resumo na lista e detalhe completo no drill-in.
