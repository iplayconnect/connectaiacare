"""Endpoints de integração com Tecnosenior (TotalCare).

Pra POC inicial: endpoint admin de teste roundtrip que pega um
care_event_id, resolve IDs, monta payload e POSTa pro TotalCare.

Operação contínua (worker que pega fila pendente, retry exponencial,
hook automático no pipeline) fica pra sprint dedicado quando tivermos
o smoke test passando.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.tecnosenior_carenote_sync_service import (
    get_tecnosenior_sync,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("tecnosenior", __name__)


@bp.get("/api/integrations/tecnosenior/health")
@require_role("super_admin", "admin_tenant")
def health():
    """Confere se o cliente está habilitado (env vars setadas)."""
    svc = get_tecnosenior_sync()
    return jsonify({
        "status": "ok",
        "client_enabled": svc.enabled,
        "base_url_set": bool(svc.client.base_url),
        "api_key_set": bool(svc.client.api_key),
    })


@bp.post("/api/integrations/tecnosenior/test-roundtrip")
@require_role("super_admin", "admin_tenant")
def test_roundtrip():
    """Smoke test: dispara sync de um care_event manualmente.

    Body: { care_event_id: UUID, force?: bool }

    Retorna estado completo da sincronização (incluindo tecnosenior_
    carenote_id se sucesso, ou reason em caso de falha).
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400

    svc = get_tecnosenior_sync()
    result = svc.sync_care_event(
        care_event_id, force=bool(body.get("force", False)),
    )
    sync_state = svc.get_sync_state(care_event_id)
    return jsonify({**result, "sync_state": sync_state})


@bp.get("/api/integrations/tecnosenior/sync-state/<care_event_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def sync_state(care_event_id: str):
    """Retorna estado atual da sincronização pra um care_event."""
    state = get_tecnosenior_sync().get_sync_state(care_event_id)
    if not state:
        return jsonify({"status": "not_synced"}), 404
    return jsonify({"status": "ok", "sync_state": state})


@bp.post("/api/integrations/tecnosenior/resolve-patient")
@require_role("super_admin", "admin_tenant")
def resolve_patient():
    """Debug: testa resolução de patient_id (UUID nosso → INT deles).

    Body: { patient_id: UUID }
    """
    body = request.get_json(silent=True) or {}
    patient_id = body.get("patient_id")
    if not patient_id:
        return jsonify({"status": "error", "reason": "patient_id_required"}), 400
    tec_id = get_tecnosenior_sync().resolve_patient_id(patient_id)
    return jsonify({
        "status": "ok",
        "patient_uuid": patient_id,
        "tecnosenior_patient_id": tec_id,
        "resolved": tec_id is not None,
    })


@bp.post("/api/integrations/tecnosenior/open-carenote")
@require_role("super_admin", "admin_tenant")
def open_carenote():
    """Cria CareNote OPEN (cenário 2 — streaming).

    Body: { care_event_id }
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400
    svc = get_tecnosenior_sync()
    result = svc.open_carenote_for_streaming(care_event_id)
    return jsonify({**result, "sync_state": svc.get_sync_state(care_event_id)})


@bp.post("/api/integrations/tecnosenior/add-addendum")
@require_role("super_admin", "admin_tenant")
def add_addendum():
    """Adiciona addendum a uma CareNote OPEN.

    Body: { care_event_id, content, content_resume, occurred_at?,
            closes?, closed_reason? }
    closes=true → manda status=CLOSED no addendum (fecha CareNote pai).
    closed_reason → texto livre ≤50 chars, só vai com closes=true (V2).
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    content = body.get("content")
    content_resume = body.get("content_resume")
    if not all([care_event_id, content, content_resume]):
        return jsonify({
            "status": "error",
            "reason": "missing_fields",
            "required": ["care_event_id", "content", "content_resume"],
        }), 400
    svc = get_tecnosenior_sync()
    result = svc.add_addendum_to_existing(
        care_event_id=care_event_id,
        content=content,
        content_resume=content_resume,
        occurred_at=body.get("occurred_at"),
        closes_note=bool(body.get("closes", False)),
        closed_reason=body.get("closed_reason"),
    )
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════
# V2: Upload de mídia (admin endpoints — smoke test do client)
# ══════════════════════════════════════════════════════════════════════

@bp.post("/api/integrations/tecnosenior/upload-audio-carenote")
@require_role("super_admin", "admin_tenant")
def upload_audio_carenote():
    """Upload de áudio pra CareNote já existente.

    Multipart form-data:
        care_event_id: UUID
        audio: arquivo (file)
        filename?: nome do arquivo (default: audio.ogg)
        content_type?: MIME (default: audio/ogg)
    """
    care_event_id = request.form.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400
    if "audio" not in request.files:
        return jsonify({"status": "error", "reason": "audio_file_required"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    filename = request.form.get("filename") or audio_file.filename or "audio.ogg"
    content_type = (
        request.form.get("content_type")
        or audio_file.content_type
        or "audio/ogg"
    )

    svc = get_tecnosenior_sync()
    result = svc.upload_audio_for_carenote(
        care_event_id=care_event_id,
        audio_bytes=audio_bytes,
        audio_filename=filename,
        content_type=content_type,
    )
    return jsonify(result)


@bp.post("/api/integrations/tecnosenior/upload-audio-addendum")
@require_role("super_admin", "admin_tenant")
def upload_audio_addendum():
    """Upload de áudio pra addendum específico.

    Multipart form-data:
        care_event_id: UUID
        addendum_id: int (ID Tecnosenior do addendum)
        audio: arquivo
    """
    care_event_id = request.form.get("care_event_id")
    addendum_id_raw = request.form.get("addendum_id")
    if not care_event_id or not addendum_id_raw:
        return jsonify({
            "status": "error",
            "reason": "care_event_id_and_addendum_id_required",
        }), 400
    try:
        addendum_id = int(addendum_id_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "reason": "invalid_addendum_id"}), 400
    if "audio" not in request.files:
        return jsonify({"status": "error", "reason": "audio_file_required"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    filename = request.form.get("filename") or audio_file.filename or "audio.ogg"
    content_type = (
        request.form.get("content_type")
        or audio_file.content_type
        or "audio/ogg"
    )

    svc = get_tecnosenior_sync()
    result = svc.upload_audio_for_addendum(
        care_event_id=care_event_id,
        addendum_id=addendum_id,
        audio_bytes=audio_bytes,
        audio_filename=filename,
        content_type=content_type,
    )
    return jsonify(result)


@bp.post("/api/integrations/tecnosenior/upload-photo")
@require_role("super_admin", "admin_tenant")
def upload_photo():
    """Upload de foto pra CareNote (opcionalmente associada a addendum).

    Multipart form-data:
        care_event_id: UUID
        image: arquivo
        addendum_id?: int (associa foto a addendum específico)
    """
    care_event_id = request.form.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400
    if "image" not in request.files:
        return jsonify({"status": "error", "reason": "image_file_required"}), 400

    image_file = request.files["image"]
    image_bytes = image_file.read()
    filename = request.form.get("filename") or image_file.filename or "photo.jpg"
    content_type = (
        request.form.get("content_type")
        or image_file.content_type
        or "image/jpeg"
    )

    addendum_id: int | None = None
    addendum_id_raw = request.form.get("addendum_id")
    if addendum_id_raw:
        try:
            addendum_id = int(addendum_id_raw)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "reason": "invalid_addendum_id"}), 400

    svc = get_tecnosenior_sync()
    result = svc.upload_photo_for_carenote(
        care_event_id=care_event_id,
        image_bytes=image_bytes,
        image_filename=filename,
        content_type=content_type,
        addendum_id=addendum_id,
    )
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════
# V2: Health Measures (TS endpoints em dev — placeholders pra alinhar)
# ══════════════════════════════════════════════════════════════════════

@bp.get("/api/integrations/tecnosenior/health-measures/<int:patient_int_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_health_measures(patient_int_id: int):
    """GET medidas de saúde de um paciente no TotalCare.

    Query params:
        type: heart_rate | blood_pressure_systolic | blood_pressure_diastolic
              | blood_glucose | temperature | weight | oxygen_saturation
        since: ISO 8601 timestamp
        until: ISO 8601 timestamp
        limit: max records (default 100)

    Endpoint Tecnosenior em dev — schema pode ajustar quando estabilizar.
    """
    qs = request.args
    measure_type = qs.get("type") or None
    since = qs.get("since") or None
    until = qs.get("until") or None
    limit_raw = qs.get("limit") or "100"
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        limit = 100

    svc = get_tecnosenior_sync()
    measures = svc.client.list_health_measures(
        patient_id=patient_int_id,
        measure_type=measure_type,
        since=since, until=until, limit=limit,
    )
    return jsonify({
        "status": "ok",
        "patient_id": patient_int_id,
        "measure_type": measure_type,
        "count": len(measures),
        "measures": measures,
    })


@bp.post("/api/integrations/tecnosenior/health-measures/<int:patient_int_id>/bulk")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def post_health_measures_bulk(patient_int_id: int):
    """POST bulk de medidas de saúde pra um paciente.

    Body: {
        idempotency_key?: string,
        measures: [
            {type, value, unit?, measured_at?, source?, confidence?, raw_text?},
            ...
        ]
    }

    Padrão de uso: cuidador relata várias medidas via WhatsApp,
    Sofia acumula, recapitula com ele, depois faz bulk send.
    Sanitização: types inválidos e values não-numéricos são
    silenciosamente filtrados antes do POST.
    """
    body = request.get_json(silent=True) or {}
    measures = body.get("measures") or []
    if not isinstance(measures, list) or not measures:
        return jsonify({
            "status": "error",
            "reason": "measures_required_list",
        }), 400

    svc = get_tecnosenior_sync()
    result = svc.client.create_health_measures_bulk(
        patient_id=patient_int_id,
        measures=measures,
        idempotency_key=body.get("idempotency_key"),
    )
    if result is None:
        return jsonify({"status": "error", "reason": "bulk_post_failed"}), 502
    return jsonify({"status": "ok", "result": result})


@bp.post("/api/integrations/tecnosenior/test-streaming")
@require_role("super_admin", "admin_tenant")
def test_streaming():
    """Smoke test do cenário 2 completo num único request:

    1. Abre CareNote OPEN pro care_event
    2. Manda N addendums sequenciais (cada um com pequeno delay)
    3. Fecha com último addendum status=CLOSED

    Body: { care_event_id, addendums: [{content, content_resume}], close: true }

    Útil pra validar com Matheus que múltiplos addendums aparecem
    no painel deles.
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    addendums = body.get("addendums") or []
    close = body.get("close", True)
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400
    if not addendums or not isinstance(addendums, list):
        return jsonify({
            "status": "error", "reason": "addendums_required_list",
        }), 400

    svc = get_tecnosenior_sync()
    out: dict = {"steps": []}

    open_res = svc.open_carenote_for_streaming(care_event_id)
    out["steps"].append({"action": "open", **open_res})
    if open_res.get("status") not in ("ok", "already_synced"):
        return jsonify(out), 400

    from datetime import datetime, timedelta, timezone as tz
    base_time = datetime.now(tz.utc)
    last_idx = len(addendums) - 1
    for i, add in enumerate(addendums):
        # occurred_at incrementa N segundos pra ordem visual no painel
        occurred = (base_time + timedelta(seconds=(i + 1) * 30)).isoformat()
        is_last_and_close = (i == last_idx) and close
        add_res = svc.add_addendum_to_existing(
            care_event_id=care_event_id,
            content=add.get("content", ""),
            content_resume=add.get("content_resume", ""),
            occurred_at=occurred,
            closes_note=is_last_and_close,
        )
        out["steps"].append({"action": f"addendum_{i+1}", **add_res})
        if add_res.get("status") != "ok":
            return jsonify(out), 400

    out["status"] = "ok"
    out["sync_state"] = svc.get_sync_state(care_event_id)
    return jsonify(out)


@bp.post("/api/integrations/tecnosenior/resolve-caretaker")
@require_role("super_admin", "admin_tenant")
def resolve_caretaker():
    """Debug: testa resolução de caretaker_id por UUID OU phone."""
    body = request.get_json(silent=True) or {}
    caregiver_id = body.get("caregiver_id")
    phone = body.get("phone")
    if not caregiver_id and not phone:
        return jsonify({
            "status": "error",
            "reason": "caregiver_id_or_phone_required",
        }), 400
    tec_id = get_tecnosenior_sync().resolve_caretaker_id(caregiver_id, phone)
    return jsonify({
        "status": "ok",
        "caregiver_uuid": caregiver_id,
        "phone": phone,
        "tecnosenior_caretaker_id": tec_id,
        "resolved": tec_id is not None,
    })
