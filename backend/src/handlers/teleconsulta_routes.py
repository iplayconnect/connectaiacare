"""REST endpoints da Teleconsulta (ADR-023).

Complementa os endpoints /api/events/:id/teleconsulta/* (criação de sala) com
operações sobre a sessão de teleconsulta:

    GET  /api/teleconsulta/:id                  Estado completo da sessão
    POST /api/teleconsulta/:id/transcription    Grava transcrição batch
    POST /api/teleconsulta/:id/soap/generate    Invoca soap_writer (LLM)
    GET  /api/teleconsulta/:id/soap             SOAP atual (pra editor)
    PUT  /api/teleconsulta/:id/soap             Médico salva edição
    POST /api/teleconsulta/:id/prescription     Valida + adiciona (validador mocked)
    POST /api/teleconsulta/:id/sign             Assina (mock) + FHIR + sync TotalCare

Workflow pós-consulta no médico:
    encerra sala → transcription (ou vazia) → soap/generate → edita SOAP →
    adiciona prescrição(ões) → sign → celebração + care-note TotalCare
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from src.services.teleconsulta.fhir_emitter import emit_bundle
from src.services.teleconsulta.prescription_validator import get_prescription_validator
from src.services.teleconsulta.soap_writer import get_soap_writer
from src.services.teleconsulta_service import get_teleconsulta_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("teleconsulta", __name__)


# ============================================================
# GET /api/teleconsulta — lista agendamentos (dashboard)
# ============================================================
@bp.get("/api/teleconsulta")
def list_teleconsultas():
    """Lista teleconsultas pra dashboard /teleconsulta.

    Query:
        ?state=scheduling|active|documentation|signed|closed (opcional, múltiplo)
        ?limit=30
    """
    from config.settings import settings as _settings
    from src.services.postgres import get_postgres

    db = get_postgres()
    tenant_id = _settings.tenant_id
    limit = min(int(request.args.get("limit", 30)), 100)
    states = request.args.getlist("state")

    where = ["tc.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if states:
        where.append("tc.state = ANY(%s)")
        params.append(states)

    params.append(limit)
    rows = db.fetch_all(
        f"""
        SELECT
            tc.id, tc.human_id, tc.state, tc.livekit_room_name,
            tc.doctor_name_snapshot, tc.doctor_crm_snapshot,
            tc.livekit_metadata, tc.scheduled_for, tc.started_at,
            tc.ended_at, tc.duration_seconds, tc.care_event_id,
            tc.soap IS NOT NULL AS has_soap,
            tc.signed_at, tc.created_at,
            p.id AS patient_id,
            p.full_name AS patient_name,
            p.nickname AS patient_nickname,
            p.birth_date AS patient_birth_date,
            p.care_unit AS patient_unit,
            p.room_number AS patient_room
        FROM aia_health_teleconsultations tc
        LEFT JOIN aia_health_patients p ON p.id = tc.patient_id
        WHERE {' AND '.join(where)}
        ORDER BY
            CASE tc.state
                WHEN 'active' THEN 0
                WHEN 'scheduling' THEN 1
                WHEN 'documentation' THEN 2
                WHEN 'signed' THEN 3
                ELSE 4
            END,
            COALESCE(tc.scheduled_for, tc.created_at) DESC
        LIMIT %s
        """,
        tuple(params),
    )

    def _to_dict(r: dict) -> dict:
        md = r.get("livekit_metadata") or {}
        return {
            "id": str(r["id"]),
            "human_id": r.get("human_id"),
            "state": r.get("state"),
            "room_name": r.get("livekit_room_name"),
            "doctor_name": r.get("doctor_name_snapshot"),
            "doctor_crm": r.get("doctor_crm_snapshot"),
            "specialty": md.get("specialty") if isinstance(md, dict) else None,
            "reason": md.get("reason") if isinstance(md, dict) else None,
            "duration_min": (md.get("duration_min") if isinstance(md, dict) else None)
                or (r.get("duration_seconds") // 60 if r.get("duration_seconds") else None),
            "scheduled_for": r["scheduled_for"].isoformat()
                if r.get("scheduled_for") and isinstance(r["scheduled_for"], datetime)
                else r.get("scheduled_for"),
            "started_at": r["started_at"].isoformat()
                if r.get("started_at") and isinstance(r["started_at"], datetime)
                else None,
            "ended_at": r["ended_at"].isoformat()
                if r.get("ended_at") and isinstance(r["ended_at"], datetime)
                else None,
            "duration_seconds": r.get("duration_seconds"),
            "has_soap": r.get("has_soap"),
            "signed_at": r["signed_at"].isoformat()
                if r.get("signed_at") and isinstance(r["signed_at"], datetime)
                else None,
            "care_event_id": str(r["care_event_id"]) if r.get("care_event_id") else None,
            "patient": {
                "id": str(r["patient_id"]) if r.get("patient_id") else None,
                "name": r.get("patient_name"),
                "nickname": r.get("patient_nickname"),
                "unit": r.get("patient_unit"),
                "room": r.get("patient_room"),
                "birth_date": r["patient_birth_date"].isoformat()
                    if r.get("patient_birth_date")
                    and hasattr(r["patient_birth_date"], "isoformat")
                    else r.get("patient_birth_date"),
            },
        }

    return jsonify({"teleconsultas": [_to_dict(r) for r in rows], "total": len(rows)}), 200


# ============================================================
# POST /api/teleconsulta/schedule — agendamento direto (sem care_event)
# ============================================================
@bp.post("/api/teleconsulta/schedule")
def schedule_teleconsulta():
    """Cria registro em aia_health_teleconsultations pro fluxo /teleconsulta/agendar.

    Gera room_name LiveKit único, persiste em state='scheduling', retorna
    share_urls pra médico e paciente (ambos já com tc_id embutido pro
    redirect pós-call achar /documentacao ou /finalizada).

    Body esperado:
        {
            "patient_id": "uuid" (obrigatório),
            "doctor_name": "Dra. Ana Silva",
            "doctor_crm": "CRM/RS 12345",
            "specialty": "Geriatria",
            "scheduled_for": "2026-04-25T14:30:00-03:00",
            "duration_min": 45,
            "reason": "motivo opcional"
        }

    Retorna:
        {
            "status": "ok",
            "id": "tc-uuid",
            "room_name": "tc-...",
            "share_url_doctor": "/consulta/<room>?tc=<id>&role=doctor",
            "share_url_patient": "/consulta/<room>?tc=<id>&role=patient",
            "scheduled_for": "..."
        }
    """
    from config.settings import settings as _settings
    from src.services.postgres import get_postgres

    body = request.get_json(silent=True) or {}
    patient_id = body.get("patient_id")
    if not patient_id:
        return jsonify({"status": "error", "message": "patient_id é obrigatório"}), 400

    doctor_name = (body.get("doctor_name") or "Médico ConnectaIACare").strip()
    doctor_crm = body.get("doctor_crm")
    scheduled_for_raw = body.get("scheduled_for")
    duration_min = int(body.get("duration_min") or 45)
    reason = body.get("reason")
    specialty = body.get("specialty")

    db = get_postgres()
    tenant_id = _settings.tenant_id

    # Verifica que o paciente existe
    patient = db.fetch_one(
        "SELECT id, full_name FROM aia_health_patients WHERE id = %s AND tenant_id = %s",
        (patient_id, tenant_id),
    )
    if not patient:
        return jsonify({"status": "error", "message": "paciente não encontrado"}), 404

    # Gera room_name único LiveKit
    room_name = f"tc-sch-{uuid.uuid4().hex[:10]}"

    # Monta metadata LiveKit + dados de agendamento
    metadata = {
        "source": "connectaiacare-schedule",
        "specialty": specialty,
        "reason": reason,
        "duration_min": duration_min,
    }

    row = db.insert_returning(
        """
        INSERT INTO aia_health_teleconsultations
            (tenant_id, patient_id, state, livekit_room_name, livekit_metadata,
             doctor_name_snapshot, doctor_crm_snapshot, scheduled_for)
        VALUES (%s, %s, 'scheduling', %s, %s::jsonb, %s, %s, %s)
        RETURNING id, human_id, livekit_room_name, scheduled_for
        """,
        (
            tenant_id,
            patient_id,
            room_name,
            db.json_adapt(metadata),
            doctor_name,
            doctor_crm,
            scheduled_for_raw,
        ),
    )

    tc_id = str(row["id"])
    logger.info(
        "teleconsulta_scheduled",
        id=tc_id, human_id=row.get("human_id"),
        patient_id=patient_id, doctor=doctor_name,
    )

    share_base = f"/consulta/{room_name}?tc={tc_id}"
    return jsonify({
        "status": "ok",
        "id": tc_id,
        "human_id": row.get("human_id"),
        "room_name": room_name,
        "share_url_doctor": f"{share_base}&role=doctor",
        "share_url_patient": f"{share_base}&role=patient",
        "scheduled_for": row.get("scheduled_for").isoformat() if row.get("scheduled_for") else None,
        "doctor_name": doctor_name,
    }), 201


# ============================================================
# POST /api/teleconsulta/:id/end — finaliza sessão agendada
# ============================================================
@bp.post("/api/teleconsulta/<tc_id>/end")
def end_teleconsulta(tc_id: str):
    """Marca sessão como encerrada (state='documentation') + timestamps.

    Chamado pelo frontend (ConsultaRoom) quando participante desconecta da
    sala. Permite o fluxo pós-call ir pra /documentacao com dados coerentes.
    """
    from src.services.postgres import get_postgres

    db = get_postgres()
    row = db.insert_returning(
        """
        UPDATE aia_health_teleconsultations
        SET ended_at = COALESCE(ended_at, NOW()),
            started_at = COALESCE(started_at, NOW()),
            state = CASE WHEN state IN ('signed', 'closed') THEN state
                         ELSE 'documentation' END,
            updated_at = NOW()
        WHERE id = %s
        RETURNING id, state, duration_seconds
        """,
        (tc_id,),
    )

    if not row:
        return jsonify({"status": "error", "message": "teleconsulta não encontrada"}), 404

    logger.info("teleconsulta_ended_manual", tc_id=tc_id, state=row.get("state"))
    return jsonify({
        "status": "ok",
        "tc_id": tc_id,
        "state": row.get("state"),
        "duration_seconds": row.get("duration_seconds"),
    }), 200


# ============================================================
# GET /api/teleconsulta/:id
# ============================================================
@bp.get("/api/teleconsulta/<tc_id>")
def get_teleconsulta(tc_id: str):
    tc = get_teleconsulta_service().get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404
    # Serializa datetimes e jsonb (o psycopg2 já decodifica JSONB como dict)
    return jsonify({"teleconsulta": _serialize(tc)})


# ============================================================
# POST /api/teleconsulta/:id/transcription
# ============================================================
@bp.post("/api/teleconsulta/<tc_id>/transcription")
def set_transcription(tc_id: str):
    """Recebe transcrição batch da consulta.

    Body: { "transcription": "texto...", "duration_seconds": 1800 }
    """
    svc = get_teleconsulta_service()
    tc = svc.get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404

    body = request.get_json(silent=True) or {}
    transcription = (body.get("transcription") or "").strip()
    if not transcription:
        return jsonify({"error": "transcription_required"}), 400

    duration = body.get("duration_seconds")
    svc.set_transcription(tc_id, transcription, duration)
    return jsonify({"status": "ok", "chars": len(transcription)})


# ============================================================
# POST /api/teleconsulta/:id/soap/generate
# ============================================================
@bp.post("/api/teleconsulta/<tc_id>/soap/generate")
def generate_soap(tc_id: str):
    """Invoca soap_writer a partir da transcrição atual.

    Retorna o SOAP gerado (mesma forma do GET subsequente).
    Se transcrição vazia, retorna fallback estruturado pra médico preencher.
    """
    import asyncio

    svc = get_teleconsulta_service()
    tc = svc.get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404

    transcription = tc.get("transcription_full") or ""
    patient = {
        "id": tc.get("patient_id"),
        "full_name": tc.get("patient_full_name"),
        "nickname": tc.get("patient_nickname"),
        "birth_date": tc.get("patient_birth_date"),
        "gender": tc.get("patient_gender"),
        "care_level": tc.get("patient_care_level"),
        "conditions": tc.get("patient_conditions") or [],
        "medications": tc.get("patient_medications") or [],
        "allergies": tc.get("patient_allergies") or [],
    }

    # Vitais recentes (formato prompt-ready)
    try:
        from src.services.vital_signs_service import get_vital_signs_service
        vitals_text = get_vital_signs_service().format_for_prompt(
            patient_id=str(patient["id"]), hours=72
        )
    except Exception:
        vitals_text = None

    duration_min = None
    if tc.get("transcription_duration_seconds"):
        duration_min = int(tc["transcription_duration_seconds"]) // 60

    try:
        soap = asyncio.run(
            get_soap_writer().write(
                teleconsultation_id=tc_id,
                transcription=transcription,
                patient=patient,
                vital_signs_text=vitals_text,
                duration_min=duration_min,
            )
        )
    except Exception as exc:
        logger.error("soap_generate_failed", tc_id=tc_id, error=str(exc))
        return jsonify({"error": "soap_generation_failed", "detail": str(exc)}), 500

    svc.set_soap(tc_id, soap)
    svc.update_state(tc_id, "documentation")
    return jsonify({"status": "ok", "soap": soap})


# ============================================================
# GET /api/teleconsulta/:id/soap
# ============================================================
@bp.get("/api/teleconsulta/<tc_id>/soap")
def get_soap(tc_id: str):
    tc = get_teleconsulta_service().get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        "soap": tc.get("soap") or {},
        "prescription": tc.get("prescription") or [],
        "signed_at": _iso(tc.get("signed_at")),
        "state": tc.get("state"),
    })


# ============================================================
# PUT /api/teleconsulta/:id/soap
# ============================================================
@bp.put("/api/teleconsulta/<tc_id>/soap")
def update_soap(tc_id: str):
    """Médico salva edição do SOAP."""
    svc = get_teleconsulta_service()
    tc = svc.get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404

    body = request.get_json(silent=True) or {}
    soap = body.get("soap")
    if not isinstance(soap, dict):
        return jsonify({"error": "soap_body_required"}), 400

    svc.set_soap(tc_id, soap)
    return jsonify({"status": "ok"})


# ============================================================
# POST /api/teleconsulta/:id/prescription
# ============================================================
@bp.post("/api/teleconsulta/<tc_id>/prescription")
def add_prescription(tc_id: str):
    """Valida + adiciona prescrição. Body:
    {
        "medication": "Losartana",
        "dose": "50mg",
        "schedule": "1x/dia manhã",
        "duration": "uso contínuo",
        "indication": "Hipertensão"
    }
    """
    import asyncio

    svc = get_teleconsulta_service()
    tc = svc.get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404

    body = request.get_json(silent=True) or {}
    medication = (body.get("medication") or "").strip()
    if not medication:
        return jsonify({"error": "medication_required"}), 400

    patient = {
        "id": tc.get("patient_id"),
        "full_name": tc.get("patient_full_name"),
        "birth_date": tc.get("patient_birth_date"),
        "gender": tc.get("patient_gender"),
        "care_level": tc.get("patient_care_level"),
        "conditions": tc.get("patient_conditions") or [],
        "medications": tc.get("patient_medications") or [],
        "allergies": tc.get("patient_allergies") or [],
    }

    try:
        validation = asyncio.run(
            get_prescription_validator().validate(
                medication=medication,
                dose=body.get("dose") or "",
                schedule=body.get("schedule") or "",
                duration=body.get("duration"),
                indication=body.get("indication"),
                patient=patient,
            )
        )
    except Exception as exc:
        logger.error("prescription_validation_failed", tc_id=tc_id, error=str(exc))
        validation = {
            "validation_status": "approved_with_warnings",
            "severity": "moderate",
            "issues": [],
            "overall_recommendation": "Validação indisponível — revisar manualmente.",
            "_error": str(exc),
        }

    # ── Cruzamento determinístico de dose máxima diária (ANVISA/Beers/SBGG) ──
    # Complementa a validação LLM com lookup em aia_health_drug_dose_limits.
    # Retorna no payload separado pra UI mostrar fonte rastreável.
    try:
        from src.services import dose_validator as _dose_validator
        # Heurística: extrair frequência do schedule textual
        sched_text = (body.get("schedule") or "").lower()
        if "4x" in sched_text or "4 x" in sched_text or "6/6" in sched_text:
            times = ["00", "06", "12", "18"]
        elif "3x" in sched_text or "3 x" in sched_text or "8/8" in sched_text:
            times = ["08", "16", "24"]
        elif "2x" in sched_text or "2 x" in sched_text or "12/12" in sched_text:
            times = ["08", "20"]
        else:
            times = ["08"]
        dose_check = _dose_validator.validate(
            medication_name=medication,
            dose=body.get("dose") or "",
            times_of_day=times,
            patient=patient,
        ).to_dict()
        validation["dose_limit_check"] = dose_check
        # Se determinístico bloquear, sobrepõe LLM
        if dose_check.get("severity") == "block":
            validation["validation_status"] = "rejected"
            validation["severity"] = "critical"
    except Exception as exc:
        logger.warning("dose_limit_check_failed tc_id=%s err=%s", tc_id, str(exc))

    # Adiciona no array de prescription
    existing = list(tc.get("prescription") or [])
    new_item = {
        "id": str(uuid.uuid4()),
        "medication": medication,
        "dose": body.get("dose"),
        "schedule": body.get("schedule"),
        "duration": body.get("duration"),
        "indication": body.get("indication"),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "validation": validation,
    }
    existing.append(new_item)
    svc.set_prescription(tc_id, existing)

    return jsonify({"status": "ok", "prescription_item": new_item, "validation": validation})


# ============================================================
# POST /api/teleconsulta/:id/sign
# ============================================================
@bp.post("/api/teleconsulta/<tc_id>/sign")
def sign_teleconsulta(tc_id: str):
    """Assina (mock) + gera FHIR Bundle + sync TotalCare + fecha evento.

    Body (opcional):
    {
        "doctor_name": "Dra. Ana Silva",  # default: snapshot do registro
        "doctor_crm": "CRM/RS 12345",
        "closure_notes": "..."  # opcional
    }
    """
    svc = get_teleconsulta_service()
    tc = svc.get_by_id(tc_id)
    if not tc:
        return jsonify({"error": "not_found"}), 404

    body = request.get_json(silent=True) or {}
    doctor_name = body.get("doctor_name") or tc.get("doctor_name_snapshot") or "Médico(a)"
    doctor_crm = body.get("doctor_crm") or tc.get("doctor_crm_snapshot") or ""

    # Monta objetos pro FHIR emitter
    patient_obj = {
        "id": tc.get("patient_id"),
        "full_name": tc.get("patient_full_name"),
        "nickname": tc.get("patient_nickname"),
        "birth_date": tc.get("patient_birth_date"),
        "gender": tc.get("patient_gender"),
    }
    doctor_obj = {
        "id": tc.get("doctor_id"),
        "full_name": doctor_name,
        "crm_number": doctor_crm,
        "crm_state": doctor_crm.split("/")[1].split(" ")[0] if "/" in doctor_crm else "",
        "specialties": ["Geriatria"],
        "active": True,
    }

    # Emite FHIR
    bundle = emit_bundle(
        teleconsultation=tc,
        patient=patient_obj,
        doctor=doctor_obj,
        soap=tc.get("soap") or {},
    )
    svc.set_fhir_bundle(tc_id, bundle)

    # Marca como assinado
    svc.mark_signed(
        tc_id,
        doctor_name=doctor_name,
        doctor_crm=doctor_crm,
        signature_method="mock",
    )

    # Tenta sincronizar com TotalCare
    sync_result = _sync_to_totalcare(tc_id, tc, patient_obj, doctor_name, body.get("closure_notes"))

    # Fecha o care_event associado como 'cuidado_iniciado'
    care_event_id = tc.get("care_event_id")
    if care_event_id:
        try:
            from src.services.care_event_service import get_care_event_service
            get_care_event_service().resolve(
                str(care_event_id),
                closed_by=f"doctor:{doctor_name}",
                closed_reason="cuidado_iniciado",
                closure_notes=f"Teleconsulta realizada e assinada. {body.get('closure_notes') or ''}",
            )
        except Exception as exc:
            logger.warning("close_event_after_sign_failed", error=str(exc))

    # Transiciona pra closed (estado final)
    svc.update_state(tc_id, "closed")

    # Gera PIN do portal do paciente + envia WhatsApp
    portal_result = _create_patient_portal_and_notify(tc_id, tc, patient_obj, doctor_name)

    # Popula medication_schedules a partir da prescrição (motor de lembretes)
    schedules_result = _populate_medication_schedules(tc, tc_id, doctor_name)

    return jsonify({
        "status": "signed",
        "teleconsulta_id": tc_id,
        "fhir_bundle_id": bundle.get("id"),
        "signature_method": "mock",
        "medmonitor_sync": sync_result,
        "patient_portal": portal_result,
        "medication_schedules": schedules_result,
    })


def _populate_medication_schedules(tc: dict, tc_id: str, doctor_name: str) -> dict:
    """Cria schedules a partir da prescrição. Não-fatal."""
    try:
        from src.services.medication_schedule_service import get_medication_schedule_service
        prescription = tc.get("prescription") or []
        if not prescription:
            return {"created": 0, "reason": "no_prescription"}
        rows = get_medication_schedule_service().populate_from_prescription(
            tenant_id=tc.get("tenant_id") or "connectaiacare_demo",
            patient_id=str(tc.get("patient_id")),
            prescription_items=prescription,
            teleconsultation_id=tc_id,
            doctor_name=doctor_name,
        )
        return {"created": len(rows), "schedule_ids": [str(r["id"]) for r in rows]}
    except Exception as exc:
        logger.warning("populate_medication_schedules_failed", error=str(exc))
        return {"created": 0, "error": str(exc)}


def _create_patient_portal_and_notify(
    tc_id: str,
    tc: dict,
    patient_obj: dict,
    doctor_name: str,
) -> dict:
    """Gera PIN 24h + envia WhatsApp pro cuidador com link do portal.

    Não-fatal: erro aqui não quebra o sign. O paciente sempre pode ser
    notificado manualmente depois.
    """
    from src.services.patient_portal_service import get_patient_portal_service
    from src.services.postgres import get_postgres

    result: dict = {"created": False}

    # caregiver_phone não está na tabela teleconsultations; está no care_event
    phone = tc.get("caregiver_phone")
    if not phone and tc.get("care_event_id"):
        try:
            row = get_postgres().fetch_one(
                "SELECT caregiver_phone FROM aia_health_care_events WHERE id = %s",
                (str(tc["care_event_id"]),),
            )
            if row:
                phone = row.get("caregiver_phone")
        except Exception as exc:
            logger.warning("fetch_caregiver_phone_failed", error=str(exc))

    if not phone:
        result["reason"] = "no_caregiver_phone"
        logger.warning("patient_portal_no_phone", tc_id=tc_id)
        return result

    try:
        pin, record = get_patient_portal_service().create_access(
            teleconsultation_id=tc_id,
            tenant_id=tc.get("tenant_id") or "connectaiacare_demo",
            recipient_phone=phone,
        )
        result["created"] = True
        result["expires_at"] = (
            record["expires_at"].isoformat() if hasattr(record["expires_at"], "isoformat") else str(record["expires_at"])
        )

        # Envia WhatsApp com link + PIN
        _send_portal_whatsapp(tc_id, phone, pin, patient_obj, doctor_name)
        result["whatsapp_sent"] = True
    except Exception as exc:
        logger.warning("patient_portal_create_failed", tc_id=tc_id, error=str(exc))
        result["error"] = str(exc)
    return result


def _send_portal_whatsapp(
    tc_id: str, phone: str, pin: str, patient: dict, doctor_name: str,
) -> None:
    """Envia mensagem WhatsApp com link do portal + PIN."""
    from src.services.evolution import get_evolution

    patient_ref = (
        patient.get("nickname") or patient.get("first_name")
        or (patient.get("full_name") or "").split()[0] or "paciente"
    )

    # URL do portal - configurável por env
    import os
    portal_base = os.getenv("PATIENT_PORTAL_URL", "https://care.connectaia.com.br/meu")
    link = f"{portal_base}/{tc_id}"

    text = (
        f"👩‍⚕️ *Teleconsulta ConnectaIACare*\n\n"
        f"A teleconsulta de *{patient_ref}* com *{doctor_name}* foi finalizada.\n\n"
        f"📄 O prontuário completo, a receita médica e informações sobre onde "
        f"encontrar os medicamentos com melhor preço estão disponíveis pelas próximas *24 horas*.\n\n"
        f"🔗 *Acesse:* {link}\n\n"
        f"🔑 *Seu código de acesso:*\n*{pin[:3]} {pin[3:]}*\n\n"
        f"_Este código é pessoal. Não compartilhe com terceiros._\n\n"
        f"Qualquer dúvida, entre em contato com a central. Cuide bem!"
    )
    try:
        get_evolution().send_text(phone, text)
        logger.info("patient_portal_whatsapp_sent", tc_id=tc_id, phone_prefix=phone[:4])
    except Exception as exc:
        logger.warning("patient_portal_whatsapp_failed", tc_id=tc_id, error=str(exc))
        raise


# ============================================================
# Helpers
# ============================================================
def _sync_to_totalcare(
    tc_id: str,
    tc: dict,
    patient_obj: dict,
    doctor_name: str,
    closure_notes: str | None,
) -> dict:
    """Cria care-note no TotalCare com resumo clínico da teleconsulta."""
    from src.services.medmonitor_client import get_medmonitor_client
    from src.services.patient_service import get_patient_service

    result: dict = {"attempted": False, "created": False}
    try:
        patient_full = get_patient_service().get_by_id(str(tc.get("patient_id")))
        mm = get_medmonitor_client()
        if not mm.enabled or not patient_full or not patient_full.get("external_id"):
            result["reason"] = "not_enabled_or_no_external_id"
            return result

        caretaker = mm.find_caretaker_by_phone(tc.get("caregiver_phone") or "")
        if not caretaker:
            # Fallback: primeiro caretaker do tenant
            caretakers = mm.list_caretakers()
            caretaker = caretakers[0] if caretakers else None

        if not caretaker:
            result["reason"] = "no_caretaker_match"
            return result

        result["attempted"] = True
        soap = tc.get("soap") or {}
        summary_plan = (soap.get("plan") or {}).get("return_follow_up", {}) or {}
        content = _build_care_note_content(tc, patient_full, doctor_name, closure_notes)
        resume = (
            f"Teleconsulta realizada por {doctor_name}. "
            f"{(soap.get('assessment') or {}).get('clinical_reasoning', '')[:300]}"
        ).strip()[:450]

        created = mm.create_care_note(
            caretaker_id=caretaker["id"],
            patient_id=int(patient_full["external_id"]),
            content=content,
            content_resume=resume,
        )
        result["created"] = bool(created)
        if created:
            result["note_id"] = created.get("id")
    except Exception as exc:
        logger.warning("sync_to_totalcare_failed", tc_id=tc_id, error=str(exc))
        result["error"] = str(exc)
    return result


def _build_care_note_content(tc: dict, patient: dict, doctor_name: str, notes: str | None) -> str:
    soap = tc.get("soap") or {}
    prescription = tc.get("prescription") or []
    subj = (soap.get("subjective") or {}).get("history_of_present_illness") or "(não abordada)"
    assess = (soap.get("assessment") or {}).get("clinical_reasoning") or "(sem raciocínio formal)"
    plan = soap.get("plan") or {}
    meds = []
    for m in prescription:
        meds.append(f"  • {m.get('medication')} · {m.get('dose', '')} · {m.get('schedule', '')}")

    return "\n".join([
        f"[Teleconsulta ConnectaIACare]",
        f"Médico: {doctor_name}",
        f"Paciente: {patient.get('full_name')}",
        "",
        "HDA:",
        subj,
        "",
        "Avaliação:",
        assess,
        "",
        "Plano terapêutico:",
        *(plan.get("non_pharmacological") or []),
        *meds,
        "",
        f"Retorno: {(plan.get('return_follow_up') or {}).get('when', '(conforme necessidade)')}",
        f"\nObservações de encerramento: {notes or '—'}",
    ])


def _serialize(row: dict) -> dict:
    """Normaliza datetimes + UUIDs pra JSON."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "hex"):  # UUID
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value)
