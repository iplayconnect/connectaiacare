"""Endpoints da revisão humana do corpus de classificação.

Sprint Henrique — clinical sign-off do gold-standard que o classificador
usa de benchmark.

Rotas:
    GET  /api/admin/corpus-review/next     — próximo caso pendente
    GET  /api/admin/corpus-review/stats    — total revisado/pendente,
                                              taxa de concordância LLM
    POST /api/admin/corpus-review/<id>     — registra revisão
    GET  /api/admin/corpus-review/list     — lista paginada (admin)

Acesso: super_admin, admin_tenant, clinical_reviewer, medico.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("corpus_review", __name__)

ALLOWED_ROLES = (
    "super_admin", "admin_tenant", "clinical_reviewer", "medico",
)

VALID_EVENT_TYPES = {
    "relato_geral", "cuidado_higiene", "alimentacao_hidratacao",
    "medicacao", "sinal_vital", "intercorrencia",
    "sintoma_novo", "apoio_emocional",
}

VALID_CLASSIFICATIONS = {"routine", "attention", "urgent", "critical"}


def _serialize_case(row: dict) -> dict:
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "case_code": row["case_code"],
        "transcript": row["transcript"],
        "llm_suggested_event_type": row["llm_suggested_event_type"],
        "llm_suggested_classification": row.get("llm_suggested_classification"),
        "llm_rationale": row.get("llm_rationale"),
        "difficulty": row.get("difficulty"),
        "source": row.get("source"),
        "review_status": row.get("review_status"),
    }


@bp.get("/api/admin/corpus-review/next")
@require_role(*ALLOWED_ROLES)
def next_case():
    """Próximo caso pendente. Não bloqueia (não cria lock) — se 2
    revisores abrirem ao mesmo tempo o mesmo caso, o segundo POST
    falha pelo UNIQUE constraint e o frontend pula pro próximo.

    Query params:
        skip_id (UUID): pula um caso específico (revisor escolheu não
                        opinar agora — útil pra "passar")
        difficulty (str): filtra por dificuldade
    """
    skip_id = request.args.get("skip_id")
    difficulty = request.args.get("difficulty")
    user_id = (getattr(g, "user", None) or {}).get("sub")

    where = ["c.review_status = 'pending'"]
    params: list = []
    if skip_id:
        where.append("c.id <> %s")
        params.append(skip_id)
    if difficulty:
        where.append("c.difficulty = %s")
        params.append(difficulty)
    # Casos que esse user JÁ revisou (defesa extra além do trigger:
    # cobre o cenário onde o status do case foi reset manualmente).
    if user_id:
        where.append(
            "NOT EXISTS (SELECT 1 FROM aia_health_classification_corpus_reviews r "
            "WHERE r.case_id = c.id AND r.reviewer_user_id = %s)"
        )
        params.append(user_id)

    where_clause = "WHERE " + " AND ".join(where)
    row = get_postgres().fetch_one(
        f"""SELECT c.* FROM aia_health_classification_corpus_cases c
            {where_clause}
            ORDER BY
              CASE c.difficulty
                WHEN 'easy' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'hard' THEN 2
                ELSE 3
              END,
              c.created_at ASC
            LIMIT 1""",
        tuple(params),
    )
    if not row:
        return jsonify({"status": "ok", "case": None, "done": True})
    return jsonify({"status": "ok", "case": _serialize_case(row)})


@bp.post("/api/admin/corpus-review/<case_id>")
@require_role(*ALLOWED_ROLES)
def submit_review(case_id: str):
    """Registra revisão de UM caso. Idempotente por (case_id, reviewer).

    Body:
        expected_event_type: 1 das 8 classes (obrigatório)
        expected_classification: routine|attention|urgent|critical (opcional)
        note: justificativa clínica curta (opcional)
    """
    body = request.get_json(silent=True) or {}
    expected = (body.get("expected_event_type") or "").strip()
    classification = (body.get("expected_classification") or "").strip() or None
    note = (body.get("note") or "").strip() or None

    if expected not in VALID_EVENT_TYPES:
        return jsonify({
            "status": "error", "reason": "invalid_event_type",
            "allowed": sorted(VALID_EVENT_TYPES),
        }), 400
    if classification and classification not in VALID_CLASSIFICATIONS:
        return jsonify({
            "status": "error", "reason": "invalid_classification",
        }), 400

    db = get_postgres()
    case = db.fetch_one(
        "SELECT id, llm_suggested_event_type FROM "
        "aia_health_classification_corpus_cases WHERE id = %s",
        (case_id,),
    )
    if not case:
        return jsonify({"status": "error", "reason": "case_not_found"}), 404

    user_ctx = getattr(g, "user", None) or {}
    user_id = user_ctx.get("sub")
    if not user_id:
        return jsonify({"status": "error", "reason": "no_user_context"}), 401

    agrees = expected == case["llm_suggested_event_type"]

    try:
        review = db.insert_returning(
            """INSERT INTO aia_health_classification_corpus_reviews (
                case_id, reviewer_user_id, expected_event_type,
                expected_classification, note, agrees_with_llm
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, reviewed_at""",
            (case_id, user_id, expected, classification, note, agrees),
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg:
            return jsonify({
                "status": "error",
                "reason": "already_reviewed_by_you",
            }), 409
        logger.exception("corpus_review_insert_failed")
        return jsonify({
            "status": "error", "reason": "insert_failed",
            "detail": str(exc)[:200],
        }), 500

    audit_log(
        action="corpus.review.submit",
        resource_type="corpus_case",
        resource_id=case_id,
        payload={
            "expected_event_type": expected,
            "agrees_with_llm": agrees,
        },
        actor=user_id,
    )

    return jsonify({
        "status": "ok",
        "review_id": str(review["id"]),
        "agrees_with_llm": agrees,
    })


@bp.get("/api/admin/corpus-review/stats")
@require_role(*ALLOWED_ROLES)
def stats():
    """Estatísticas: total de cases, revisados, pendentes, taxa de
    concordância LLM, breakdown por difficulty.
    """
    db = get_postgres()
    user_id = (getattr(g, "user", None) or {}).get("sub")

    totals = db.fetch_one(
        """SELECT
            COUNT(*) AS total_cases,
            COUNT(*) FILTER (WHERE review_status = 'reviewed') AS reviewed,
            COUNT(*) FILTER (WHERE review_status = 'pending') AS pending
           FROM aia_health_classification_corpus_cases""",
    ) or {}

    agreement = db.fetch_one(
        """SELECT
            COUNT(*) AS reviews_total,
            COUNT(*) FILTER (WHERE agrees_with_llm) AS agreed
           FROM aia_health_classification_corpus_reviews""",
    ) or {}

    by_difficulty = db.fetch_all(
        """SELECT difficulty,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE review_status = 'reviewed') AS reviewed
           FROM aia_health_classification_corpus_cases
           GROUP BY difficulty
           ORDER BY difficulty NULLS LAST""",
    )
    for r in by_difficulty:
        r["total"] = int(r.get("total") or 0)
        r["reviewed"] = int(r.get("reviewed") or 0)

    by_reviewer = db.fetch_all(
        """SELECT u.full_name AS reviewer_name,
                  COUNT(*) AS reviews,
                  COUNT(*) FILTER (WHERE r.agrees_with_llm) AS agreed
           FROM aia_health_classification_corpus_reviews r
           JOIN aia_health_users u ON u.id = r.reviewer_user_id
           GROUP BY u.full_name
           ORDER BY reviews DESC
           LIMIT 10""",
    )
    for r in by_reviewer:
        r["reviews"] = int(r.get("reviews") or 0)
        r["agreed"] = int(r.get("agreed") or 0)

    # Pendentes que esse user ainda não revisou
    my_remaining = 0
    if user_id:
        row = db.fetch_one(
            """SELECT COUNT(*) AS n
               FROM aia_health_classification_corpus_cases c
               WHERE NOT EXISTS (
                 SELECT 1 FROM aia_health_classification_corpus_reviews r
                 WHERE r.case_id = c.id AND r.reviewer_user_id = %s
               )""",
            (user_id,),
        )
        my_remaining = int((row or {}).get("n") or 0)

    return jsonify({
        "status": "ok",
        "totals": {
            "total_cases": int(totals.get("total_cases") or 0),
            "reviewed": int(totals.get("reviewed") or 0),
            "pending": int(totals.get("pending") or 0),
        },
        "agreement": {
            "reviews_total": int(agreement.get("reviews_total") or 0),
            "agreed": int(agreement.get("agreed") or 0),
        },
        "by_difficulty": by_difficulty,
        "by_reviewer": by_reviewer,
        "my_remaining": my_remaining,
    })


@bp.get("/api/admin/corpus-review/list")
@require_role("super_admin", "admin_tenant")
def list_cases():
    """Lista paginada (admin) — útil pra spot-check. Não pra revisor
    comum, que usa /next.

    Query: status=pending|reviewed, limit (default 50), offset.
    """
    qs = request.args
    status = qs.get("status")
    limit = max(1, min(int(qs.get("limit") or 50), 200))
    offset = max(0, int(qs.get("offset") or 0))

    where = []
    params: list = []
    if status in ("pending", "reviewed"):
        where.append("c.review_status = %s")
        params.append(status)
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = get_postgres().fetch_all(
        f"""SELECT c.*,
                   (SELECT COUNT(*) FROM aia_health_classification_corpus_reviews r
                     WHERE r.case_id = c.id) AS review_count
            FROM aia_health_classification_corpus_cases c
            {where_clause}
            ORDER BY c.created_at DESC
            LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "cases": [
            {**_serialize_case(r), "review_count": int(r.get("review_count") or 0)}
            for r in rows
        ],
    })
