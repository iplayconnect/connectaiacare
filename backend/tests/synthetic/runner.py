"""Runner de testes sintéticos — multiclassificação event_type.

Carrega corpus YAML, roda o analyzer real (extract_entities) sobre
cada transcript, compara contra rótulos ground truth, calcula
métricas (precision/recall/F1 por classe + macro + confusion matrix).

Uso:
    cd backend && python -m tests.synthetic.runner
    # ou específico:
    python -m tests.synthetic.runner --corpus tests/synthetic/corpus/event_type_seed.yaml

Saídas:
    - relatório markdown em stdout
    - JSON estruturado em tests/synthetic/results/<timestamp>.json
    - exit code 1 se F1 macro abaixo do threshold (CI/CD-friendly)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml


# ──────────── CONFIG ────────────

DEFAULT_CORPUS = "tests/synthetic/corpus/event_type_seed.yaml"
DEFAULT_RESULTS_DIR = "tests/synthetic/results"
F1_MACRO_THRESHOLD = 0.85  # falha CI se cair abaixo


def _setup_path():
    """Permite rodar como script ou módulo."""
    here = Path(__file__).resolve().parents[2]  # backend/
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))


def load_corpus(path: str) -> list[dict]:
    with open(path) as f:
        items = yaml.safe_load(f)
    if not isinstance(items, list):
        raise ValueError(f"Corpus inválido em {path}: esperava lista, veio {type(items)}")
    required = {"id", "transcript", "expected_event_type", "expected_classification"}
    for it in items:
        miss = required - set(it.keys())
        if miss:
            raise ValueError(f"Item {it.get('id')} sem campos obrigatórios: {miss}")
    return items


def run_analyzer(transcript: str) -> dict:
    """Chama o analyzer real (extract_entities). Retorna dict com event_type."""
    _setup_path()
    from src.services.analysis_service import get_analysis_service
    svc = get_analysis_service()
    result = svc.extract_entities(transcript)
    return result or {}


def compute_metrics(predictions: list[dict]) -> dict:
    """Calcula precision/recall/F1 por classe + macro + confusion matrix.

    predictions: lista de dicts {expected: str, predicted: str, ...}
    """
    classes = sorted({p["expected"] for p in predictions} | {p["predicted"] for p in predictions if p["predicted"]})
    cm: dict[str, dict[str, int]] = {c: defaultdict(int) for c in classes}
    correct = 0
    total = len(predictions)

    for p in predictions:
        exp, pred = p["expected"], p["predicted"]
        if pred not in classes:
            cm.setdefault(exp, defaultdict(int))[pred or "<missing>"] += 1
            continue
        cm[exp][pred] += 1
        if exp == pred:
            correct += 1

    per_class = {}
    f1_scores = []
    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[other][c] for other in classes if other != c)
        fn = sum(cm[c][other] for other in classes if other != c)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[c] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": sum(cm[c].values()),
        }
        # só inclui no macro se a classe tem suporte (evita divisão zerada inflar)
        if per_class[c]["support"] > 0:
            f1_scores.append(f1)

    accuracy = correct / total if total > 0 else 0.0
    f1_macro = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    return {
        "accuracy": round(accuracy, 3),
        "f1_macro": round(f1_macro, 3),
        "total": total,
        "correct": correct,
        "per_class": per_class,
        "confusion_matrix": {c: dict(d) for c, d in cm.items()},
    }


def render_markdown(metrics: dict, predictions: list[dict], elapsed_s: float) -> str:
    out = []
    out.append(f"# Synthetic Test Report — event_type")
    out.append(f"\n**Generated**: {datetime.now().isoformat()}  ")
    out.append(f"**Total**: {metrics['total']} items  ")
    out.append(f"**Accuracy**: {metrics['accuracy']:.1%}  ")
    out.append(f"**F1 macro**: {metrics['f1_macro']:.3f}  ")
    out.append(f"**Wall time**: {elapsed_s:.1f}s\n")
    out.append("## Per-class metrics\n")
    out.append("| Class | Support | Precision | Recall | F1 |")
    out.append("|---|---|---|---|---|")
    for c, m in sorted(metrics["per_class"].items()):
        out.append(
            f"| {c} | {m['support']} | {m['precision']:.2f} | "
            f"{m['recall']:.2f} | {m['f1']:.2f} |"
        )
    out.append("\n## Errors (predicted ≠ expected)\n")
    errors = [p for p in predictions if p["expected"] != p["predicted"]]
    if not errors:
        out.append("_(none)_")
    else:
        out.append("| id | expected | predicted | difficulty |")
        out.append("|---|---|---|---|")
        for e in errors:
            out.append(
                f"| {e['id']} | {e['expected']} | "
                f"{e['predicted'] or '<missing>'} | {e.get('difficulty', '?')} |"
            )
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--threshold", type=float, default=F1_MACRO_THRESHOLD)
    parser.add_argument("--save", action="store_true", help="salva resultado em results/")
    args = parser.parse_args()

    corpus = load_corpus(args.corpus)
    print(f"Loaded {len(corpus)} items from {args.corpus}", file=sys.stderr)

    predictions: list[dict] = []
    started = time.time()
    for i, item in enumerate(corpus, 1):
        try:
            result = run_analyzer(item["transcript"])
            predicted = result.get("event_type")
        except Exception as exc:
            print(f"  [{i}/{len(corpus)}] {item['id']} ERROR: {exc}", file=sys.stderr)
            predicted = None
        else:
            ok = "✓" if predicted == item["expected_event_type"] else "✗"
            print(
                f"  [{i}/{len(corpus)}] {ok} {item['id']}: "
                f"expected={item['expected_event_type']} "
                f"predicted={predicted}",
                file=sys.stderr,
            )

        predictions.append({
            "id": item["id"],
            "expected": item["expected_event_type"],
            "predicted": predicted,
            "difficulty": item.get("difficulty"),
        })

    elapsed = time.time() - started
    metrics = compute_metrics(predictions)

    print(render_markdown(metrics, predictions, elapsed))

    if args.save:
        results_dir = Path(args.corpus).resolve().parent.parent / "results"
        results_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = results_dir / f"event_type_{ts}.json"
        with open(out_path, "w") as f:
            json.dump({
                "metrics": metrics,
                "predictions": predictions,
                "elapsed_seconds": elapsed,
                "corpus": args.corpus,
            }, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved: {out_path}", file=sys.stderr)

    if metrics["f1_macro"] < args.threshold:
        print(
            f"\n❌ F1 macro {metrics['f1_macro']:.3f} below threshold "
            f"{args.threshold}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"\n✓ F1 macro {metrics['f1_macro']:.3f} >= {args.threshold}", file=sys.stderr)


if __name__ == "__main__":
    main()
