"""Import/export do corpus de classificação entre YAML e DB.

Modos:

  import-seed     YAML semente → DB (idempotente, marca source='seed')
  import-llm      YAML gerado por LLM → DB (source='llm_generated')
  export          DB com reviews → YAML gold-standard
                  (usa expected_event_type da revisão se houver, senão
                   o llm_suggested_event_type — flag opcional pra
                   exportar SÓ revisados)

Uso:
    cd backend
    python -m scripts.corpus_review_io import-seed \\
        tests/synthetic/corpus/event_type_seed.yaml
    python -m scripts.corpus_review_io import-llm \\
        tests/synthetic/corpus/event_type_full.yaml
    python -m scripts.corpus_review_io export \\
        tests/synthetic/corpus/event_type_gold.yaml \\
        --only-reviewed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.postgres import get_postgres  # noqa: E402


def cmd_import(yaml_path: Path, source: str) -> int:
    if not yaml_path.exists():
        print(f"erro: arquivo não existe: {yaml_path}", file=sys.stderr)
        return 1
    with open(yaml_path) as f:
        items = yaml.safe_load(f) or []
    if not isinstance(items, list):
        print("erro: YAML não é lista", file=sys.stderr)
        return 1

    db = get_postgres()
    inserted = 0
    updated = 0
    for item in items:
        case_code = (item.get("id") or "").strip()
        transcript = (item.get("transcript") or "").strip()
        et = (item.get("expected_event_type") or "").strip()
        cls = item.get("expected_classification")
        rationale = item.get("rationale")
        difficulty = item.get("difficulty")
        if not case_code or not transcript or not et:
            print(f"skip: item incompleto: {item}", file=sys.stderr)
            continue

        existing = db.fetch_one(
            "SELECT id FROM aia_health_classification_corpus_cases "
            "WHERE case_code = %s",
            (case_code,),
        )
        if existing:
            db.execute(
                """UPDATE aia_health_classification_corpus_cases
                      SET transcript = %s,
                          llm_suggested_event_type = %s,
                          llm_suggested_classification = %s,
                          llm_rationale = %s,
                          difficulty = %s,
                          source = %s,
                          updated_at = NOW()
                    WHERE case_code = %s""",
                (transcript, et, cls, rationale, difficulty, source, case_code),
            )
            updated += 1
        else:
            db.execute(
                """INSERT INTO aia_health_classification_corpus_cases (
                    case_code, transcript, llm_suggested_event_type,
                    llm_suggested_classification, llm_rationale,
                    difficulty, source
                  ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (case_code, transcript, et, cls, rationale, difficulty, source),
            )
            inserted += 1

    print(
        f"OK · inseridos: {inserted} · atualizados: {updated} · "
        f"total no arquivo: {len(items)}"
    )
    return 0


def cmd_export(yaml_path: Path, only_reviewed: bool) -> int:
    db = get_postgres()
    where_extra = ""
    if only_reviewed:
        where_extra = " AND c.review_status = 'reviewed' "
    rows = db.fetch_all(
        f"""SELECT c.case_code, c.transcript, c.difficulty, c.source,
                   c.llm_suggested_event_type AS llm_et,
                   c.llm_suggested_classification AS llm_cls,
                   c.llm_rationale,
                   r.expected_event_type AS rev_et,
                   r.expected_classification AS rev_cls,
                   r.note AS rev_note,
                   u.full_name AS reviewer
              FROM aia_health_classification_corpus_cases c
         LEFT JOIN aia_health_classification_corpus_reviews r
                ON r.case_id = c.id
         LEFT JOIN aia_health_users u
                ON u.id = r.reviewer_user_id
             WHERE 1=1 {where_extra}
          ORDER BY c.case_code ASC""",
    )

    out: list[dict] = []
    for row in rows:
        et = row.get("rev_et") or row.get("llm_et")
        cls = row.get("rev_cls") or row.get("llm_cls")
        rationale_parts = []
        if row.get("rev_note"):
            rationale_parts.append(
                f"[Revisor {row.get('reviewer') or '?'}]: {row['rev_note']}"
            )
        if row.get("llm_rationale"):
            rationale_parts.append(f"[LLM]: {row['llm_rationale']}")
        out.append({
            "id": row["case_code"],
            "transcript": row["transcript"],
            "expected_event_type": et,
            "expected_classification": cls,
            "rationale": " | ".join(rationale_parts) or None,
            "difficulty": row.get("difficulty"),
            "_meta": {
                "source": row.get("source"),
                "reviewed": bool(row.get("rev_et")),
                "agreement_with_llm": bool(
                    row.get("rev_et") and row["rev_et"] == row["llm_et"]
                ),
            },
        })

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False)

    print(
        f"OK · exportados: {len(out)} casos → {yaml_path} "
        f"({'só revisados' if only_reviewed else 'todos'})"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    p_seed = sub.add_parser("import-seed")
    p_seed.add_argument("yaml_path", type=Path)
    p_llm = sub.add_parser("import-llm")
    p_llm.add_argument("yaml_path", type=Path)
    p_exp = sub.add_parser("export")
    p_exp.add_argument("yaml_path", type=Path)
    p_exp.add_argument("--only-reviewed", action="store_true")
    args = p.parse_args()

    if args.cmd == "import-seed":
        return cmd_import(args.yaml_path, "seed")
    if args.cmd == "import-llm":
        return cmd_import(args.yaml_path, "llm_generated")
    if args.cmd == "export":
        return cmd_export(args.yaml_path, args.only_reviewed)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
