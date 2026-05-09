# PR `fix/caregiver-wellness-separation` — separação cuidador↔paciente + expansão clínica do corpus

**Branch**: `fix/caregiver-wellness-separation`
**Data**: 2026-05-09
**Stacked em**: `feat/operador-central` (precisa mergear primeiro)

Endereça **3 problemas reais** descobertos na sessão de revisão com Henrique:

1. **PHI clínico contaminado por relato de cuidador** — `apoio_emocional` virava `care_event` no prontuário do paciente, mistura semântica (e LGPD) ruim.
2. **UX de revisão induz vício de concordância** — UI antiga pré-selecionava sugestão LLM e o botão "Salvar" submetia silenciosamente. Resultado: 100% de "concordância" falsa nas 21 reviews que Henrique fez.
3. **Taxonomia de event_type incompleta** — faltavam categorias clínicas relevantes (avaliação funcional, evolução clínica, evento adverso medicamentoso) e o classifier não considerava comorbidade ao definir severity.

---

## 1. Mudanças por área

### 1.1 Migration 072 — separação estrutural

**`aia_health_classification_corpus_cases.review_track`** (TEXT, default `'clinical'`):
- Track `clinical` (Henrique/médico/farma) ↔ `caregiver_wellness` (gestora de unidade/coordenador)
- Backfill: todos os apoio_emocional viram `caregiver_wellness`

**Nova tabela `aia_health_caregiver_wellness_events`**:
- `tenant_id NOT NULL` (referencia tenant da unidade do cuidador, não do paciente)
- `caregiver_id` (nullable — Sofia pode não conseguir resolver)
- `caregiver_phone NOT NULL`
- `severity` (routine|attention|urgent|critical) com semântica de wellness
- `status` (open|acknowledged|resolved|escalated)
- Audit: `notified_managers TEXT[]`, `acknowledged_by_user_id`, `resolved_by_user_id`
- Índices parciais pra fila aberta + por cuidador recente

### 1.2 Migration 073 — invalidação seletiva + 3 categorias novas

- **Invalida** todas as reviews `apoio_emocional` (devem ser refeitas pelo reviewer correto)
- Mantém intactas as reviews clínicas que Henrique fez
- Adiciona 3 categorias ao CHECK constraint:
  - `avaliacao_funcional` — ABVD/AIVD, mobilidade, autonomia
  - `evolucao_clinica` — status update de quadro JÁ CONHECIDO
  - `evento_adverso_medicamentoso` — separa de `medicacao` genérico

### 1.3 Prompts atualizados (3 arquivos)

**`patient_extraction.py`**, **`clinical_analysis.py`**, **`classification_judge.py`**:
- 11 categorias documentadas com diferenciais explícitos (avaliacao_funcional vs sintoma_novo, evolucao_clinica vs sintoma_novo, evento_adverso_medicamentoso vs medicacao genérico)
- **Hierarquia rígida** atualizada: anafilaxia medicamentosa → `intercorrencia` (não evento_adverso_medicamentoso); HSD em anticoagulado pós-queda → severity ≥ urgent
- **Nova seção "AJUSTE DE SEVERITY POR COMORBIDADE"** — diretrizes pra LLM elevar severity quando paciente tem comorbidade conhecida:
  - Diabetes + tontura/sudorese/confusão → urgent (suspeitar hipoglicemia)
  - DPOC + dispneia → ≥ attention (descompensação)
  - Cardiopatia + edema/dor torácica → urgent (IC descompensada)
  - Anticoagulado + queda → urgent (HSD)
  - Imunossuprimido + febrícula → urgent (infecção grave)
  - Demência + agitação noturna → ≥ attention (delirium)
  - Insuficiência renal + alt débito urinário → ≥ attention

### 1.4 Pipeline branch (`pipeline.py:_finalize_*`)

Quando cascade decide `event_type=apoio_emocional`:
- **NÃO cria care_event** (skip events.open)
- **NÃO chama notify_responsible** (responsável do paciente não tem que receber alerta de burnout do cuidador)
- Cria `caregiver_wellness_event` via `CaregiverWellnessService.create_event()`
- Service notifica gestores (admin_tenant do tenant) via outbound stream WhatsApp se severity ≥ attention
- Sofia responde com texto empático adaptado à severity (`_wellness_ack_text`):
  - routine: "Te ouvi. ... Quando quiser conversar, estou disponível."
  - attention: "Vou compartilhar com a coordenação pra te darem suporte."
  - urgent/critical: "Sinalizei pra coordenação ... Se quiser conversar com alguém em tempo real, posso acionar a central."

Fluxo NUNCA dispara cascata clínica (notify_responsible/escalate_to_human_clinical) pra apoio_emocional.

### 1.5 Frontend Corpus Review — UX Concordo/Discordo (fix de vício de concordância)

`/admin/governance/corpus-review/page.tsx` redesenhado:
- **Sugestão LLM em destaque** num card próprio (categoria + severidade + justificativa)
- **2 botões grandes** em vez de pre-select silencioso:
  - **Concordo** (verde) — aceita sugestão LLM como gold-standard, sem note
  - **Discordo** (laranja) — abre painel de re-classificação
- Modo `disagree`:
  - Pre-fill com sugestão LLM (ponto de partida)
  - Permite mudar categoria + severidade
  - **Motivo da discordância OBRIGATÓRIO** (textarea destacada em laranja)
  - Validação: se reviewer marcar exatamente o que LLM sugeriu, bloqueia ("se concorda, use Concordo")
- "Passar" continua existindo pra "não tenho opinião agora"

**Resultado esperado**: estatística de concordância passa a refletir decisão real, não viés de UI.

### 1.6 11 categorias no enum — backend e frontend sincronizados

| | onde |
|---|---|
| `corpus_review_routes.VALID_EVENT_TYPES` | backend |
| `analysis_service.ALLOWED_EVENT_TYPES` | backend |
| Migration 073 CHECK constraints | DB |
| Prompts (3 arquivos) | LLM |
| `corpus-review/page.tsx EVENT_TYPES` (com ícones e hints) | frontend |

### 1.7 Wellness API endpoints (`wellness_routes.py`)

Acesso: `super_admin`, `admin_tenant`, `enfermeiro`, `operador_central`.

| Endpoint | Função |
|---|---|
| `GET /api/admin/wellness/events` | Lista events abertos (scope por tenant; super_admin pode `?all_tenants=true`) |
| `GET /api/admin/wellness/events/<id>` | Detalhe do evento |
| `POST /api/admin/wellness/events/<id>/acknowledge` | Gestor reconheceu, vira `acknowledged` |
| `POST /api/admin/wellness/events/<id>/resolve` | Gestor resolveu, body `{summary?: string}` |
| `GET /api/admin/wellness/stats` | Stats agregadas (totals, by_severity, top_caregivers_recurring) |

`top_caregivers_recurring` retorna cuidadores com >1 evento — sinaliza padrão de fadiga recorrente que merece atenção da gestão antes do pedido de demissão.

---

## 2. O que NÃO foi implementado neste PR (Fase B)

### 2.1 Multi-event extraction com regras de causa/efeito

Henrique levantou questão importante (a #5 que perguntei): "evitar confusões entre causa/efeito". Exemplos:

**Caso AMBÍGUO de causa/efeito** (NÃO deve virar dual extraction):
> "Dona Maria caiu, tô com medo, não consigo dormir."

Aqui o medo do cuidador é REAÇÃO direta à queda. NÃO é caso wellness genuíno; é evento clínico (queda) com nota emocional do cuidador. Tratar como `intercorrencia` única, com nota emocional no contexto.

**Caso GENUÍNO de dual extraction**:
> "Dona Maria está agitada à noite e eu não estou dormindo direito."

2 sinais INDEPENDENTES: agitação noturna do paciente (sintoma com risco clínico — delirium? dor mascarada? efeito de medicação?) + privação crônica de sono do cuidador (wellness). Cada um vai pro seu fluxo.

**Regra heurística pra implementar (Fase B)**:
1. Se sinal do cuidador é **REAÇÃO direta** a evento agudo recente do paciente → single event clínico
2. Se sinal do cuidador é **CRÔNICO** (privação acumulada, exaustão recorrente) → dual extraction
3. Se há SINAIS clínicos do paciente E sinais wellness do cuidador independentes → dual extraction

Implementação: novo prompt `multi_event_extractor.py` que retorna `primary_event` + `secondary_events: []` com flag `is_reaction_to_primary`. Quando flag true, secondary vai como context/tag do primary; quando false, secondary vira evento próprio (clínico ou wellness).

### 2.2 Risk modifiers como dado estruturado

Os ajustes de severity por comorbidade hoje vivem nos prompts (instrução textual). Funciona, mas é frágil:
- Difícil auditar se o LLM aplicou
- Difícil testar deterministicamente
- Difícil customizar por paciente

**Próximo PR**: tabela `aia_health_clinical_risk_modifiers` com:
- `condition_pattern` (regex/keyword no campo `patient.conditions`)
- `symptom_pattern` (regex/keyword no transcript)
- `severity_floor` (severity mínima resultante)
- `rationale` (mostrado no audit)

Aplicado como POST-PROCESSING após cascade decide. Se LLM decidiu `attention` mas modifier dispara `severity_floor=urgent`, força urgent + nota no audit.

### 2.3 Aba "Bem-estar" no Corpus Review pro reviewer dedicado

Migration 072 já criou o track. Backend já filtra por `?track=caregiver_wellness`. Falta:
- Aba na UI `/admin/governance/corpus-review` com toggle "Clínica | Bem-estar"
- Definir o role do reviewer (provavelmente novo `wellness_reviewer` mapeado pra Gestora/Coordenador)
- Talvez prompt diferente quando track=wellness (perguntas distintas pra Henrique vs gestora)

### 2.4 Painel do gestor pra wellness

Hoje os endpoints existem mas não tem UI. Próximo PR: `/admin/system/operations/wellness/page.tsx` com:
- Lista de events abertos (filtros por severity)
- Stats: total/open/urgent/last_30d
- "Top caregivers recurring" — sinal precoce
- Botões acknowledge/resolve

---

## 3. Como testar

### 3.1 Subir migrations
```sql
\i backend/migrations/072_caregiver_wellness_separation.sql
\i backend/migrations/073_corpus_event_types_expansion.sql
```

### 3.2 Verificar invalidação seletiva
```sql
-- Antes da 073: confirma que reviews de apoio_emocional existem
SELECT COUNT(*) FROM aia_health_classification_corpus_reviews r
JOIN aia_health_classification_corpus_cases c ON c.id = r.case_id
WHERE c.llm_suggested_event_type = 'apoio_emocional';

-- Depois da 073: deve ser 0
```

### 3.3 Smoke test pipeline branch
1. Mandar pra Sofia (via WhatsApp ou test endpoint): "Sofia, tô esgotada hoje, não aguento mais."
2. Verificar:
   - NÃO criou row em `aia_health_care_events`
   - Criou row em `aia_health_caregiver_wellness_events`
   - Sofia respondeu com texto empático (não clínico)
   - Se severity ≥ attention: gestor admin_tenant recebeu WhatsApp

### 3.4 Smoke test corpus review UX
1. `/admin/governance/corpus-review` (logado como `clinical_reviewer`)
2. Caso aparece com sugestão LLM em destaque
3. Botão "Concordo" salva sem note
4. Botão "Discordo" exige re-classificar + motivo
5. Tentar discordar marcando o mesmo que LLM → bloqueia com mensagem
6. Verificar que `apoio_emocional` NÃO aparece (filtrado pelo track default `clinical`)

### 3.5 3 categorias novas
1. No corpus review, agora aparecem 11 botões (incluindo Footprints, TrendingUp, PillBottle)
2. Submit funciona com `expected_event_type=avaliacao_funcional`/`evolucao_clinica`/`evento_adverso_medicamentoso`

---

## 4. Arquivos modificados/criados

### Criados
- `backend/migrations/072_caregiver_wellness_separation.sql`
- `backend/migrations/073_corpus_event_types_expansion.sql`
- `backend/src/services/caregiver_wellness_service.py`
- `backend/src/handlers/wellness_routes.py`
- `docs/PR_CAREGIVER_WELLNESS_SEPARATION.md`

### Modificados
- `backend/app.py` (registra wellness_bp)
- `backend/src/handlers/corpus_review_routes.py` (track filter + 11 categorias)
- `backend/src/handlers/pipeline.py` (branch apoio_emocional → wellness + `_wellness_ack_text`)
- `backend/src/services/analysis_service.py` (ALLOWED_EVENT_TYPES expandido)
- `backend/src/prompts/patient_extraction.py` (11 categorias + comorbidade)
- `backend/src/prompts/clinical_analysis.py` (idem)
- `backend/src/prompts/classification_judge.py` (idem)
- `frontend/src/app/admin/governance/corpus-review/page.tsx` (UX Concordo/Discordo + 11 categorias)

---

## 5. Validação

- ✅ Python compila em todos os arquivos tocados
- ✅ TypeScript `tsc --noEmit` 0 erros no frontend
- ✅ Migrations idempotentes (DROP CONSTRAINT IF EXISTS, ADD COLUMN IF NOT EXISTS)
- ✅ Backfill da migration 073 mantém reviews clínicas, invalida só apoio_emocional

---

## 6. Riscos e pontos de atenção

1. **Invalidação destrutiva (073)**: deletamos reviews de apoio_emocional. Se Henrique tinha alguma com note clínica importante, perde. Mitigação: backup antes de rodar a migration em prod, ou guardar as deletadas numa tabela archive.

2. **Pipeline branch é early return**: quando `apoio_emocional`, pulamos `_finalize_analysis`. O análise clínico (drug safety, próximos check-ins) NÃO roda. Isso é intencional (não há paciente envolvido), mas vale validar que não estamos perdendo nada útil.

3. **Notificação de gestor é WhatsApp**: usa o mesmo outbound stream do resto. Se o gestor não tem phone cadastrado em `aia_health_users`, fica sem notificação (vê só no painel quando entrar). Vale ter um campo de email backup.

4. **Comorbidade só nos prompts**: o ajuste de severity por comorbidade depende do LLM seguir a instrução. Não é determinístico. PR Fase B (risk modifiers como dado) é mais robusto.

5. **`avaliacao_funcional` vs `evolucao_clinica` pode confundir o LLM**: a diferença é sutil ("não consegue mais subir escada" — capacidade) vs ("escada cansa mais que antes" — evolução de queixa conhecida). Vale benchmark depois com casos seed novos.

---

## 7. Resposta clínica do Henrique (registro pra próximas iterações)

1. ✅ "Invalidar somente as de apoio emocional" — feito na migration 073
2. ✅ "Risk modifier por comorbidade" — feito como instrução nos prompts (Fase B: dado estruturado)
3. ✅ "Adicionar avaliação funcional, evolução clínica, evento adverso medicamentoso" — feito
4. ✅ "Reviewer wellness = gestora de unidade / coordenador de cuidados" — track separado, role concreto fica pra próximo PR
5. ⏳ "Multi-event extraction com cuidado pra causa/efeito" — Fase B (heurística + prompt novo)

---

## 8. Como mergear

PR é **stacked sobre `feat/operador-central`**. Ordem correta:
1. Mergear `feat/operador-central` primeiro (PR base)
2. Mergear `fix/caregiver-wellness-separation` depois
3. Aplicar migrations 072 + 073 na VPS na ordem
4. Rebuild api + sofia-service + frontend
