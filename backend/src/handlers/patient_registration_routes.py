"""Endpoints do wizard de cadastro de paciente + lookup de bases curadas.

Endpoints:
    POST /api/patients                            — cria paciente novo (stub)
    GET  /api/cid10/search?q=press                — autocomplete CID-10
    GET  /api/medication-class/lookup?name=X      — classifica medicamento
    POST /api/registration/validate               — cross-validation
    GET  /api/patients/<id>/registration          — sessão atual + completude
    POST /api/patients/<id>/registration/start    — inicia sessão
    POST /api/patients/<id>/registration/save     — salva passo do wizard
    POST /api/patients/<id>/registration/complete — finaliza
    POST /api/patients/<id>/verify/<section>      — clínico verifica seção

Acesso varia por endpoint — wizard de cadastro pode ser acessado por
roles operacionais (admin_tenant, gestor, enfermeiro, médico) e
verificação clínica só por enfermeiro/médico/farmaceutico.
"""
from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.audit_log_writer import write_audit
from src.services.postgres import get_postgres
from src.services.registration_validation_service import (
    lookup_medication_class,
    search_cid10,
    validate_conditions_medications,
)
from src.utils.logger import get_logger
from src.utils.patient_data_helpers import (
    extract_names,
    merge_items,
    normalize_clinical_array,
)

logger = get_logger(__name__)

bp = Blueprint("patient_registration", __name__)


VALID_SECTIONS = (
    "demographics", "conditions", "medications", "allergies",
    "functional_baseline", "responsibles",
)

# Roles que podem iniciar/operar o wizard de cadastro
WIZARD_ROLES = (
    "super_admin", "admin_tenant",
    "medico", "enfermeiro", "cuidador_pro",
    "familia",  # familiar responsável B2C
)

# Roles que podem MARCAR uma seção como verified_by_clinician
CLINICAL_VERIFY_ROLES = ("super_admin", "medico", "enfermeiro")


def _user() -> dict:
    return getattr(g, "user", None) or {}


# ════════════════════ CRIAÇÃO DE PACIENTE NOVO ══════════════════════

@bp.post("/api/patients")
@require_role(*WIZARD_ROLES)
def create_patient():
    """Cria um paciente "stub" mínimo (só nome + CPF opcional).

    Usado pelo botão "Novo paciente" — a UI cria o paciente vazio e
    redireciona pro wizard `/patients/<id>/registration` onde o resto
    do cadastro é preenchido (demografia completa, condições,
    medicamentos, alergias, responsável).

    Body: { full_name (obrigatório), nickname?, cpf? }
    Retorna: { status, patient: { id, full_name, ... } }

    Tenant: pego do JWT (g.user.tenant_id).
    """
    body = request.get_json(silent=True) or {}
    full_name = (body.get("full_name") or "").strip()
    if not full_name or len(full_name) < 2:
        return jsonify({
            "status": "error",
            "reason": "full_name_obrigatorio",
            "hint": "Nome com pelo menos 2 caracteres",
        }), 400

    user = _user()
    tenant_id = user.get("tenant_id") or user.get("tenantId")
    if not tenant_id:
        return jsonify({
            "status": "error", "reason": "tenant_indefinido",
        }), 400

    from src.services.patient_service import get_patient_service
    svc = get_patient_service()
    try:
        patient = svc.create(
            tenant_id=tenant_id,
            full_name=full_name,
            nickname=body.get("nickname"),
            cpf=body.get("cpf"),
        )
    except Exception as exc:
        logger.error("create_patient_failed error=%s", str(exc))
        return jsonify({
            "status": "error", "reason": "create_failed",
            "detail": str(exc),
        }), 500

    if not patient:
        return jsonify({"status": "error", "reason": "create_returned_null"}), 500

    write_audit(
        action="patient_created",
        actor=user.get("sub") or "system",
        actor_role=user.get("role"),
        tenant_id=tenant_id,
        resource_type="patient",
        resource_id=patient["id"],
        payload={
            "full_name": full_name,
            "via": "wizard_new_patient_button",
        },
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )

    return jsonify({"status": "ok", "patient": patient}), 201


# ════════════════════ LOOKUP DE BASES CURADAS ═══════════════════════

@bp.get("/api/cid10/search")
@require_role(*WIZARD_ROLES)
def cid10_search():
    """Autocomplete CID-10 (subset geriátrico curado).

    Query: q=press (mín 2 chars)
    """
    q = request.args.get("q", "")
    limit = max(1, min(int(request.args.get("limit") or 20), 50))
    items = search_cid10(q, limit=limit)
    return jsonify({"status": "ok", "count": len(items), "items": items})


@bp.get("/api/medication-class/lookup")
@require_role(*WIZARD_ROLES)
def medication_class_lookup():
    """Classifica medicamento (texto livre) em classe terapêutica.
    Útil pra UI mostrar feedback imediato enquanto paciente digita."""
    q = request.args.get("name", "")
    entry = lookup_medication_class(q)
    if not entry:
        return jsonify({"status": "ok", "match": None})
    return jsonify({"status": "ok", "match": entry})


@bp.post("/api/registration/validate")
@require_role(*WIZARD_ROLES)
def validate_registration():
    """Cross-validation condição × medicamento.

    Body: {conditions: [...], medications: [...]}
    Retorna lista de prompts (vazia se tudo ok).
    """
    body = request.get_json(silent=True) or {}
    conditions = body.get("conditions") or []
    medications = body.get("medications") or []
    prompts = validate_conditions_medications(conditions, medications)
    return jsonify({
        "status": "ok",
        "prompts_count": len(prompts),
        "prompts": prompts,
    })


# ════════════════════ SESSÃO DE CADASTRO ════════════════════════════

def _serialize_session(row: dict | None) -> dict | None:
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif hasattr(v, "hex") and not isinstance(v, (bytes, bytearray)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


@bp.get("/api/patients/<patient_id>/registration")
@require_role(*WIZARD_ROLES)
def get_registration_state(patient_id: str):
    """Retorna sessão ativa + completude do paciente.
    Se não houver sessão ativa, retorna o estado atual sem session."""
    db = get_postgres()
    patient = db.fetch_one(
        """SELECT id::text AS id, full_name, conditions, medications,
                  allergies, responsible, registration_completeness,
                  active_registration_session_id::text AS active_session_id,
                  last_self_review_at, is_self_reporting
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    session = None
    if patient.get("active_session_id"):
        session = db.fetch_one(
            """SELECT id::text AS id, registered_by_user_id::text AS registered_by_user_id,
                      registered_by_role, last_completed_step, total_steps,
                      status, started_at, completed_at,
                      consent_lgpd_accepted_at
               FROM aia_health_patient_registration_sessions
               WHERE id = %s""",
            (patient["active_session_id"],),
        )

    return jsonify({
        "status": "ok",
        "patient": {
            "id": patient["id"],
            "full_name": patient["full_name"],
            "conditions": normalize_clinical_array(patient["conditions"] or []),
            "medications": normalize_clinical_array(patient["medications"] or []),
            "allergies": normalize_clinical_array(patient["allergies"] or []),
            "responsible": patient.get("responsible"),
            "completeness": patient.get("registration_completeness") or {},
            "is_self_reporting": patient.get("is_self_reporting"),
            "last_self_review_at": (
                patient["last_self_review_at"].isoformat()
                if patient.get("last_self_review_at") else None
            ),
        },
        "active_session": _serialize_session(session),
    })


@bp.post("/api/patients/<patient_id>/registration/start")
@require_role(*WIZARD_ROLES)
def start_registration(patient_id: str):
    """Inicia uma nova sessão de cadastro.

    Body: {
        registered_by_role: paciente_b2c|familiar_responsavel|...,
        consent_lgpd_accepted: bool (true se B2C/familiar),
        consent_lgpd_ip?: str
    }
    """
    body = request.get_json(silent=True) or {}
    role = body.get("registered_by_role")
    if role not in ("paciente_b2c", "familiar_responsavel", "procurador",
                    "gestor_unidade", "enfermeiro", "medico"):
        return jsonify({
            "status": "error", "reason": "invalid_registered_by_role",
        }), 400

    db = get_postgres()
    patient = db.fetch_one(
        "SELECT id FROM aia_health_patients WHERE id = %s", (patient_id,),
    )
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    user = _user()
    consent_at = None
    if body.get("consent_lgpd_accepted") and role in ("paciente_b2c", "familiar_responsavel"):
        from datetime import datetime, timezone
        consent_at = datetime.now(timezone.utc)

    session = db.fetch_one(
        """INSERT INTO aia_health_patient_registration_sessions
            (patient_id, registered_by_user_id, registered_by_role,
             consent_lgpd_accepted_at, consent_lgpd_ip,
             consent_lgpd_user_agent)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id::text AS id""",
        (
            patient_id, user.get("sub"), role,
            consent_at,
            body.get("consent_lgpd_ip") or request.remote_addr,
            request.headers.get("User-Agent"),
        ),
    )
    if not session:
        return jsonify({"status": "error", "reason": "session_create_failed"}), 500

    db.execute(
        """UPDATE aia_health_patients
           SET active_registration_session_id = %s
           WHERE id = %s""",
        (session["id"], patient_id),
    )

    write_audit(
        action="patient_registration_started",
        actor=user.get("sub") or "system",
        resource_type="patient",
        resource_id=patient_id,
        payload={"role": role, "session_id": session["id"]},
    )

    return jsonify({"status": "ok", "session_id": session["id"]})


@bp.post("/api/patients/<patient_id>/registration/save")
@require_role(*WIZARD_ROLES)
def save_registration_step(patient_id: str):
    """Salva o passo atual do wizard.

    Body: {
        section: 'demographics'|'conditions'|'medications'|'allergies'|...,
        data: {...campo conforme section...},
        step_number: int  (pra atualizar last_completed_step)
    }

    Aplica merge inteligente preservando provenance:
        - Items existentes mantém original_source
        - Items novos ganham declared_at + declared_by_user_id
    """
    body = request.get_json(silent=True) or {}
    section = body.get("section")
    if section not in VALID_SECTIONS:
        return jsonify({
            "status": "error", "reason": "invalid_section",
            "valid": list(VALID_SECTIONS),
        }), 400

    data = body.get("data")
    step_number = body.get("step_number")

    db = get_postgres()
    patient = db.fetch_one(
        """SELECT conditions, medications, allergies, responsible,
                  active_registration_session_id::text AS session_id
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404
    session_id = patient.get("session_id")
    if not session_id:
        return jsonify({
            "status": "error", "reason": "no_active_session",
            "hint": "Chame /registration/start antes",
        }), 400

    user = _user()
    user_id = user.get("sub")

    # Resolve registered_by_role pra estampar source
    sess_role = db.fetch_one(
        """SELECT registered_by_role FROM aia_health_patient_registration_sessions
           WHERE id = %s""",
        (session_id,),
    )
    role = (sess_role or {}).get("registered_by_role") or "self_declared"
    # Mapping role da sessão → source no item
    source_map = {
        "paciente_b2c": "self_declared",
        "familiar_responsavel": "family_declared",
        "procurador": "procurador_declared",
        "gestor_unidade": "manager_declared",
        "enfermeiro": "clinician_validated",
        "medico": "clinician_validated",
    }
    item_source = source_map.get(role, "self_declared")

    # Aplica updates por section
    if section in ("conditions", "medications", "allergies"):
        if not isinstance(data, list):
            return jsonify({
                "status": "error", "reason": "data_must_be_list",
            }), 400
        # Normaliza inputs novos
        new_items: list[dict[str, Any]] = []
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        for raw in data:
            if isinstance(raw, str):
                new_items.append({
                    "name": raw.strip(),
                    "source": item_source,
                    "declared_at": now_iso,
                    "declared_by_user_id": user_id,
                })
            elif isinstance(raw, dict):
                merged = {
                    **raw,
                    "source": raw.get("source") or item_source,
                    "declared_at": raw.get("declared_at") or now_iso,
                    "declared_by_user_id": raw.get("declared_by_user_id") or user_id,
                }
                new_items.append(merged)
        # Merge com items existentes preservando provenance histórica
        existing = patient.get(section) or []
        merged = merge_items(existing, new_items, by_field="name")
        db.execute(
            f"UPDATE aia_health_patients SET {section} = %s::jsonb WHERE id = %s",
            (json.dumps(merged), patient_id),
        )
    elif section == "demographics":
        # Demographics atualiza campos individuais — não é JSONB blob
        allowed = (
            "full_name", "nickname", "cpf", "birth_date", "gender",
            "preferred_form_of_address", "is_self_reporting",
            "care_unit", "room_number", "care_level", "photo_url",
        )
        updates: list[str] = []
        params: list = []
        for k in allowed:
            if k in (data or {}):
                updates.append(f"{k} = %s")
                params.append(data[k])
        if updates:
            params.append(patient_id)
            db.execute(
                f"UPDATE aia_health_patients SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s",
                tuple(params),
            )
    elif section == "responsibles":
        # responsible é JSONB livre (pode ser objeto único ou array)
        db.execute(
            "UPDATE aia_health_patients SET responsible = %s::jsonb WHERE id = %s",
            (json.dumps(data) if data else "null", patient_id),
        )
    elif section == "functional_baseline":
        # Cabe num campo dedicado futuro; por ora vai pra notes
        db.execute(
            """UPDATE aia_health_patients
               SET notes = COALESCE(notes, '') ||
                          E'\n[Baseline funcional ' || NOW()::text || E']\n' || %s
               WHERE id = %s""",
            (json.dumps(data, ensure_ascii=False), patient_id),
        )

    # Atualiza progresso da sessão + completude
    if step_number is not None:
        db.execute(
            """UPDATE aia_health_patient_registration_sessions
               SET last_completed_step = GREATEST(last_completed_step, %s)
               WHERE id = %s""",
            (int(step_number), session_id),
        )

    # Atualiza completeness
    _refresh_completeness(patient_id)

    return jsonify({"status": "ok", "section": section})


def _refresh_completeness(patient_id: str) -> None:
    """Recalcula registration_completeness baseado no que tá preenchido."""
    db = get_postgres()
    p = db.fetch_one(
        """SELECT full_name, birth_date, gender,
                  conditions, medications, allergies, responsible
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not p:
        return

    def _section(arr_or_obj: Any) -> str:
        if not arr_or_obj:
            return "missing"
        if isinstance(arr_or_obj, list) and len(arr_or_obj) > 0:
            return "complete"
        if isinstance(arr_or_obj, dict) and arr_or_obj:
            return "complete"
        return "missing"

    completeness = {
        "demographics": "complete" if (p.get("full_name") and p.get("birth_date")) else "partial",
        "conditions": _section(p.get("conditions")),
        "medications": _section(p.get("medications")),
        "allergies": _section(p.get("allergies")),
        "responsibles": _section(p.get("responsible")),
        "functional_baseline": "missing",  # TODO: campo dedicado
    }
    sections_total = len(completeness)
    sections_complete = sum(1 for v in completeness.values() if v == "complete")
    completeness["completion_percentage"] = round(100 * sections_complete / sections_total)
    from datetime import datetime, timezone
    completeness["last_updated_at"] = datetime.now(timezone.utc).isoformat()

    db.execute(
        """UPDATE aia_health_patients
           SET registration_completeness = %s::jsonb
           WHERE id = %s""",
        (json.dumps(completeness), patient_id),
    )


@bp.post("/api/patients/<patient_id>/registration/complete")
@require_role(*WIZARD_ROLES)
def complete_registration(patient_id: str):
    """Marca sessão como completa."""
    db = get_postgres()
    patient = db.fetch_one(
        """SELECT active_registration_session_id::text AS session_id
           FROM aia_health_patients WHERE id = %s""",
        (patient_id,),
    )
    if not patient or not patient.get("session_id"):
        return jsonify({"status": "error", "reason": "no_active_session"}), 400

    db.execute(
        """UPDATE aia_health_patient_registration_sessions
           SET status = 'complete', completed_at = NOW()
           WHERE id = %s""",
        (patient["session_id"],),
    )
    db.execute(
        """UPDATE aia_health_patients
           SET active_registration_session_id = NULL
           WHERE id = %s""",
        (patient_id,),
    )
    _refresh_completeness(patient_id)

    write_audit(
        action="patient_registration_completed",
        actor=_user().get("sub") or "system",
        resource_type="patient",
        resource_id=patient_id,
        payload={"session_id": patient["session_id"]},
    )
    return jsonify({"status": "ok"})


# ════════════════════ VERIFICAÇÃO CLÍNICA ════════════════════════════

@bp.post("/api/patients/<patient_id>/verify/<section>")
@require_role(*CLINICAL_VERIFY_ROLES)
def verify_section(patient_id: str, section: str):
    """Clínico confirma uma seção. Marca items como
    verified_by_clinician + grava snapshot imutável."""
    if section not in VALID_SECTIONS:
        return jsonify({
            "status": "error", "reason": "invalid_section",
        }), 400

    body = request.get_json(silent=True) or {}
    notes = body.get("notes")

    db = get_postgres()
    patient = db.fetch_one(
        f"SELECT {section} AS content FROM aia_health_patients WHERE id = %s"
        if section in ("conditions", "medications", "allergies")
        else "SELECT * FROM aia_health_patients WHERE id = %s",
        (patient_id,),
    )
    if not patient:
        return jsonify({"status": "error", "reason": "patient_not_found"}), 404

    user = _user()
    user_id = user.get("sub")
    role = user.get("role") or "medico"

    # Snapshot pra auditoria imutável
    if section in ("conditions", "medications", "allergies"):
        content = patient.get("content")
    else:
        content = {section: "verified"}  # placeholder

    db.execute(
        """INSERT INTO aia_health_patient_field_verifications
            (patient_id, section, verified_by_user_id, verified_by_role,
             content_snapshot, notes)
           VALUES (%s, %s, %s, %s, %s::jsonb, %s)""",
        (
            patient_id, section, user_id, role,
            json.dumps(content) if content else "null", notes,
        ),
    )

    # Marca items como verified_by_clinician quando aplicável
    if section in ("conditions", "medications", "allergies"):
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        items = normalize_clinical_array(content or [])
        for it in items:
            it["verified_by_clinician_at"] = now_iso
            it["verified_by_user_id"] = user_id
        db.execute(
            f"UPDATE aia_health_patients SET {section} = %s::jsonb WHERE id = %s",
            (json.dumps(items), patient_id),
        )

    write_audit(
        action="patient_section_verified",
        actor=user_id or "clinician",
        resource_type="patient",
        resource_id=patient_id,
        payload={"section": section, "role": role, "notes": notes},
    )
    return jsonify({"status": "ok"})
