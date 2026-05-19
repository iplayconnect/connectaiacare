"""Endpoints de integração com parceiro integrador (TotalCare).

Pra POC inicial: endpoint admin de teste roundtrip que pega um
care_event_id, resolve IDs, monta payload e POSTa pro TotalCare.

Operação contínua (worker que pega fila pendente, retry exponencial,
hook automático no pipeline) fica pra sprint dedicado quando tivermos
o smoke test passando.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.partner_carenote_sync_service import (
    get_partner_carenote_sync,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("partner_integrations", __name__)


@bp.get("/api/integrations/partner/health")
@require_role("super_admin", "admin_tenant")
def health():
    """Confere se o cliente está habilitado (env vars setadas)."""
    svc = get_partner_carenote_sync()
    return jsonify({
        "status": "ok",
        "client_enabled": svc.enabled,
        "base_url_set": bool(svc.client.base_url),
        "api_key_set": bool(svc.client.api_key),
    })


@bp.post("/api/integrations/partner/test-roundtrip")
@require_role("super_admin", "admin_tenant")
def test_roundtrip():
    """Smoke test: dispara sync de um care_event manualmente.

    Body: { care_event_id: UUID, force?: bool }

    Retorna estado completo da sincronização (incluindo partner_carenote_id
    se sucesso, ou reason em caso de falha).
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400

    svc = get_partner_carenote_sync()
    result = svc.sync_care_event(
        care_event_id, force=bool(body.get("force", False)),
    )
    sync_state = svc.get_sync_state(care_event_id)
    return jsonify({**result, "sync_state": sync_state})


@bp.get("/api/integrations/partner/sync-state/<care_event_id>")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def sync_state(care_event_id: str):
    """Retorna estado atual da sincronização pra um care_event."""
    state = get_partner_carenote_sync().get_sync_state(care_event_id)
    if not state:
        return jsonify({"status": "not_synced"}), 404
    return jsonify({"status": "ok", "sync_state": state})


@bp.post("/api/integrations/partner/resolve-patient")
@require_role("super_admin", "admin_tenant")
def resolve_patient():
    """Debug: testa resolução de patient_id (UUID nosso → INT deles).

    Body: { patient_id: UUID }
    """
    body = request.get_json(silent=True) or {}
    patient_id = body.get("patient_id")
    if not patient_id:
        return jsonify({"status": "error", "reason": "patient_id_required"}), 400
    tec_id = get_partner_carenote_sync().resolve_patient_id(patient_id)
    return jsonify({
        "status": "ok",
        "patient_uuid": patient_id,
        "external_partner_patient_id": tec_id,
        "resolved": tec_id is not None,
    })


@bp.post("/api/integrations/partner/open-carenote")
@require_role("super_admin", "admin_tenant")
def open_carenote():
    """Cria CareNote OPEN (cenário 2 — streaming).

    Body: { care_event_id }
    """
    body = request.get_json(silent=True) or {}
    care_event_id = body.get("care_event_id")
    if not care_event_id:
        return jsonify({"status": "error", "reason": "care_event_id_required"}), 400
    svc = get_partner_carenote_sync()
    result = svc.open_carenote_for_streaming(care_event_id)
    return jsonify({**result, "sync_state": svc.get_sync_state(care_event_id)})


@bp.post("/api/integrations/partner/add-addendum")
@require_role("super_admin", "admin_tenant")
def add_addendum():
    """Adiciona addendum a uma CareNote OPEN.

    Body: { care_event_id, content, content_resume, occurred_at?, closes? }
    closes=true → manda status=CLOSED no addendum (fecha CareNote pai).
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
    svc = get_partner_carenote_sync()
    result = svc.add_addendum_to_existing(
        care_event_id=care_event_id,
        content=content,
        content_resume=content_resume,
        occurred_at=body.get("occurred_at"),
        closes_note=bool(body.get("closes", False)),
    )
    return jsonify(result)


@bp.post("/api/integrations/partner/test-streaming")
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

    svc = get_partner_carenote_sync()
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


@bp.post("/api/integrations/partner/resolve-caretaker")
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
    tec_id = get_partner_carenote_sync().resolve_caretaker_id(caregiver_id, phone)
    return jsonify({
        "status": "ok",
        "caregiver_uuid": caregiver_id,
        "phone": phone,
        "external_partner_caretaker_id": tec_id,
        "resolved": tec_id is not None,
    })
