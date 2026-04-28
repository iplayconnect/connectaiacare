# Decisões — B2C + Individual (estrutura de licença + tom + uso)

**Data**: 2026-04-28
**Última revisão**: 2026-04-28 — após correção arquitetural do Alexandre.

**Origem**: Alexandre confirmou que tem casos de **usuários
individuais** entrando agora. Precisamos fechar 3 pontos:

1. B2C: 1 paciente ou múltiplos por tenant?
2. Tom da Sofia para paciente que reporta sobre si mesmo (forma de
   tratamento)
3. Cap de mensagens em planos com mensalidade

> **Correção arquitetural (sessão 2026-04-28)**: a primeira versão
> deste doc tinha `tenant_type='individual'` e `licensing_model=
> 'individual'` como entidades de primeira classe. **Errado**.
> Alexandre apontou: "B2C direto no ID_CPF, não vamos queimar uma
> posição de Tenant pra um único usuário, mas podemos pensar em
> casos de 3 cuidadores manhã/tarde/noite". A arquitetura final
> está abaixo.

---

## 1. Estrutura de licença: tudo dentro de B2C, "individual" é flag por paciente

### Cenários reais que vão acontecer

| Cenário | Quem assina | Quem é paciente | Quem reporta |
|---------|-------------|-----------------|--------------|
| Filho cuida da mãe em casa | Filho | Mãe | Filho ou cuidador particular |
| Filho cuida do pai E da mãe juntos | Filho | Pai E mãe | Filho ou 1+ cuidadores |
| Casal idoso, cada um contrata sua Sofia | Cada idoso | Si mesmo | Si mesmo (privacidade) |
| Idoso solo na casa, autônomo | Idoso | Si mesmo | Si mesmo |
| Filho mora longe, paga Sofia + 3 cuidadores rotativos pra mãe | Filho | Mãe | 3 cuidadores (manhã/tarde/noite) |

### Posição (final, após correção)

**Não criamos tenant separado pra cada paciente "individual"**. Em
vez disso, **1 tenant B2C agrega N pacientes**, com privacy via
patient_id + RBAC.

**Modelo único pra fora de instituição:**

- `tenant_type = 'B2C'` — todos os casos domiciliares.
- `licensing_model = 'b2c_per_patient'` — fatura por paciente.
- Cada paciente identificado por **CPF** (`aia_health_patients.cpf`),
  índice único por tenant.
- Paciente sem cuidador (idoso solo) marcado por
  `is_self_reporting = TRUE`.
- Paciente com 1-3 cuidadores: relação explícita em
  `aia_health_caregiver_patient_assignments`.
- Plantão por cuidador (já implementado), agora cruzado com
  assignments na VIEW `aia_health_active_caregivers_by_patient`.

**Casos resolvidos:**

| Cenário | Configuração |
|---------|--------------|
| Filho cuidando de mãe em casa | tenant B2C, 1 paciente (mãe), filho como caregiver `family` is_primary, mãe `is_self_reporting=FALSE` |
| Filho cuidando de pai E mãe | tenant B2C, 2 pacientes, filho assigned aos dois |
| Idoso solo na casa | tenant B2C, 1 paciente com `is_self_reporting=TRUE`, 0 caregivers |
| Casal idoso, contas separadas | 2 tenants B2C distintos, 1 paciente cada (privacidade) |
| 3 cuidadores rotativos manhã/tarde/noite | tenant B2C, 1 paciente, 3 caregivers assignados, cada um com `aia_health_shift_schedules` no seu turno |

### Por que assim?

1. **Não desperdiça posição de tenant** (preocupação válida do
   Alexandre — escala administrativa).
2. **Privacy preservada** entre pacientes via patient_id + RBAC.
3. **Plantão funciona em B2C também**: 3 cuidadores rotativos por
   paciente já cabem no schema atual + `caregiver_patient_assignments`.
4. **CPF como login estável** (não muda quando paciente troca de
   telefone/cuidador).
5. **`is_self_reporting`** captura o caso "idoso solo" como flag de
   comportamento, sem inflação de schema.

### Casal idoso — caso de privacidade absoluta

Marido e esposa onde **cada um quer privacidade total** = 2 tenants
B2C distintos. Não é "1 tenant com 2 pacientes". O dado da depressão
da esposa não pode estar na mesma fronteira de privacidade do marido.

(Se eles aceitam compartilhar, podem usar 1 tenant com 2 pacientes
e ter Sofia atendendo família — mas é decisão deles na contratação.)

---

## 2. Tom da Sofia para paciente `is_self_reporting=TRUE`

### Considerações

- Idoso brasileiro **frequentemente** prefere "senhor/senhora"
  como sinal de respeito.
- Mas há quem prefira intimidade ("me chama de Maria mesmo, pelo
  amor de Deus").
- Tom da Sofia (calma, acolhedora, lenta) é **separado** da forma
  de tratamento.

### Posição (recomendação)

**Sofia pergunta no onboarding** e grava preferência por paciente:

```
Sofia: "Olá! Eu sou a Sofia, sua assistente.
       Você prefere que eu te chame de Maria ou de Dona Maria?
       Pode escolher o jeito que se sentir mais à vontade."
```

Resposta gravada em **`aia_health_patients.preferred_form_of_address`**:
- `first_name` → "Maria"
- `formal` → "Dona Maria" / "Sr. José"
- `full_first_name` → "Dona Maria Helena" (nome composto)
- `nickname` → "Mariazinha" (apelido carinhoso)

**Default conservador** se paciente não respondeu: `formal`. É
melhor errar pelo respeito.

### Tom independente da forma

Tom da Sofia em paciente `is_self_reporting=TRUE` é **sempre
acolhedor**, independente de como chama. Características:

- Frases curtas (idoso processa mais devagar texto longo)
- Pausas naturais em áudio (TTS com SSML)
- Repete pergunta de forma diferente se não entender
- Nunca usa termos técnicos sem explicar
- Pergunta "sim ou não" em situações críticas (Grok insight)

Em B2C com cuidador, Sofia trata **cuidador** pelo primeiro nome
(filho/neto chama pela informalidade) e **paciente** pelo
`preferred_form_of_address` quando se dirige a ele.

---

## 3. Cap de mensagens em B2C/individual

### Problema

Em planos com mensalidade fixa, sem cap o cliente que abusa do uso
fica caro pra gente (custo Deepgram + LLM + storage). Mas
**capping rígido pode cortar quem mais precisa** — paciente em
crise mandando 30 mensagens numa noite é exatamente quando Sofia
deve atender.

### Posição (recomendação)

**Fair use com cap soft + emergency override:**

| Plano | Quota mensal | Comportamento |
|-------|--------------|---------------|
| Essencial | 100 msg/mês | Cobre uso normal (3-4 msg/dia) |
| Padrão | 300 msg/mês | Pra famílias mais ativas |
| Premium | 2.000 msg/mês | Teto suave + atendimento humano prioritário; cap rígido só acima de 2.000 (proteção contra abuso) |

**Regras:**

1. **Aviso aos 80%** — Sofia menciona uma única vez: "Você usou
   80% do plano deste mês. Se passar de 100% continuo te atendendo,
   mas pra uso pesado o plano X custa mais barato."

2. **Acima de 100% — continua atendendo, com 2 modificações:**
   - Latência levemente maior (modelo mais barato no STT, classifier
     menor). Não cortado, só mais devagar.
   - Não dispara push proativo da Sofia até reset.

3. **Override de emergência — sempre passa**, mesmo se zerou quota:
   - Mensagens com keywords críticas (queda, dor torácica, parada,
     convulsão, sangramento intenso, AVC, suspeita IAM)
   - Detectada pelo regex fast-path (ele roda antes da quota check)
   - Loga em `quota_emergency_overrides` pra futuro audit

4. **Reset no dia 1** do mês via cron.

### Alternativa que descarto

**Cap rígido** (corta no Nº mensagem). **Risco**: dia que cuidador
realmente precisa, sistema falha por motivo financeiro. Imagem
ruim, risco clínico. Quota deve ser sinal econômico, não barreira
clínica.

---

## 4. Schema final (migrations 052 + 053 + 054)

Migrations 052 e 053 criaram a base. Migration 054 corrigiu a
arquitetura após o feedback do Alexandre:

```sql
-- 052: tenant_type (sem 'individual' após 054)
-- valores finais: 'ILPI' | 'clinica' | 'hospital' | 'B2C'
ALTER TABLE aia_health_tenant_config
    ADD COLUMN tenant_type TEXT NOT NULL DEFAULT 'ILPI';

-- 053 + 054: licensing_model binário
-- valores finais: 'b2b_organization' | 'b2c_per_patient'
ALTER TABLE aia_health_tenant_config
    ADD COLUMN licensing_model TEXT DEFAULT 'b2b_organization';

-- Quota
ALTER TABLE aia_health_tenant_config
    ADD COLUMN message_quota_monthly INT,  -- NULL = ilimitado
    ADD COLUMN quota_warning_threshold_pct INT NOT NULL DEFAULT 80;

-- 053: forma de tratamento por paciente
ALTER TABLE aia_health_patients
    ADD COLUMN preferred_form_of_address TEXT
        DEFAULT 'formal'
        CHECK (preferred_form_of_address IN (
            'first_name', 'formal', 'full_first_name', 'nickname'
        ));

-- 054: paciente solo + CPF
ALTER TABLE aia_health_patients
    ADD COLUMN is_self_reporting BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN cpf TEXT;
CREATE UNIQUE INDEX idx_patients_cpf_per_tenant
    ON aia_health_patients(tenant_id, cpf) WHERE cpf IS NOT NULL;

-- 054: relação explícita cuidador ↔ paciente (N:M)
CREATE TABLE aia_health_caregiver_patient_assignments (
    id UUID PRIMARY KEY,
    tenant_id TEXT,
    caregiver_id UUID REFERENCES aia_health_caregivers,
    patient_id UUID REFERENCES aia_health_patients,
    relationship TEXT,  -- professional|family|volunteer
    is_primary BOOLEAN,
    active BOOLEAN
);

-- 054: VIEW pra resolver pool de biometria por paciente
CREATE VIEW aia_health_active_caregivers_by_patient AS ...

-- 053: contadores de uso e overrides de emergência
CREATE TABLE aia_health_message_usage (...);
CREATE TABLE aia_health_quota_overrides (...);
```

---

## 5. Não vou implementar agora

A enforcement de quota (verificar no pipeline antes de processar)
fica pra próximo sprint. Hoje:

- ✅ Schema da migration 053 (decisões persistidas no banco)
- ✅ `licensing_model` e `tenant_type` independentes:
  - `tenant_type` afeta comportamento operacional (plantão, biometria)
  - `licensing_model` afeta cobrança e cap de uso
- ❌ Quota check no pipeline (próximo sprint)
- ❌ Cron de reset mensal (próximo sprint)
- ❌ Aviso aos 80% (próximo sprint)
- ❌ Onboarding pergunta forma de tratamento (próximo sprint —
  parte do classifier de inputs)

Por que separar: as decisões precisam estar no banco já pra cadastrar
os primeiros tenants individual sem dívida de schema. A enforcement
pode ser wired quando tivermos os primeiros tenants reais usando.

---

## 6. Status das decisões (sessão 2026-04-28)

| # | Decisão | Status | Notas |
|---|---------|--------|-------|
| 1 | B2C por paciente / individual = flag, não tenant | ✅ Confirmado + corrigido em 054 | "Não vamos queimar tenant pra usuário único" |
| 2 | `preferred_form_of_address` default formal | ✅ Implícito em manter o default | Sofia pergunta no onboarding pra ajustar |
| 3 | Quotas 100/300/Premium com teto 2000 + cap rígido acima | ✅ Confirmado | Premium não é ilimitado, é "alto e protegido" |
| 4 | Emergency override (keywords críticas sempre passam) | ✅ Confirmado | Não-negociável |

### Observações pendentes (próximos sprints)

- **Plantão por paciente** em B2C com 3 cuidadores rotativos:
  schema cobre via `aia_health_caregiver_patient_assignments` +
  `aia_health_shift_schedules`. UI de cadastro precisa expor a
  relação (frontend `/admin/plantoes` ainda assume cuidador→tenant
  sem `patient_id` no fluxo de cadastro).

- **Onboarding de paciente B2C com CPF** como login: a tela
  precisa coletar CPF + telefone + se é `is_self_reporting` ou
  tem cuidadores. Sofia conduz isso via WhatsApp (já existe ADR-026
  pra B2C onboarding).

- **Enforcement de quota** (cron de reset + check no pipeline):
  fica pra sprint dedicado. Schema preparado, lógica não.
