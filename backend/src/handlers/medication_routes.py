"""Endpoints de medicação — schedules, events, upload OCR, adesão.

Endpoints públicos (internos ao CRM):
    GET  /api/patients/<id>/medication-schedules       → lista ativos
    POST /api/patients/<id>/medication-schedules       → cria manual
    PUT  /api/medication-schedules/<id>                → update
    DELETE /api/medication-schedules/<id>              → desativa

    GET  /api/patients/<id>/medication-events/upcoming → próximas 24h
    GET  /api/patients/<id>/medication-events/history  → últimos 7d
    POST /api/medication-events/<id>/confirm           → marca tomada manual
    POST /api/medication-events/<id>/skip              → pula com motivo

    GET  /api/patients/<id>/medication-adherence       → métricas %

    POST /api/patients/<id>/medication-imports         → upload foto/audio
    GET  /api/medication-imports/<id>                  → estado da análise
    POST /api/medication-imports/<id>/confirm          → confirma e popula schedules
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from src.services.medication_event_service import get_medication_event_service
from src.services.medication_schedule_service import get_medication_schedule_service
from src.services.prescription_ocr_service import get_prescription_ocr_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("medication", __name__)


# ══════════════════════════════════════════════════════════════════
# Schedules
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/patients/<patient_id>/medication-schedules")
def list_schedules(patient_id: str):
    schedules = get_medication_schedule_service().list_active_for_patient(patient_id)
    return jsonify({
        "results": [_serialize_schedule(s) for s in schedules],
    })


@bp.post("/api/patients/<patient_id>/medication-schedules")
def create_schedule(patient_id: str):
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id") or "connectaiacare_demo"

    if not body.get("medication_name") or not body.get("dose"):
        return jsonify({"error": "medication_name_and_dose_required"}), 400

    # ── Validação de dose máxima diária (cruzamento determinístico) ──
    # Bloqueia hard se ratio > 2× e source confidence ≥ 0.9.
    # Cliente pode forçar com `force=true` (médico assume responsabilidade,
    # registramos no warnings da schedule pra audit).
    from src.services import dose_validator
    from src.services.postgres import get_postgres
    patient_row = get_postgres().fetch_one(
        "SELECT id, full_name, birth_date FROM aia_health_patients WHERE id = %s",
        (patient_id,),
    )
    validation = dose_validator.validate(
        medication_name=body["medication_name"],
        dose=body["dose"],
        times_of_day=body.get("times_of_day"),
        route=(body.get("route") or "oral").lower(),
        patient=dict(patient_row) if patient_row else None,
        schedule_type=body.get("schedule_type"),
    ).to_dict()

    force = bool(body.get("force"))
    if validation["severity"] == "block" and not force:
        return jsonify({
            "status": "error",
            "reason": "dose_validation_blocked",
            "validation": validation,
        }), 422

    # Anexa warnings da validação às warnings já passadas pelo cliente
    extra_warnings = [
        i["message"] for i in validation["issues"]
        if i["severity"] in ("warning", "warning_strong", "block")
    ]
    body_warnings = body.get("warnings") or []
    if extra_warnings:
        body_warnings = list(body_warnings) + extra_warnings

    svc = get_medication_schedule_service()
    row = svc.create(
        tenant_id=tenant_id,
        patient_id=patient_id,
        medication_name=body["medication_name"],
        dose=body["dose"],
        schedule_type=body.get("schedule_type", "fixed_daily"),
        times_of_day=body.get("times_of_day"),
        days_of_week=body.get("days_of_week"),
        day_of_month=body.get("day_of_month"),
        cycle_length_days=body.get("cycle_length_days"),
        dose_form=body.get("dose_form", "comprimido"),
        with_food=body.get("with_food", "either"),
        special_instructions=body.get("special_instructions"),
        warnings=body_warnings,
        source_type=body.get("source_type", "manual_admin"),
        added_by_type=body.get("added_by_type"),
        starts_at=_parse_date(body.get("starts_at")),
        ends_at=_parse_date(body.get("ends_at")),
        reminder_advance_min=body.get("reminder_advance_min", 10),
        tolerance_minutes=body.get("tolerance_minutes", 60),
        preferred_channels=body.get("preferred_channels"),
    )

    # Cria alerta automático se houve warning_strong/block e schedule foi criada
    if validation["severity"] in ("warning_strong", "block"):
        try:
            get_postgres().execute(
                """
                INSERT INTO aia_health_alerts
                    (tenant_id, patient_id, level, title, description,
                     recommended_actions, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tenant_id, patient_id,
                    "high" if validation["severity"] == "block" else "medium",
                    f"Dose acima do limite: {body['medication_name']}",
                    " ".join(i["message"] for i in validation["issues"]),
                    psycopg2_json([{"action": "review_with_doctor"}]),
                    psycopg2_json({"validation": validation, "schedule_id": str(row["id"])}),
                ),
            )
        except Exception as exc:
            logger.warning("alert_create_failed name=%s err=%s", body["medication_name"], str(exc))

    return jsonify({
        "status": "ok",
        "schedule": _serialize_schedule(row),
        "validation": validation,
    })


# Helper local pra json adapter sem importar psycopg2 ali em cima
def psycopg2_json(data):
    import psycopg2.extras
    return psycopg2.extras.Json(data)


@bp.put("/api/medication-schedules/<schedule_id>")
def update_schedule(schedule_id: str):
    body = request.get_json(silent=True) or {}
    svc = get_medication_schedule_service()
    row = svc.update(schedule_id, body)
    if not row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"status": "ok", "schedule": _serialize_schedule(row)})


@bp.delete("/api/medication-schedules/<schedule_id>")
def delete_schedule(schedule_id: str):
    reason = (request.args.get("reason") or "desativado pelo usuário")
    get_medication_schedule_service().deactivate(schedule_id, reason)
    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════════════
# Events
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/patients/<patient_id>/medication-events/upcoming")
def events_upcoming(patient_id: str):
    hours = int(request.args.get("hours", 24))
    # Materializa events pendentes antes de listar
    get_medication_event_service().materialize_for_patient(
        patient_id, horizon_hours=hours,
    )
    events = get_medication_event_service().list_upcoming(patient_id, hours=hours)
    return jsonify({"results": [_serialize_event(e) for e in events]})


@bp.get("/api/patients/<patient_id>/medication-events/history")
def events_history(patient_id: str):
    days = int(request.args.get("days", 7))
    events = get_medication_event_service().list_history(patient_id, days=days)
    return jsonify({"results": [_serialize_event(e) for e in events]})


@bp.post("/api/medication-events/<event_id>/confirm")
def confirm_event(event_id: str):
    body = request.get_json(silent=True) or {}
    get_medication_event_service().mark_taken(
        event_id=event_id,
        confirmed_by=body.get("confirmed_by", "caregiver"),
        actual_dose=body.get("actual_dose"),
        notes=body.get("notes"),
    )
    return jsonify({"status": "ok"})


@bp.post("/api/medication-events/<event_id>/skip")
def skip_event(event_id: str):
    body = request.get_json(silent=True) or {}
    reason = body.get("reason", "Sem motivo informado")
    get_medication_event_service().mark_skipped(event_id, reason)
    return jsonify({"status": "ok"})


# ══════════════════════════════════════════════════════════════════
# Adesão
# ══════════════════════════════════════════════════════════════════

@bp.get("/api/patients/<patient_id>/medication-adherence")
def adherence(patient_id: str):
    days = int(request.args.get("days", 30))
    svc = get_medication_event_service()
    return jsonify({
        "summary": svc.adherence_summary(patient_id, days=days),
        "by_medication": svc.adherence_by_medication(patient_id, days=days),
        "consecutive_missed": svc.detect_consecutive_missed(patient_id, threshold=3),
    })


# ══════════════════════════════════════════════════════════════════
# Imports (foto/áudio)
# ══════════════════════════════════════════════════════════════════

@bp.post("/api/patients/<patient_id>/medication-imports")
def create_import(patient_id: str):
    """Recebe imagem base64 e inicia análise Claude Vision.

    Body:
        {
          "source_type": "photo_prescription" | "photo_package" | "photo_leaflet" | "photo_pill_organizer",
          "file_b64": "data:image/jpeg;base64,xxx",
          "file_mime": "image/jpeg",
          "uploaded_by_type": "patient" | "family" | "caregiver",
          "uploaded_by_id": "uuid opcional"
        }

    Response (síncrono pra simplicidade — se ficar lento, migrar pra queue):
        {
          "import_id": "uuid",
          "status": "done" | "failed",
          "analysis": { ... }
        }
    """
    body = request.get_json(silent=True) or {}
    tenant_id = body.get("tenant_id") or "connectaiacare_demo"

    file_b64 = body.get("file_b64")
    file_mime = body.get("file_mime", "image/jpeg")
    source_type = body.get("source_type", "photo_package")

    if not file_b64:
        return jsonify({"error": "file_b64_required"}), 400

    if source_type not in (
        "photo_prescription", "photo_package", "photo_leaflet",
        "photo_pill_organizer", "audio_description", "text_description",
    ):
        return jsonify({"error": "invalid_source_type"}), 400

    ocr = get_prescription_ocr_service()

    # Grava upload
    import_row = ocr.create_import_record(
        tenant_id=tenant_id,
        patient_id=patient_id,
        source_type=source_type,
        file_b64=file_b64[:500_000],  # limite prudente pra não estourar DB
        file_mime=file_mime,
        uploaded_by_type=body.get("uploaded_by_type"),
        uploaded_by_id=body.get("uploaded_by_id"),
        device_user_agent=request.headers.get("User-Agent", "")[:300],
    )
    import_id = str(import_row["id"])

    # Analisa (síncrono — ~3-8s)
    try:
        analysis = ocr.analyze_image(file_b64, mime_type=file_mime)
        ocr.save_analysis(import_id, analysis)

        return jsonify({
            "status": "ok",
            "import_id": import_id,
            "analysis_status": "done" if analysis.get("medications") else "failed",
            "kind": analysis.get("kind"),
            "confidence": analysis.get("confidence"),
            "needs_more_info": analysis.get("needs_more_info"),
            "medications": analysis.get("medications") or [],
            "notes_for_user": analysis.get("notes_for_user"),
            "doctor_info": analysis.get("doctor_info"),
            "issue_date": analysis.get("issue_date"),
        })
    except Exception as exc:
        logger.error("import_analysis_failed", import_id=import_id, error=str(exc))
        return jsonify({
            "status": "error",
            "import_id": import_id,
            "detail": str(exc),
        }), 500


@bp.get("/api/medication-imports/<import_id>")
def get_import(import_id: str):
    row = get_prescription_ocr_service().get_import(import_id)
    if not row:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        "id": str(row["id"]),
        "source_type": row["source_type"],
        "analysis_status": row["analysis_status"],
        "confirmation_status": row["confirmation_status"],
        "analyzed_at": _iso(row.get("analyzed_at")),
        "parsed_medications": row.get("parsed_medications") or [],
        "needs_more_info": row.get("needs_more_info"),
        "created_schedule_ids": row.get("created_schedule_ids") or [],
    })


@bp.post("/api/medication-imports/<import_id>/confirm")
def confirm_import(import_id: str):
    """Usuário confirmou a lista extraída — popula schedules.

    Body:
        {
          "medications": [  // pode ser versão editada
            { "name", "dose", "schedule_text", "parsed_schedule", "duration_days", ... }
          ],
          "added_by_type": "patient" | "family" | "caregiver"
        }
    """
    body = request.get_json(silent=True) or {}
    medications = body.get("medications") or []
    added_by_type = body.get("added_by_type", "patient")

    ocr = get_prescription_ocr_service()
    imp = ocr.get_import(import_id)
    if not imp:
        return jsonify({"error": "not_found"}), 404

    schedules_svc = get_medication_schedule_service()
    created_ids = []

    for med in medications:
        if not med.get("name") or not med.get("dose"):
            continue

        parsed = med.get("parsed_schedule") or {}
        schedule_type = "prn" if parsed.get("prn") else "fixed_daily"
        if parsed.get("days_of_week"):
            schedule_type = "fixed_weekly"

        # Confidence baixa → marca needs_review
        field_conf = med.get("field_confidence") or {}
        min_conf = min(
            field_conf.get("name", 1.0),
            field_conf.get("dose", 1.0),
            field_conf.get("schedule", 1.0),
        ) if field_conf else 1.0
        verification_status = "needs_review" if min_conf < 0.7 else "confirmed"

        try:
            row = schedules_svc.create(
                tenant_id=imp["tenant_id"],
                patient_id=str(imp["patient_id"]),
                medication_name=med["name"],
                dose=med["dose"],
                schedule_type=schedule_type,
                times_of_day=parsed.get("times_of_day"),
                days_of_week=parsed.get("days_of_week"),
                dose_form=med.get("dose_form", "comprimido"),
                with_food=med.get("with_food", "either"),
                special_instructions=med.get("indication"),
                warnings=med.get("warnings") or [],
                source_type=f"ocr_image",
                source_id=import_id,
                source_confidence=min_conf,
                added_by_type=added_by_type,
                verification_status=verification_status,
                ends_at=_duration_to_end_date(med.get("duration_days")),
            )
            created_ids.append(str(row["id"]))
        except Exception as exc:
            logger.warning(
                "schedule_from_import_failed",
                import_id=import_id, medication=med.get("name"), error=str(exc),
            )

    ocr.confirm_import(
        import_id,
        user_corrections=medications,
        created_schedule_ids=created_ids,
    )

    return jsonify({
        "status": "ok",
        "created_schedule_ids": created_ids,
        "count": len(created_ids),
    })


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _serialize_schedule(s: dict) -> dict:
    return {
        "id": str(s["id"]),
        "medication_name": s.get("medication_name"),
        "dose": s.get("dose"),
        "dose_form": s.get("dose_form"),
        "schedule_type": s.get("schedule_type"),
        "times_of_day": [str(t) for t in (s.get("times_of_day") or [])],
        "days_of_week": s.get("days_of_week"),
        "with_food": s.get("with_food"),
        "special_instructions": s.get("special_instructions"),
        "warnings": s.get("warnings") or [],
        "source_type": s.get("source_type"),
        "source_confidence": float(s["source_confidence"]) if s.get("source_confidence") is not None else 1.0,
        "verification_status": s.get("verification_status"),
        "active": s.get("active"),
        "starts_at": _iso(s.get("starts_at")),
        "ends_at": _iso(s.get("ends_at")),
    }


def _serialize_event(e: dict) -> dict:
    return {
        "id": str(e["id"]),
        "schedule_id": str(e["schedule_id"]),
        "medication_name": e.get("medication_name"),
        "dose": e.get("dose"),
        "scheduled_at": _iso(e["scheduled_at"]),
        "reminder_sent_at": _iso(e.get("reminder_sent_at")),
        "confirmed_at": _iso(e.get("confirmed_at")),
        "confirmed_by": e.get("confirmed_by"),
        "status": e.get("status"),
        "actual_dose_taken": e.get("actual_dose_taken"),
        "notes": e.get("notes"),
        "special_instructions": e.get("special_instructions"),
        "with_food": e.get("with_food"),
        "warnings": e.get("warnings") or [],
    }


def _iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _parse_date(s):
    if not s:
        return None
    try:
        from datetime import date
        return date.fromisoformat(s)
    except Exception:
        return None


def _duration_to_end_date(days):
    if not days:
        return None
    try:
        from datetime import date, timedelta
        return date.today() + timedelta(days=int(days))
    except Exception:
        return None
