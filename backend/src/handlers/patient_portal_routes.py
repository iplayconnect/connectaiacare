"""Rotas públicas do Portal do Paciente.

Endpoint único de acesso: POST com PIN, valida, retorna pacote completo
(resumo em linguagem simples + prescrição + preços).

Design:
    - Sem auth do CRM
    - Rate-limit por IP + por teleconsultation
    - LGPD Art. 37: todo acesso loggado (ip, ua, action)

Endpoints:
    POST /api/patient-portal/<tc_id>/access         → valida PIN + retorna resumo+preços
    POST /api/patient-portal/<tc_id>/refresh-prices → força recache dos preços
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from src.services.patient_portal_service import get_patient_portal_service
from src.services.patient_summary_service import get_patient_summary_service
from src.services.prescription_pdf_service import get_prescription_pdf_service
from src.services.price_search_service import get_price_search_service
from src.services.teleconsulta_service import get_teleconsulta_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("patient_portal", __name__)


@bp.post("/api/patient-portal/<tc_id>/access")
def access(tc_id: str):
    """Valida PIN e retorna o pacote completo pro portal do paciente.

    Body: {"pin": "123456"}

    Respostas:
        200 → {"status": "ok", "summary": {...}, "prices": [...], "teleconsulta": {...}}
        401 → {"status": "invalid_pin", "attempts_remaining": N}
        403 → {"status": "locked" | "revoked"}
        410 → {"status": "expired"}
        404 → {"status": "not_found"}
    """
    body = request.get_json(silent=True) or {}
    pin = (body.get("pin") or "").strip()
    if not pin or not pin.isdigit() or len(pin) != 6:
        return jsonify({"status": "invalid_pin_format"}), 400

    ip = _client_ip()
    ua = request.headers.get("User-Agent", "")[:300]

    portal = get_patient_portal_service()
    result = portal.validate_pin(tc_id, pin, ip_address=ip, user_agent=ua)

    status = result.get("status")
    if status == "not_found":
        return jsonify(result), 404
    if status == "expired":
        return jsonify(result), 410
    if status in ("locked", "revoked"):
        return jsonify(result), 403
    if status == "invalid_pin":
        return jsonify(result), 401
    if status != "valid":
        return jsonify(result), 500

    # Carrega teleconsulta + prescrição
    tc = get_teleconsulta_service().get_by_id(tc_id)
    if not tc:
        return jsonify({"status": "not_found"}), 404

    # Resumo (cacheado)
    summary = portal.get_cached_summary(tc_id)
    if not summary:
        try:
            patient_obj = {
                "id": tc.get("patient_id"),
                "full_name": tc.get("patient_full_name"),
                "nickname": tc.get("patient_nickname"),
                "birth_date": tc.get("patient_birth_date"),
            }
            summary = get_patient_summary_service().generate(
                soap=tc.get("soap") or {},
                prescription=tc.get("prescription") or [],
                patient=patient_obj,
                doctor_name=tc.get("doctor_name_snapshot") or "Médico(a)",
                doctor_specialty="Geriatria",
            )
            portal.save_summary(tc_id, summary)
        except Exception as exc:
            logger.error("summary_generate_failed", tc_id=tc_id, error=str(exc))
            summary = {"_error": str(exc)}

    # Preços (cacheados)
    prices = portal.get_cached_prices(tc_id)
    if not prices:
        try:
            meds = _extract_medication_names(tc.get("prescription") or [])
            if meds:
                searches = get_price_search_service().search_many(meds)
                prices = {"results": searches, "cached_at": _now_iso()}
                portal.save_prices(tc_id, prices)
            else:
                prices = {"results": [], "cached_at": _now_iso()}
        except Exception as exc:
            logger.error("prices_fetch_failed", tc_id=tc_id, error=str(exc))
            prices = {"results": [], "error": str(exc)}

    # Dados públicos-safe da teleconsulta (só o mínimo necessário)
    tc_public = {
        "id": tc_id,
        "patient_full_name": tc.get("patient_full_name"),
        "patient_nickname": tc.get("patient_nickname"),
        "doctor_name": tc.get("doctor_name_snapshot"),
        "doctor_crm": tc.get("doctor_crm_snapshot"),
        "signed_at": _iso(tc.get("signed_at")),
        "prescription": tc.get("prescription") or [],
    }

    return jsonify({
        "status": "ok",
        "teleconsulta": tc_public,
        "summary": summary,
        "prices": prices,
    })


@bp.post("/api/patient-portal/<tc_id>/pdf")
def download_pdf(tc_id: str):
    """Gera PDF da receita médica. Requer PIN válido.

    Body: {"pin": "123456"}
    Response: application/pdf
    """
    body = request.get_json(silent=True) or {}
    pin = (body.get("pin") or "").strip()
    if not pin:
        return jsonify({"status": "pin_required"}), 400

    portal = get_patient_portal_service()
    result = portal.validate_pin(
        tc_id, pin,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent", "")[:300],
    )
    if result.get("status") != "valid":
        return jsonify(result), 401

    tc = get_teleconsulta_service().get_by_id(tc_id)
    if not tc:
        return jsonify({"status": "not_found"}), 404

    patient_obj = {
        "full_name": tc.get("patient_full_name"),
        "birth_date": tc.get("patient_birth_date"),
        "gender": tc.get("patient_gender"),
        "care_unit": tc.get("patient_care_unit"),
        "allergies": tc.get("patient_allergies") or [],
    }
    doctor_obj = {
        "full_name": tc.get("doctor_name_snapshot") or "Médico(a)",
        "crm_number": tc.get("doctor_crm_snapshot") or "",
        "specialties": ["Geriatria"],
    }
    pdf_bytes = get_prescription_pdf_service().generate(
        teleconsultation=tc,
        patient=patient_obj,
        doctor=doctor_obj,
        prescription_items=tc.get("prescription") or [],
        soap=tc.get("soap") or {},
    )
    try:
        portal._log(
            result.get("access_id"), tc_id, tc.get("tenant_id") or "connectaiacare_demo",
            action="pdf_downloaded",
            detail={"bytes": len(pdf_bytes)},
            ip=_client_ip(),
            ua=request.headers.get("User-Agent", "")[:300],
        )
    except Exception:
        pass

    filename = f"receita-{tc.get('human_id', 0):04d}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@bp.post("/api/patient-portal/<tc_id>/refresh-prices")
def refresh_prices(tc_id: str):
    """Força refresh do cache de preços. Requer PIN válido (idempotente).

    Útil se o paciente quer atualizar. Rate-limit por IP recomendado (futuro).
    """
    body = request.get_json(silent=True) or {}
    pin = (body.get("pin") or "").strip()
    if not pin:
        return jsonify({"status": "pin_required"}), 400

    portal = get_patient_portal_service()
    result = portal.validate_pin(tc_id, pin, ip_address=_client_ip(), user_agent=request.headers.get("User-Agent", "")[:300])
    if result.get("status") != "valid":
        return jsonify(result), 401

    tc = get_teleconsulta_service().get_by_id(tc_id)
    if not tc:
        return jsonify({"status": "not_found"}), 404

    meds = _extract_medication_names(tc.get("prescription") or [])
    searches = get_price_search_service().search_many(meds)
    prices = {"results": searches, "cached_at": _now_iso()}
    portal.save_prices(tc_id, prices)

    return jsonify({"status": "ok", "prices": prices})


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _extract_medication_names(prescription: list[dict]) -> list[str]:
    names: list[str] = []
    for p in prescription or []:
        med = (p.get("medication") or "").strip()
        if not med:
            continue
        # Concatena nome + dose pra busca melhor
        dose = (p.get("dose") or "").strip()
        query = f"{med} {dose}".strip()
        if query:
            names.append(query)
    return names


def _client_ip() -> str | None:
    # Respeita X-Forwarded-For (ProxyFix já limpa no Flask app principal)
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip() or None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return str(value)
