"""Admin CRUD pras tabelas de regras clínicas (motor de cruzamentos).

Endpoints:
    /api/clinical-rules/dose-limits         (CRUD)
    /api/clinical-rules/aliases             (CRUD)
    /api/clinical-rules/interactions        (CRUD)
    /api/clinical-rules/allergy-mappings    (CRUD)
    /api/clinical-rules/condition-contraindications (CRUD)
    /api/clinical-rules/renal-adjustments   (CRUD)
    /api/clinical-rules/hepatic-adjustments (CRUD)
    /api/clinical-rules/fall-risk           (CRUD)
    /api/clinical-rules/anticholinergic-burden (CRUD)
    /api/clinical-rules/vital-constraints   (CRUD)
    /api/clinical-rules/stats               (resumo agregado)

Permissões: super_admin, admin_tenant. Auditoria automática (cada edição
gera entrada em aia_health_audit_chain via audit_service).
"""
from __future__ import annotations

import psycopg2.extras
from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_service import audit_log
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("clinical_rules", __name__)


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    out: dict = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            # UUID-like
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _list(table: str, order_by: str = "principle_active") -> list[dict]:
    rows = get_postgres().fetch_all(
        f"SELECT * FROM {table} WHERE active = TRUE ORDER BY {order_by}"
    )
    return [_serialize(r) for r in rows]


def _delete_soft(table: str, row_id: str) -> bool:
    pg = get_postgres()
    try:
        pg.execute(f"UPDATE {table} SET active = FALSE WHERE id = %s", (row_id,))
        return True
    except Exception as exc:
        logger.warning("clinical_rules_delete_failed table=%s id=%s err=%s",
                       table, row_id, str(exc))
        return False


def _audit(action: str, table: str, row_id: str | None, payload: dict | None = None):
    audit_log(
        action=action,
        resource_type=f"clinical_rule.{table}",
        resource_id=str(row_id) if row_id else None,
        payload=payload or {},
    )


# ════════════════════════════════════════════════════════════════
# STATS — resumo agregado pra dashboard admin
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/stats")
@require_role("super_admin", "admin_tenant")
def stats():
    pg = get_postgres()
    out = {}
    for table, label in [
        ("aia_health_drug_dose_limits", "dose_limits"),
        ("aia_health_drug_aliases", "aliases"),
        ("aia_health_drug_interactions", "interactions"),
        ("aia_health_allergy_mappings", "allergy_mappings"),
        ("aia_health_condition_contraindications", "condition_contraindications"),
        ("aia_health_drug_renal_adjustments", "renal_adjustments"),
        ("aia_health_drug_hepatic_adjustments", "hepatic_adjustments"),
        ("aia_health_drug_fall_risk", "fall_risk"),
        ("aia_health_drug_anticholinergic_burden", "anticholinergic_burden"),
        ("aia_health_drug_vital_constraints", "vital_constraints"),
    ]:
        try:
            row = pg.fetch_one(f"SELECT COUNT(*) AS n FROM {table} WHERE active = TRUE")
            out[label] = int(row["n"]) if row else 0
        except Exception:
            out[label] = None
    return jsonify({"status": "ok", "stats": out})


# ════════════════════════════════════════════════════════════════
# DOSE LIMITS
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/dose-limits")
@require_role("super_admin", "admin_tenant")
def list_dose_limits():
    return jsonify({"status": "ok", "items": _list("aia_health_drug_dose_limits")})


@bp.post("/api/clinical-rules/dose-limits")
@require_role("super_admin", "admin_tenant")
def create_dose_limit():
    b = request.get_json(silent=True) or {}
    required = ["principle_active", "max_daily_dose_value", "max_daily_dose_unit", "source"]
    if not all(k in b and b[k] not in (None, "") for k in required):
        return jsonify({"status": "error", "reason": "missing_fields", "required": required}), 400
    row = get_postgres().insert_returning(
        """
        INSERT INTO aia_health_drug_dose_limits
            (principle_active, route, max_daily_dose_value, max_daily_dose_unit,
             age_group_min, age_group_max, beers_avoid, beers_rationale,
             source, source_ref, confidence, notes,
             therapeutic_class, narrow_therapeutic_index, nti_monitoring)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            b["principle_active"].lower(), b.get("route", "oral"),
            b["max_daily_dose_value"], b["max_daily_dose_unit"],
            b.get("age_group_min", 60), b.get("age_group_max"),
            bool(b.get("beers_avoid", False)), b.get("beers_rationale"),
            b["source"], b.get("source_ref"),
            b.get("confidence", 0.85), b.get("notes"),
            b.get("therapeutic_class"),
            bool(b.get("narrow_therapeutic_index", False)),
            b.get("nti_monitoring"),
        ),
    )
    _audit("rule.dose_limit.create", "dose_limits", row.get("id"),
           {"principle": b["principle_active"]})
    return jsonify({"status": "ok", "item": _serialize(row)}), 201


@bp.patch("/api/clinical-rules/dose-limits/<rid>")
@require_role("super_admin", "admin_tenant")
def update_dose_limit(rid: str):
    b = request.get_json(silent=True) or {}
    allowed = {
        "max_daily_dose_value", "max_daily_dose_unit", "age_group_min",
        "age_group_max", "beers_avoid", "beers_rationale", "source",
        "source_ref", "confidence", "notes", "therapeutic_class",
        "narrow_therapeutic_index", "nti_monitoring", "active",
    }
    sets = []
    vals = []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"status": "ok", "noop": True})
    vals.append(rid)
    row = get_postgres().insert_returning(
        f"UPDATE aia_health_drug_dose_limits SET {', '.join(sets)}, updated_at = NOW() WHERE id = %s RETURNING *",
        tuple(vals),
    )
    _audit("rule.dose_limit.update", "dose_limits", rid, {"changed": list(b.keys())})
    return jsonify({"status": "ok", "item": _serialize(row)})


@bp.delete("/api/clinical-rules/dose-limits/<rid>")
@require_role("super_admin", "admin_tenant")
def delete_dose_limit(rid: str):
    _delete_soft("aia_health_drug_dose_limits", rid)
    _audit("rule.dose_limit.delete", "dose_limits", rid)
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# ALIASES
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/aliases")
@require_role("super_admin", "admin_tenant")
def list_aliases():
    rows = get_postgres().fetch_all(
        "SELECT * FROM aia_health_drug_aliases ORDER BY principle_active, alias"
    )
    return jsonify({"status": "ok", "items": [_serialize(r) for r in rows]})


@bp.post("/api/clinical-rules/aliases")
@require_role("super_admin", "admin_tenant")
def create_alias():
    b = request.get_json(silent=True) or {}
    if not b.get("alias") or not b.get("principle_active"):
        return jsonify({"status": "error", "reason": "missing_fields"}), 400
    try:
        row = get_postgres().insert_returning(
            "INSERT INTO aia_health_drug_aliases (alias, principle_active, alias_type, notes) "
            "VALUES (%s, %s, %s, %s) RETURNING *",
            (b["alias"], b["principle_active"].lower(),
             b.get("alias_type", "brand"), b.get("notes")),
        )
    except Exception as exc:
        return jsonify({"status": "error", "reason": "duplicate_alias", "detail": str(exc)}), 409
    _audit("rule.alias.create", "aliases", row.get("id"), {"alias": b["alias"]})
    return jsonify({"status": "ok", "item": _serialize(row)}), 201


@bp.delete("/api/clinical-rules/aliases/<rid>")
@require_role("super_admin", "admin_tenant")
def delete_alias(rid: str):
    get_postgres().execute("DELETE FROM aia_health_drug_aliases WHERE id = %s", (rid,))
    _audit("rule.alias.delete", "aliases", rid)
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# INTERACTIONS
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/interactions")
@require_role("super_admin", "admin_tenant")
def list_interactions():
    rows = get_postgres().fetch_all(
        """
        SELECT * FROM aia_health_drug_interactions
        WHERE active = TRUE
        ORDER BY
            CASE severity
                WHEN 'contraindicated' THEN 1
                WHEN 'major' THEN 2
                WHEN 'moderate' THEN 3
                ELSE 4 END,
            COALESCE(principle_a, class_a),
            COALESCE(principle_b, class_b)
        """
    )
    return jsonify({"status": "ok", "items": [_serialize(r) for r in rows]})


@bp.post("/api/clinical-rules/interactions")
@require_role("super_admin", "admin_tenant")
def create_interaction():
    b = request.get_json(silent=True) or {}
    required = ["severity", "mechanism", "clinical_effect", "recommendation", "source"]
    if not all(k in b and b[k] for k in required):
        return jsonify({"status": "error", "reason": "missing_fields", "required": required}), 400
    if not (b.get("principle_a") or b.get("class_a")) or not (b.get("principle_b") or b.get("class_b")):
        return jsonify({"status": "error", "reason": "missing_pair_sides"}), 400

    row = get_postgres().insert_returning(
        """
        INSERT INTO aia_health_drug_interactions
            (principle_a, principle_b, class_a, class_b,
             severity, mechanism, clinical_effect, recommendation,
             onset, source, source_ref, confidence,
             time_separation_minutes, separation_strategy, food_warning)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            (b.get("principle_a") or "").lower() or None,
            (b.get("principle_b") or "").lower() or None,
            (b.get("class_a") or "").lower() or None,
            (b.get("class_b") or "").lower() or None,
            b["severity"], b["mechanism"], b["clinical_effect"], b["recommendation"],
            b.get("onset"), b["source"], b.get("source_ref"),
            b.get("confidence", 0.85),
            b.get("time_separation_minutes"),
            b.get("separation_strategy"),
            b.get("food_warning"),
        ),
    )
    _audit("rule.interaction.create", "interactions", row.get("id"),
           {"severity": b["severity"], "mechanism": b["mechanism"]})
    return jsonify({"status": "ok", "item": _serialize(row)}), 201


@bp.patch("/api/clinical-rules/interactions/<rid>")
@require_role("super_admin", "admin_tenant")
def update_interaction(rid: str):
    b = request.get_json(silent=True) or {}
    allowed = {
        "severity", "mechanism", "clinical_effect", "recommendation",
        "onset", "source", "source_ref", "confidence", "active",
        "time_separation_minutes", "separation_strategy", "food_warning",
    }
    sets = []
    vals = []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return jsonify({"status": "ok", "noop": True})
    vals.append(rid)
    row = get_postgres().insert_returning(
        f"UPDATE aia_health_drug_interactions SET {', '.join(sets)} WHERE id = %s RETURNING *",
        tuple(vals),
    )
    _audit("rule.interaction.update", "interactions", rid, {"changed": list(b.keys())})
    return jsonify({"status": "ok", "item": _serialize(row)})


@bp.delete("/api/clinical-rules/interactions/<rid>")
@require_role("super_admin", "admin_tenant")
def delete_interaction(rid: str):
    _delete_soft("aia_health_drug_interactions", rid)
    _audit("rule.interaction.delete", "interactions", rid)
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════
# Read-only listings das outras tabelas (admin pode visualizar mas
# CRUD direto fica pra próxima onda — estas mudam menos)
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/allergy-mappings")
@require_role("super_admin", "admin_tenant")
def list_allergy_mappings():
    return jsonify({"status": "ok", "items": _list(
        "aia_health_allergy_mappings", "allergy_term"
    )})


@bp.get("/api/clinical-rules/condition-contraindications")
@require_role("super_admin", "admin_tenant")
def list_condition_contraindications():
    return jsonify({"status": "ok", "items": _list(
        "aia_health_condition_contraindications", "condition_term"
    )})


@bp.get("/api/clinical-rules/renal-adjustments")
@require_role("super_admin", "admin_tenant")
def list_renal_adjustments():
    return jsonify({"status": "ok", "items": _list(
        "aia_health_drug_renal_adjustments", "principle_active"
    )})


@bp.get("/api/clinical-rules/hepatic-adjustments")
@require_role("super_admin", "admin_tenant")
def list_hepatic_adjustments():
    return jsonify({"status": "ok", "items": _list(
        "aia_health_drug_hepatic_adjustments", "principle_active"
    )})


@bp.get("/api/clinical-rules/fall-risk")
@require_role("super_admin", "admin_tenant")
def list_fall_risk():
    rows = get_postgres().fetch_all(
        "SELECT * FROM aia_health_drug_fall_risk WHERE active = TRUE "
        "ORDER BY fall_risk_score DESC"
    )
    return jsonify({"status": "ok", "items": [_serialize(r) for r in rows]})


@bp.get("/api/clinical-rules/anticholinergic-burden")
@require_role("super_admin", "admin_tenant")
def list_anticholinergic_burden():
    rows = get_postgres().fetch_all(
        "SELECT * FROM aia_health_drug_anticholinergic_burden WHERE active = TRUE "
        "ORDER BY burden_score DESC, principle_active"
    )
    return jsonify({"status": "ok", "items": [_serialize(r) for r in rows]})


@bp.get("/api/clinical-rules/vital-constraints")
@require_role("super_admin", "admin_tenant")
def list_vital_constraints():
    rows = get_postgres().fetch_all(
        "SELECT * FROM aia_health_drug_vital_constraints WHERE active = TRUE "
        "ORDER BY vital_field, threshold"
    )
    return jsonify({"status": "ok", "items": [_serialize(r) for r in rows]})


# ─────────────────── Validação ad-hoc (sem persistir) ───────────────────
# Usado por:
#   • Sofia tool `check_medication_safety` (médico pergunta "se eu prescrever X
#     pro paciente Y, é seguro?")
#   • UI de prescrição (preview antes de salvar)
#
# NÃO escreve aia_health_alerts — só retorna o ValidationResult. Quem cria
# o alerta é o endpoint que de fato persiste a schedule.
@bp.post("/api/clinical-rules/validate-prescription")
def validate_prescription():
    """Roda o motor de cruzamentos para uma prescrição candidata.

    Body:
        medication_name: str (required)
        dose: str (required, ex: "10 mg", "0,5 mg")
        times_of_day: list[str] (opcional, ex: ["08:00", "20:00"])
        route: str (default "oral")
        schedule_type: str (opcional)
        patient_id: str (opcional, se passado busca patient row)
        patient: dict (opcional, alternativa a patient_id, com full_name,
                       birth_date, allergies, conditions)
    Retorna: {status, validation: ValidationResult.to_dict()}
    """
    from src.services import dose_validator
    body = request.get_json(silent=True) or {}

    if not body.get("medication_name") or not body.get("dose"):
        return jsonify({
            "status": "error",
            "reason": "medication_name_and_dose_required",
        }), 400

    patient = body.get("patient")
    patient_id = body.get("patient_id")
    if patient_id and not patient:
        row = get_postgres().fetch_one(
            "SELECT id, full_name, birth_date, allergies, conditions "
            "FROM aia_health_patients WHERE id = %s",
            (patient_id,),
        )
        patient = dict(row) if row else None

    try:
        result = dose_validator.validate(
            medication_name=body["medication_name"],
            dose=body["dose"],
            times_of_day=body.get("times_of_day"),
            route=(body.get("route") or "oral").lower(),
            patient=patient,
            schedule_type=body.get("schedule_type"),
        ).to_dict()
    except Exception as exc:
        logger.exception("validate_prescription_failed")
        return jsonify({
            "status": "error",
            "reason": "validator_exception",
            "detail": str(exc),
        }), 500

    return jsonify({"status": "ok", "validation": result})


# ════════════════════════════════════════════════════════════════
# CASCADAS DE PRESCRIÇÃO (dimensão 13 do motor)
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/cascades")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_cascades_endpoint():
    """Lista todas cascatas configuradas (admin viewer)."""
    from src.services import cascade_detector
    items = cascade_detector.list_cascades()
    return jsonify({"status": "ok", "count": len(items), "items": items})


@bp.get("/api/patients/<patient_id>/cascades")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro",
              "cuidador_pro", "familia")
def detect_cascades_endpoint(patient_id: str):
    """Roda detector pra um paciente — retorna cascatas que bateram nas
    medicações ativas dele, com detalhe de quais drogas matched em cada
    bracket (A/B/C). Exclusões por condição clínica são suprimidas."""
    from src.services import cascade_detector
    result = cascade_detector.detect_cascades(patient_id)
    if not result.get("ok"):
        return jsonify({"status": "error", "reason": result.get("error")}), 404
    return jsonify({"status": "ok", **result})


# ════════════════════════════════════════════════════════════════
# RENAME 2024 — base oficial de cobertura do motor
# ════════════════════════════════════════════════════════════════

@bp.get("/api/clinical-rules/rename/coverage")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def rename_coverage_summary():
    """Resumo de cobertura RENAME 2024 por componente + relevância geriátrica.

    Retorna percentual de fármacos do RENAME que já estão cobertos pelo
    motor (12 dimensões), pendentes ou em andamento.
    """
    from src.services.postgres import get_postgres
    rows = get_postgres().fetch_all(
        """SELECT componente, geriatric_relevance, total, covered,
                  in_progress, pending, pct_covered
           FROM aia_health_rename_coverage_summary"""
    )
    return jsonify({
        "status": "ok",
        "edicao": "2024",
        "summary": [dict(r) for r in (rows or [])],
    })


@bp.get("/api/clinical-rules/rename/gaps")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def rename_gaps():
    """Lista fármacos RENAME que ainda não estão cobertos pelo motor.

    Query params:
        relevance: high | medium | low (filtra por relevância geriátrica)
        componente: basico | estrategico | especializado
        limit: default 100

    Útil pra Henrique/farmacêutico priorizar o que codificar próximo.
    """
    relevance = request.args.get("relevance")
    componente = request.args.get("componente")
    limit = min(int(request.args.get("limit", 100)), 500)

    where = ["motor_coverage IN ('pending', 'in_progress')"]
    params: list = []
    if relevance:
        where.append("geriatric_relevance = %s")
        params.append(relevance)
    if componente:
        where.append("componente = %s")
        params.append(componente)
    params.append(limit)

    from src.services.postgres import get_postgres
    rows = get_postgres().fetch_all(
        f"""SELECT principle_active, componente, grupo_terapeutico,
                   populacao_alvo, indicacao_sus, geriatric_relevance,
                   motor_coverage, notes
            FROM aia_health_rename_drugs
            WHERE {' AND '.join(where)}
            ORDER BY
                CASE geriatric_relevance
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    WHEN 'excluded' THEN 4
                END,
                principle_active
            LIMIT %s""",
        tuple(params),
    )
    out = []
    for r in rows or []:
        d = dict(r)
        # Convert array to list pra JSON
        if d.get("populacao_alvo"):
            d["populacao_alvo"] = list(d["populacao_alvo"])
        out.append(d)
    return jsonify({
        "status": "ok",
        "count": len(out),
        "edicao": "2024",
        "gaps": out,
    })


# ════════════════════════════════════════════════════════════════
# REVISÃO CLÍNICA — admin/farmacêutico revisa regras auto_pending
# ════════════════════════════════════════════════════════════════
#
# 4 tabelas com flag review_status='auto_pending':
# - aia_health_drug_dose_limits
# - aia_health_condition_contraindications
# - aia_health_drug_anticholinergic_burden
# - aia_health_drug_fall_risk

_REVIEW_TABLES = {
    "dose_limits": {
        "table": "aia_health_drug_dose_limits",
        "label": "Dose máxima",
        "id_column": "id",
        "key_column": "principle_active",
        "display_columns": [
            "principle_active", "route", "max_daily_dose_value",
            "max_daily_dose_unit", "therapeutic_class", "age_group_min",
            "source", "source_auto", "auto_review_notes",
        ],
    },
    "contraindications": {
        "table": "aia_health_condition_contraindications",
        "label": "Contraindicação por condição (Beers/CID)",
        "id_column": "id",
        "key_column": "affected_principle_active",
        "display_columns": [
            "condition_term", "condition_icd10", "affected_principle_active",
            "affected_therapeutic_class", "severity", "rationale",
            "recommendation", "source", "source_ref", "confidence",
        ],
    },
    "acb": {
        "table": "aia_health_drug_anticholinergic_burden",
        "label": "ACB Score (Boustani)",
        "id_column": "id",
        "key_column": "principle_active",
        "display_columns": [
            "principle_active", "burden_score", "notes", "source",
        ],
    },
    "fall_risk": {
        "table": "aia_health_drug_fall_risk",
        "label": "Fall Risk Score",
        "id_column": "id",
        "key_column": "therapeutic_class",
        "display_columns": [
            "principle_active", "therapeutic_class", "fall_risk_score",
            "rationale", "source",
        ],
    },
}


@bp.get("/api/clinical-rules/review/pending")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_pending_review():
    """Lista TODAS as regras com review_status='auto_pending' de todas
    as tabelas do motor. Retorno organizado por tabela."""
    from src.services.postgres import get_postgres
    db = get_postgres()
    out = {}
    total_pending = 0
    for slug, meta in _REVIEW_TABLES.items():
        cols = ", ".join(meta["display_columns"])
        rows = db.fetch_all(
            f"""SELECT {meta['id_column']} AS row_id, {cols}
                FROM {meta['table']}
                WHERE review_status = 'auto_pending'
                ORDER BY {meta['key_column']}"""
        )
        items = []
        for r in rows or []:
            d = dict(r)
            d["row_id"] = str(d["row_id"])
            items.append(d)
        out[slug] = {
            "label": meta["label"],
            "table": meta["table"],
            "count": len(items),
            "items": items,
        }
        total_pending += len(items)
    return jsonify({
        "status": "ok",
        "total_pending": total_pending,
        "by_table": out,
    })


@bp.post("/api/clinical-rules/review/<slug>/<row_id>/approve")
@require_role("super_admin", "admin_tenant")
def approve_pending_review(slug: str, row_id: str):
    """Marca uma linha como 'verified' (aprovada por curador clínico).

    Body opcional: { "notes": "comentário do revisor" }
    """
    from src.services.postgres import get_postgres
    from src.services.audit_service import audit_log
    from flask import g

    if slug not in _REVIEW_TABLES:
        return jsonify({"status": "error", "reason": "invalid_table_slug"}), 400

    meta = _REVIEW_TABLES[slug]
    body = request.get_json(silent=True) or {}
    user_ctx = getattr(g, "user", None) or {}
    reviewer = user_ctx.get("sub")

    extra_set = ""
    extra_params: tuple = ()
    if "reviewed_by" in [
        c["column_name"]
        for c in get_postgres().fetch_all(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            (meta["table"],),
        )
    ]:
        extra_set = ", reviewed_by = %s, reviewed_at = NOW()"
        extra_params = (reviewer,)

    notes_set = ""
    notes_params: tuple = ()
    if body.get("notes") and "auto_review_notes" in [
        c["column_name"]
        for c in get_postgres().fetch_all(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            (meta["table"],),
        )
    ]:
        notes_set = ", auto_review_notes = %s"
        notes_params = (body["notes"],)

    sql = (
        f"UPDATE {meta['table']} "
        f"SET review_status = 'verified'{extra_set}{notes_set} "
        f"WHERE {meta['id_column']} = %s "
        f"AND review_status = 'auto_pending' "
        f"RETURNING {meta['id_column']}"
    )
    params = extra_params + notes_params + (row_id,)
    row = get_postgres().fetch_one(sql, params)
    if not row:
        return jsonify({
            "status": "error",
            "reason": "row_not_found_or_not_auto_pending",
        }), 404

    audit_log(action="clinical_rules.review.approved", payload={
        "table": meta["table"], "row_id": row_id,
        "reviewer": reviewer, "notes": body.get("notes"),
    })
    return jsonify({"status": "ok", "table": slug, "row_id": row_id})


@bp.post("/api/clinical-rules/review/<slug>/<row_id>/reject")
@require_role("super_admin", "admin_tenant")
def reject_pending_review(slug: str, row_id: str):
    """Rejeita uma regra auto_pending (desativa via active=FALSE).
    Mantém histórico mas remove da fila ativa do motor.

    Body: { "reason": "motivo da rejeição" }
    """
    from src.services.postgres import get_postgres
    from src.services.audit_service import audit_log
    from flask import g

    if slug not in _REVIEW_TABLES:
        return jsonify({"status": "error", "reason": "invalid_table_slug"}), 400

    meta = _REVIEW_TABLES[slug]
    body = request.get_json(silent=True) or {}
    user_ctx = getattr(g, "user", None) or {}

    if not body.get("reason"):
        return jsonify({
            "status": "error", "reason": "rejection_reason_required",
        }), 400

    row = get_postgres().fetch_one(
        f"UPDATE {meta['table']} SET active = FALSE "
        f"WHERE {meta['id_column']} = %s AND review_status = 'auto_pending' "
        f"RETURNING {meta['id_column']}",
        (row_id,),
    )
    if not row:
        return jsonify({
            "status": "error",
            "reason": "row_not_found_or_not_auto_pending",
        }), 404

    audit_log(action="clinical_rules.review.rejected", payload={
        "table": meta["table"], "row_id": row_id,
        "reviewer": user_ctx.get("sub"), "reason": body["reason"],
    })
    return jsonify({"status": "ok", "table": slug, "row_id": row_id})


@bp.post("/api/clinical-rules/rename/<principle>/mark-covered")
@require_role("super_admin", "admin_tenant")
def mark_rename_drug_covered(principle: str):
    """Marca um fármaco RENAME como coberto pelo motor (após codificação
    das 12 dimensões). Chamado quando admin/farmacêutico promove o fármaco
    pra produção.
    """
    from src.services.postgres import get_postgres
    from src.services.audit_service import audit_log
    from flask import g

    body = request.get_json(silent=True) or {}
    user_ctx = getattr(g, "user", None) or {}

    row = get_postgres().fetch_one(
        """UPDATE aia_health_rename_drugs
           SET motor_coverage = 'covered',
               last_reviewed_at = NOW(),
               last_reviewed_by = %s,
               notes_curador = COALESCE(%s, notes_curador)
           WHERE principle_active = %s AND edicao = '2024'
           RETURNING principle_active, componente, motor_coverage""",
        (user_ctx.get("sub"), body.get("notes"), principle),
    )
    if not row:
        return jsonify({"status": "error", "reason": "principle_not_found_in_rename"}), 404

    # Marca também na drug_dose_limits se existir
    get_postgres().execute(
        """UPDATE aia_health_drug_dose_limits
           SET in_rename = TRUE,
               rename_componente = %s,
               rename_edicao = '2024'
           WHERE principle_active = %s""",
        (row["componente"], principle),
    )

    audit_log(action="clinical_rules.rename.coverage_updated", payload={
        "principle": principle, "actor": user_ctx.get("sub"),
        "from": "pending_or_in_progress", "to": "covered",
    })
    return jsonify({"status": "ok", "principle": principle, "covered": True})
