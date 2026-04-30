# Synthetic Tests — Multiclassificação event_type

Avaliação automatizada do classificador de relatos de cuidadores. Usado pra detectar regressão de qualidade em cada deploy do pipeline.

## Estrutura

```
tests/synthetic/
├── corpus/
│   ├── event_type_seed.yaml       # 24 itens curados (ground truth humano)
│   └── event_type_full.yaml       # 240 itens (gerados via DeepSeek + revisão)
├── runner.py                      # roda analyzer real, calcula F1/precision/recall
├── judge.py                       # LLM-as-judge classifica erros (real / ambíguo / corpus)
├── corpus_generator.py            # expande seed via DeepSeek
├── results/                       # JSONs com runs históricos
└── README.md
```

## Quickstart

### 1. Rodar contra o seed (24 itens)

```bash
cd backend
python -m tests.synthetic.runner --corpus tests/synthetic/corpus/event_type_seed.yaml --save
```

Saída: relatório markdown + JSON em `tests/synthetic/results/`. Exit code 1 se F1 macro < 0.85.

### 2. Gerar corpus expandido (240 itens)

```bash
export DEEPSEEK_API_KEY="<sua-chave>"
python -m tests.synthetic.corpus_generator \
    --seed tests/synthetic/corpus/event_type_seed.yaml \
    --output tests/synthetic/corpus/event_type_full.yaml \
    --per-class 30
```

Custo: ~$0.20 com V4-Pro. **Revisar manualmente os itens gerados antes de aceitar como ground truth.**

### 3. Rodar judge sobre erros do último run

```python
from tests.synthetic.judge import judge_all_errors
import json
with open("tests/synthetic/results/event_type_<ts>.json") as f:
    run = json.load(f)
# corpus_index = {item['id']: item} carregado do YAML correspondente
verdicts = judge_all_errors(run["predictions"], corpus_index)
```

Custo: ~$0.005 por run (V4-Flash, ~50 erros).

## Métricas reportadas

- **F1 macro**: F1 médio entre as 8 classes (não ponderado por suporte). Treshold padrão: 0.85.
- **Per-class precision/recall/F1/support**: detalhe por classe.
- **Confusion matrix**: onde o modelo confunde uma classe com outra.
- **Errors list**: todos os items onde predicted ≠ expected, com `difficulty` flag.

## Threshold de aceitação (CI)

| Métrica | Mínimo aceitável | Falha se |
|---|---|---|
| F1 macro | 0.85 | abaixo |
| Critical recall | 0.95 | falso negativo crítico (sintoma_novo/intercorrencia rotulado como routine) |
| Latency p95 | <2s | extract_entities lento |

## Quando atualizar o corpus

- Adicionar `seed` quando descobrir caso real produzido em prod que o classificador errou
- Regenerar `full` quando taxonomia mudar (raro)
- Após cada bug encontrado em prod: criar regression test no seed

## LLMs em uso

| Componente | Modelo | $ por run | Risco LGPD |
|---|---|---|---|
| Geração corpus | DeepSeek V4-Pro | $0.20 (1×) | Sem PII (sintético) |
| Judge | DeepSeek V4-Flash | $0.005 | Sem PII |
| Classificador testado | Modelo prod (extract_entities) | varia | PII real em prod |

DeepSeek é usado apenas pra **avaliação** (corpus + judge), com dados sintéticos. Modelo de classificação de produção (`extract_entities`) permanece definido por configuração separada (LLMRouter).
