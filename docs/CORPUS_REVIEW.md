# Revisão clínica do corpus de classificação

> **Sprint Henrique** — clinical sign-off do gold-standard que o
> classificador event_type usa de benchmark.
> Atualizado: 2026-04-30

## Por quê isso existe

A Sofia precisa classificar relatos de cuidadores em 8 categorias
(`relato_geral`, `cuidado_higiene`, `alimentacao_hidratacao`,
`medicacao`, `sinal_vital`, `intercorrencia`, `sintoma_novo`,
`apoio_emocional`). Pra medir se ela acerta, precisamos de um corpus
de exemplos rotulados como "verdade".

O corpus foi gerado em duas camadas:
- **24 casos seed** — semente humana (Alexandre).
- **~240 casos full** — gerados pelo DeepSeek V4-Pro. **Esses precisam
  de revisão clínica** antes de virar gold-standard, porque LLM pode
  errar e contaminar o benchmark.

## Arquitetura (3 partes)

### 1. Persistência

Duas tabelas (migration `060_classification_corpus_review.sql`):

- `aia_health_classification_corpus_cases` — casos (transcript, sugestão
  LLM, dificuldade, status de revisão)
- `aia_health_classification_corpus_reviews` — decisão de cada revisor
  (expected_event_type final, severidade, nota, agrees_with_llm)

Trigger `trg_corpus_review_marks_case` atualiza `review_status` do
case automaticamente quando uma review é inserida.

### 2. UI de revisão

Página `/admin/corpus-review`:
- Mostra UM caso por vez
- 8 botões grandes (uma categoria cada) — pré-selecionado na sugestão
  LLM pra reduzir cliques nos óbvios
- 4 botões opcionais de severidade (rotina/atenção/urgente/crítico)
- Campo livre de justificativa
- Botões "Passar" e "Salvar e ir pro próximo"
- Mobile-friendly (alvo: revisar do celular)

Stats no topo: quantos faltam pro user atual, total geral, taxa de
concordância LLM (útil pra estimar qualidade do corpus inicial).

### 3. Scripts I/O

`backend/scripts/corpus_review_io.py`:

```bash
# Carregar seed humano (já rotulado) — idempotente
python -m scripts.corpus_review_io import-seed \
    tests/synthetic/corpus/event_type_seed.yaml

# Carregar casos gerados pelo LLM (precisam revisão)
python -m scripts.corpus_review_io import-llm \
    tests/synthetic/corpus/event_type_full.yaml

# Exportar gold-standard pós-revisão (só os revisados)
python -m scripts.corpus_review_io export \
    tests/synthetic/corpus/event_type_gold.yaml \
    --only-reviewed
```

## Fluxo operacional pra deploy

1. **Migration**: `psql ... -f backend/migrations/060_classification_corpus_review.sql`
2. **Criar role + user pro Henrique** em `/admin/usuarios`:
   - role: `clinical_reviewer`
   - email + WhatsApp dele cadastrados (link de senha vai por Zap)
3. **Importar seed**: roda o `import-seed` apontando pro `event_type_seed.yaml`
4. **Gerar full corpus**:
   ```bash
   python -m tests.synthetic.corpus_generator \
       --seed tests/synthetic/corpus/event_type_seed.yaml \
       --output tests/synthetic/corpus/event_type_full.yaml \
       --per-class 30
   ```
5. **Importar full**: `import-llm event_type_full.yaml`
6. **Mandar texto pro Henrique** (em `docs/CARTA_HENRIQUE_CORPUS.md`)
7. Henrique revisa pelo /admin/corpus-review
8. Quando estiver "no campo verde" (pode rodar `export --only-reviewed`
   periodicamente pra ver o gold-standard atual), exporta o YAML final
9. Roda novo benchmark contra o gold:
   ```bash
   POST /api/admin/synthetic-tests/run
   { "corpus_name": "event_type_gold", "mode": "cascade" }
   ```

## Política de revisão

- **1 revisor por caso** na versão atual (UNIQUE constraint).
- Quando crescer pro multi-revisor: drop UNIQUE, usar `review_status =
  'conflict'` quando 2 reviews divergem, página separada de "decisão
  final".
- Revisores possíveis: `super_admin`, `admin_tenant`, `clinical_reviewer`,
  `medico`. Os 2 últimos são os que devem fazer a maior parte —
  super_admin/admin_tenant existem na lista só pra spot-check.

## Audit / LGPD

- Toda submissão de review dispara `audit_log(action="corpus.review.submit")`
  com `actor=user_id`, `expected_event_type`, `agrees_with_llm`.
- Reviews têm `reviewer_user_id` + `reviewed_at` — autoria clínica
  rastreável.
- Os transcripts são sintéticos (gerados por LLM) — não há PII real
  de paciente nesta tabela.
