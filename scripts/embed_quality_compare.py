"""Quality gate pra migração de modelo de embeddings.

Compara recall semântico entre:
  - models/embedding-001 (modelo legacy do backend, anterior à migração)
  - text-embedding-004 (Matryoshka nativo, novo padrão)

Usado pra validar PR feat/embedding-text-004-migration ANTES de fazer
backfill irreversível. Se text-embedding-004 ≥ models/embedding-001 em
recall@3 nos 5 cenários clínicos, libera backfill. Caso contrário,
rollback via env var GEMINI_EMBED_MODEL=models/embedding-001.

Uso:
    # Dentro do container connectaiacare-sofia-service (tem deps Google):
    docker compose exec sofia-service python /app/scripts/embed_quality_compare.py

    # Ou local com GOOGLE_API_KEY exportada:
    GOOGLE_API_KEY=... python scripts/embed_quality_compare.py

Métricas:
  - overlap@3: dos top-3 do modelo A, quantos aparecem no top-3 do B?
              (sinal de que ambos concordam nos resultados mais relevantes)
  - latency: ms p/ embedding (importante: text-embedding-004 não pode ser >2x
            mais lento)
  - dims: confirma que ambos retornam 768

Cenários clínicos curated (geriatria/cuidado em casa):
  - Sintomas cardiovasculares com nuance
  - Polifarmácia + dificuldade de adesão
  - Quedas com sinais cognitivos
  - Recusa alimentar + emagrecimento
  - Confusão aguda (delirium triage)
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional


# ─── Cenários clínicos: query + 5 candidatos rotulados ──────────────
# Cada cenário tem: query (busca), candidates (textos pra rankear),
# expected_top (índices dos candidates que MELHOR respondem a query —
# bom modelo deve colocar esses no topo).

SCENARIOS = [
    {
        "name": "1_cardio_subtle",
        "query": "minha mãe está com dor no peito e falta de ar há 2 horas",
        "candidates": [
            "paciente relatou angina típica em repouso, dispneia aos pequenos esforços",  # ★ relevante
            "tosse seca de alergia sazonal, sem outros sintomas",                          # irrelevante
            "queixa de aperto no peito após subir escada, ofegante",                       # ★ relevante
            "diarreia há 3 dias, sem febre, leve desidratação",                            # irrelevante
            "confusão mental aguda à noite, agitação, possível delirium",                  # parcial
        ],
        "expected_top": [0, 2],  # candidates 0 e 2 são os mais relevantes
    },
    {
        "name": "2_polifarmacia_adesao",
        "query": "ela toma 9 remédios por dia e mistura os horários",
        "candidates": [
            "polifarmácia com 8 medicações, paciente esquece doses noturnas",              # ★
            "uso correto de levotiroxina pela manhã em jejum",                             # irrelevante
            "dificuldade de adesão por número alto de comprimidos, confusão",              # ★
            "prescrição nova de losartana 50mg uma vez ao dia",                            # parcial
            "queda no banheiro sem perda de consciência",                                  # irrelevante
        ],
        "expected_top": [0, 2],
    },
    {
        "name": "3_queda_cognitiva",
        "query": "minha avó caiu de novo, é a terceira queda este mês",
        "candidates": [
            "queda recorrente com sinais de declínio cognitivo, possível alzheimer",       # ★
            "uso de paracetamol pra cefaleia ocasional",                                   # irrelevante
            "história de quedas múltiplas em 30 dias, instabilidade postural",             # ★
            "dieta hipossódica pra hipertensão controlada",                                # irrelevante
            "dor lombar após esforço, melhora com repouso",                                # parcial
        ],
        "expected_top": [0, 2],
    },
    {
        "name": "4_recusa_alimentar",
        "query": "ela não quer comer, perdeu 4kg em 3 semanas",
        "candidates": [
            "anorexia do idoso, perda ponderal significativa, investigar causa",           # ★
            "alergia a frutos do mar conhecida há anos",                                   # irrelevante
            "recusa alimentar progressiva, suspeita de depressão geriátrica",              # ★
            "uso de omeprazol pela manhã antes do café",                                   # irrelevante
            "constipação crônica, evacuação a cada 4-5 dias",                              # parcial
        ],
        "expected_top": [0, 2],
    },
    {
        "name": "5_delirium",
        "query": "minha mãe está agitada à noite e não me reconhece",
        "candidates": [
            "delirium hiperativo noturno em paciente com demência, agitação psicomotora",  # ★
            "controle de glicemia pré e pós prandial estável",                             # irrelevante
            "confusão aguda à noite, desorientação, possível infecção urinária",           # ★
            "alimentação com 6 refeições pequenas no dia",                                 # irrelevante
            "prescrição de melatonina 3mg pra insônia leve",                               # parcial
        ],
        "expected_top": [0, 2],
    },
]


@dataclass
class ModelResult:
    name: str
    embeddings: dict = field(default_factory=dict)  # text → vec
    latencies_ms: list = field(default_factory=list)
    dim: Optional[int] = None
    error: Optional[str] = None


def cosine(a: list[float], b: list[float]) -> float:
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def get_client():
    """Cria client google-genai com api_version=v1 (necessário pra
    text-embedding-004 — ver bug fix 2026-05-03 no embedding_service.py)."""
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERRO: GOOGLE_API_KEY ou GEMINI_API_KEY env var precisa estar setada")
        sys.exit(1)
    return genai.Client(
        api_key=api_key,
        http_options={"api_version": os.getenv("GENAI_API_VERSION", "v1")},
    )


def embed_with_model(client, model: str, text: str, task: str) -> tuple[list[float], int]:
    """Retorna (vector, latency_ms). Vetor pode ser [] se falhar."""
    from google.genai import types
    try:
        cfg = types.EmbedContentConfig(
            output_dimensionality=768,
            task_type=task,
        )
        t0 = time.time()
        result = client.models.embed_content(
            model=model, contents=text[:8000], config=cfg,
        )
        elapsed = int((time.time() - t0) * 1000)
        embeddings = getattr(result, "embeddings", None) or []
        if not embeddings:
            return [], elapsed
        values = getattr(embeddings[0], "values", None)
        return (list(values) if values else []), elapsed
    except Exception as exc:
        print(f"  ! embed failed model={model}: {str(exc)[:120]}")
        return [], 0


def evaluate_scenario(client, scenario: dict, model: str) -> ModelResult:
    """Embeda query + candidates, calcula similarity, retorna ranks."""
    res = ModelResult(name=model)
    # Query embedding (RETRIEVAL_QUERY)
    qvec, qlat = embed_with_model(client, model, scenario["query"], "RETRIEVAL_QUERY")
    if not qvec:
        res.error = "query_embed_failed"
        return res
    res.embeddings[scenario["query"]] = qvec
    res.latencies_ms.append(qlat)
    res.dim = len(qvec)

    # Candidate embeddings (RETRIEVAL_DOCUMENT)
    sims = []
    for i, cand in enumerate(scenario["candidates"]):
        cvec, clat = embed_with_model(client, model, cand, "RETRIEVAL_DOCUMENT")
        if not cvec:
            sims.append((i, 0.0))
            continue
        res.embeddings[cand] = cvec
        res.latencies_ms.append(clat)
        sims.append((i, cosine(qvec, cvec)))
    # Top-3
    sims.sort(key=lambda x: x[1], reverse=True)
    res.embeddings["_ranks"] = [idx for idx, _ in sims]
    res.embeddings["_scores"] = {idx: round(s, 4) for idx, s in sims}
    return res


def run():
    client = get_client()
    MODELS = [
        ("models/embedding-001", "Legacy (anterior à migração)"),
        ("text-embedding-004", "Novo padrão (Matryoshka)"),
    ]
    print("=" * 80)
    print(f"Quality gate — comparativo de modelos de embedding ({len(SCENARIOS)} cenários)")
    print("=" * 80)

    summary = {}  # model_name → {recall_at_3_total, latency_avg_ms}

    for model, label in MODELS:
        print(f"\n>>> Testando {model}  ({label})")
        recall_total = 0
        recall_max = 0
        all_lats = []
        for sc in SCENARIOS:
            res = evaluate_scenario(client, sc, model)
            if res.error:
                print(f"  [{sc['name']}] FALHOU: {res.error}")
                continue
            ranks = res.embeddings.get("_ranks", [])[:3]
            scores = res.embeddings.get("_scores", {})
            top3 = [(i, scores.get(i, 0.0)) for i in ranks]
            hits = sum(1 for i in ranks if i in sc["expected_top"])
            recall_total += hits
            recall_max += len(sc["expected_top"])
            all_lats.extend(res.latencies_ms)
            top_str = " ".join(f"{i}({s:.3f})" for i, s in top3)
            ok = "✓" if hits >= len(sc["expected_top"]) else "✗"
            print(f"  [{sc['name']}] dim={res.dim}  top3={top_str}  hits={hits}/{len(sc['expected_top'])} {ok}")

        avg_lat = sum(all_lats) / len(all_lats) if all_lats else 0
        recall_pct = (recall_total / recall_max * 100) if recall_max else 0
        summary[model] = {
            "recall_at_3": f"{recall_total}/{recall_max} ({recall_pct:.0f}%)",
            "latency_avg_ms": int(avg_lat),
        }
        print(f"\n  → recall@3 total: {recall_total}/{recall_max} ({recall_pct:.0f}%)")
        print(f"  → latência média: {int(avg_lat)}ms")

    # Decisão
    print("\n" + "=" * 80)
    print("RESUMO + DECISÃO")
    print("=" * 80)
    for model, stats in summary.items():
        print(f"  {model:35s}  recall@3={stats['recall_at_3']}  latency={stats['latency_avg_ms']}ms")

    if "text-embedding-004" in summary and "models/embedding-001" in summary:
        new_recall = int(summary["text-embedding-004"]["recall_at_3"].split("/")[0])
        old_recall = int(summary["models/embedding-001"]["recall_at_3"].split("/")[0])
        new_lat = summary["text-embedding-004"]["latency_avg_ms"]
        old_lat = summary["models/embedding-001"]["latency_avg_ms"]

        if new_recall >= old_recall and new_lat < old_lat * 2:
            print("\n  ✅ APROVADO — text-embedding-004 ≥ models/embedding-001 em recall E latência aceitável")
            print("     → liberar backfill (UPDATE NULL nas rows com models/embedding-001)")
            sys.exit(0)
        else:
            print(f"\n  ❌ REPROVADO — recall novo {new_recall} < antigo {old_recall} OU latência {new_lat}ms > 2× {old_lat}ms")
            print("     → rollback via env: GEMINI_EMBED_MODEL=models/embedding-001 + SOFIA_EMBED_MODEL=models/embedding-001")
            sys.exit(1)


if __name__ == "__main__":
    run()
