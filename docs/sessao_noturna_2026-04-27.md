# Sessão noturna autônoma — 2026-04-26 → 2026-04-27

> Modo automático ativado pelo Alexandre. ~6h de trabalho contínuo,
> 11 commits, 4 migrations, ~3.000 linhas de código.

## ✅ Entregue e em produção

### Sprint A.1 — Safety Guardrail Layer (commits 8f45eb1, adc11f8, 30c6ab4, 5900ae2, da9e985)

Sofia tem inteligência mas **não tem autoridade**. Toda ação clínica passa por router determinístico.

**Backend (`src/services/safety_guardrail.py`)**:
- 5 tipos de ação: INFORMATIVE / REGISTER_HISTORY / INVOKE_ATTENDANT / EMERGENCY_REALTIME / MODIFY_PRESCRIPTION (bloqueado no piloto)
- Circuit breaker: >5% queue rate em 5min = pausa tenant 30min
- Auto-execute: critical com timeout 5min sem decisão = auto_executed
- HTTP central `POST /api/safety/route-action` chamado por sofia-service e voice-call-service

**Frontend de revisão** (endpoints prontos, UI fica pra depois):
- `GET /api/safety/queue` lista pendentes
- `POST /api/safety/queue/<id>/decide` familiar/atendente resolve

**Hooks integrados**:
- sofia-service `execute_tool` (chat texto + voz browser)
- voice-call-service `execute_voice_tool` (ligações)
- Disclaimer auto-injetado em TODA tool clínica
- Tool nova: `escalate_to_attendant` (Sofia aciona ramal humano)

**Tabelas (migration 035)**:
- `aia_health_action_review_queue` (fila de decisão)
- `aia_health_safety_circuit_breaker` (estado por tenant)
- `aia_health_patients` += `ramal_extension`, `escalation_channel`
- `aia_health_tenant_config` += `tenant_type`, `default_attendant_ramal`, `guardrail_settings`

### Sprint A.2 — Posicionamento "Support não decisão" (commit c34a311)

- Migration 036 prepend bloco POSICIONAMENTO INSTITUCIONAL OBRIGATÓRIO em todos os 5 cenários ativos
- `sofia_base.txt` ganhou bloco POSICIONAMENTO ABSOLUTO no topo (herdado por chat texto, voz browser e ligações)
- Sofia agora SABE quando usar `escalate_to_attendant` e como variar disclaimer naturalmente

### Sprint A.3 — Memória semântica + Active Context (commits 5963922, 2649925)

**pgvector embeddings** (migration 037):
- `aia_health_sofia_messages` += `embedding vector(768)` + HNSW index
- Worker batch `embedding_service.py` processa 20 messages/min via Gemini embedding-001 + Matryoshka truncation pra 768d
- Tool nova `recall_semantic(query, patient_id, top_k, days)` — busca verbatim em mensagens passadas
- **Smoke validou**: busca por "regras clínicas Beers idoso" trouxe 3 mensagens reais de você com similarity 0.55-0.56

**Active Context cross-channel** (UNLOGGED table TTL 45min):
- `aia_health_sofia_active_context`
- `active_context.append_turn` chamado em cada mensagem (chat texto + voz browser)
- `_load_active_context_block` injeta no system prompt de TODA nova sessão
- Hook na voice-call-service: transcripts user + assistant vão pro buffer
- Cuidador conversa via chat às 8h, idoso liga voice às 8h30 → Sofia da ligação SABE do que falaram no chat

### Sprint B.1 — Versionamento de prompts (migration 038)

- `aia_health_call_scenarios_versions` com status (draft/testing/published/archived)
- `aia_health_call_scenarios_golden_set` (conversas-tipo pra validar mudanças)
- Snapshot inicial: cada cenário ativo virou versão 1 published
- `current_version_id` aponta pra versão ativa
- **Schema pronto**, endpoints + UI admin pra próxima sprint

### Sprint B.2 — Risk Scoring Engine (commits 7083788, 7af411f)

3 sinais determinísticos Fase 1:
1. Frequência de queixas (care_events) últimos 7d
2. Adesão medicação % 7d (confirmed/total)
3. Care_events urgent+critical 7d

Score 0-100, 4 níveis (baixo/moderado/alto/crítico), tendência (improving/stable/worsening), breakdown JSONB pra UI explicar.

**Resultado real do batch**: 45 pacientes scored
- 39 baixo · 4 moderado · 0 alto · **2 críticos** (Carmen 100/100 e Antonia 85/100 — invisíveis antes)

Endpoints prontos:
- `GET /api/safety/risk-score/<patient>`
- `POST /api/safety/risk-score/<patient>/compute`
- `GET /api/safety/risk-score/high`
- `POST /api/safety/risk-score/recompute-all`

## ⏸ Não fiz (intencional)

### LiveKit migration (Sprint A.4)
Você disse: "deixo pronto local mas só ativo com você acordado pra testar áudio". Como mexer em voice prod sem você presente é arriscado, deixei pra próxima sessão. Credenciais já estão no `.env` da VPS:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (rotacionar quando der)

## ⚠️ Bugs encontrados e corrigidos durante o trabalho

1. **fetch_one não commita INSERT** — usei insert_returning (mesma armadilha do collective_memory)
2. **audit_log fora de Flask context** quebrava workers/scheduler — adicionei try/except no acesso a `g`
3. **text-embedding-004 não existe** na API v1beta atual — migrei pra `gemini-embedding-001` com Matryoshka truncation
4. **care_events colunas erradas** — corrigi `classification` → `current_classification` e `created_at` → `opened_at`

## 📋 Próximas decisões/sprints (pra discutirmos)

### Decisões pendentes pra você
1. **LiveKit migration**: testar e ativar (precisa você acordado pra validar áudio)
2. **Frontend admin pra versioning de prompts**: criar UI ou usar só DB direto por enquanto?
3. **Risk score scheduler**: rodar batch automático 1×/dia? (hoje só manual via endpoint)
4. **Notificação familiar** quando guardrail enfileira ação: WhatsApp? Push? SMS?

### Sprint C (próxima sessão sugerida)
- Frontend `/admin/safety` com:
  - Queue de revisão (familiar aprova/rejeita)
  - Dashboard de circuit breaker
  - Lista pacientes alto risco com breakdown
- Frontend `/admin/cenarios-sofia` com versionamento (draft → publish + diff visual)
- Cron diário pra `recompute_all_risk` (a cada 4h)

### Sprint D (médio prazo)
- LiveKit migration (depois que validarmos juntos)
- Baseline individual por paciente (Fase 2 do risk engine — comparar paciente contra ele mesmo)
- Inbound calls (quando tiver número definitivo)

## 📊 Métricas da sessão

| Métrica | Valor |
|---------|-------|
| Commits | 11 |
| Migrations aplicadas | 4 (035, 036, 037, 038, 039) |
| Arquivos novos | 8 |
| Arquivos modificados | 9 |
| LOC adicionadas | ~3.000 |
| Smoke tests passados | 7 |
| Bugs encontrados+corrigidos | 4 |
| Containers redeployados | api (5×), sofia-service (4×), voice-call-service (2×) |
| Pacientes com risk score | 45 |
| Pacientes flagged crítico | 2 |
| Embedding workers ativos | 2 (gunicorn workers) |
| Tools clínicas com guardrail | 4 (create_care_event, schedule_teleconsulta, send_check_in, escalate_to_attendant) |

## 🔍 Onde ver a evidência

```bash
# Logs recentes
ssh root@72.60.242.245 "docker logs --since 6h connectaiacare-api 2>&1 | grep -iE 'guardrail|risk|embedding'"

# Status do guardrail circuit breaker
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c 'SELECT * FROM aia_health_safety_circuit_breaker'"

# Pacientes em alto risco
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c \"SELECT p.full_name, r.score, r.risk_level FROM aia_health_patient_risk_score r JOIN aia_health_patients p ON p.id = r.patient_id WHERE r.risk_level IN ('alto', 'critico') ORDER BY r.score DESC\""

# Embeddings populados
ssh root@72.60.242.245 "docker exec connectaiacare-postgres psql -U postgres -d connectaiacare -c 'SELECT COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embed, COUNT(*) AS total FROM aia_health_sofia_messages'"
```

## 💭 Reflexão crítica do que entreguei

**O que ficou MUITO BOM**:
- Safety Guardrail é arquiteturalmente sólido — separa decisão da Sofia da execução
- Recall semântico funcionando com 768d Matryoshka é avant-garde
- Risk scoring expôs 2 pacientes críticos que ninguém tinha visto

**O que ficou MEDIO**:
- Tool `escalate_to_attendant` ainda só "sinaliza intenção" — não disca o ramal de fato. Quando guardrail aprova, alguém precisa ler a queue e ligar manualmente. Próxima sprint: fechar esse loop com discagem PJSIP automática.
- Risk engine hoje é threshold absoluto. Idoso com baseline de 5 queixas/semana vai sempre dar score alto. Fase 2 precisa comparar paciente contra ele mesmo.
- Versionamento de prompts: só schema. Sem UI, admin ainda edita em produção.

**O que ficou frágil**:
- Embedding worker depende de `GOOGLE_API_KEY` válida — se rate-limit, fila de pending acumula sem alarme
- Active context cross-channel funciona mas TTL 45min pode ser curto pra idoso B2C que conversa esporadicamente. Avaliar.
- `_TOOLS_REQUIRING_REVIEW` é hardcoded em 2 lugares (sofia + voice-call) — eventualmente DRY isso

Bom dia, Alexandre. Pega um café, lê esse resumo, e decidimos juntos a próxima sprint.
