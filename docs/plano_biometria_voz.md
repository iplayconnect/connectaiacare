# Plano — Biometria de Voz (full)

**Status**: implementação inicial pronta na branch `claude/auth-impl`.
NÃO foi deployado em produção. Aguardando revisão do Alexandre.

**Data**: 2026-04-28

---

## 1. Objetivo

A Sofia recebe áudio de WhatsApp e atende ligações via PJSIP. Hoje o
remetente é identificado pelo número de telefone — mas em um lar com
paciente + cuidador, ambos podem usar o mesmo aparelho. Sintomas
reportados por terceiro acabam atribuídos ao paciente errado.

Biometria de voz resolve identificando QUEM está falando, não só de
qual número. Isso aumenta:

- Precisão clínica (sintoma vai pro prontuário certo).
- Trust score (relato do próprio paciente vale diferente do relato de
  cuidador).
- Anti-fraude (terceiro tentando se passar pelo paciente).

---

## 2. Arquitetura

```
[áudio entra]
    ↓
audio_preprocessing.preprocess()
  → VAD + normalização + quality gate (SNR + duração)
    ↓
Resemblyzer (256-dim L2-normalized)
    ↓
pgvector cosine similarity
    ↓
identify_1toN entre cuidadores+pacientes do tenant
    ↓
escolha do match com threshold + ambiguity margin
```

**Modelo**: Resemblyzer (~50MB, MIT, runs CPU). Empilha em ~0.5-1s por
clipe de 5s. Embedding 256-dim L2-normalized — comparação por cosine.

**Por que Resemblyzer e não ECAPA-TDNN/SpeechBrain**: Resemblyzer já
estava em `requirements.txt` (migration 003 do projeto) e o serviço
`voice_biometrics_service.py` foi escrito em torno dele. Não vale o
custo de migrar até termos métricas que justifiquem.

---

## 3. Esquema de banco

### Tabela `aia_health_voice_embeddings` (estendida em 050)

| Coluna | Tipo | Notas |
|--------|------|-------|
| id | UUID PK | |
| **person_type** | TEXT | `caregiver` \| `patient` (XOR via CHECK) |
| caregiver_id | UUID NULL | FK aia_health_caregivers (nullable agora) |
| **patient_id** | UUID NULL | FK aia_health_patients (novo) |
| tenant_id | TEXT | |
| embedding | VECTOR(256) | Resemblyzer |
| sample_label | TEXT | "enrollment_1", "enrollment_2", … |
| audio_duration_ms | INT | |
| quality_score | NUMERIC(4,3) | overall do preprocess |
| consent_ip | TEXT | IP do enrollment (LGPD) |
| consent_given_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

**Constraint**: `voice_embeddings_xor_person` garante exatamente um
dos dois IDs preenchido (paciente OU cuidador, nunca os dois).

### Tabela `aia_health_voice_consent_log`

Estendida com `patient_id` e `person_type`. Ações:
`consent_given`, `consent_revoked`, `data_accessed`, `data_deleted`,
`enrollment_added`. Cada chamada do motor (1:1, 1:N, identify_any)
loga em `data_accessed` com metadata JSONB para calibração futura
de threshold com dados reais.

### View `aia_health_voice_coverage_summary`

Resumo por tenant + person_type: pessoas enroladas, total de
amostras, qualidade média, primeira e última gravação.

---

## 4. Service (`voice_biometrics_service.py`)

### Métodos cuidador (já existiam)
- `enroll(caregiver_id, ...)` — quality gate `MIN_ENROLL_QUALITY=0.55`
- `verify_1to1(caregiver_id, audio)` — threshold 0.75
- `identify_1toN(audio)` — threshold 0.65 + ambiguity margin 0.05
- `delete_enrollment(caregiver_id)` — LGPD revogação
- `get_enrollment_status(caregiver_id)` — N amostras, qualidade

### Métodos paciente (novos, 2026-04-28)
- `enroll_patient(patient_id, ...)`
- `verify_patient_1to1(patient_id, audio)`
- `identify_patient_1toN(audio)` — só em pool de pacientes
- `identify_any_1toN(audio)` — pool unificado paciente + cuidador
- `delete_patient_enrollment(patient_id)`
- `get_patient_enrollment_status(patient_id)`

### Helper geral
- `list_coverage_summary(tenant_id)` — para painel admin

### Cache
Cache em memória 5 min de embeddings agregados por tenant
(`_CacheEntry`). Carrega cuidadores e pacientes em uma passada;
invalidado em todo enroll/delete. Para tenants pequenos, full-scan
em RAM é mais rápido que pgvector index.

---

## 5. Endpoints REST

### Cuidador (já existiam, sem auth)
- `POST /api/voice/enroll`
- `GET /api/voice/enrollment/<caregiver_id>`
- `DELETE /api/voice/enrollment/<caregiver_id>`

> **TODO de segurança**: aplicar `@require_role` nos endpoints de
> cuidador (hoje estão sem RBAC). Foi mantido como estava pra não
> quebrar testes existentes — mover em PR separado com migração de
> testes.

### Paciente (novos, com `@require_role`)
- `POST /api/voice/patient/enroll` — `super_admin, admin_tenant, medico, enfermeiro`
- `GET /api/voice/patient/enrollment/<patient_id>` — idem
- `DELETE /api/voice/patient/enrollment/<patient_id>` — só `super_admin, admin_tenant`

### Painel
- `GET /api/voice/coverage` — resumo de cobertura
- `GET /api/voice/enrollments` — lista pessoas enroladas

---

## 6. Frontend

### `/admin/biometria-voz`

- Cards de cobertura (pacientes / cuidadores / amostras / qualidade).
- Tabela de pessoas enroladas com filtro por tipo + busca por nome.
- Botão "Cadastrar amostra" abre modal:
  1. Escolhe tipo (paciente / cuidador) e seleciona pessoa do dropdown.
  2. Grava 5-10s via `MediaRecorder` API do navegador.
  3. Preview do áudio com `<audio controls>` antes de enviar.
  4. Envia base64 para `/api/voice/(patient/)?enroll`.
  5. Mostra resultado: amostras totais, qualidade desta, e se
     enrollment está completo (3+ amostras).

### Sidebar
Item "Biometria de Voz" no grupo admin, ícone `Volume2`. Visível pra
super_admin, admin_tenant, médico, enfermeiro.

---

## 7. LGPD — pontos críticos

1. **Embedding ≠ áudio**. O vetor 256-dim não é reversível para o áudio
   original — não pode ser usado pra reproduzir voz. Mesmo assim é
   considerado dado biométrico sensível (Art. 11) e exige consentimento
   explícito.

2. **Consentimento**: hoje o admin clica "Cadastrar" — o ato implica
   consentimento. Cada enrollment grava em
   `aia_health_voice_consent_log` com IP e timestamp. **Próxima fase**:
   modal de consentimento explícito antes de gravar (assinatura
   digital ou áudio verbal de consent). Hoje é registro implícito via
   audit_log.

3. **Direito ao esquecimento**: botão de revogar na tabela apaga TODOS
   os embeddings da pessoa + log `data_deleted`. Operação irreversível.

4. **Acesso ao dado**: cada `identify_1toN` ou `verify_1to1` loga
   `data_accessed` com score, qualidade, accepted/rejected. Permite
   auditoria de quem/quando consultou biometria de quem.

5. **Retenção**: hoje sem TTL. Quando paciente sai do programa
   (active=FALSE), embeddings ficam. **Próxima fase**: cron de limpeza
   após 30 dias de inatividade ou exclusão explícita do paciente.

---

## 8. Thresholds e qualidade

Valores conservadores (cenário médico):

| Threshold | Valor | Significado |
|-----------|-------|-------------|
| `VERIFY_1TO1_THRESHOLD` | 0.75 | confirma identidade conhecida |
| `IDENTIFY_1TON_THRESHOLD` | 0.65 | identifica entre N |
| `IDENTIFY_AMBIGUITY_MARGIN` | 0.05 | top1 deve superar top2 em ≥5pp |
| `MIN_ENROLL_QUALITY` | 0.55 | recusa enrollment ruim |
| `MIN_IDENTIFY_QUALITY` | 0.30 | tolera identificação em condição ruim |
| `MAX_ENROLLMENT_SAMPLES` | 5 | limite de amostras por pessoa |
| `MIN_SAMPLES_FOR_COMPLETE` | 3 | ideal pra estabilidade |

Após 100+ enrollments reais com calibration log preenchido, refinamos
thresholds via análise dos `data_accessed` em `voice_consent_log` —
basicamente histograma de scores aceitos/rejeitados.

---

## 9. Riscos conhecidos

1. **Voz idosa varia**. Resfriado, prótese dentária mal posicionada,
   medicação afetam timbre. Mitigação: 3+ amostras + threshold
   conservador. Re-enroll periódico (anual?) sugerido.

2. **Replay attack**. Alguém grava o paciente e reproduz pro Sofia.
   Resemblyzer não detecta liveness. Mitigação: combinar biometria com
   challenge-response em chamadas críticas (Sofia pede frase aleatória
   pra paciente repetir).

3. **Falso positivo grave**. Se cuidador é confundido com paciente,
   sintoma vai pro prontuário errado. Mitigação: ambiguity margin +
   logging de match_method em `aia_health_reports.caregiver_voice_method`.

4. **Cold start em pacientes b2c**. Antes do paciente gravar amostra,
   `identify_1toN` retorna `not_enrolled`. Mitigação: fluxo de
   onboarding pede 1 amostra logo no primeiro contato com Sofia
   ("oi, vou só gravar sua voz pra te reconhecer da próxima vez, ok?").

5. **Custo computacional**. Resemblyzer carrega 50MB + 0.5-1s/clipe.
   Em pico de 100 áudios/min, gera load. Mitigação: cache embedding +
   pool de workers Gunicorn dimensionado.

---

## 10. Checklist para deploy

Antes de fazer merge na main:

- [ ] Revisar plano (este doc).
- [ ] Aprovar fluxo de consent — implícito é suficiente pra POC?
- [ ] Definir RBAC final dos endpoints de cuidador (hoje sem auth).
- [ ] Aplicar migrations 049 + 050 em ordem em ambiente de staging
      antes de produção.
- [ ] Validar com Henrique se há contraindicação clínica para
      identificação automática (ex: paciente com doença neurológica
      que altera fala progressivamente).
- [ ] Dry-run do enrollment em pelo menos 1 paciente real + 1
      cuidador real antes de generalizar.

---

## 11. Roadmap após deploy

1. **Fase 1 (curta)**: integrar `identify_1toN` no pipeline WhatsApp
   pra preencher `reporter_person_type` + ajustar trust_score conforme
   quem reportou.

2. **Fase 2 (média)**: hook em `voice-call-service` — sample inicial
   da chamada → identify_any_1toN → Sofia personaliza saudação ("oi
   dona Maria" vs "oi Marlene, está com a dona Maria?").

3. **Fase 3 (longa)**: liveness check via challenge-response.
   Re-enrollment anual automatizado. Pgvector index quando
   ultrapassarmos 100+ embeddings por tenant.
