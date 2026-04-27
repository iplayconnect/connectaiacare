"""Patient Risk Scoring Engine.

Score 0-100 agregado de 3 sinais determinísticos (Fase 1):
  1. Frequência de queixas registradas últimos 7d
  2. Adesão medicação (% confirmadas vs planejadas) últimos 7d
  3. # de care_events severity≥urgent últimos 7d

Saída: aia_health_patient_risk_score com breakdown JSONB pra UI explicar
"por que esse paciente está em alto risco".

Fase 2 (implementada em risk_baseline.py):
  - Cada paciente tem baseline individual (median + MAD por sinal)
  - Robust z-score detecta desvios mesmo abaixo do threshold absoluto
  - combined_score = max(phase1, phase1 + bonus_deviation)
"""
from __future__ import annotations

import json
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Thresholds e pesos por sinal
COMPLAINTS_THRESHOLDS = [(0, 0), (2, 10), (5, 25), (10, 40)]   # (qtd, score)
URGENT_THRESHOLDS = [(0, 0), (1, 20), (3, 35), (5, 50)]
ADHERENCE_THRESHOLDS = [(80, 0), (60, 10), (40, 25), (20, 40)]  # (pct, score) — abaixo de X = penalidade


def _bucket(value: float, brackets: list[tuple[float, int]]) -> int:
    """Retorna score do maior bracket cujo limite o value supera."""
    matched = 0
    for limit, score in brackets:
        if value >= limit:
            matched = score
        else:
            break
    return matched


def _bucket_inverse(value: float, brackets: list[tuple[float, int]]) -> int:
    """Pra adherence: brackets ordenados por valor decrescente."""
    matched = 0
    for limit, score in brackets:
        if value <= limit:
            matched = score
    return matched


def _level_from_score(score: int) -> str:
    if score >= 76:
        return "critico"
    if score >= 51:
        return "alto"
    if score >= 26:
        return "moderado"
    return "baixo"


def compute_for_patient(patient_id: str, tenant_id: str | None = None) -> dict:
    """Calcula score atual e persiste."""
    db = get_postgres()

    # Busca tenant_id se não fornecido
    if not tenant_id:
        prow = db.fetch_one(
            "SELECT tenant_id FROM aia_health_patients WHERE id = %s",
            (patient_id,),
        )
        if not prow:
            return {"ok": False, "error": "patient_not_found"}
        tenant_id = prow["tenant_id"]

    # Sinal 1: queixas (care_events) últimos 7d (qualquer classification)
    s1 = db.fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_care_events
           WHERE patient_id = %s AND opened_at > NOW() - INTERVAL '7 days'""",
        (patient_id,),
    )
    complaints_7d = int((s1 or {}).get("n") or 0)
    complaints_score = _bucket(complaints_7d, COMPLAINTS_THRESHOLDS)

    # Sinal 2: adesão medicação 7d (status confirmed = tomou)
    s2 = db.fetch_one(
        """SELECT
            COUNT(*) FILTER (WHERE status = 'confirmed') AS confirmed,
            COUNT(*) AS total
           FROM aia_health_medication_events
           WHERE patient_id = %s
             AND scheduled_at > NOW() - INTERVAL '7 days'
             AND scheduled_at < NOW()""",
        (patient_id,),
    )
    confirmed = int((s2 or {}).get("confirmed") or 0)
    total = int((s2 or {}).get("total") or 0)
    adherence_pct = (confirmed / total * 100) if total > 0 else 100
    adherence_score = _bucket_inverse(adherence_pct, ADHERENCE_THRESHOLDS) if total >= 5 else 0

    # Sinal 3: care_events urgent/critical últimos 7d (current_classification)
    s3 = db.fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_care_events
           WHERE patient_id = %s
             AND current_classification IN ('urgent', 'critical')
             AND opened_at > NOW() - INTERVAL '7 days'""",
        (patient_id,),
    )
    urgent_7d = int((s3 or {}).get("n") or 0)
    urgent_score = _bucket(urgent_7d, URGENT_THRESHOLDS)

    # Score agregado (cap 100)
    total_score = min(100, complaints_score + adherence_score + urgent_score)
    level = _level_from_score(total_score)

    # Tendência vs cálculo anterior
    prev = db.fetch_one(
        "SELECT score FROM aia_health_patient_risk_score WHERE patient_id = %s",
        (patient_id,),
    )
    prev_score = int(prev["score"]) if prev else None
    trend = None
    if prev_score is not None:
        delta = total_score - prev_score
        if delta <= -5:
            trend = "improving"
        elif delta >= 5:
            trend = "worsening"
        else:
            trend = "stable"

    # ── Fase 2: baseline individual (se disponível) ──
    from src.services import risk_baseline
    deviation = risk_baseline.compute_deviation_score(
        patient_id,
        current_complaints_7d=complaints_7d,
        current_adherence_pct=adherence_pct,
        current_urgent_7d=urgent_7d,
        current_adherence_total=total,
    )
    combined_score, combined_level = risk_baseline.combine_scores(
        total_score, deviation.get("deviation_score"),
    )

    breakdown = {
        "complaints": {"count_7d": complaints_7d, "score": complaints_score},
        "adherence": {"pct": round(adherence_pct, 1), "events_7d": total, "score": adherence_score},
        "urgent_events": {"count_7d": urgent_7d, "score": urgent_score},
        "phase2_baseline": deviation,
        "phase1_score": total_score,
        "phase1_level": level,
        "combined_score": combined_score,
        "combined_level": combined_level,
    }

    db.execute(
        """INSERT INTO aia_health_patient_risk_score
            (patient_id, tenant_id, score, risk_level,
             signal_complaints_7d, signal_complaints_score,
             signal_adherence_pct, signal_adherence_score,
             signal_urgent_events_7d, signal_urgent_events_score,
             trend, previous_score, breakdown,
             baseline_complaints_z, baseline_adherence_z, baseline_urgent_z,
             baseline_deviation_score, combined_score, combined_level,
             has_baseline, last_computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (patient_id) DO UPDATE SET
            score = EXCLUDED.score,
            risk_level = EXCLUDED.risk_level,
            signal_complaints_7d = EXCLUDED.signal_complaints_7d,
            signal_complaints_score = EXCLUDED.signal_complaints_score,
            signal_adherence_pct = EXCLUDED.signal_adherence_pct,
            signal_adherence_score = EXCLUDED.signal_adherence_score,
            signal_urgent_events_7d = EXCLUDED.signal_urgent_events_7d,
            signal_urgent_events_score = EXCLUDED.signal_urgent_events_score,
            trend = EXCLUDED.trend,
            previous_score = aia_health_patient_risk_score.score,
            breakdown = EXCLUDED.breakdown,
            baseline_complaints_z = EXCLUDED.baseline_complaints_z,
            baseline_adherence_z = EXCLUDED.baseline_adherence_z,
            baseline_urgent_z = EXCLUDED.baseline_urgent_z,
            baseline_deviation_score = EXCLUDED.baseline_deviation_score,
            combined_score = EXCLUDED.combined_score,
            combined_level = EXCLUDED.combined_level,
            has_baseline = EXCLUDED.has_baseline,
            last_computed_at = NOW()""",
        (
            patient_id, tenant_id, total_score, level,
            complaints_7d, complaints_score,
            adherence_pct, adherence_score,
            urgent_7d, urgent_score,
            trend, prev_score,
            json.dumps(breakdown),
            deviation.get("complaints_z"),
            deviation.get("adherence_z"),
            deviation.get("urgent_z"),
            deviation.get("deviation_score"),
            combined_score, combined_level,
            bool(deviation.get("has_baseline")),
        ),
    )
    return {
        "ok": True, "patient_id": patient_id, "score": total_score,
        "risk_level": level, "trend": trend, "breakdown": breakdown,
        "combined_score": combined_score,
        "combined_level": combined_level,
        "deviation": deviation,
    }


def compute_for_all_active(tenant_id: str | None = None) -> dict:
    """Recalcula score pra todos os pacientes ativos do tenant. Idempotente."""
    db = get_postgres()
    where = "active = TRUE"
    params: list = []
    if tenant_id:
        where += " AND tenant_id = %s"
        params.append(tenant_id)
    rows = db.fetch_all(
        f"SELECT id, tenant_id FROM aia_health_patients WHERE {where}",
        tuple(params) if params else (),
    )
    results = {"computed": 0, "errors": 0, "by_level": {"baixo": 0, "moderado": 0, "alto": 0, "critico": 0}}
    for r in rows:
        try:
            out = compute_for_patient(str(r["id"]), r["tenant_id"])
            if out.get("ok"):
                results["computed"] += 1
                results["by_level"][out["risk_level"]] = results["by_level"].get(out["risk_level"], 0) + 1
            else:
                results["errors"] += 1
        except Exception:
            logger.exception("risk_compute_failed patient=%s", r["id"])
            results["errors"] += 1
    return results


def list_high_risk(tenant_id: str, limit: int = 20) -> list[dict]:
    """Lista pacientes em alto risco/crítico pro dashboard."""
    rows = get_postgres().fetch_all(
        """SELECT r.patient_id, r.score, r.risk_level, r.trend, r.breakdown,
                  r.last_computed_at,
                  p.full_name, p.nickname, p.care_unit, p.room_number
           FROM aia_health_patient_risk_score r
           JOIN aia_health_patients p ON p.id = r.patient_id
           WHERE r.tenant_id = %s AND r.risk_level IN ('alto', 'critico')
           ORDER BY r.score DESC LIMIT %s""",
        (tenant_id, limit),
    )
    return rows
