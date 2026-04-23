"""Rotas de consulta ao catálogo de doenças (CID-10 DATASUS).

Endpoints:
    GET /api/diseases/search?q=artrose       → autocomplete
    GET /api/diseases/:code                  → lookup exato
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("diseases", __name__)


@bp.get("/api/diseases/search")
def search_diseases():
    """Busca fuzzy por código ou descrição.

    Query params:
        q: termo de busca (mín 2 chars)
        limit: máx 20 (default 10)
        geriatric_first: true|false (default true — boost em comuns em idosos)
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": []})

    limit = min(int(request.args.get("limit", 10)), 20)
    geriatric_first = request.args.get("geriatric_first", "true").lower() == "true"

    # Estratégia:
    #   1. Match exato por código prefix (ex: "I10" → I10, I10.0, I10.1...)
    #   2. Full-text search (to_tsvector) sobre descrição + sinônimos
    #   3. Trigram fuzzy (pg_trgm) pra typos
    # Ranking: geriátricas primeiro (opcional), depois prefix match,
    # depois FTS score, depois trigram similarity.

    db = get_postgres()
    q_upper = q.upper().strip()

    sql = """
        WITH scored AS (
            SELECT
                id, code, code_family, description_pt, synonyms,
                is_geriatric_common,
                CASE
                    WHEN UPPER(code) = %(q_upper)s THEN 100
                    WHEN UPPER(code) LIKE %(q_upper_prefix)s THEN 80
                    WHEN ts_rank(search_vector, plainto_tsquery('portuguese', unaccent(%(q)s))) > 0 THEN 50 + (ts_rank(search_vector, plainto_tsquery('portuguese', unaccent(%(q)s))) * 20)
                    WHEN similarity(unaccent(description_pt), unaccent(%(q)s)) > 0.25 THEN 20 + (similarity(unaccent(description_pt), unaccent(%(q)s)) * 20)
                    ELSE 0
                END AS score
            FROM aia_health_disease_catalog
            WHERE
                UPPER(code) LIKE %(q_upper_prefix)s
                OR search_vector @@ plainto_tsquery('portuguese', unaccent(%(q)s))
                OR similarity(unaccent(description_pt), unaccent(%(q)s)) > 0.25
        )
        SELECT id, code, code_family, description_pt, synonyms, is_geriatric_common, score
        FROM scored
        WHERE score > 0
        ORDER BY
            CASE WHEN %(boost_geriatric)s AND is_geriatric_common THEN 1 ELSE 0 END DESC,
            score DESC,
            LENGTH(code) ASC,
            code ASC
        LIMIT %(limit)s
    """
    rows = db.fetch_all(sql, {
        "q": q,
        "q_upper": q_upper,
        "q_upper_prefix": f"{q_upper}%",
        "boost_geriatric": geriatric_first,
        "limit": limit,
    })

    return jsonify({
        "results": [
            {
                "id": str(r["id"]),
                "code": r["code"],
                "code_family": r["code_family"],
                "description": r["description_pt"],
                "synonyms": r.get("synonyms") or [],
                "is_geriatric_common": bool(r.get("is_geriatric_common")),
            }
            for r in rows
        ],
        "query": q,
    })


@bp.get("/api/diseases/<path:code>")
def get_disease(code: str):
    """Lookup exato por código."""
    db = get_postgres()
    row = db.fetch_one(
        "SELECT id, code, code_family, description_pt, synonyms, is_geriatric_common "
        "FROM aia_health_disease_catalog WHERE code = %s LIMIT 1",
        (code.upper(),),
    )
    if not row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        "id": str(row["id"]),
        "code": row["code"],
        "code_family": row["code_family"],
        "description": row["description_pt"],
        "synonyms": row.get("synonyms") or [],
        "is_geriatric_common": bool(row.get("is_geriatric_common")),
    })
