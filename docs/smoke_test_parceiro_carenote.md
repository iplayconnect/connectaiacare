# Smoke Test — Integração parceiro integrador CareNotes

**Data**: 2026-04-28
**Status**: pronto pra rodar após merge + migration 055.

---

## 1. Pré-requisitos

### Variáveis de ambiente já configuradas

```bash
MEDMONITOR_API_URL=https://<tenant>.contactto.care/agent
MEDMONITOR_API_KEY=<chave fornecida pelo Matheus>
```

(Configuradas em 2026-04-20 conforme settings.py:69. Matheus
confirmou em 2026-04-28: `Authorization: Api-Key {chave}` única
por empresa, sem rotação.)

### Dados pra teste

Você precisa ter pelo menos 1 paciente e 1 cuidador cadastrados
**dos dois lados** com phone batendo. Lookup atual é por phone
(CPF chega 2026-04-29, aí trocamos).

Como saber se está cadastrado do lado da parceiro integrador:

```bash
curl -H "Authorization: Api-Key $KEY" \
  "$URL/patients/?phone=+555199616XXXX"

curl -H "Authorization: Api-Key $KEY" \
  "$URL/caretakers/?phone=+555199616XXXX"
```

Esperado: lista com 1+ resultados contendo `id`.

---

## 2. Roundtrip via API admin (preferido)

### 2.1 Health check

```bash
curl -H "Authorization: Bearer $JWT" \
  https://care.connectaia.com.br/api/integrations/parceiro_integrador/health
```

Esperado:
```json
{"status":"ok", "client_enabled":true,
 "base_url_set":true, "api_key_set":true}
```

Se `client_enabled=false`, env vars não chegaram. Confere
`docker compose exec api env | grep MEDMONITOR`.

### 2.2 Resolução de IDs (UUID → INT) — debug

```bash
# Patient lookup
curl -X POST -H "Authorization: Bearer $JWT" \
  -H "content-type: application/json" \
  https://care.connectaia.com.br/api/integrations/parceiro_integrador/resolve-patient \
  -d '{"patient_id": "bbb4967e-da4b-4e0d-9518-f8e77a02266e"}'
```

Esperado:
```json
{"status":"ok",
 "patient_uuid":"bbb4967e-...",
 "external_partner_patient_id": 7,
 "resolved": true}
```

```bash
# Caretaker lookup por phone
curl -X POST -H "Authorization: Bearer $JWT" \
  -H "content-type: application/json" \
  https://care.connectaia.com.br/api/integrations/parceiro_integrador/resolve-caretaker \
  -d '{"phone": "5551996161700"}'
```

Esperado:
```json
{"status":"ok",
 "phone":"5551996161700",
 "external_partner_caretaker_id": 12,
 "resolved": true}
```

Side effect: o external_partner_id resolvido fica cacheado em
`aia_health_patients.external_partner_patient_id` /
`aia_health_caregivers.external_partner_caretaker_id`. Próxima
resolução é instantânea (sem chamada remota).

### 2.3 Roundtrip completo

Pega um `care_event_id` real (ex: do `/alertas` ou
`SELECT id FROM aia_health_care_events ORDER BY opened_at DESC LIMIT 1;`).

```bash
curl -X POST -H "Authorization: Bearer $JWT" \
  -H "content-type: application/json" \
  https://care.connectaia.com.br/api/integrations/parceiro_integrador/test-roundtrip \
  -d '{"care_event_id": "<uuid_do_care_event>"}'
```

Sucesso:
```json
{
  "status": "ok",
  "partner_carenote_id": 431,
  "partner_sync_status": "OPEN",
  "patient_int": 7,
  "caretaker_int": 12,
  "sync_state": {
    "partner_carenote_id": 431,
    "partner_sync_status": "OPEN",
    "last_synced_at": "2026-04-28T...",
    "sync_error": null,
    "retry_count": 0
  }
}
```

### 2.4 Erros esperados

| `reason` | Causa | Como resolver |
|----------|-------|---------------|
| `client_disabled` | env vars MEDMONITOR_* faltando | Setar no compose |
| `event_not_found` | UUID não existe | Conferir |
| `patient_not_found_in_partner` | Phone do paciente não cadastrado lá | Pedir Matheus pra cadastrar paciente de teste |
| `caretaker_not_found_in_partner` | Idem cuidador | Idem |
| `remote_create_failed` | API deles retornou 4xx/5xx | Olhar logs do api container, conferir auth + payload |

### 2.5 Idempotência

Repete o mesmo POST de roundtrip:

```bash
curl -X POST ... -d '{"care_event_id": "<mesmo>"}'
```

Esperado: `status: "already_synced"` retornando o mesmo
`partner_carenote_id`. Não faz nova POST pro parceiro integrador.

Pra forçar re-envio:
```bash
curl -X POST ... -d '{"care_event_id": "<mesmo>", "force": true}'
```

(Cria duplicata do lado deles — só usar pra debug.)

---

## 3. Cenários a validar com Matheus

### Cenário 1: One-off CLOSED
- Care_event nosso resolved/expired → POST com `status: CLOSED`
- Não aceita addendum depois

### Cenário 2: Streaming (próximo sprint)
- Care_event ainda ativo → POST com `status: OPEN`
- Cada novo aia_health_reports do mesmo evento → POST `/care-notes/{id}/addendums/`
- Quando event resolve → POST addendum com `status: CLOSED`

### Cenário 3 e 4: Bulk
- POST `/care-notes/bulk/` com array de addendums
- `status: OPEN` (continua) ou `status: CLOSED` (já fecha)
- Atômico: se 1 addendum falha, NADA é gravado

POC implementa **só o cenário 1**. Streaming e bulk vêm no
próximo sprint quando tivermos hook automático no pipeline +
worker de retry.

---

## 4. Checklist pra dar ok no piloto

- [ ] Health check retorna `client_enabled: true`
- [ ] Resolve patient por phone retorna `resolved: true`
- [ ] Resolve caretaker por phone retorna `resolved: true`
- [ ] Resolve patient por CPF retorna `resolved: true` (após
      Matheus subir 2026-04-29)
- [ ] Resolve caretaker por CPF retorna `resolved: true` (idem)
- [ ] Roundtrip retorna `status: "ok"` + `partner_carenote_id` numérico
- [ ] Mesmo POST 2× retorna `already_synced` (idempotência local)
- [ ] CareNote criada aparece no painel da parceiro integrador (Matheus
      confirma via screenshot ou GET pelo lado dele)
- [ ] content_resume segue formato `[CLASSE] / Resumo: / Severidade: /`
- [ ] occurred_at do evento está correto no painel deles

---

## 5. Próximos passos pós-validação

1. **Matheus aprova roundtrip** → seguimos pra streaming (cenário 2)
2. **CPF lookup ativo** → trocamos `find_patient_by_phone` pra
   `find_patient_by_cpf` no service (mais estável, telefone muda)
3. **Hook no pipeline** → quando care_event muda status / novo
   report chega, dispara sync async
4. **Worker de retry** → cron pega rows com `sync_error != NULL`
   e re-tenta com backoff exponencial
5. **Webhook reverso** (se Matheus expor) → recebemos quando
   humano edita CareNote no painel deles, atualizamos espelho
