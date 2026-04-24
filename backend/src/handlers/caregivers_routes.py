"""Handler de Caregivers (cuidadores profissionais da equipe).

Schema: aia_health_caregivers (migration 001)
    id UUID, tenant_id, full_name, cpf, phone, role (cuidador|enfermagem|tecnico|coordenador),
    shift (manha|tarde|noite|24h), voice_embedding_json, active, metadata, timestamps

Uso na UI:
    /equipe → lista + cadastro (admin/coordenador)
    /api/caregivers GET — lista (com filtro por role/shift/active)
    /api/caregivers POST — cria novo
    /api/caregivers/:id PATCH — atualiza
    /api/caregivers/:id DELETE — soft delete (active=false)
"""
from __future__ import annotations

import re

from flask import Blueprint, jsonify, request

from config.settings import settings
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("caregivers", __name__)


ALLOWED_ROLES = (
    "cuidador", "cuidadora", "profissional",
    "enfermagem", "tecnico", "coordenador", "medico",
)
ALLOWED_SHIFTS = (
    "manha", "tarde", "noite", "noturno", "diurno",
    "12x36", "24h", "plantao", "flexivel",
)


# ══════════════════════════════════════════════════════════════════
# GET /api/caregivers — lista
# ══════════════════════════════════════════════════════════════════

@bp.get("/caregivers")
def list_caregivers():
    """Lista cuidadores. Query params:
        ?role=cuidador|enfermagem|tecnico|coordenador|medico
        ?shift=manha|tarde|noite|12x36|24h|plantao|flexivel
        ?active=true|false (default true)
        ?q=<busca por nome/phone>
    """
    db = get_postgres()
    tenant_id = settings.tenant_id

    role = request.args.get("role")
    shift = request.args.get("shift")
    active_raw = request.args.get("active", "true").lower()
    active = active_raw not in ("false", "0", "no")
    q = (request.args.get("q") or "").strip()

    where = ["tenant_id = %s"]
    params: list = [tenant_id]

    if active is not None:
        where.append("active = %s")
        params.append(active)

    if role and role in ALLOWED_ROLES:
        where.append("role = %s")
        params.append(role)

    if shift and shift in ALLOWED_SHIFTS:
        where.append("shift = %s")
        params.append(shift)

    if q:
        where.append("(full_name ILIKE %s OR phone ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])

    rows = db.fetch_all(
        f"""
        SELECT id, full_name, cpf, phone, role, shift, active, metadata,
               created_at, updated_at
        FROM aia_health_caregivers
        WHERE {' AND '.join(where)}
        ORDER BY active DESC, full_name ASC
        """,
        tuple(params),
    )

    # Mascara CPF antes de retornar (só mostra ****78-90)
    for r in rows:
        if r.get("cpf"):
            r["cpf"] = _mask_cpf(r["cpf"])

    return jsonify({"caregivers": rows, "total": len(rows)}), 200


# ══════════════════════════════════════════════════════════════════
# POST /api/caregivers — cria
# ══════════════════════════════════════════════════════════════════

@bp.post("/caregivers")
def create_caregiver():
    """Cria novo cuidador.

    Body esperado:
        {
            "full_name": "Júlia Amorim Silva",
            "cpf": "123.456.789-00",
            "phone": "5511987654321",
            "role": "enfermagem",
            "shift": "manha",
            "metadata": {"email": "...", "crm": "...", "notes": "..."}
        }
    """
    body = request.get_json(silent=True) or {}

    error = _validate(body)
    if error:
        return jsonify({"status": "error", **error}), 400

    db = get_postgres()
    tenant_id = settings.tenant_id

    # Normaliza CPF
    cpf_raw = (body.get("cpf") or "").strip()
    cpf_clean = re.sub(r"\D", "", cpf_raw) if cpf_raw else None

    # Normaliza phone
    phone_raw = (body.get("phone") or "").strip()
    phone_clean = re.sub(r"\D", "", phone_raw) if phone_raw else None
    if phone_clean and not phone_clean.startswith("55") and len(phone_clean) in (10, 11):
        phone_clean = "55" + phone_clean

    row = db.insert_returning(
        """
        INSERT INTO aia_health_caregivers
            (tenant_id, full_name, cpf, phone, role, shift, metadata, active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id, full_name, role, shift, active, created_at
        """,
        (
            tenant_id,
            body["full_name"].strip(),
            cpf_clean,
            phone_clean,
            body.get("role", "cuidador"),
            body.get("shift"),
            db.json_adapt(body.get("metadata") or {}),
        ),
    )

    logger.info(
        "caregiver_created",
        id=str(row["id"]),
        role=row["role"],
        full_name=row["full_name"][:30],
    )

    return jsonify({"status": "ok", "caregiver": row}), 201


# ══════════════════════════════════════════════════════════════════
# PATCH /api/caregivers/:id — atualiza
# ══════════════════════════════════════════════════════════════════

@bp.patch("/caregivers/<cg_id>")
def update_caregiver(cg_id: str):
    body = request.get_json(silent=True) or {}
    db = get_postgres()
    tenant_id = settings.tenant_id

    # Constrói SET dinâmico só com campos fornecidos
    allowed = {"full_name", "phone", "role", "shift", "metadata", "active"}
    updates: list[str] = []
    params: list = []
    for k, v in body.items():
        if k not in allowed:
            continue
        if k == "role" and v not in ALLOWED_ROLES:
            continue
        if k == "shift" and v and v not in ALLOWED_SHIFTS:
            continue
        if k == "phone" and v:
            v = re.sub(r"\D", "", str(v))
            if v and not v.startswith("55") and len(v) in (10, 11):
                v = "55" + v
        if k == "metadata":
            v = db.json_adapt(v)
        updates.append(f"{k} = %s")
        params.append(v)

    if not updates:
        return jsonify({"status": "error", "message": "nenhum campo válido"}), 400

    updates.append("updated_at = NOW()")
    params.extend([cg_id, tenant_id])

    row = db.insert_returning(
        f"""
        UPDATE aia_health_caregivers
        SET {', '.join(updates)}
        WHERE id = %s AND tenant_id = %s
        RETURNING id, full_name, role, shift, active, updated_at
        """,
        tuple(params),
    )

    if not row:
        return jsonify({"status": "error", "message": "caregiver não encontrado"}), 404

    logger.info("caregiver_updated", id=cg_id)
    return jsonify({"status": "ok", "caregiver": row}), 200


# ══════════════════════════════════════════════════════════════════
# DELETE /api/caregivers/:id — soft delete (active=false)
# ══════════════════════════════════════════════════════════════════

@bp.delete("/caregivers/<cg_id>")
def deactivate_caregiver(cg_id: str):
    db = get_postgres()
    tenant_id = settings.tenant_id

    row = db.insert_returning(
        """
        UPDATE aia_health_caregivers
        SET active = FALSE, updated_at = NOW()
        WHERE id = %s AND tenant_id = %s
        RETURNING id
        """,
        (cg_id, tenant_id),
    )

    if not row:
        return jsonify({"status": "error", "message": "caregiver não encontrado"}), 404

    logger.info("caregiver_deactivated", id=cg_id)
    return jsonify({"status": "ok"}), 200


# ══════════════════════════════════════════════════════════════════
# Validação
# ══════════════════════════════════════════════════════════════════

def _validate(body: dict) -> dict | None:
    full_name = (body.get("full_name") or "").strip()
    if not full_name or len(full_name.split()) < 2:
        return {"field": "full_name", "message": "Nome completo é obrigatório (nome + sobrenome)"}
    if len(full_name) > 200:
        return {"field": "full_name", "message": "Nome muito longo"}

    cpf = re.sub(r"\D", "", (body.get("cpf") or "").strip())
    if cpf and len(cpf) != 11:
        return {"field": "cpf", "message": "CPF deve ter 11 dígitos"}

    phone = re.sub(r"\D", "", (body.get("phone") or "").strip())
    if phone and (len(phone) < 10 or len(phone) > 13):
        return {"field": "phone", "message": "Telefone com DDD completo"}

    role = body.get("role", "cuidador")
    if role not in ALLOWED_ROLES:
        return {
            "field": "role",
            "message": f"Função inválida. Opções: {', '.join(ALLOWED_ROLES)}",
        }

    shift = body.get("shift")
    if shift and shift not in ALLOWED_SHIFTS:
        return {
            "field": "shift",
            "message": f"Turno inválido. Opções: {', '.join(ALLOWED_SHIFTS)}",
        }

    return None


def _mask_cpf(cpf: str) -> str:
    """123.456.789-00 → ***.***.789-00"""
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11:
        return cpf
    return f"***.***.{digits[6:9]}-{digits[9:11]}"
