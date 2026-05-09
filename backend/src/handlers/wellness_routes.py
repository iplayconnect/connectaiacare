"""Caregiver wellness — endpoints pro gestor responsável.

Acesso: super_admin, admin_tenant (gestor da unidade), enfermeiro
(coordenador de cuidados).

Eventos de wellness são SEPARADOS do prontuário do paciente — não
viram CareNote no Tecnosenior, não disparam cascata clínica.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from src.handlers.auth_routes import require_role
from src.services.caregiver_wellness_service import get_caregiver_wellness
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("wellness", __name__)


# Acesso: gestores e coordenadores. Operador central também — pra fazer
# acolhimento humano em tempo real quando severity=urgent.
ALLOWED_ROLES = (
    "super_admin", "admin_tenant", "enfermeiro", "operador_central",
)


def _serialize(row: dict | None) -> dict | None:
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


def _user_tenant() -> str | None:
    user = getattr(g, "user", None) or {}
    return user.get("tenant_id")


def _user_id() -> str | None:
    user = getattr(g, "user", None) or {}
    return user.get("sub")


# ════════════════════ LIST / GET ═════════════════════════════════════

@bp.get("/api/admin/wellness/events")
@require_role(*ALLOWED_ROLES)
def list_events():
    """Lista wellness events abertos/em-andamento.

    Query params:
        all_tenants: super_admin pode passar 'true' pra ver cross-tenant
        limit: max 200 (default 50)
    """
    qs = request.args
    user = getattr(g, "user", None) or {}
    role = user.get("role")
    all_tenants = qs.get("all_tenants", "").lower() in ("true", "1", "yes")

    # Scoping: super_admin pode cross-tenant (com flag); demais ficam no
    # próprio tenant.
    if role == "super_admin" and all_tenants:
        tenant_filter = None
    else:
        tenant_filter = _user_tenant()
        if not tenant_filter:
            return jsonify({
                "status": "error", "reason": "no_tenant_in_session",
            }), 403

    limit = max(1, min(int(qs.get("limit") or 50), 200))
    rows = get_caregiver_wellness().list_open(
        tenant_id=tenant_filter, limit=limit,
    )
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "items": [_serialize(r) for r in rows],
    })


@bp.get("/api/admin/wellness/events/<event_id>")
@require_role(*ALLOWED_ROLES)
def get_event(event_id: str):
    row = get_caregiver_wellness().get_event(event_id)
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    # Scoping: super_admin vê tudo; demais só do próprio tenant
    user = getattr(g, "user", None) or {}
    if user.get("role") != "super_admin":
        if row.get("tenant_id") != _user_tenant():
            return jsonify({
                "status": "error", "reason": "forbidden",
            }), 403
    return jsonify({"status": "ok", "event": _serialize(row)})


# ════════════════════ WORKFLOW ═══════════════════════════════════════

@bp.post("/api/admin/wellness/events/<event_id>/acknowledge")
@require_role(*ALLOWED_ROLES)
def acknowledge_event(event_id: str):
    """Gestor reconheceu o evento — vai cuidar. Vira 'acknowledged'."""
    svc = get_caregiver_wellness()
    row = svc.get_event(event_id)
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    user = getattr(g, "user", None) or {}
    if user.get("role") != "super_admin":
        if row.get("tenant_id") != _user_tenant():
            return jsonify({"status": "error", "reason": "forbidden"}), 403

    ok = svc.acknowledge(event_id, user_id=_user_id())
    if not ok:
        return jsonify({"status": "error", "reason": "ack_failed"}), 500
    return jsonify({"status": "ok"})


@bp.post("/api/admin/wellness/events/<event_id>/resolve")
@require_role(*ALLOWED_ROLES)
def resolve_event(event_id: str):
    """Gestor resolveu o caso. Body: {summary?: string}."""
    body = request.get_json(silent=True) or {}
    svc = get_caregiver_wellness()
    row = svc.get_event(event_id)
    if not row:
        return jsonify({"status": "error", "reason": "not_found"}), 404

    user = getattr(g, "user", None) or {}
    if user.get("role") != "super_admin":
        if row.get("tenant_id") != _user_tenant():
            return jsonify({"status": "error", "reason": "forbidden"}), 403

    ok = svc.resolve(event_id, user_id=_user_id(), summary=body.get("summary"))
    if not ok:
        return jsonify({"status": "error", "reason": "resolve_failed"}), 500
    return jsonify({"status": "ok"})


# ════════════════════ STATS ══════════════════════════════════════════

@bp.get("/api/admin/wellness/stats")
@require_role(*ALLOWED_ROLES)
def stats():
    """Stats agregadas — pra dashboard de gestor."""
    from src.services.postgres import get_postgres
    db = get_postgres()
    user = getattr(g, "user", None) or {}
    role = user.get("role")

    where = []
    params: list = []
    if role != "super_admin":
        where.append("tenant_id = %s")
        params.append(_user_tenant())
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    totals = db.fetch_one(
        f"""SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'open') AS open,
                   COUNT(*) FILTER (WHERE status = 'acknowledged') AS acknowledged,
                   COUNT(*) FILTER (WHERE status = 'resolved') AS resolved,
                   COUNT(*) FILTER (WHERE severity IN ('urgent', 'critical')
                                      AND status IN ('open', 'acknowledged'))
                       AS urgent_open,
                   COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days')
                       AS last_30d
            FROM aia_health_caregiver_wellness_events
            {where_sql}""",
        tuple(params),
    ) or {}

    by_severity = db.fetch_all(
        f"""SELECT severity, COUNT(*) AS n
            FROM aia_health_caregiver_wellness_events
            {where_sql}
            GROUP BY severity""",
        tuple(params),
    )

    by_caregiver = db.fetch_all(
        f"""SELECT c.id::text AS caregiver_id, c.full_name,
                   COUNT(w.id) AS event_count,
                   MAX(w.created_at) AS last_event_at
            FROM aia_health_caregiver_wellness_events w
            LEFT JOIN aia_health_caregivers c ON c.id = w.caregiver_id
            {where_sql.replace('tenant_id', 'w.tenant_id') if where_sql else ''}
            GROUP BY c.id, c.full_name
            HAVING COUNT(w.id) > 1
            ORDER BY event_count DESC, last_event_at DESC
            LIMIT 20""",
        tuple(params),
    )

    return jsonify({
        "status": "ok",
        "totals": {k: int(v or 0) for k, v in totals.items()},
        "by_severity": {r["severity"]: int(r["n"]) for r in by_severity},
        "top_caregivers_recurring": [
            {
                "caregiver_id": r.get("caregiver_id"),
                "full_name": r.get("full_name"),
                "event_count": int(r["event_count"]),
                "last_event_at": (
                    r["last_event_at"].isoformat()
                    if r.get("last_event_at") else None
                ),
            }
            for r in by_caregiver
        ],
    })
