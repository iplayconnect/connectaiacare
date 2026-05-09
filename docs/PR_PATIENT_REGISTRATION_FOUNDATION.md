# PR `feat/patient-registration-foundation` — base do cadastro completo de paciente

**Branch**: `feat/patient-registration-foundation`
**Stack**: stacked sobre `feat/glossary-api-and-propagation` → `feat/medical-acronyms-glossary` → main
**Data**: 2026-05-09

PR 1 do plano em 3 fases discutido com Henrique. Foundation: schema + bases curadas + endpoints + helpers + acúmulo de papéis. **Não muda nenhuma UI ainda** — UX wizard vem no PR 2.

---

## 1. O que está dentro

### 1.1 Migrations
- **`074_patient_registration_foundation.sql`**:
  - `aia_health_users.additional_roles TEXT[]` — acúmulo de papéis
  - `aia_health_patient_registration_sessions` — audit de sessão (1 row por wizard run)
  - `aia_health_patients.registration_completeness JSONB` — denormalizado pra dashboard
  - `aia_health_patients.last_self_review_at` — trigger automático em conditions/medications/allergies update
  - `aia_health_patient_field_verifications` — clínico validou seção (snapshot imutável)

- **`075_curated_clinical_bases.sql`**: 3 tabelas com versionamento + ciclo de revisão (`draft` → `under_review` → `approved`):
  - `aia_health_cid10_curated` — CID-10 geriátrico (com search trgm)
  - `aia_health_medication_class_dictionary` — medicamento → classe (match por substring)
  - `aia_health_disease_medication_expectations` — regras de cross-validation

- **`076_seed_curated_clinical_bases.sql`**: baseline inicial:
  - **150 CIDs** geriátricos cobrindo cardiovascular, respiratório, endócrino, neuro, psiquiátrico, osteomuscular, **infeccioso (13 entries — Henrique pediu)**, oncológico, urinário, digestivo, sensorial, paliativo
  - **80+ medicamentos** com classes terapêuticas e match patterns
  - **8 condições baseline** pra cross-validation (HAS, DM, IC, FA, Hipotireoidismo, DPOC, Asma, DAC) com `prompt_severity` (critical em FA — risco AVC)
  - Tudo entra como `review_status='draft'` — Henrique e Coordenadora PUC revisam item por item

### 1.2 Backend — helpers e services

- **`utils/patient_data_helpers.py`**: helpers tolerantes pra ler conditions/medications/allergies em formato antigo (string) ou novo (objeto com provenance). Funções:
  - `normalize_clinical_item()` — converte string → objeto canônico
  - `normalize_clinical_array()` — sobre array misto
  - `extract_names()` — só nomes pra match/cross-validation
  - `merge_items()` — preserva provenance histórica ao atualizar (mantém `original_source`, `verified_by_clinician_at`)

- **`services/registration_validation_service.py`**:
  - `validate_conditions_medications(conditions, medications)` — motor de cross-validation
  - `search_cid10(q)` — autocomplete usando pg_trgm
  - `lookup_medication_class(name)` — classifica texto livre

### 1.3 Backend — auth e acúmulo de papéis

- **`services/permissions.py`**: `has_role(user, *roles)` agora checa `role` E `additional_roles[]`. Nova `all_user_roles(user)` lista todos.
- **`handlers/auth_routes.py`**: JWT payload + response do login agora incluem `additional_roles`/`additionalRoles`. Sem breaking change — campo é opcional/array vazio.

### 1.4 Backend — endpoints

Todos sob `patient_registration_routes.py` (novo blueprint):

| Método | Path | Acesso | Função |
|---|---|---|---|
| GET | `/api/cid10/search?q=press` | wizard roles | autocomplete CID-10 |
| GET | `/api/medication-class/lookup?name=losart` | wizard roles | classifica medicamento |
| POST | `/api/registration/validate` | wizard roles | cross-validation |
| GET | `/api/patients/<id>/registration` | wizard roles | sessão atual + completude |
| POST | `/api/patients/<id>/registration/start` | wizard roles | inicia sessão |
| POST | `/api/patients/<id>/registration/save` | wizard roles | salva passo |
| POST | `/api/patients/<id>/registration/complete` | wizard roles | finaliza |
| POST | `/api/patients/<id>/verify/<section>` | clínico (médico/enfermeiro) | marca seção como verified_by_clinician |

`source_map` no save converte `registered_by_role` em `source` no item:
- `paciente_b2c` → `self_declared`
- `familiar_responsavel` → `family_declared`
- `gestor_unidade` → `manager_declared`
- `enfermeiro` / `medico` → `clinician_validated`

### 1.5 Frontend

- **`lib/auth.ts`**: `AuthUser.additionalRoles?: Role[]` (opcional, não-breaking)
- **`lib/permissions.ts`**: `hasRole()` checa primário + acumulados; nova `allUserRoles()` pra UI de chips

---

## 2. O que NÃO está dentro (PR 2 e 3)

### PR 2 — Wizard de cadastro (UI principal)
- Rota `/admin/patients/<id>/registration` (operacional — gestor/clínico)
- Rota pública `/registro` (B2C autônomo, com consent LGPD)
- Stepper de 6-7 telas (Identidade → Condições → Medicações → Alergias → Funcional → Responsáveis → Revisão)
- Autocomplete CID-10 consumindo `/api/cid10/search`
- Soft prompt de cross-validation consumindo `/api/registration/validate`
- Edição de cada seção independente
- Badge de origem (importado / auto-declarado / validado por clínico)

### PR 3 — Acúmulo de papéis na UI
- Página `/admin/usuarios/<id>` permite atribuir N papéis
- Sidebar/roteamento respeitam `additionalRoles` (já tecnicamente respeita via `hasRole`)
- Painéis condicionais (gestor+enfermeiro vê fila wellness E pode validar dados clínicos)

### PR 4 — Procurador (4.3 — diferido)
Quando você quiser ativar. Schema já suporta (`registered_by_role='procurador'` + `procuracao_document_url` no `registration_sessions`).

---

## 3. Como testar

### 3.1 Subir migrations (na ordem)
```sql
\i backend/migrations/074_patient_registration_foundation.sql
\i backend/migrations/075_curated_clinical_bases.sql
\i backend/migrations/076_seed_curated_clinical_bases.sql
```

### 3.2 Verificar bases populadas
```sql
SELECT COUNT(*), category FROM aia_health_cid10_curated GROUP BY category;
SELECT COUNT(*), unnest(therapeutic_classes) AS cls
  FROM aia_health_medication_class_dictionary GROUP BY cls;
SELECT condition_label, prompt_severity FROM aia_health_disease_medication_expectations;
```

### 3.3 Testar autocomplete CID
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://care.connectaia.com.br/api/cid10/search?q=press"
# Esperado: I10 Hipertensão, I11, I12...
```

### 3.4 Testar cross-validation
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": ["Hipertensão Arterial"],
    "medications": []
  }' \
  https://care.connectaia.com.br/api/registration/validate
# Esperado: prompts[0].severity="medium", message="Você marcou HAS mas..."
```

```bash
# Mesmo input com Losartana → prompt vazio
curl -X POST ... -d '{"conditions":["HAS"],"medications":["Losartana 50mg"]}' ...
# Esperado: prompts_count=0
```

### 3.5 Testar acúmulo de papéis
```sql
UPDATE aia_health_users
   SET additional_roles = ARRAY['enfermeiro']
 WHERE email = 'gestor-teste@example.com';
```
Login com esse user → JWT incluirá `additional_roles=["enfermeiro"]` → user pode acessar `/admin/system/operations/wellness` (admin_tenant) **E** revisar campos clínicos como enfermeiro.

### 3.6 Smoke wizard de registro
```bash
# 1. Iniciar sessão
curl -X POST ... \
  -d '{"registered_by_role":"familiar_responsavel","consent_lgpd_accepted":true}' \
  /api/patients/<UUID>/registration/start
# → {session_id: "..."}

# 2. Salvar conditions
curl -X POST ... \
  -d '{"section":"conditions","data":[{"name":"Hipertensão Arterial Sistêmica (HAS)","icd10_code":"I10"}],"step_number":2}' \
  /api/patients/<UUID>/registration/save

# 3. Completar
curl -X POST ... /api/patients/<UUID>/registration/complete

# 4. Ver estado
curl ... /api/patients/<UUID>/registration
# → patient.completeness com percentage atualizado
```

---

## 4. Arquivos modificados/criados

### Criados (8)
- `backend/migrations/074_patient_registration_foundation.sql`
- `backend/migrations/075_curated_clinical_bases.sql`
- `backend/migrations/076_seed_curated_clinical_bases.sql`
- `backend/src/utils/patient_data_helpers.py`
- `backend/src/services/registration_validation_service.py`
- `backend/src/handlers/patient_registration_routes.py`
- `docs/PR_PATIENT_REGISTRATION_FOUNDATION.md` (este)

### Modificados (4)
- `backend/app.py` (registra patient_registration_bp)
- `backend/src/services/permissions.py` (`has_role` + `all_user_roles`)
- `backend/src/handlers/auth_routes.py` (JWT inclui `additional_roles`)
- `frontend/src/lib/auth.ts` (`additionalRoles?` em AuthUser)
- `frontend/src/lib/permissions.ts` (`hasRole` checa acumulado + `allUserRoles`)

---

## 5. Validação técnica

- ✅ Python compila em todos os arquivos tocados (6)
- ✅ TypeScript `tsc --noEmit` 0 erros
- ✅ Migrations idempotentes (CREATE TABLE IF NOT EXISTS, ON CONFLICT DO NOTHING nos seeds)
- ✅ Sem breaking change visual — UI atual continua funcionando
- ✅ Helpers toleram formato antigo (string) e novo (objeto)
- ✅ JWT backward-compat (campo `additional_roles` é array vazio por default)

---

## 6. Pontos clínicos pra Henrique e Coordenadora PUC revisarem

### 6.1 CID-10 (150 entries)
Acessar `aia_health_cid10_curated` ordenado por `category`. Marcar como `approved`/`under_review` por entry. **Discutir adições** — provavelmente faltam alguns CIDs específicos de geriatria que o Henrique conhece bem.

Inclusive **13 infecciosos** (atendendo pedido dele):
- N39.0 (ITU), N30 (cistite), N10 (pielonefrite)
- J18 (pneumonia), J15.9 (broncopneumonia), J69.0 (aspirativa)
- A46 (erisipela), L03 (celulite), B02 (herpes-zóster)
- A41 (sepse), A15 (TB), U07.1 (COVID), B34.2 (coronavírus)

### 6.2 Medicamentos (80+ entries)
Validar:
- Match patterns suficientes? (paciente pode escrever "puran t4" ou "synthroid" ou "levotiroxina")
- Classes terapêuticas corretas?
- Faltou algum medicamento muito comum?

### 6.3 Cross-validation (8 baseline)
- **FA com `severity=critical`** — defendi como o mais grave (risco AVC embólico). Validar.
- Outros estão `medium`/`high` — discutir.
- `prompt_message` — texto que o paciente vê. Validar tom (amigável vs técnico).
- `clinical_rationale` — só audit, não vai ao paciente, mas justifica clinicamente.

---

## 7. Próximos passos

Mergeada esta PR + migrations rodadas em prod, próximo é o **PR 2 (Wizard UI)**. Vai consumir:
- `/api/cid10/search` (autocomplete na tela de condições)
- `/api/medication-class/lookup` (feedback enquanto digita medicação)
- `/api/registration/validate` (soft prompt antes de avançar)
- `/api/patients/<id>/registration/*` (start/save/complete)

UI proposta:
- 7 telas (1 pergunta principal por tela em mobile)
- Stepper visual com badge de "completed/current/locked"
- Cada item lista mostra badge de origem (cinza="importado", azul="auto-declarado", verde="validado por clínico")
- Soft prompt aparece como modal antes de "Próximo" se houver mismatch (resposta vai pro `notes` do item)

Estimativa: 1-2 dias de trabalho.
