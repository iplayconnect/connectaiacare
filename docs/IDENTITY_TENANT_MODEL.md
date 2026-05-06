# Identity & Tenant Model — Decisão Arquitetural Pendente

> Doc decisório. Estado: pendente revisão de Alexandre + Henrique + Willian.
> Última atualização: 2026-05-06

## Por que isso importa

ConnectaIACare hoje amarra TODA identidade a um único `tenant_id` por linha:
- `aia_health_users` (médico/enfermeiro/operador/admin) — `tenant_id NOT NULL`
- `aia_health_caregivers` — `tenant_id NOT NULL`
- `aia_health_patients` — `tenant_id NOT NULL`

Isso funciona pra ILPI grande mas **quebra** em 6 cenários reais que vão aparecer
no piloto Tecnosenior, Hospital Divina Providência e em qualquer cliente B2C.

## Tipos de tenant atuais (migration 052)

`ILPI | clinica | hospital | B2C | individual`

## Os 6 cenários que quebram

### 1. Médico com vínculo em N organizações

Cardiologista atende ILPI A (3x/sem) + clínica B (consultório próprio) + hospital
C (plantão emergência). Mesmo CRM, mesma pessoa, **3 tenants**.

**Hoje**: precisa criar 3 rows em `aia_health_users` (3 contas separadas, login
distinto, históricos isolados). Errado: o médico é UM, só atua em N orgs.

### 2. Cuidador profissional autônomo (PJ/MEI)

Cuidadora autônoma atende família X (idoso em casa) + família Y + às vezes
plantão extra na ILPI Z quando chamam. Não é funcionária de ninguém — é
prestadora.

**Hoje**: precisa de tenant. Solução improvisada hoje seria criar tenant `B2C`
per família, e ela vira "caregiver" em cada um. 3 famílias = 3 tenants = 3 rows.
Pior: ela não tem login institucional próprio.

### 3. Família com idosos em N ILPIs

Pessoa cuida da mãe no lar X e do pai no lar Y. Mesmo phone resolve **dois
matches `familia`**, em **dois tenants**. Hoje `_select_primary` escolhe um —
perde contexto do outro. Pra Sofia conversar coerente, ela precisa saber:
"essa pergunta é sobre mãe ou pai?".

### 4. Operador da Central 24h

Trabalho do operador é receber handoff **de qualquer tenant** que contratou a
Central. Hoje `users.tenant_id NOT NULL` o trava em um tenant. Funciona porque
`alexandre@connectaia.com.br` é `super_admin` (cross-tenant by design). Mas
operador comum não é super_admin — precisa de scope cross-tenant intermediário.

### 5. Parceiros institucionais (Henrique PUC/RS, Murilo Tecnosenior)

Henrique revisa regras clínicas — atravessa tenants por definição (regras
farmacológicas são plataforma-wide). Murilo opera Tecnosenior mas integra com
o ConnectaIACare via API — pode precisar visão consolidada.

### 6. Paciente individual que muda de contexto

Paciente assina sozinho como `individual`. 6 meses depois muda pra ILPI.
**Hoje**: criar novo `aia_health_patients` no tenant ILPI + migrar histórico
clínico (medications, conditions, baselines) manualmente. Risco de perder dados.

## Proposta arquitetural

**Separar IDENTIDADE GLOBAL de MEMBERSHIP por tenant**:

```sql
-- aia_health_users (refactor)
-- Identidade global da pessoa (CPF, CRM, nome, phone)
-- tenant_id vira home_tenant_id NULLABLE (autônomo = NULL)
ALTER TABLE aia_health_users
  RENAME COLUMN tenant_id TO home_tenant_id;
ALTER TABLE aia_health_users
  ALTER COLUMN home_tenant_id DROP NOT NULL;

-- NOVA: aia_health_user_tenant_memberships
-- N memberships por user (1:N tenants), com role e scope
CREATE TABLE aia_health_user_tenant_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES aia_health_users(id) ON DELETE CASCADE,
  tenant_id text NOT NULL REFERENCES aia_health_tenants(id),
  role text NOT NULL CHECK (role IN (
    'medico', 'enfermeiro', 'cuidador_pro', 'admin', 'operador',
    'central_operator_24h', 'clinical_reviewer', 'parceiro'
  )),
  scopes jsonb DEFAULT '{}'::jsonb,
  -- ex: {"can_prescribe": true, "patients": ["all" | <patient_ids>]}
  active boolean NOT NULL DEFAULT TRUE,
  started_at timestamptz NOT NULL DEFAULT NOW(),
  ended_at timestamptz,
  PRIMARY KEY (user_id, tenant_id, role)
);

-- aia_health_caregivers — mesmo padrão
-- caregiver autônomo: tenant_id NULL, memberships só pra ILPI/clínica que o emprega

-- aia_health_patients — tenant_id NOT NULL (paciente sempre pertence a 1 contexto)
-- Pra mover paciente entre tenants, criar tabela de migration history
CREATE TABLE aia_health_patient_tenant_history (
  patient_id uuid REFERENCES aia_health_patients(id),
  from_tenant_id text,
  to_tenant_id text NOT NULL,
  moved_at timestamptz NOT NULL DEFAULT NOW(),
  reason text
);

-- family (JSONB responsible) — fica como está. Familiar não vira user
-- até decidir assinar/criar conta.
```

## Identity resolver passa a retornar

```python
Identity(
    phone=...,
    user_id="abc123",                  # GLOBAL (mesmo em N tenants)
    matches=[
        IdentityMatch(tenant_id="hospital_divina", profile="medico", scope={"patients": ["all"]}),
        IdentityMatch(tenant_id="ilpi_a", profile="medico", scope={"patients": [<ids>]}),
        IdentityMatch(tenant_id="connectaiacare_demo", profile="medico_emergencia"),
    ],
    primary=...,  # escolhido por: tenant da instance/DID que recebeu webhook
)
```

## Sofia escolhe tenant ativo por contexto do canal

| Canal | Tenant ativo |
|---|---|
| WhatsApp via instância `Connectaiacare` | `connectaiacare_demo` |
| WhatsApp via futura instância `Tecnosenior` | `tecnosenior` |
| Voice via DID `5130624363` | `connectaiacare_demo` |
| Voice via futuro DID Hospital Divina Providência | `hospital_divina` |

Se o phone tem membership no tenant da instância, role daquele tenant manda.
Se não tem, cai pra primary global ou anonymous.

## Operador cross-tenant (Caso 4)

Operador da Central 24h fica como user com:
- `home_tenant_id = NULL`
- `memberships`:
  - `(connectaiacare_demo, central_operator_24h)`
  - `(hospital_divina, central_operator_24h)`
  - `(tecnosenior, central_operator_24h)`
  - …todo cliente que contratou a Central

Painel de handoff filtra por tenant_id da fila + verifica que operador tem
membership ativo nesse tenant pra reivindicar.

## Henrique / clinical_reviewer (Caso 5)

User com `home_tenant_id = NULL` e memberships em todos os tenants com
role `clinical_reviewer`. Acessa endpoints `/clinical-rules/*` direto
(curadoria global) sem necessidade de tenant scope.

Murilo Tecnosenior fica como `parceiro` em `tenant=tecnosenior`. Vê só
dados do próprio tenant. APIs externas (totalcare-vidafone) continuam
mediadas por integration tokens.

## Migração proposta — passos seguros

### Fase 1 — Membership tabela (zero risco)

```sql
CREATE TABLE aia_health_user_tenant_memberships (...);
-- Backfill: pra cada row em aia_health_users existente, criar
-- 1 membership com role=users.role e tenant_id=users.tenant_id
INSERT INTO aia_health_user_tenant_memberships (user_id, tenant_id, role)
SELECT id, tenant_id, role FROM aia_health_users WHERE active = TRUE;
```

Schema antigo continua funcionando. Novo schema fica disponível pra leitura.

### Fase 2 — Identity resolver lê membership

```python
def _lookup_users(phone, tenant_id=None):
    # ANTIGO: SELECT * FROM users WHERE phone = phone AND tenant_id = ?
    # NOVO: SELECT u.*, m.tenant_id, m.role
    #         FROM users u
    #         JOIN memberships m ON m.user_id = u.id
    #         WHERE u.phone = phone AND m.active = TRUE
    #           [AND m.tenant_id = ? if tenant_id]
```

Compatibilidade: enquanto user tem 1:1 (todo user tem 1 membership do
backfill), comportamento idêntico. Quando user passa a ter N memberships,
identity_resolver retorna N matches.

### Fase 3 — Suporte a `home_tenant_id NULL`

Auth/JWT muda pra não exigir `tenant_id` no token. Login retorna lista de
memberships, frontend escolhe contexto ativo. APIs aceitam `X-Active-Tenant`
header pra scopear queries (validado contra memberships).

### Fase 4 — Caregivers refactor (mesmo padrão)

Caregiver autônomo passa a poder atender N famílias sem N rows duplicadas.

## Impacto em Phase C (agents)

- **Phase C v2 (atual)**: `CareSofiaAgent` assume cuidador 1 tenant
  (compatible com schema atual + membership single-row do backfill)
- **Phase C v3 — `MedicalSofiaAgent`**: PRIMEIRO agente que **força**
  decisão de membership porque médico-N-orgs é caso comum. NÃO codar
  antes de Fase 2 desta migração estar em prod.
- **Phase C v3 — `FamilySofiaAgent`**: pode codar antes (família continua
  via JSONB `responsible`, não vira user até subscrever app)

## Decisão pendente — 3 opções

**(A) Migrar agora, antes de mais agents** (3-5 sessões dedicadas)
- Pro: schema correto desde já. Phase C v3+ nasce em cima do modelo certo.
- Con: atrasa entregas clínicas (CareSofiaAgent + Familia + Paciente).

**(B) Migrar depois do piloto Tecnosenior validar** (3-4 meses adiante)
- Pro: piloto valida produto antes de mexer em fundação.
- Con: refactor maior porque mais rows pra migrar; possível dor com
  médicos N-orgs em hospitais.

**(C) Migração incremental — Fase 1 (memberships table) agora,
Fases 2-4 quando primeiro caso real bater** (recomendado)
- Pro: tabela existe, backfill done, código velho continua funcionando.
  Quando médico N-orgs aparecer (provável: Hospital Divina Providência),
  Fases 2-3 executam só pra esse caso.
- Con: alguma complexidade de "qual schema tô usando" durante transição.

Recomendação: **(C)**.

## Próximos passos sugeridos

1. **Decisão (A)/(B)/(C) com Willian + Henrique** na reunião 2026-05-07
2. Se (C) aprovado: migration `068_user_tenant_memberships.sql` (aditiva,
   zero risco) na próxima sessão de manutenção
3. Phase C v3 (FamilySofiaAgent + PatientSofiaAgent) pode prosseguir sem
   bloqueio
4. MedicalSofiaAgent só após Fase 2 estar em prod
