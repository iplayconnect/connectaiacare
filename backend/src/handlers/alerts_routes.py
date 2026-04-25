"""Handler /api/alerts — derivado de care_events + reports.

Estratégia: em vez de uma tabela separada de alertas, derivamos em tempo real
dos care_events ativos/recentes + report mais recente. Cada care_event em
status ativo (não resolved/expired) vira um alerta. Reports críticos sem
care_event também contam.

Schema shape do frontend (hooks/use-alerts.ts ClinicalAlert):
    id, classification, patient {id,name,age,unit,ward,room,seed,family_contact},
    report_id, excerpt, ai_reason, created_at, minutes_ago,
    acknowledged_at, acknowledged_by, escalated_to, call_state,
    vitals_snapshot, audio_url, transcription
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from config.settings import settings
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("alerts", __name__)


@bp.get("/alerts/clinical")
def list_clinical_alerts():
    """Alertas escritos em aia_health_alerts pelo motor de cruzamentos
    (dose validator) + outras fontes. Diferente de /alerts (care_events).

    Query params:
      level: low|medium|high|critical (multi via vírgula)
      status: open|acknowledged|resolved|active (default)|all
      kind: dose_validation
      limit: default 100
    """
    db = get_postgres()
    tenant_id = settings.tenant_id
    args = request.args

    levels = [s.strip() for s in (args.get("level") or "").split(",") if s.strip()]
    status_param = args.get("status") or "active"
    kind = args.get("kind")
    limit = max(1, min(int(args.get("limit") or 100), 500))

    where_parts = ["a.tenant_id = %s"]
    params: list = [tenant_id]

    if levels:
        placeholders = ",".join(["%s"] * len(levels))
        where_parts.append(f"a.level IN ({placeholders})")
        params.extend(levels)

    if status_param == "open":
        where_parts.append("a.acknowledged_at IS NULL AND a.resolved_at IS NULL")
    elif status_param == "acknowledged":
        where_parts.append("a.acknowledged_at IS NOT NULL AND a.resolved_at IS NULL")
    elif status_param == "resolved":
        where_parts.append("a.resolved_at IS NOT NULL")
    elif status_param == "active":
        where_parts.append("a.resolved_at IS NULL")
    # status=all → sem filtro

    if kind == "dose_validation":
        where_parts.append("a.metadata ? 'validation'")

    where_sql = " AND ".join(where_parts)
    rows = db.fetch_all(
        f"""
        SELECT a.id, a.level, a.title, a.description,
               a.recommended_actions, a.acknowledged_by, a.acknowledged_at,
               a.resolved_at, a.metadata, a.created_at, a.patient_id,
               p.full_name AS patient_name, p.nickname AS patient_nickname,
               p.care_unit AS patient_unit, p.room_number AS patient_room
        FROM aia_health_alerts a
        LEFT JOIN aia_health_patients p ON p.id = a.patient_id
        WHERE {where_sql}
        ORDER BY
            CASE a.level
                WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                WHEN 'medium' THEN 2 ELSE 3 END,
            a.created_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    out = []
    for r in rows:
        meta = r.get("metadata") or {}
        validation = meta.get("validation")
        kinds: set[str] = set()
        if validation:
            kinds.add("dose_validation")
            for issue in (validation.get("issues") or []):
                if issue.get("code"):
                    kinds.add(issue["code"])
        status_str = (
            "resolved" if r.get("resolved_at")
            else "acknowledged" if r.get("acknowledged_at")
            else "open"
        )
        out.append({
            "id": str(r["id"]),
            "level": r["level"],
            "title": r["title"],
            "description": r.get("description"),
            "recommended_actions": r.get("recommended_actions") or [],
            "status": status_str,
            "acknowledged_by": r.get("acknowledged_by"),
            "acknowledged_at": r["acknowledged_at"].isoformat() if r.get("acknowledged_at") else None,
            "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "patient_id": str(r["patient_id"]) if r.get("patient_id") else None,
            "patient_name": r.get("patient_name"),
            "patient_nickname": r.get("patient_nickname"),
            "patient_unit": r.get("patient_unit"),
            "patient_room": r.get("patient_room"),
            "kinds": sorted(kinds),
            "validation": validation,
        })
    return jsonify({"status": "ok", "alerts": out, "count": len(out)})


@bp.post("/alerts/<alert_id>/acknowledge")
def acknowledge_alert(alert_id: str):
    body = request.get_json(silent=True) or {}
    by = body.get("by") or "admin"
    get_postgres().execute(
        "UPDATE aia_health_alerts SET acknowledged_by = %s, acknowledged_at = NOW() "
        "WHERE id = %s AND acknowledged_at IS NULL",
        (by, alert_id),
    )
    return jsonify({"status": "ok"})


@bp.post("/alerts/<alert_id>/resolve")
def resolve_alert(alert_id: str):
    get_postgres().execute(
        "UPDATE aia_health_alerts SET resolved_at = NOW() WHERE id = %s AND resolved_at IS NULL",
        (alert_id,),
    )
    return jsonify({"status": "ok"})


@bp.get("/alerts")
def list_alerts():
    """Lista alertas derivados de care_events ativos + reports críticos recentes.

    Ordenação: severidade desc, recência desc.
    Inclui áudio url quando disponível.
    """
    db = get_postgres()
    tenant_id = settings.tenant_id

    # Care events ativos (abertos) ou resolvidos nas últimas 48h
    events = db.fetch_all(
        """
        SELECT
            ce.id AS event_id,
            ce.human_id,
            ce.current_classification,
            ce.initial_classification,
            ce.event_type,
            ce.status,
            ce.summary,
            ce.opened_at,
            ce.resolved_at,
            ce.closed_reason,
            ce.caregiver_phone,
            ce.context,
            ce.initial_report_id,
            p.id AS patient_id,
            p.full_name AS patient_name,
            p.nickname AS patient_nickname,
            p.birth_date AS patient_birth_date,
            p.care_unit AS patient_unit,
            p.room_number AS patient_room,
            p.responsible AS patient_responsible
        FROM aia_health_care_events ce
        LEFT JOIN aia_health_patients p ON p.id = ce.patient_id
        WHERE ce.tenant_id = %s
          AND (
            ce.status NOT IN ('resolved', 'expired')
            OR ce.resolved_at > NOW() - INTERVAL '48 hours'
          )
        ORDER BY
            CASE ce.current_classification
                WHEN 'critical' THEN 0
                WHEN 'urgent'   THEN 1
                WHEN 'attention' THEN 2
                WHEN 'routine'  THEN 3
                ELSE 4
            END,
            ce.opened_at DESC
        LIMIT 30
        """,
        (tenant_id,),
    )

    # Busca TODOS reports ligados aos care_events desta lista (pra timeline/áudios)
    event_ids = [str(e["event_id"]) for e in events if e.get("event_id")]
    reports_by_event: dict[str, list[dict]] = {}
    if event_ids:
        reports_rows = db.fetch_all(
            """
            SELECT
                id, care_event_id, audio_url, audio_duration_seconds,
                transcription, classification, analysis, received_at,
                caregiver_name_claimed
            FROM aia_health_reports
            WHERE care_event_id = ANY(%s::uuid[])
            ORDER BY received_at ASC
            """,
            (event_ids,),
        )
        for r in reports_rows:
            ev_id = str(r["care_event_id"])
            reports_by_event.setdefault(ev_id, []).append(r)

    alerts = [_shape_alert(e, reports_by_event.get(str(e["event_id"]), [])) for e in events]
    logger.info("alerts_list_served", count=len(alerts), tenant_id=tenant_id)

    return jsonify({"alerts": alerts, "total": len(alerts)}), 200


# ══════════════════════════════════════════════════════════════════
# Shape transformer
# ══════════════════════════════════════════════════════════════════

def _shape_alert(event: dict, reports: list[dict]) -> dict:
    """Transforma care_event + reports + patient no shape ClinicalAlert.

    `reports` é a lista de TODOS os reports ligados ao care_event (ordenados
    cronologicamente), não só o inicial. Cada um com audio_url próprio.
    """
    now = datetime.now(timezone.utc)
    opened = event.get("opened_at")
    minutes_ago = 0
    if opened and isinstance(opened, datetime):
        delta = now - (opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc))
        minutes_ago = max(0, int(delta.total_seconds() / 60))

    # Report mais recente (pra excerpt + ai_reason) OU inicial como fallback
    primary = reports[-1] if reports else None
    initial = reports[0] if reports else None
    analysis = (primary or {}).get("analysis") or {}

    # Extrai family_contact do responsible (schema JSONB)
    responsible = event.get("patient_responsible") or {}
    family_contact = None
    if isinstance(responsible, dict):
        name = responsible.get("name")
        phone = responsible.get("phone")
        if name and phone:
            family_contact = {
                "name": name,
                "relationship": responsible.get("relationship") or "familiar",
                "phone": "".join(ch for ch in phone if ch.isdigit()) or phone,
            }

    classification = (
        event.get("current_classification")
        or event.get("initial_classification")
        or "attention"
    )

    patient_age = _calc_age(event.get("patient_birth_date"))

    # Shape histórico (todos os reports em ordem)
    history = [
        {
            "report_id": str(r.get("id")),
            "received_at": r.get("received_at").isoformat()
            if isinstance(r.get("received_at"), datetime)
            else r.get("received_at"),
            "caregiver_name": r.get("caregiver_name_claimed"),
            "classification": r.get("classification"),
            "audio_url": r.get("audio_url"),
            "audio_duration_seconds": r.get("audio_duration_seconds"),
            "transcription": r.get("transcription"),
            "analysis_summary": (r.get("analysis") or {}).get("summary")
            if isinstance(r.get("analysis"), dict)
            else None,
        }
        for r in reports
    ]

    # Áudio + transcrição primária = do PRIMEIRO relato (inicial) pra retrocompat
    # (se quiser mudar pra mais recente, basta trocar initial → primary)
    return {
        "id": f"ce-{event.get('event_id')}",
        "classification": classification,
        "patient": {
            "id": str(event.get("patient_id") or ""),
            "name": event.get("patient_name") or "Paciente desconhecido",
            "age": patient_age or 0,
            "unit": event.get("patient_unit") or "",
            "ward": event.get("patient_unit") or "",
            "room": event.get("patient_room") or "",
            "seed": _seed_from_name(event.get("patient_name") or ""),
            "family_contact": family_contact,
        },
        "report_id": str(initial.get("id")) if initial else None,
        "excerpt": (
            event.get("summary")
            or (analysis.get("summary") if isinstance(analysis, dict) else None)
            or ((primary or {}).get("transcription") or "")[:200]
            or "Relato em análise..."
        ),
        "ai_reason": (
            analysis.get("classification_reasoning")
            if isinstance(analysis, dict)
            else None
        ),
        "created_at": opened.isoformat() if isinstance(opened, datetime) else None,
        "minutes_ago": minutes_ago,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "escalated_to": None,
        "call_state": None,
        "vitals_snapshot": _extract_vitals_from_analysis(analysis),
        # Campos "primários" (retrocompat com código existente)
        "audio_url": (initial or {}).get("audio_url"),
        "audio_duration_seconds": (initial or {}).get("audio_duration_seconds"),
        "transcription": (initial or {}).get("transcription"),
        # Histórico COMPLETO — todos os reports ligados ao care_event
        "history": history,
        "reports_count": len(reports),
        # Metadata extra
        "event_status": event.get("status"),
        "event_human_id": event.get("human_id"),
        "closed_reason": event.get("closed_reason"),
    }


def _calc_age(birth_date: Any) -> int | None:
    if not birth_date:
        return None
    try:
        if isinstance(birth_date, str):
            bd = datetime.strptime(birth_date.split("T")[0], "%Y-%m-%d").date()
        else:
            bd = birth_date
        today = datetime.now().date()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None


def _seed_from_name(name: str) -> int:
    """Hash estável pra avatar."""
    if not name:
        return 0
    return sum(ord(c) for c in name) % 6


def _extract_vitals_from_analysis(analysis: Any) -> dict | None:
    """Extrai snapshot de vitais da análise se disponível."""
    if not isinstance(analysis, dict):
        return None
    vitals = analysis.get("vital_signs") or {}
    if not isinstance(vitals, dict):
        return None
    out: dict = {}
    if "blood_pressure" in vitals:
        out["bp"] = vitals["blood_pressure"]
    if "heart_rate" in vitals:
        out["hr"] = vitals["heart_rate"]
    if "oxygen_saturation" in vitals:
        out["spo2"] = vitals["oxygen_saturation"]
    if "temperature" in vitals:
        out["temp"] = vitals["temperature"]
    return out if out else None
