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
