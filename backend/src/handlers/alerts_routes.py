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

from flask import Blueprint, jsonify

from config.settings import settings
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

bp = Blueprint("alerts", __name__)


@bp.get("/alerts")
def list_alerts():
    """Lista alertas derivados de care_events ativos + reports críticos recentes.

    Ordenação: severidade desc, recência desc.
    Inclui áudio url quando disponível.
    """
    db = get_postgres()
    tenant_id = settings.tenant_id

    # Care events ativos (abertos) ou resolvidos nas últimas 48h
    rows = db.fetch_all(
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
            ce.caregiver_phone,
            ce.context,
            ce.initial_report_id,
            r.id AS report_id,
            r.audio_url,
            r.audio_duration_seconds,
            r.transcription,
            r.analysis,
            r.received_at AS report_received_at,
            p.id AS patient_id,
            p.full_name AS patient_name,
            p.nickname AS patient_nickname,
            p.birth_date AS patient_birth_date,
            p.care_unit AS patient_unit,
            p.room_number AS patient_room,
            p.responsible AS patient_responsible
        FROM aia_health_care_events ce
        LEFT JOIN aia_health_reports r ON r.id = ce.initial_report_id
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

    alerts = [_shape_alert(r) for r in rows]
    logger.info("alerts_list_served", count=len(alerts), tenant_id=tenant_id)

    return jsonify({"alerts": alerts, "total": len(alerts)}), 200


# ══════════════════════════════════════════════════════════════════
# Shape transformer
# ══════════════════════════════════════════════════════════════════

def _shape_alert(row: dict) -> dict:
    """Transforma row do care_events+reports+patients no shape ClinicalAlert."""
    now = datetime.now(timezone.utc)
    opened = row.get("opened_at")
    minutes_ago = 0
    if opened:
        if isinstance(opened, datetime):
            delta = now - (opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc))
            minutes_ago = max(0, int(delta.total_seconds() / 60))

    analysis = row.get("analysis") or {}

    # Extrai family_contact do responsible (schema JSONB)
    responsible = row.get("patient_responsible") or {}
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
        row.get("current_classification")
        or row.get("initial_classification")
        or "attention"
    )

    patient_age = _calc_age(row.get("patient_birth_date"))

    return {
        "id": f"ce-{row.get('event_id')}",
        "classification": classification,
        "patient": {
            "id": str(row.get("patient_id") or ""),
            "name": row.get("patient_name") or "Paciente desconhecido",
            "age": patient_age or 0,
            "unit": row.get("patient_unit") or "",
            "ward": row.get("patient_unit") or "",
            "room": row.get("patient_room") or "",
            "seed": _seed_from_name(row.get("patient_name") or ""),
            "family_contact": family_contact,
        },
        "report_id": str(row.get("report_id")) if row.get("report_id") else None,
        "excerpt": (
            row.get("summary")
            or (analysis.get("summary") if isinstance(analysis, dict) else None)
            or (row.get("transcription") or "")[:200]
            or "Relato em análise..."
        ),
        "ai_reason": (
            analysis.get("classification_reasoning")
            if isinstance(analysis, dict)
            else None
        ),
        "created_at": opened.isoformat() if isinstance(opened, datetime) else None,
        "minutes_ago": minutes_ago,
        "acknowledged_at": None,  # care_events não tem ACK separado ainda
        "acknowledged_by": None,
        "escalated_to": None,
        "call_state": None,
        "vitals_snapshot": _extract_vitals_from_analysis(analysis),
        "audio_url": row.get("audio_url"),
        "audio_duration_seconds": row.get("audio_duration_seconds"),
        "transcription": row.get("transcription"),
        # Metadata extra pra debug
        "event_status": row.get("status"),
        "event_human_id": row.get("human_id"),
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
