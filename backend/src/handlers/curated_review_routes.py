"""Revisão das bases curadas (CIDs / Medicamentos / Cross-validation).

Decisão Alexandre+Henrique 2026-05-09: bases curadas (migration 075-076)
têm ciclo de revisão draft → under_review → approved. Henrique e
Coordenadora PUC Farmácia revisam direto na plataforma — não em PDF
offline. Audit trail completo (quem aprovou, quando, com qual nota).

Endpoints:
    GET  /api/admin/curated/stats              — counts por tabela/status
    GET  /api/admin/curated/cid10              — lista CIDs filtrável
    GET  /api/admin/curated/medications        — lista meds filtrável
    GET  /api/admin/curated/expectations       — lista regras de validação
    PATCH /api/admin/curated/cid10/<code>      — atualiza/aprova CID
    PATCH /api/admin/curated/medications/<id>  — atualiza/aprova med
    PATCH /api/admin/curated/expectations/<id> — atualiza/aprova regra

Acesso: super_admin, admin_tenant, clinical_reviewer, medico, farmaceutico.
"""
from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("curated_review", __name__)


REVIEWER_ROLES = (
    "super_admin", "admin_tenant",
    "clinical_reviewer", "medico", "farmaceutico",
)

VALID_REVIEW_STATUS = {"draft", "under_review", "approved"}


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _user_id() -> str | None:
    return (getattr(g, "user", None) or {}).get("sub")


# ════════════════════ STATS GLOBAL ═══════════════════════════════════

@bp.get("/api/admin/curated/stats")
@require_role(*REVIEWER_ROLES)
def stats():
    """Counts globais pra dashboard. Pra cada tabela: draft / under_review /
    approved + total."""
    db = get_postgres()
    out = {"status": "ok", "tables": {}}
    for table_key, table_name in (
        ("cid10", "aia_health_cid10_curated"),
        ("medications", "aia_health_medication_class_dictionary"),
        ("expectations", "aia_health_disease_medication_expectations"),
    ):
        row = db.fetch_one(
            f"""SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE review_status = 'draft') AS draft,
                COUNT(*) FILTER (WHERE review_status = 'under_review') AS under_review,
                COUNT(*) FILTER (WHERE review_status = 'approved') AS approved
            FROM {table_name}""",
        ) or {}
        out["tables"][table_key] = {k: int(v or 0) for k, v in row.items()}
    return jsonify(out)


# ════════════════════ CID-10 ═════════════════════════════════════════

@bp.get("/api/admin/curated/cid10")
@require_role(*REVIEWER_ROLES)
def list_cid10():
    """Lista CIDs filtrável. Query: status=draft|under_review|approved,
    category=cardiovascular|..., q=press, limit=200."""
    qs = request.args
    where = ["1=1"]
    params: list = []
    status = qs.get("status")
    if status in VALID_REVIEW_STATUS:
        where.append("review_status = %s")
        params.append(status)
    category = qs.get("category")
    if category:
        where.append("category = %s")
        params.append(category)
    q = (qs.get("q") or "").strip().lower()
    if q:
        where.append("search_text ILIKE %s")
        params.append(f"%{q}%")
    limit = max(1, min(int(qs.get("limit") or 200), 500))

    rows = get_postgres().fetch_all(
        f"""SELECT code, description_pt, description_layman, description_en,
                   category, review_status,
                   reviewed_by_user_id::text AS reviewed_by_user_id,
                   reviewed_at, reviewer_notes, version,
                   created_at, updated_at
            FROM aia_health_cid10_curated
            WHERE {' AND '.join(where)}
            ORDER BY review_status, category, code
            LIMIT %s""",
        tuple(params + [limit]),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.patch("/api/admin/curated/cid10/<code>")
@require_role(*REVIEWER_ROLES)
def update_cid10(code: str):
    """Atualiza/aprova CID. Body opcionais:
        review_status, description_pt, description_layman, description_en,
        category, reviewer_notes
    """
    body = request.get_json(silent=True) or {}
    db = get_postgres()
    existing = db.fetch_one(
        "SELECT version FROM aia_health_cid10_curated WHERE code = %s",
        (code,),
    )
    if not existing:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    updates: list[str] = []
    params: list = []
    if "review_status" in body:
        if body["review_status"] not in VALID_REVIEW_STATUS:
            return jsonify({
                "status": "error", "reason": "invalid_review_status",
                "allowed": sorted(VALID_REVIEW_STATUS),
            }), 400
        updates.append("review_status = %s")
        params.append(body["review_status"])
        updates.append("reviewed_by_user_id = %s")
        params.append(_user_id())
        updates.append("reviewed_at = NOW()")
    for k in ("description_pt", "description_layman", "description_en",
              "category", "reviewer_notes"):
        if k in body:
            updates.append(f"{k} = %s")
            params.append(body[k])
    # Edição de conteúdo bumpa version
    content_changed = any(k in body for k in (
        "description_pt", "description_layman", "description_en", "category",
    ))
    if content_changed:
        updates.append("version = version + 1")

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(code)
    db.execute(
        f"UPDATE aia_health_cid10_curated SET {', '.join(updates)} WHERE code = %s",
        tuple(params),
    )
    write_audit(
        action="curated_cid10_updated",
        actor=_user_id() or "reviewer",
        resource_type="curated_cid10",
        resource_id=code,
        payload={"fields": list(body.keys())},
    )
    return jsonify({"status": "ok"})


# ════════════════════ MEDICAMENTOS ═══════════════════════════════════

@bp.get("/api/admin/curated/medications")
@require_role(*REVIEWER_ROLES)
def list_medications():
    """Lista medicamentos filtrável. Query: status, q (active_ingredient
    ou brand), therapeutic_class."""
    qs = request.args
    where = ["1=1"]
    params: list = []
    status = qs.get("status")
    if status in VALID_REVIEW_STATUS:
        where.append("review_status = %s")
        params.append(status)
    q = (qs.get("q") or "").strip().lower()
    if q:
        # Match por nome OU brand_names OU match_patterns
        where.append(
            "(lower(active_ingredient) ILIKE %s "
            "OR EXISTS (SELECT 1 FROM unnest(brand_names) bn WHERE lower(bn) ILIKE %s) "
            "OR EXISTS (SELECT 1 FROM unnest(match_patterns) mp WHERE lower(mp) ILIKE %s))"
        )
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    therapeutic_class = qs.get("therapeutic_class")
    if therapeutic_class:
        where.append("%s = ANY(therapeutic_classes)")
        params.append(therapeutic_class)
    limit = max(1, min(int(qs.get("limit") or 200), 500))

    rows = get_postgres().fetch_all(
        f"""SELECT id::text AS id, active_ingredient, brand_names,
                   match_patterns, therapeutic_classes, main_indications,
                   notes, review_status,
                   reviewed_by_user_id::text AS reviewed_by_user_id,
                   reviewed_at, reviewer_notes, version,
                   created_at, updated_at
            FROM aia_health_medication_class_dictionary
            WHERE {' AND '.join(where)}
            ORDER BY review_status, active_ingredient
            LIMIT %s""",
        tuple(params + [limit]),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.patch("/api/admin/curated/medications/<med_id>")
@require_role(*REVIEWER_ROLES)
def update_medication(med_id: str):
    """Atualiza/aprova medicamento. Body opcionais:
        review_status, active_ingredient, brand_names (array),
        match_patterns (array), therapeutic_classes (array),
        main_indications (array), notes, reviewer_notes
    """
    body = request.get_json(silent=True) or {}
    db = get_postgres()
    existing = db.fetch_one(
        "SELECT id, version FROM aia_health_medication_class_dictionary WHERE id = %s",
        (med_id,),
    )
    if not existing:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    updates: list[str] = []
    params: list = []
    if "review_status" in body:
        if body["review_status"] not in VALID_REVIEW_STATUS:
            return jsonify({"status": "error", "reason": "invalid_review_status"}), 400
        updates.append("review_status = %s")
        params.append(body["review_status"])
        updates.append("reviewed_by_user_id = %s")
        params.append(_user_id())
        updates.append("reviewed_at = NOW()")
    for k in ("active_ingredient", "notes", "reviewer_notes"):
        if k in body:
            updates.append(f"{k} = %s")
            params.append(body[k])
    for k in ("brand_names", "match_patterns",
              "therapeutic_classes", "main_indications"):
        if k in body:
            if not isinstance(body[k], list):
                return jsonify({
                    "status": "error",
                    "reason": f"{k}_must_be_array",
                }), 400
            updates.append(f"{k} = %s")
            params.append(body[k])
    content_changed = any(k in body for k in (
        "active_ingredient", "brand_names", "match_patterns",
        "therapeutic_classes", "main_indications", "notes",
    ))
    if content_changed:
        updates.append("version = version + 1")

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(med_id)
    db.execute(
        f"UPDATE aia_health_medication_class_dictionary "
        f"SET {', '.join(updates)} WHERE id = %s",
        tuple(params),
    )
    write_audit(
        action="curated_medication_updated",
        actor=_user_id() or "reviewer",
        resource_type="curated_medication",
        resource_id=med_id,
        payload={"fields": list(body.keys())},
    )
    return jsonify({"status": "ok"})


# ════════════════════ EXPECTATIONS (cross-validation) ════════════════

@bp.get("/api/admin/curated/expectations")
@require_role(*REVIEWER_ROLES)
def list_expectations():
    """Lista regras de cross-validation. Query: status, severity, active."""
    qs = request.args
    where = ["1=1"]
    params: list = []
    status = qs.get("status")
    if status in VALID_REVIEW_STATUS:
        where.append("review_status = %s")
        params.append(status)
    severity = qs.get("severity")
    if severity in ("low", "medium", "high", "critical"):
        where.append("prompt_severity = %s")
        params.append(severity)
    active_param = qs.get("active")
    if active_param is not None:
        where.append("active = %s")
        params.append(active_param.lower() in ("true", "1", "yes"))
    limit = max(1, min(int(qs.get("limit") or 200), 500))

    rows = get_postgres().fetch_all(
        f"""SELECT id::text AS id, condition_label, cid10_code,
                   condition_match_patterns, expected_therapeutic_classes,
                   prompt_severity, prompt_message, response_options,
                   clinical_rationale, active, review_status,
                   reviewed_by_user_id::text AS reviewed_by_user_id,
                   reviewed_at, reviewer_notes, version,
                   created_at, updated_at
            FROM aia_health_disease_medication_expectations
            WHERE {' AND '.join(where)}
            ORDER BY
              CASE prompt_severity
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
              END,
              review_status, condition_label
            LIMIT %s""",
        tuple(params + [limit]),
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.patch("/api/admin/curated/expectations/<exp_id>")
@require_role(*REVIEWER_ROLES)
def update_expectation(exp_id: str):
    """Atualiza/aprova regra de cross-validation. Body opcionais:
        review_status, condition_label, cid10_code,
        condition_match_patterns (array),
        expected_therapeutic_classes (array),
        prompt_severity, prompt_message, response_options (jsonb),
        clinical_rationale, active (bool), reviewer_notes
    """
    body = request.get_json(silent=True) or {}
    db = get_postgres()
    existing = db.fetch_one(
        "SELECT id, version FROM aia_health_disease_medication_expectations WHERE id = %s",
        (exp_id,),
    )
    if not existing:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    updates: list[str] = []
    params: list = []
    if "review_status" in body:
        if body["review_status"] not in VALID_REVIEW_STATUS:
            return jsonify({"status": "error", "reason": "invalid_review_status"}), 400
        updates.append("review_status = %s")
        params.append(body["review_status"])
        updates.append("reviewed_by_user_id = %s")
        params.append(_user_id())
        updates.append("reviewed_at = NOW()")
    if "prompt_severity" in body:
        if body["prompt_severity"] not in ("low", "medium", "high", "critical"):
            return jsonify({
                "status": "error", "reason": "invalid_severity",
            }), 400
        updates.append("prompt_severity = %s")
        params.append(body["prompt_severity"])
    if "active" in body:
        updates.append("active = %s")
        params.append(bool(body["active"]))
    for k in ("condition_label", "cid10_code", "prompt_message",
              "clinical_rationale", "reviewer_notes"):
        if k in body:
            updates.append(f"{k} = %s")
            params.append(body[k])
    for k in ("condition_match_patterns", "expected_therapeutic_classes"):
        if k in body:
            if not isinstance(body[k], list):
                return jsonify({
                    "status": "error",
                    "reason": f"{k}_must_be_array",
                }), 400
            updates.append(f"{k} = %s")
            params.append(body[k])
    if "response_options" in body:
        updates.append("response_options = %s::jsonb")
        params.append(json.dumps(body["response_options"]))

    content_changed = any(k in body for k in (
        "condition_label", "cid10_code", "condition_match_patterns",
        "expected_therapeutic_classes", "prompt_severity", "prompt_message",
        "response_options", "clinical_rationale",
    ))
    if content_changed:
        updates.append("version = version + 1")

    if not updates:
        return jsonify({"status": "error", "reason": "no_fields"}), 400

    params.append(exp_id)
    db.execute(
        f"UPDATE aia_health_disease_medication_expectations "
        f"SET {', '.join(updates)} WHERE id = %s",
        tuple(params),
    )
    write_audit(
        action="curated_expectation_updated",
        actor=_user_id() or "reviewer",
        resource_type="curated_expectation",
        resource_id=exp_id,
        payload={"fields": list(body.keys())},
    )
    return jsonify({"status": "ok"})


# ════════════════════ CATEGORIAS DISPONÍVEIS ═════════════════════════

@bp.get("/api/admin/curated/cid10/categories")
@require_role(*REVIEWER_ROLES)
def list_cid10_categories():
    """Lista categorias usadas em CIDs com count. Pra UI de filtro."""
    rows = get_postgres().fetch_all(
        """SELECT category, COUNT(*) AS n
           FROM aia_health_cid10_curated
           GROUP BY category ORDER BY category""",
    )
    return jsonify({
        "status": "ok",
        "categories": [
            {"category": r["category"], "count": int(r["n"])}
            for r in rows
        ],
    })


@bp.get("/api/admin/curated/medications/therapeutic-classes")
@require_role(*REVIEWER_ROLES)
def list_therapeutic_classes():
    """Lista classes terapêuticas usadas + count. Pra UI de filtro."""
    rows = get_postgres().fetch_all(
        """SELECT cls AS therapeutic_class, COUNT(*) AS n
           FROM aia_health_medication_class_dictionary,
                unnest(therapeutic_classes) AS cls
           GROUP BY cls ORDER BY cls""",
    )
    return jsonify({
        "status": "ok",
        "classes": [
            {"class": r["therapeutic_class"], "count": int(r["n"])}
            for r in rows
        ],
    })
