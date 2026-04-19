---
description: Auditoria LGPD do código atual — PHI handling, base legal, direitos do titular, retenção
---

Execute uma auditoria LGPD completa do código atual do ConnectaIACare.

**Contexto**: dados médicos são sensíveis (Art. 11). Responsabilidade primária do controlador (SPA/clínica), mas operador (nós) tem obrigações concretas.

## Passos

### 1. Inventário de dados pessoais
Identifique TODAS as entidades no código que contêm dados pessoais:
- Tabelas com PII/PHI em `backend/migrations/*.sql`
- Campos JSONB que podem conter PII (ex: `conditions`, `medications`, `responsible`)
- Logs que podem vazar PII em `src/**/*.py`
- Frontend que exibe PII em `frontend/src/**/*.tsx`

Para cada entidade, documente em formato:
| Tabela/Campo | Tipo LGPD | Base legal |
|--------------|-----------|-----------|
| `aia_health_patients.full_name` | PII comum | Art. 11 §2º II f |
| `aia_health_patients.conditions` | Sensível (saúde) | Art. 11 §2º II f |
| ... | | |

### 2. Direitos do titular (Art. 18)
Verifique se os endpoints existem:
- [ ] Acesso (Art. 18 II): `GET /api/me/data` ou equivalente
- [ ] Correção (Art. 18 III): `PATCH /api/me/data`
- [ ] Portabilidade (Art. 18 V): `GET /api/me/data/export`
- [ ] Eliminação (Art. 18 VI): `DELETE /api/me/data`
- [ ] Histórico de acessos (Art. 18 II): endpoint que lista quem viu

Se não existem, **flag como P0** para antes de produção com dados reais.

### 3. Retenção de dados
Cheque cada tabela para definição de retenção:
- `aia_health_reports.audio_url` — áudios: TTL 90 dias?
- `aia_health_voice_embeddings` — TTL ou retenção indefinida com consentimento?
- `aia_health_audit_chain` — retenção legal (5 anos CFM + 20 anos prontuário)
- `aia_health_conversation_sessions` — já tem TTL 30min ✅

Se não há política, **propor concreta baseada em**:
- CFM: prontuário 20 anos
- LGPD: mínimo necessário para finalidade declarada

### 4. Segurança de acesso
- [ ] Endpoints com PHI têm auth? (em `backend/src/handlers/routes.py`)
- [ ] Audit log toda vez que PHI é acessado?
- [ ] Logs de backend evitam dumping de PHI?

### 5. Transferências para terceiros
Identifique nos pacotes quem recebe dados:
- Anthropic (Claude API): recebe transcrição → **PHI transferida**
- Deepgram (STT): recebe áudio → **PHI transferida**
- Sofia Voice (Grok): recebe contexto do paciente → **PHI transferida**
- Tecnosenior/MedMonitor/Amparo: vão receber via webhook → **PHI transferida**

Para cada, verificar:
- Contrato de processamento (DPA) assinado? (não é responsabilidade do código mas relevante)
- Dados mínimos necessários (minimização)?
- Claude/Deepgram têm certificação HIPAA/LGPD?

### 6. Consentimento
- `aia_health_voice_consent_log` existe ✅
- Mas há consent log para uso de relatos na análise IA?
- E para compartilhamento com cuidador/família?

Propor tabela `aia_health_consent` (a criar) para registro granular de consentimentos.

### 7. Proteção técnica
- [ ] TLS 1.3 em todas as conexões externas
- [ ] Criptografia at-rest? (hoje não — só PostgreSQL default)
- [ ] Secrets gerenciados (não em código)
- [ ] Backup criptografado? (ainda não implementado)

### 8. DPO e responsabilidades
- Quem é o DPO da ConnectaIACare? (documentar em `docs/LGPD.md`)
- Há plano de notificação de incidente (Art. 48)?

## Formato do relatório

```markdown
## LGPD Audit — ConnectaIACare — <data>

### Resumo executivo
- ✅ N itens em conformidade
- ⚠️ N itens parciais
- ❌ N itens críticos faltando

### Inventário de dados
<tabela>

### Direitos do titular
<checklist com status>

### Retenção
<proposta concreta por tabela>

### Segurança técnica
<findings>

### Ações P0 (antes de produção)
1. ...
2. ...

### Ações P1 (antes de 100 pacientes)
1. ...

### Ações P2 (roadmap)
1. ...
```

**Não proponha soluções genéricas**. Cada ação deve citar arquivo:linha e exemplificar código ou migration concreta.
