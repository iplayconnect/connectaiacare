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
    """Lista relatos com filtros opcionais.

    Query params:
        limit             int (default 50, max 500)
        classification    str | list — routine|attention|urgent|critical (comma sep ok)
        patient_id        str — filtra por paciente específico
        caregiver_phone   str — normaliza phone (só dígitos)
        days              int — últimos N dias (default 30, max 365)
        search            str — busca em transcription + summary (trigram ILIKE)
    """
    from config.settings import settings
    from datetime import datetime, timedelta, timezone
    from src.services.postgres import get_postgres

    args = request.args
    tenant_id = settings.tenant_id
    limit = min(int(args.get("limit", 50)), 500)
    days = min(int(args.get("days", 30)), 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    classifications_raw = args.get("classification")
    classifications = (
        [c.strip() for c in classifications_raw.split(",") if c.strip()]
        if classifications_raw
        else None
    )

    patient_id = args.get("patient_id")
    caregiver_phone = args.get("caregiver_phone")
    if caregiver_phone:
        caregiver_phone = "".join(c for c in caregiver_phone if c.isdigit())

    search = (args.get("search") or "").strip() or None

    # Monta query dinâmica com bindings seguros
    where_clauses = ["r.tenant_id = %s", "r.received_at >= %s"]
    params: list = [tenant_id, since]

    if classifications:
        where_clauses.append("r.classification = ANY(%s)")
        params.append(classifications)
    if patient_id:
        where_clauses.append("r.patient_id = %s")
        params.append(patient_id)
    if caregiver_phone:
        where_clauses.append("r.caregiver_phone = %s")
        params.append(caregiver_phone)
    if search:
        where_clauses.append(
            "(r.transcription ILIKE %s OR (r.analysis->>'summary') ILIKE %s)"
        )
        like = f"%{search}%"
        params.extend([like, like])

    where_sql = " AND ".join(where_clauses)
    params.append(limit)

    rows = get_postgres().fetch_all(
        f"""
        SELECT r.id, r.patient_id, r.caregiver_phone, r.caregiver_name_claimed,
               r.transcription, r.classification, r.status,
               r.analysis, r.received_at, r.analyzed_at,
               p.full_name AS patient_name, p.nickname AS patient_nickname,
               p.photo_url AS patient_photo, p.room_number AS patient_room,
               p.care_unit AS patient_care_unit
        FROM aia_health_reports r
        LEFT JOIN aia_health_patients p ON p.id = r.patient_id
        WHERE {where_sql}
        ORDER BY r.received_at DESC
        LIMIT %s
        """,
        params,
    )

    return jsonify({
        "reports": rows,
        "filters_applied": {
            "classifications": classifications,
            "patient_id": patient_id,
            "caregiver_phone": caregiver_phone,
            "search": search,
            "days": days,
        },
        "total_returned": len(rows),
    })


@bp.get("/api/reports/<report_id>")
def get_report(report_id: str):
    report = get_report_service().get_by_id(report_id)
    if not report:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"report": report})


@bp.get("/api/reports/<report_id>/audio")
def get_report_audio(report_id: str):
    """Serve o áudio original do relato (OGG do WhatsApp).

    Storage local em /app/storage/audio/<report_id>.ogg (gitignored, volume).
    """
    import os
    from flask import send_file, Response

    # Valida UUID básico
    try:
        import uuid
        uuid.UUID(report_id)
    except ValueError:
        return jsonify({"error": "invalid_id"}), 400

    path = os.path.join("/app/storage/audio", f"{report_id}.ogg")
    if not os.path.exists(path):
        return jsonify({"error": "audio_not_found"}), 404

    return send_file(
        path,
        mimetype="audio/ogg",
        as_attachment=False,
        download_name=f"relato-{report_id[:8]}.ogg",
    )


# ==============================================================
# Teleconsulta via LiveKit (ADR-012, módulo novo 2026-04-22)
# ==============================================================
@bp.post("/api/events/<event_id>/teleconsulta/start")
def start_teleconsultation(event_id: str):
    """Inicia sala LiveKit para teleconsulta, associada ao care_event.

    Body JSON (opcional):
        { "initiator_name": "Dr. Mauricio", "initiator_role": "doctor" }

    Retorna URLs + tokens prontos para:
      - Profissional entrar na sala (doctor_url)
      - Paciente/familiar entrar na sala (patient_url, pode ser enviado via WhatsApp)
    """
    import asyncio
    from src.services.care_event_service import get_care_event_service
    from src.services.patient_service import get_patient_service
    from src.services.teleconsulta_service import get_teleconsulta_service

    svc = get_teleconsulta_service()
    if not svc.enabled:
        return jsonify({
            "status": "error",
            "reason": "teleconsulta_not_configured",
            "message": "LIVEKIT_API_KEY/SECRET não configurados no ambiente."
        }), 503

    event = get_care_event_service().get_by_id(event_id)
    if not event:
        return jsonify({"status": "error", "reason": "event_not_found"}), 404

    patient = get_patient_service().get_by_id(str(event["patient_id"]))
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    body = request.get_json(silent=True) or {}
    initiator_role = body.get("initiator_role", "doctor")
    initiator_name = body.get("initiator_name")

    try:
        result = asyncio.run(
            svc.create_consultation_room(
                event_id=event_id,
                human_id=event.get("human_id"),
                patient_id=str(event["patient_id"]),
                patient_name=patient.get("nickname") or patient.get("full_name") or "Paciente",
                initiator_role=initiator_role,
                initiator_name=initiator_name,
            )
        )
    except Exception as exc:
        logger.error("teleconsulta_start_failed", event_id=event_id, error=str(exc))
        return jsonify({"status": "error", "reason": "livekit_error", "detail": str(exc)}), 500

    return jsonify({"status": "ok", **result})


@bp.post("/api/events/<event_id>/teleconsulta/end")
def end_teleconsultation(event_id: str):
    """Encerra a sala LiveKit da teleconsulta."""
    import asyncio
    from src.services.care_event_service import get_care_event_service
    from src.services.teleconsulta_service import get_teleconsulta_service

    event = get_care_event_service().get_by_id(event_id)
    if not event:
        return jsonify({"status": "error", "reason": "event_not_found"}), 404

    tele_data = (event.get("context") or {}).get("teleconsulta") or {}
    room_name = tele_data.get("room_name")
    if not room_name:
        return jsonify({"status": "error", "reason": "no_active_consultation"}), 400

    body = request.get_json(silent=True) or {}
    notes = body.get("closure_notes")

    try:
        asyncio.run(
            get_teleconsulta_service().end_consultation(
                event_id=event_id, room_name=room_name, closure_notes=notes
            )
        )
    except Exception as exc:
        logger.warning("teleconsulta_end_failed", event_id=event_id, error=str(exc))

    return jsonify({"status": "ended", "room_name": room_name})


@bp.get("/api/events/<event_id>/teleconsulta/participants")
def list_teleconsultation_participants(event_id: str):
    """Lista participantes atuais da sala (polling do dashboard do médico)."""
    import asyncio
    from src.services.care_event_service import get_care_event_service
    from src.services.teleconsulta_service import get_teleconsulta_service

    event = get_care_event_service().get_by_id(event_id)
    if not event:
        return jsonify({"status": "error", "reason": "event_not_found"}), 404

    tele_data = (event.get("context") or {}).get("teleconsulta") or {}
    room_name = tele_data.get("room_name")
    if not room_name:
        return jsonify({"participants": [], "active": False})

    try:
        participants = asyncio.run(
            get_teleconsulta_service().list_participants(room_name)
        )
    except Exception as exc:
        logger.warning("teleconsulta_list_participants_failed", error=str(exc))
        participants = []

    return jsonify({
        "room_name": room_name,
        "participants": participants,
        "active": len(participants) > 0,
    })


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


# ---------- Vital Signs (MedMonitor-ready) ----------
@bp.get("/api/patients/<patient_id>/vitals")
def list_vitals(patient_id: str):
    """Lista sinais vitais de um paciente.

    Query params:
        type: filtro por tipo (blood_pressure_composite, heart_rate, etc.)
        days: janela em dias (default 7)
    """
    from datetime import datetime, timedelta, timezone

    from src.services.vital_signs_service import get_vital_signs_service

    vital_type = request.args.get("type")
    try:
        days = max(1, min(int(request.args.get("days", 7)), 90))
    except ValueError:
        days = 7

    since = datetime.now(timezone.utc) - timedelta(days=days)
    svc = get_vital_signs_service()
    rows = svc.list_by_patient(patient_id, vital_type=vital_type, since=since, limit=1000)
    return jsonify({"vitals": rows, "days": days})


@bp.get("/api/patients/<patient_id>/vitals/summary")
def vitals_summary(patient_id: str):
    """Sumário para prontuário: última medição por tipo + trend + contadores."""
    from src.services.vital_signs_service import get_vital_signs_service

    svc = get_vital_signs_service()
    return jsonify(svc.summary_for_prontuario(patient_id))


# ==============================================================
# Eventos de Cuidado (ADR-018) — dashboard vivo + timeline
# ==============================================================
@bp.get("/api/events/active")
def list_active_events():
    """Lista eventos ativos do tenant — dashboard principal."""
    from config.settings import settings
    from src.services.care_event_service import get_care_event_service

    limit = int(request.args.get("limit", 100))
    rows = get_care_event_service().list_active(settings.tenant_id, limit=limit)
    return jsonify([_serialize_event_summary(r) for r in rows])


@bp.get("/api/events/<event_id>")
def get_event_detail(event_id: str):
    """Detalhes completos de um evento: contexto, timeline, escalações, checkins."""
    from src.services.care_event_service import get_care_event_service
    from src.services.patient_service import get_patient_service
    from src.services.postgres import get_postgres

    svc = get_care_event_service()
    event = svc.get_by_id(event_id)
    if not event:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    patient = get_patient_service().get_by_id(str(event["patient_id"]))
    escalations = svc.list_escalations_for_event(event_id)

    # Checkins (scheduler events)
    db = get_postgres()
    checkins = db.fetch_all(
        """
        SELECT id, kind, scheduled_for, sent_at, response_received_at, response_text,
               response_classification, status, message_sent
        FROM aia_health_care_event_checkins
        WHERE event_id = %s
        ORDER BY scheduled_for
        """,
        (event_id,),
    )

    # Reports ligados ao evento
    reports = db.fetch_all(
        """
        SELECT id, received_at, transcription, classification,
               analysis, audio_duration_seconds
        FROM aia_health_reports
        WHERE care_event_id = %s
        ORDER BY received_at
        """,
        (event_id,),
    )

    return jsonify({
        "event": _serialize_event_detail(event),
        "patient": {
            "id": str(patient["id"]) if patient else None,
            "full_name": patient.get("full_name") if patient else None,
            "nickname": patient.get("nickname") if patient else None,
            "photo_url": patient.get("photo_url") if patient else None,
            "care_unit": patient.get("care_unit") if patient else None,
            "room_number": patient.get("room_number") if patient else None,
            "conditions": patient.get("conditions") if patient else [],
            "medications": patient.get("medications") if patient else [],
        } if patient else None,
        "timeline": _build_timeline(event, checkins, escalations, reports),
        "escalations": [_serialize_escalation(e) for e in escalations],
        "checkins": [_serialize_checkin(c) for c in checkins],
        "reports": [_serialize_report_brief(r) for r in reports],
    })


@bp.post("/api/events/<event_id>/close")
def close_event(event_id: str):
    """Encerra manualmente um evento, com categoria de desfecho.

    Body JSON: { closed_by, closed_reason, closure_notes }
    Sincroniza care-note no MedMonitor (TotalCare) quando possível.
    """
    from config.settings import settings
    from src.services.care_event_service import get_care_event_service
    from src.services.patient_service import get_patient_service
    from src.services.medmonitor_client import get_medmonitor_client

    body = request.get_json(silent=True) or {}
    closed_by = body.get("closed_by") or "operator"
    closed_reason = body.get("closed_reason") or "sem_intercorrencia"
    notes = body.get("closure_notes")

    valid_reasons = {
        "cuidado_iniciado", "encaminhado_hospital", "transferido",
        "sem_intercorrencia", "falso_alarme", "paciente_estavel",
        "expirou_sem_feedback", "obito", "outro",
    }
    if closed_reason not in valid_reasons:
        return jsonify({"status": "error", "reason": "invalid_closed_reason",
                        "valid": sorted(valid_reasons)}), 400

    svc = get_care_event_service()
    event = svc.get_by_id(event_id)
    if not event:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    svc.resolve(event_id, closed_by=closed_by, closed_reason=closed_reason, closure_notes=notes)

    # Tenta sincronizar care-note no MedMonitor
    sync_result: dict[str, Any] = {"attempted": False, "created": False}
    try:
        patient = get_patient_service().get_by_id(str(event["patient_id"]))
        mm = get_medmonitor_client()
        if mm.enabled and patient and patient.get("external_id"):
            # Busca caretaker no MedMonitor pelo phone
            caretaker = mm.find_caretaker_by_phone(event["caregiver_phone"])
            if not caretaker:
                member = mm.find_member_by_phone(event["caregiver_phone"])
                if member and member.get("caretaker_id"):
                    caretaker = {"id": member["caretaker_id"]}
            if caretaker:
                sync_result["attempted"] = True
                content = _build_care_note_content(event, patient, closed_reason, notes)
                summary = event.get("summary") or content[:450]
                created = mm.create_care_note(
                    caretaker_id=caretaker["id"],
                    patient_id=int(patient["external_id"]),
                    content=content,
                    content_resume=summary,
                )
                sync_result["created"] = bool(created)
                sync_result["note_id"] = (created or {}).get("id")
    except Exception as exc:
        logger.warning("care_note_sync_failed", event_id=event_id, error=str(exc))
        sync_result["error"] = str(exc)

    return jsonify({
        "status": "resolved",
        "event_id": event_id,
        "closed_reason": closed_reason,
        "medmonitor_sync": sync_result,
    })


@bp.get("/api/patients/<patient_id>/events")
def list_patient_events(patient_id: str):
    """Timeline completa de eventos de um paciente (dashboard individual)."""
    from src.services.care_event_service import get_care_event_service

    include_closed = request.args.get("include_closed", "true").lower() == "true"
    limit = int(request.args.get("limit", 50))
    rows = get_care_event_service().list_by_patient(
        patient_id, include_closed=include_closed, limit=limit,
    )
    return jsonify([_serialize_event_summary(r) for r in rows])


# ---------- Serializers ----------
def _serialize_event_summary(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "human_id": row.get("human_id"),
        "patient_id": str(row.get("patient_id")) if row.get("patient_id") else None,
        "patient_name": row.get("patient_name"),
        "patient_nickname": row.get("patient_nickname"),
        "patient_photo": row.get("patient_photo"),
        "patient_care_unit": row.get("patient_care_unit"),
        "caregiver_phone": row.get("caregiver_phone"),
        "classification": row.get("current_classification"),
        "status": row.get("status"),
        "event_type": row.get("event_type"),
        "event_tags": row.get("event_tags") or [],
        "summary": row.get("summary"),
        "opened_at": str(row.get("opened_at")) if row.get("opened_at") else None,
        "resolved_at": str(row.get("resolved_at")) if row.get("resolved_at") else None,
        "closed_by": row.get("closed_by"),
        "closed_reason": row.get("closed_reason"),
        "expires_at": str(row.get("expires_at")) if row.get("expires_at") else None,
    }


def _serialize_event_detail(row: dict) -> dict:
    base = _serialize_event_summary(row)
    base.update({
        "context": row.get("context") or {},
        "reasoning": row.get("reasoning"),
        "initial_classification": row.get("initial_classification"),
        "pattern_analyzed_at": str(row.get("pattern_analyzed_at")) if row.get("pattern_analyzed_at") else None,
        "first_escalation_at": str(row.get("first_escalation_at")) if row.get("first_escalation_at") else None,
        "last_check_in_at": str(row.get("last_check_in_at")) if row.get("last_check_in_at") else None,
        "closure_notes": row.get("closure_notes"),
    })
    return base


def _serialize_escalation(e: dict) -> dict:
    return {
        "id": str(e["id"]),
        "target_role": e.get("target_role"),
        "target_name": e.get("target_name"),
        "target_phone": e.get("target_phone"),
        "channel": e.get("channel"),
        "status": e.get("status"),
        "sent_at": str(e.get("sent_at")) if e.get("sent_at") else None,
        "delivered_at": str(e.get("delivered_at")) if e.get("delivered_at") else None,
        "read_at": str(e.get("read_at")) if e.get("read_at") else None,
        "responded_at": str(e.get("responded_at")) if e.get("responded_at") else None,
        "response_summary": e.get("response_summary"),
    }


def _serialize_checkin(c: dict) -> dict:
    return {
        "id": str(c["id"]),
        "kind": c.get("kind"),
        "scheduled_for": str(c.get("scheduled_for")) if c.get("scheduled_for") else None,
        "sent_at": str(c.get("sent_at")) if c.get("sent_at") else None,
        "response_received_at": str(c.get("response_received_at")) if c.get("response_received_at") else None,
        "response_text": c.get("response_text"),
        "response_classification": c.get("response_classification"),
        "status": c.get("status"),
    }


def _serialize_report_brief(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "received_at": str(r.get("received_at")) if r.get("received_at") else None,
        "transcription": r.get("transcription"),
        "classification": r.get("classification"),
        "audio_duration_seconds": r.get("audio_duration_seconds"),
        "analysis_summary": (r.get("analysis") or {}).get("summary") if r.get("analysis") else None,
    }


def _build_timeline(event: dict, checkins: list[dict], escalations: list[dict], reports: list[dict]) -> list[dict]:
    """Mescla checkins+escalations+messages em uma timeline cronológica."""
    items: list[dict] = []

    items.append({
        "t": str(event.get("opened_at")),
        "kind": "event_opened",
        "label": f"Evento aberto (#{event.get('human_id'):04d})" if event.get("human_id") else "Evento aberto",
    })

    # Mensagens do contexto
    for msg in (event.get("context") or {}).get("messages", []):
        ts = msg.get("timestamp")
        if not ts:
            continue
        role = msg.get("role")
        kind = msg.get("kind")
        items.append({
            "t": str(ts),
            "kind": f"message_{role}_{kind}",
            "label": {
                ("caregiver", "audio"): "🎙️ Áudio do cuidador",
                ("caregiver", "text"): "💬 Texto do cuidador",
                ("caregiver", "confirmation"): "✅ Confirmação SIM",
                ("assistant", "analysis_summary"): "📊 Análise emitida",
                ("assistant", "pattern_alert"): "🔍 Padrão histórico detectado",
                ("assistant", "status_check_in"): "🔄 Check-in proativo",
                ("assistant", "text"): "🤖 Resposta do sistema",
            }.get((role, kind), f"{role}/{kind}"),
            "text": msg.get("text") or msg.get("summary"),
        })

    for c in checkins:
        if c.get("sent_at"):
            items.append({
                "t": str(c["sent_at"]),
                "kind": f"checkin_{c.get('kind')}",
                "label": {
                    "pattern_analysis": "🔍 Análise de padrão histórico disparada",
                    "status_update": "🔄 Check-in de status enviado",
                    "closure_check": "⏱️ Decisão de encerramento",
                    "post_escalation": "📞 Escalação para próximo nível",
                }.get(c.get("kind"), f"Check-in {c.get('kind')}"),
            })

    for e in escalations:
        if e.get("sent_at"):
            items.append({
                "t": str(e["sent_at"]),
                "kind": f"escalation_{e.get('target_role')}",
                "label": f"🔔 {e.get('target_role')}: {e.get('target_name') or e.get('target_phone')} "
                         f"({e.get('channel')})",
            })

    if event.get("resolved_at"):
        items.append({
            "t": str(event["resolved_at"]),
            "kind": "event_resolved",
            "label": f"🔚 Encerrado: {event.get('closed_reason')} (por {event.get('closed_by')})",
        })

    # Ordena cronologicamente
    items.sort(key=lambda x: x.get("t") or "")
    return items


def _build_care_note_content(event: dict, patient: dict, closed_reason: str, notes: str | None) -> str:
    """Gera texto da care-note pra sincronizar no TotalCare."""
    cls = (event.get("current_classification") or "").upper()
    human_id = event.get("human_id")
    parts = [
        f"Evento ConnectaIACare #{human_id:04d}" if human_id else "Evento ConnectaIACare",
        f"Classificação: {cls}" if cls else "",
        f"Resumo: {event.get('summary') or '(sem resumo)'}",
        f"Desfecho: {closed_reason}",
    ]
    if notes:
        parts.append(f"Observações: {notes}")
    if event.get("reasoning"):
        parts.append(f"Raciocínio clínico: {event['reasoning']}")
    return "\n".join(p for p in parts if p)


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
