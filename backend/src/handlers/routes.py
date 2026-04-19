"""Rotas HTTP — webhook + API para dashboard."""
from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request

from src.handlers.pipeline import get_pipeline
from src.services.patient_service import get_patient_service
from src.services.report_service import get_report_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "connectaiacare-api"})


# ---------- Webhook WhatsApp (Evolution API) ----------
@bp.post("/webhook/whatsapp")
def whatsapp_webhook():
    # `silent=True` já retorna None em JSON inválido (não levanta exceção).
    # Remove o try/except dead code que existia antes.
    event = request.get_json(silent=True)
    if event is None:
        logger.warning("webhook_invalid_json", remote=request.remote_addr)
        return jsonify({"status": "error", "reason": "invalid_json"}), 400

    # Não vazar str(exc) para o cliente — pode conter stack trace, detalhes de DB,
    # nomes de paciente em mensagens de erro, etc. Retorna trace_id para correlacionar
    # com o log interno (structlog preserva todo o traceback).
    # Ver FINDING-004 do security audit.
    try:
        result = get_pipeline().handle_webhook(event)
        return jsonify(result), 200
    except Exception as exc:  # noqa: BLE001 - catchall intencional (webhook pode receber qualquer coisa)
        trace_id = str(uuid.uuid4())
        logger.exception(
            "webhook_processing_failed",
            trace_id=trace_id,
            error_class=type(exc).__name__,
        )
        # Evolution API espera 200 para confirmar entrega (senão desabilita webhook).
        # TODO(P1): distinguir erros transitórios (retry) vs permanentes — FINDING-007.
        return jsonify({"status": "error", "reason": "internal_error", "trace_id": trace_id}), 200


# ---------- API para dashboard ----------
@bp.get("/api/patients")
def list_patients():
    from config.settings import settings

    rows = get_patient_service().list_all(settings.tenant_id)
    return jsonify({"patients": rows})


@bp.get("/api/patients/<patient_id>")
def get_patient(patient_id: str):
    patient = get_patient_service().get_by_id(patient_id)
    if not patient:
        return jsonify({"error": "not_found"}), 404
    reports = get_report_service().recent_for_patient(patient_id, limit=20)
    return jsonify({"patient": patient, "reports": reports})


@bp.get("/api/reports")
def list_reports():
    from config.settings import settings

    limit = int(request.args.get("limit", 50))
    rows = get_report_service().list_recent(settings.tenant_id, limit=limit)
    return jsonify({"reports": rows})


@bp.get("/api/reports/<report_id>")
def get_report(report_id: str):
    report = get_report_service().get_by_id(report_id)
    if not report:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"report": report})


# ---------- Voice Biometrics ----------
@bp.post("/api/voice/enroll")
def voice_enroll():
    """Cadastra amostra de voz de um cuidador.

    Body: {
        "caregiver_id": "uuid",
        "audio_base64": "...",
        "sample_label": "enrollment_1",
        "sample_rate": 0  # 0 = auto-detect via ffmpeg
    }
    """
    import base64

    from config.settings import settings
    from src.services.voice_biometrics_service import get_voice_biometrics

    body = request.get_json(silent=True) or {}
    caregiver_id = body.get("caregiver_id")
    audio_b64 = body.get("audio_base64")
    if not caregiver_id or not audio_b64:
        return jsonify({"error": "caregiver_id e audio_base64 obrigatórios"}), 400

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return jsonify({"error": "audio_base64 inválido"}), 400

    svc = get_voice_biometrics()
    result = svc.enroll(
        caregiver_id=caregiver_id,
        tenant_id=settings.tenant_id,
        audio_bytes=audio_bytes,
        sample_label=body.get("sample_label", "enrollment"),
        consent_ip=request.remote_addr or "",
        sample_rate=int(body.get("sample_rate", 0)),
    )
    return jsonify(result), 200 if result.get("success") else 400


@bp.get("/api/voice/enrollment/<caregiver_id>")
def voice_enrollment_status(caregiver_id: str):
    from config.settings import settings
    from src.services.voice_biometrics_service import get_voice_biometrics

    svc = get_voice_biometrics()
    return jsonify(svc.get_enrollment_status(caregiver_id, settings.tenant_id))


@bp.delete("/api/voice/enrollment/<caregiver_id>")
def voice_delete_enrollment(caregiver_id: str):
    from config.settings import settings
    from src.services.voice_biometrics_service import get_voice_biometrics

    svc = get_voice_biometrics()
    result = svc.delete_enrollment(caregiver_id, settings.tenant_id, ip=request.remote_addr or "")
    return jsonify(result), 200 if result.get("success") else 400


@bp.get("/api/dashboard/summary")
def dashboard_summary():
    """Resumo para dashboard: contadores por classificação + alertas ativos."""
    from config.settings import settings
    from src.services.postgres import get_postgres

    db = get_postgres()
    totals = db.fetch_all(
        """
        SELECT classification, COUNT(*) AS n
        FROM aia_health_reports
        WHERE tenant_id = %s AND analyzed_at > NOW() - INTERVAL '24 hours'
        GROUP BY classification
        """,
        (settings.tenant_id,),
    )
    counts = {row["classification"]: row["n"] for row in totals if row["classification"]}

    active_patients = db.fetch_one(
        "SELECT COUNT(*) AS n FROM aia_health_patients WHERE tenant_id = %s AND active = TRUE",
        (settings.tenant_id,),
    )

    recent_reports = get_report_service().list_recent(settings.tenant_id, limit=5)

    return jsonify(
        {
            "last_24h_by_classification": counts,
            "active_patients": active_patients["n"] if active_patients else 0,
            "recent_reports": recent_reports,
        }
    )
