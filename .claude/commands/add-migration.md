---
description: Cria nova migration SQL seguindo o padrão do projeto (aia_health_*)
argument-hint: <short-description>
---

Crie uma nova migration PostgreSQL para o ConnectaIACare.

**Argumento `$ARGUMENTS`**: descrição curta do que a migration faz (ex: `add_medication_interactions_table`).

## Processo

1. **Leia o schema atual** para contexto:
   - `backend/migrations/001_initial_schema.sql`
   - `backend/migrations/002_mock_patients.sql`
   - `backend/migrations/003_voice_biometrics.sql`

2. **Determine o próximo número sequencial**: liste `backend/migrations/*.sql`, pegue o maior número, some 1.

3. **Pergunte ao usuário** detalhes que faltam:
   - Nome exato da tabela (deve começar com `aia_health_`)
   - Campos e tipos (incluir JSONB quando fizer sentido)
   - FKs necessárias (ex: `patient_id REFERENCES aia_health_patients(id)`)
   - Índices necessários (pensar em queries comuns)
   - Se precisa trigger `updated_at` (usar `aia_health_set_updated_at()`)
   - LGPD: se contém PHI, precisa de audit trail?

4. **Crie o arquivo** `backend/migrations/NNN_<slug>.sql` seguindo estes padrões:

```sql
-- ConnectaIACare — Migration NNN: <descrição>
-- Data: YYYY-MM-DD
-- Motivo: <por que essa migration existe>

BEGIN;

-- Tabela principal
CREATE TABLE IF NOT EXISTS aia_health_<nome> (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id TEXT NOT NULL DEFAULT 'connectaiacare_demo',
    -- ... outros campos
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_<nome>_tenant ON aia_health_<nome>(tenant_id);
-- ... mais índices conforme queries

-- Trigger updated_at
DROP TRIGGER IF EXISTS trg_<nome>_updated ON aia_health_<nome>;
CREATE TRIGGER trg_<nome>_updated BEFORE UPDATE ON aia_health_<nome>
    FOR EACH ROW EXECUTE FUNCTION aia_health_set_updated_at();

COMMIT;
```

5. **Regras críticas**:
   - ✅ Use `CREATE TABLE IF NOT EXISTS` — migrations são re-executadas em setup-vps
   - ✅ Sempre incluir `tenant_id` (multi-tenant preparado)
   - ✅ Sempre incluir `created_at` e `updated_at` com trigger
   - ✅ UUIDs via `uuid_generate_v4()`
   - ✅ JSONB para campos flexíveis (conditions, metadata, etc.)
   - ❌ NUNCA reverter/drop sem confirmar com o usuário
   - ❌ NUNCA incluir dados reais de paciente no arquivo de migration

6. **Atualize scripts relacionados**:
   - `scripts/init_db.sh`: adicionar linha para rodar a nova migration
   - `scripts/verify.sh`: se for crítico, adicionar check
   - Atualizar `CLAUDE.md` seção 4 (Estrutura do Banco de Dados) se adicionou tabela nova

7. **Sintaxe check** (opcional mas recomendado):
   ```
   docker compose exec -T postgres psql -U postgres -d connectaiacare --set ON_ERROR_STOP=on -f - < backend/migrations/NNN_<slug>.sql
   ```
   (rodar em ambiente de teste primeiro)

8. **Ofereça ao usuário**:
   - Commit único com a migration + updates nos scripts
   - Mensagem sugerida: `feat(db): migration NNN — <descrição>`
