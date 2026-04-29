# STATUS — Smoke Test Tecnosenior (POC validado)

**Data**: 2026-04-29 ~10:25 BRT
**Resultado**: ✅ **POC funcionando end-to-end**, validado por Matheus.

---

## O que foi validado

| Item | Status |
|------|--------|
| Auth `Authorization: Api-Key {chave}` | ✅ |
| `/agent/caretakers/?phone=X` (variants 51XXX, 5551XXX, +5551XXX) | ✅ |
| `/agent/patients/?cpf=X` (CPF sem máscara) | ✅ |
| `POST /agent/care-notes/` com `status:CLOSED` (cenário 1 one-off) | ✅ |
| Idempotência local via `care_event_id UNIQUE` | ✅ |
| Cache local em `aia_health_caregivers/patients.tecnosenior_*_id` | ✅ |
| Format do `content_resume` (`[CLASSE]/Resumo/Severidade/Tags/Encerramento`) | ✅ Matheus confirmou visual no painel |

## Dados do teste

- **Patient**: Armindo Trevisan (UUID nosso `ad36f1ac-6d81-4abb-ad6a-b9dd41ce4614`, CPF `04475046068`, Tecnosenior id=11)
- **Caretaker**: Matheus Campello (UUID `4f805997-74c9-41bb-ba5a-e22e7a4feea2`, phone 51999524816, Tecnosenior id=2)
- **Care Event**: `d013f79d-fc70-40cc-aba4-6f3d0e0ab81b` (#30, status=resolved, "Aferição PA 120x80")
- **CareNote criada**: id=2 status=CLOSED no painel TotalCare-Vidafone

## Próximas frentes

1. Cenário 2 (streaming) — care_event OPEN + addendums conforme follow-ups
2. Hook automático no pipeline quando event muda status / novo report
3. Worker de retry (sync_error != NULL → backoff exponencial)
4. Webhook reverso (V2 — quando Matheus implementar fechamento manual no TotalCare)
