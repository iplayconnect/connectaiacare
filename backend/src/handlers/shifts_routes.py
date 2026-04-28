"""Endpoints REST para gestão de plantões + phone_type.

Plantões definem janelas horárias por cuidador. Usados pra reduzir
o pool de busca da biometria de voz (1:N grande → 1:N pequeno do
plantão atual). phone_type ('shared'/'personal') controla se um
número de WhatsApp é celular do plantão (compartilhado) ou pessoal
do cuidador.

Insight do panel LLM (Grok fase 2). Ver docs/consolidacao_panel_llm.md.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.postgres import get_postgres
from src.services.shift_resolver_service import get_shift_resolver
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("shifts", __name__)


# ════════════════════════════════════════════════════════════════════
# Plantões — schedules por cuidador
# ════════════════════════════════════════════════════════════════════

@bp.get("/api/shifts")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_shifts():
    """Lista todos os plantões cadastrados do tenant."""
    from config.settings import settings
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT s.id::text AS id, s.caregiver_id::text AS caregiver_id,
                  c.full_name, c.phone, c.phone_type,
                  s.shift_name, s.starts_at::text AS starts_at,
                  s.ends_at::text AS ends_at, s.weekdays,
                  s.active, s.notes
           FROM aia_health_shift_schedules s
           JOIN aia_health_caregivers c ON c.id = s.caregiver_id
           WHERE s.tenant_id = %s
           ORDER BY s.shift_name, s.starts_at, c.full_name""",
        (settings.tenant_id,),
    )
    return jsonify({"status": "ok", "shifts": [dict(r) for r in rows or []]})


@bp.post("/api/shifts")
@require_role("super_admin", "admin_tenant")
def create_shift():
    """Cria novo plantão.

    Body: {
      caregiver_id, shift_name,
      starts_at: "HH:MM", ends_at: "HH:MM",
      weekdays: [1..7],   # default todos os dias
      notes?: string
    }
    """
    from config.settings import settings
    body = request.get_json(silent=True) or {}
    required = ["caregiver_id", "shift_name", "starts_at", "ends_at"]
    if any(not body.get(k) for k in required):
        return jsonify({
            "status": "error",
            "reason": "missing_fields",
            "required": required,
        }), 400

    weekdays = body.get("weekdays") or [1, 2, 3, 4, 5, 6, 7]
    if not all(isinstance(d, int) and 1 <= d <= 7 for d in weekdays):
        return jsonify({"status": "error", "reason": "invalid_weekdays"}), 400

    db = get_postgres()
    row = db.fetch_one(
        """INSERT INTO aia_health_shift_schedules (
              tenant_id, caregiver_id, shift_name,
              starts_at, ends_at, weekdays, notes
           ) VALUES (%s, %s, %s, %s, %s, %s, %s)
           RETURNING id::text""",
        (settings.tenant_id, body["caregiver_id"], body["shift_name"],
         body["starts_at"], body["ends_at"], weekdays,
         body.get("notes")),
    )
    return jsonify({"status": "ok", "id": row["id"] if row else None}), 201


@bp.patch("/api/shifts/<shift_id>")
@require_role("super_admin", "admin_tenant")
def update_shift(shift_id: str):
    """Atualiza plantão. Aceita: starts_at, ends_at, weekdays, active, notes."""
    body = request.get_json(silent=True) or {}
    fields = []
    params: list = []
    for col in ("shift_name", "starts_at", "ends_at",
                "weekdays", "active", "notes"):
        if col in body:
            fields.append(f"{col} = %s")
            params.append(body[col])
    if not fields:
        return jsonify({"status": "error", "reason": "no_fields_to_update"}), 400
    params.append(shift_id)

    db = get_postgres()
    db.execute(
        f"UPDATE aia_health_shift_schedules SET "
        f"{', '.join(fields)} WHERE id = %s",
        tuple(params),
    )
    return jsonify({"status": "ok"})


@bp.delete("/api/shifts/<shift_id>")
@require_role("super_admin", "admin_tenant")
def delete_shift(shift_id: str):
    """Soft delete (active=FALSE)."""
    db = get_postgres()
    db.execute(
        "UPDATE aia_health_shift_schedules SET active = FALSE WHERE id = %s",
        (shift_id,),
    )
    return jsonify({"status": "ok"})


# ════════════════════════════════════════════════════════════════════
# phone_type por cuidador
# ════════════════════════════════════════════════════════════════════

@bp.patch("/api/caregivers/<caregiver_id>/phone-type")
@require_role("super_admin", "admin_tenant")
def set_phone_type(caregiver_id: str):
    """Define se o número é compartilhado (celular do plantão) ou
    pessoal (WhatsApp particular). Decide se biometria é usada nesse
    número.

    Body: { phone_type: 'shared' | 'personal' | 'unknown' }
    """
    body = request.get_json(silent=True) or {}
    new_type = body.get("phone_type")
    if new_type not in ("shared", "personal", "unknown"):
        return jsonify({
            "status": "error", "reason": "invalid_phone_type",
        }), 400

    db = get_postgres()
    db.execute(
        "UPDATE aia_health_caregivers SET phone_type = %s WHERE id = %s",
        (new_type, caregiver_id),
    )
    return jsonify({"status": "ok", "phone_type": new_type})


# ════════════════════════════════════════════════════════════════════
# Estado atual — plantão + cuidadores ativos
# ════════════════════════════════════════════════════════════════════

@bp.get("/api/shifts/current")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def current_shift():
    """Mostra plantão ativo agora + cuidadores no pool atual."""
    from config.settings import settings
    resolver = get_shift_resolver()
    shift = resolver.get_current_shift_name(settings.tenant_id)
    active = resolver.list_active_caregivers(settings.tenant_id)
    overrides = resolver.list_active_overrides(settings.tenant_id)
    return jsonify({
        "status": "ok",
        "tenant_id": settings.tenant_id,
        "current_shift_name": shift,
        "active_caregivers": active,
        "active_overrides": overrides,
        "pool_size": len(active),
    })


# ════════════════════════════════════════════════════════════════════
# Overrides — cobertura temporária de plantão
# ════════════════════════════════════════════════════════════════════

@bp.get("/api/shifts/overrides")
@require_role("super_admin", "admin_tenant", "medico", "enfermeiro")
def list_overrides():
    from config.settings import settings
    return jsonify({
        "status": "ok",
        "overrides": get_shift_resolver().list_active_overrides(
            settings.tenant_id,
        ),
    })


@bp.post("/api/shifts/overrides")
@require_role("super_admin", "admin_tenant")
def create_override():
    """Body: { caregiver_id, shift_name, valid_from, valid_until,
              reason?, created_by? }"""
    from config.settings import settings
    body = request.get_json(silent=True) or {}
    required = ["caregiver_id", "shift_name", "valid_from", "valid_until"]
    if any(not body.get(k) for k in required):
        return jsonify({
            "status": "error", "reason": "missing_fields",
            "required": required,
        }), 400

    result = get_shift_resolver().register_override(
        tenant_id=settings.tenant_id,
        caregiver_id=body["caregiver_id"],
        shift_name=body["shift_name"],
        valid_from=body["valid_from"],
        valid_until=body["valid_until"],
        reason=body.get("reason", "cobertura_temporaria"),
        created_by=body.get("created_by", "admin"),
    )
    return jsonify({"status": "ok", **result}), 201
