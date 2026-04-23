"""Endpoints do Weekly Report (família).

    POST /api/patients/<patient_id>/weekly-report        → gera/cacheia
    GET  /api/patients/<patient_id>/weekly-report        → retorna o último
    POST /api/patients/<patient_id>/weekly-report/send   → envia via WhatsApp
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.services.evolution import get_evolution
from src.services.postgres import get_postgres
from src.services.weekly_report_service import get_weekly_report_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("weekly_report", __name__)


@bp.post("/api/patients/<patient_id>/weekly-report")
def generate(patient_id: str):
    """Força geração (ou retorna cached) pro paciente."""
    tenant_id = request.args.get("tenant", "connectaiacare_demo")
    try:
        result = get_weekly_report_service().generate_for_patient(
            tenant_id=tenant_id, patient_id=patient_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error("weekly_report_endpoint_failed", error=str(e))
        return jsonify({"error": "generation_failed", "detail": str(e)}), 500

    return jsonify({
        "status": "ok",
        "report_id": str(result["report_id"]),
        "cached": result["cached"],
        "payload": result["payload"],
        "whatsapp_text": result["text"],
        "email_html": result["html"],
    })


@bp.get("/api/patients/<patient_id>/weekly-report")
def last_report(patient_id: str):
    db = get_postgres()
    row = db.fetch_one(
        """
        SELECT id, period_start, period_end, payload,
               rendered_html, rendered_text, sent_at, sent_channels
        FROM aia_health_periodic_reports
        WHERE subject_type = 'patient' AND subject_id = %s
          AND report_kind = 'weekly_family'
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (patient_id,),
    )
    if not row:
        return jsonify({"error": "no_report"}), 404
    return jsonify({
        "report_id": str(row["id"]),
        "period_start": row["period_start"].isoformat() if row.get("period_start") else None,
        "period_end": row["period_end"].isoformat() if row.get("period_end") else None,
        "payload": row.get("payload"),
        "whatsapp_text": row.get("rendered_text"),
        "email_html": row.get("rendered_html"),
        "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
        "sent_channels": row.get("sent_channels") or [],
    })


@bp.post("/api/patients/<patient_id>/weekly-report/send")
def send_report(patient_id: str):
    """Envia relatório mais recente via WhatsApp pro telefone do cuidador principal.

    Body opcional: {"phone": "55519XXXXXXXX"}
    """
    body = request.get_json(silent=True) or {}
    phone = body.get("phone")

    db = get_postgres()
    # Se phone não veio, tenta pegar do último care_event do paciente
    if not phone:
        row = db.fetch_one(
            "SELECT caregiver_phone FROM aia_health_care_events "
            "WHERE patient_id = %s ORDER BY opened_at DESC LIMIT 1",
            (patient_id,),
        )
        phone = row["caregiver_phone"] if row else None

    if not phone:
        return jsonify({"error": "no_recipient_phone"}), 400

    # Carrega último relatório
    report = db.fetch_one(
        """
        SELECT id, rendered_text FROM aia_health_periodic_reports
        WHERE subject_type = 'patient' AND subject_id = %s
          AND report_kind = 'weekly_family'
        ORDER BY generated_at DESC LIMIT 1
        """,
        (patient_id,),
    )
    if not report or not report.get("rendered_text"):
        return jsonify({"error": "no_report"}), 404

    try:
        get_evolution().send_text(phone, report["rendered_text"])
        db.execute(
            """
            UPDATE aia_health_periodic_reports
            SET sent_at = NOW(),
                sent_channels = ARRAY_APPEND(COALESCE(sent_channels, ARRAY[]::TEXT[]), 'whatsapp'),
                recipients = ARRAY_APPEND(COALESCE(recipients, ARRAY[]::TEXT[]), %s)
            WHERE id = %s
            """,
            (phone, report["id"]),
        )
        return jsonify({"status": "sent", "phone_prefix": phone[:4]})
    except Exception as e:
        logger.error("weekly_report_send_failed", error=str(e))
        return jsonify({"error": "send_failed", "detail": str(e)}), 500
