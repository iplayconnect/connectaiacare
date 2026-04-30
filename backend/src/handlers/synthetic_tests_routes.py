"""Endpoints admin pra testes sintéticos de classificação.

Rotas:
    POST /api/admin/synthetic-tests/run        — dispara um run novo
    GET  /api/admin/synthetic-tests/history    — runs anteriores
    GET  /api/admin/synthetic-tests/<id>       — detalhe de um run
    GET  /api/admin/synthetic-tests/timeline   — F1 ao longo do tempo

Acesso: super_admin, admin_tenant.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("synthetic_tests", __name__)


CORPUS_BASE = Path(__file__).resolve().parents[2] / "tests" / "synthetic" / "corpus"


@bp.post("/api/admin/synthetic-tests/run")
@require_role("super_admin", "admin_tenant")
def trigger_run():
    """Dispara um run sintético em background.

    Body: { corpus_name: 'event_type_seed' | 'event_type_full',
            mode: 'tier1' | 'cascade', notes?: str }
    """
    body = request.get_json(silent=True) or {}
    corpus_name = body.get("corpus_name") or "event_type_seed"
    mode = body.get("mode") or "tier1"
    notes = body.get("notes")

    if mode not in ("tier1", "cascade"):
        return jsonify({"status": "error", "reason": "invalid_mode"}), 400

    corpus_path = CORPUS_BASE / f"{corpus_name}.yaml"
    if not corpus_path.exists():
        return jsonify({
            "status": "error", "reason": "corpus_not_found",
            "available": [p.stem for p in CORPUS_BASE.glob("*.yaml")],
        }), 404

    # Roda inline (24-240 itens, ~1-3 min). Pra futuros, mover pra worker.
    import sys
    base = Path(__file__).resolve().parents[2]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))

    from tests.synthetic.runner import (
        compute_metrics, load_corpus, run_analyzer,
    )
    import time

    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"

    corpus = load_corpus(str(corpus_path))
    predictions = []
    cascade_stats = {"tier1_only": 0, "tier2_triggered": 0, "tier3_triggered": 0}
    started = time.time()

    for item in corpus:
        try:
            result = run_analyzer(item["transcript"], mode=mode)
            predicted = result.get("event_type")
            if mode == "cascade":
                if result.get("_t3_triggered"):
                    cascade_stats["tier3_triggered"] += 1
                elif result.get("_t2_triggered"):
                    cascade_stats["tier2_triggered"] += 1
                else:
                    cascade_stats["tier1_only"] += 1
        except Exception as exc:
            logger.warning("synth_run_item_failed",
                           item_id=item["id"], error=str(exc))
            predicted = None
            result = {}

        predictions.append({
            "id": item["id"],
            "expected": item["expected_event_type"],
            "predicted": predicted,
            "difficulty": item.get("difficulty"),
        })

    elapsed = time.time() - started
    metrics = compute_metrics(predictions)
    errors = [p for p in predictions if p["expected"] != p["predicted"]]

    threshold = float(body.get("threshold") or 0.85)
    threshold_pass = metrics["f1_macro"] >= threshold

    db = get_postgres()
    run_row = db.insert_returning(
        """INSERT INTO aia_health_synthetic_test_runs (
            tenant_id, corpus_path, corpus_size, mode, threshold,
            accuracy, f1_macro, threshold_pass,
            per_class, confusion_matrix, errors, cascade_stats,
            elapsed_seconds, ran_by_user_id, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, ran_at""",
        (
            tenant_id, str(corpus_path), len(corpus), mode, threshold,
            metrics["accuracy"], metrics["f1_macro"], threshold_pass,
            json.dumps(metrics["per_class"]),
            json.dumps(metrics["confusion_matrix"]),
            json.dumps(errors),
            json.dumps(cascade_stats) if mode == "cascade" else None,
            round(elapsed, 2), user_id, notes,
        ),
    )

    return jsonify({
        "status": "ok",
        "run_id": str(run_row["id"]) if run_row else None,
        "ran_at": run_row["ran_at"].isoformat() if run_row else None,
        "metrics": {
            "accuracy": metrics["accuracy"],
            "f1_macro": metrics["f1_macro"],
            "threshold_pass": threshold_pass,
            "errors_count": len(errors),
        },
    })


@bp.get("/api/admin/synthetic-tests/history")
@require_role("super_admin", "admin_tenant")
def list_runs():
    """Lista últimos runs (default 50)."""
    limit = min(int(request.args.get("limit", 50)), 200)
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    rows = get_postgres().fetch_all(
        """SELECT id, ran_at, corpus_path, corpus_size, mode,
                  accuracy, f1_macro, threshold_pass, elapsed_seconds,
                  jsonb_array_length(errors) AS errors_count,
                  cascade_stats, notes
           FROM aia_health_synthetic_test_runs
           WHERE tenant_id = %s
           ORDER BY ran_at DESC
           LIMIT %s""",
        (tenant_id, limit),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "runs": [
            {
                **r,
                "id": str(r["id"]),
                "ran_at": r["ran_at"].isoformat() if r["ran_at"] else None,
                "corpus_name": Path(r["corpus_path"]).stem,
            } for r in rows
        ],
    })


@bp.get("/api/admin/synthetic-tests/<run_id>")
@require_role("super_admin", "admin_tenant")
def get_run(run_id: str):
    """Detalhe completo de 1 run."""
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    row = get_postgres().fetch_one(
        """SELECT * FROM aia_health_synthetic_test_runs
           WHERE id = %s AND tenant_id = %s""",
        (run_id, tenant_id),
    )
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404
    row["id"] = str(row["id"])
    row["ran_at"] = row["ran_at"].isoformat() if row["ran_at"] else None
    row["created_at"] = row["created_at"].isoformat() if row["created_at"] else None
    row["corpus_name"] = Path(row["corpus_path"]).stem
    if row.get("ran_by_user_id"):
        row["ran_by_user_id"] = str(row["ran_by_user_id"])
    return jsonify({"status": "ok", "run": row})


@bp.get("/api/admin/synthetic-tests/timeline")
@require_role("super_admin", "admin_tenant")
def timeline():
    """Time series de F1 macro pra dashboard."""
    days = min(int(request.args.get("days", 30)), 90)
    user_ctx = getattr(g, "user", None) or {}
    tenant_id = user_ctx.get("tenant_id") or "connectaiacare_demo"
    rows = get_postgres().fetch_all(
        """SELECT ran_at, mode, f1_macro, accuracy, threshold_pass,
                  jsonb_array_length(errors) AS errors_count, corpus_size
           FROM aia_health_synthetic_test_runs
           WHERE tenant_id = %s AND ran_at >= NOW() - (%s || ' days')::interval
           ORDER BY ran_at ASC""",
        (tenant_id, str(days)),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "timeline": [
            {**r, "ran_at": r["ran_at"].isoformat() if r["ran_at"] else None}
            for r in rows
        ],
    })
