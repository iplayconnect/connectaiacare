"""Risk Baseline (Fase 2) — baseline individual por paciente.

Fase 1 (risk_scoring.py) usa thresholds absolutos. Fase 2 adiciona dimensão
de desvio individual: cada paciente comparado com seu próprio padrão
histórico.

Estatística usada: **median + MAD (Median Absolute Deviation)** — robusto
a outliers e funciona bem com N pequeno (4-12 semanas).

Robust z-score:
    z = (current - median) / (1.4826 * MAD)

Onde 1.4826 = 1/Φ⁻¹(0.75), o fator que torna MAD comparável ao stddev
sob distribuição normal.

Combinação Fase 1 + Fase 2:
    combined_score = max(phase1, phase1 + bonus)
    onde bonus vem de desvios individuais altos (z >= 2 em qualquer dim).
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Janela observada pra computar baseline
DEFAULT_PERIOD_DAYS = 60
WEEK_DAYS = 7

# Mínimo de semanas com dados pra considerar baseline confiável
MIN_WEEKS_FOR_BASELINE = 4

# z-score acima do qual flagamos desvio significativo
Z_SIGNIFICANT = 2.0
Z_STRONG = 3.0

# Fator de Bessel correction pra MAD virar comparable a stddev
MAD_TO_STDDEV = 1.4826


# ────────────────────────────────────────────────────────────────────
# Estatística robusta
# ────────────────────────────────────────────────────────────────────

def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _mad(values: list[float], median: float) -> float:
    """Median Absolute Deviation. Sempre >= 0."""
    if not values:
        return 0.0
    deviations = [abs(v - median) for v in values]
    return float(statistics.median(deviations))


def _robust_z(current: float, median: float | None, mad: float) -> float | None:
    """Robust z-score. None se MAD == 0 e current == median (sem variação)."""
    if median is None:
        return None
    if mad <= 1e-9:
        # Distribuição com variância zero: se current = median, z = 0;
        # se diferente, comportamento ambíguo. Convencionamos:
        if abs(current - median) < 1e-9:
            return 0.0
        # current diferiu de constante histórica → desvio máximo flag
        return 5.0 if current > median else -5.0
    return (current - median) / (MAD_TO_STDDEV * mad)


# ────────────────────────────────────────────────────────────────────
# Coleta de aggregations semanais
# ────────────────────────────────────────────────────────────────────

def _weekly_complaints(patient_id: str, period_days: int) -> list[float]:
    """Retorna lista de contagens semanais de queixas (care_events)
    no período. Cada item = 1 semana, da mais antiga pra mais recente."""
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT
            FLOOR(EXTRACT(EPOCH FROM (NOW() - opened_at)) / 604800) AS week_idx,
            COUNT(*) AS n
           FROM aia_health_care_events
           WHERE patient_id = %s
             AND opened_at > NOW() - INTERVAL '%s days'
             AND opened_at <= NOW() - INTERVAL '7 days'
           GROUP BY week_idx
           ORDER BY week_idx""",
        (patient_id, period_days),
    )
    # Constroe lista por week_idx — preenche zeros pra semanas sem queixa
    by_week: dict[int, int] = {}
    for r in rows or []:
        by_week[int(r["week_idx"])] = int(r["n"])
    weeks_in_period = max(1, period_days // WEEK_DAYS - 1)  # exclui semana atual
    return [float(by_week.get(i, 0)) for i in range(1, weeks_in_period + 1)]


def _weekly_adherence(patient_id: str, period_days: int) -> list[float]:
    """Retorna lista de adesão % por semana (cada semana com >= 5 eventos).
    Semanas com poucos eventos são excluídas — não geram baseline.
    """
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT
            FLOOR(EXTRACT(EPOCH FROM (NOW() - scheduled_at)) / 604800) AS week_idx,
            COUNT(*) FILTER (WHERE status = 'confirmed') AS confirmed,
            COUNT(*) AS total
           FROM aia_health_medication_events
           WHERE patient_id = %s
             AND scheduled_at > NOW() - INTERVAL '%s days'
             AND scheduled_at <= NOW() - INTERVAL '7 days'
           GROUP BY week_idx
           HAVING COUNT(*) >= 5
           ORDER BY week_idx""",
        (patient_id, period_days),
    )
    return [
        float(int(r["confirmed"]) / int(r["total"]) * 100)
        for r in (rows or [])
    ]


def _weekly_urgent_events(patient_id: str, period_days: int) -> list[float]:
    """Eventos urgent/critical por semana."""
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT
            FLOOR(EXTRACT(EPOCH FROM (NOW() - opened_at)) / 604800) AS week_idx,
            COUNT(*) AS n
           FROM aia_health_care_events
           WHERE patient_id = %s
             AND current_classification IN ('urgent', 'critical')
             AND opened_at > NOW() - INTERVAL '%s days'
             AND opened_at <= NOW() - INTERVAL '7 days'
           GROUP BY week_idx
           ORDER BY week_idx""",
        (patient_id, period_days),
    )
    by_week: dict[int, int] = {}
    for r in rows or []:
        by_week[int(r["week_idx"])] = int(r["n"])
    weeks_in_period = max(1, period_days // WEEK_DAYS - 1)
    return [float(by_week.get(i, 0)) for i in range(1, weeks_in_period + 1)]


# ────────────────────────────────────────────────────────────────────
# Compute baseline pra um paciente
# ────────────────────────────────────────────────────────────────────

def compute_baseline(patient_id: str, period_days: int = DEFAULT_PERIOD_DAYS) -> dict:
    """Computa e persiste baseline. Retorna o resultado."""
    db = get_postgres()

    prow = db.fetch_one(
        "SELECT id, tenant_id FROM aia_health_patients WHERE id = %s",
        (patient_id,),
    )
    if not prow:
        return {"ok": False, "error": "patient_not_found"}
    tenant_id = prow["tenant_id"]

    complaints = _weekly_complaints(patient_id, period_days)
    adherence = _weekly_adherence(patient_id, period_days)
    urgent = _weekly_urgent_events(patient_id, period_days)

    # Filtra histórico que tem dados — semanas vazias contam pra complaints/urgent
    # (zero é dado válido), mas adherence só conta semanas com prescrição
    complaints_n = sum(1 for x in complaints if x is not None)
    adherence_n = len(adherence)
    urgent_n = sum(1 for x in urgent if x is not None)

    has_sufficient = (
        complaints_n >= MIN_WEEKS_FOR_BASELINE
        or adherence_n >= MIN_WEEKS_FOR_BASELINE
        or urgent_n >= MIN_WEEKS_FOR_BASELINE
    )

    insufficient_reason = None
    if not has_sufficient:
        insufficient_reason = (
            f"need_{MIN_WEEKS_FOR_BASELINE}_weeks: "
            f"complaints={complaints_n} adherence={adherence_n} urgent={urgent_n}"
        )

    cm = _median(complaints) if complaints_n >= MIN_WEEKS_FOR_BASELINE else None
    cmad = _mad(complaints, cm) if cm is not None else None
    am = _median(adherence) if adherence_n >= MIN_WEEKS_FOR_BASELINE else None
    amad = _mad(adherence, am) if am is not None else None
    um = _median(urgent) if urgent_n >= MIN_WEEKS_FOR_BASELINE else None
    umad = _mad(urgent, um) if um is not None else None

    weeks_observed = max(complaints_n, adherence_n, urgent_n)

    db.execute(
        """INSERT INTO aia_health_patient_baselines
            (patient_id, tenant_id, period_days, weeks_observed,
             complaints_median, complaints_mad, complaints_history,
             adherence_median, adherence_mad, adherence_history,
             urgent_median, urgent_mad, urgent_history,
             has_sufficient_data, insufficient_reason, last_computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb,
                %s, %s, %s::jsonb, %s, %s, %s::jsonb,
                %s, %s, NOW())
        ON CONFLICT (patient_id) DO UPDATE SET
            tenant_id = EXCLUDED.tenant_id,
            period_days = EXCLUDED.period_days,
            weeks_observed = EXCLUDED.weeks_observed,
            complaints_median = EXCLUDED.complaints_median,
            complaints_mad = EXCLUDED.complaints_mad,
            complaints_history = EXCLUDED.complaints_history,
            adherence_median = EXCLUDED.adherence_median,
            adherence_mad = EXCLUDED.adherence_mad,
            adherence_history = EXCLUDED.adherence_history,
            urgent_median = EXCLUDED.urgent_median,
            urgent_mad = EXCLUDED.urgent_mad,
            urgent_history = EXCLUDED.urgent_history,
            has_sufficient_data = EXCLUDED.has_sufficient_data,
            insufficient_reason = EXCLUDED.insufficient_reason,
            last_computed_at = NOW()""",
        (
            patient_id, tenant_id, period_days, weeks_observed,
            cm, cmad, json.dumps(complaints),
            am, amad, json.dumps(adherence),
            um, umad, json.dumps(urgent),
            has_sufficient, insufficient_reason,
        ),
    )

    return {
        "ok": True, "patient_id": patient_id,
        "weeks_observed": weeks_observed,
        "has_sufficient_data": has_sufficient,
        "insufficient_reason": insufficient_reason,
        "complaints": {"median": cm, "mad": cmad, "n": complaints_n},
        "adherence": {"median": am, "mad": amad, "n": adherence_n},
        "urgent": {"median": um, "mad": umad, "n": urgent_n},
    }


# ────────────────────────────────────────────────────────────────────
# Compute deviation score pra um paciente (com baseline já computado)
# ────────────────────────────────────────────────────────────────────

def compute_deviation_score(
    patient_id: str,
    *,
    current_complaints_7d: int,
    current_adherence_pct: float,
    current_urgent_7d: int,
    current_adherence_total: int,
) -> dict:
    """Calcula desvios individuais e score 0-100 derivado.

    Inputs são os mesmos que risk_scoring.compute_for_patient já calcula
    — passa pra cá pra evitar duplicar query.
    """
    db = get_postgres()
    base = db.fetch_one(
        """SELECT complaints_median, complaints_mad,
                  adherence_median, adherence_mad,
                  urgent_median, urgent_mad,
                  has_sufficient_data, weeks_observed
           FROM aia_health_patient_baselines
           WHERE patient_id = %s""",
        (patient_id,),
    )

    if not base or not base.get("has_sufficient_data"):
        return {
            "has_baseline": False,
            "complaints_z": None,
            "adherence_z": None,
            "urgent_z": None,
            "deviation_score": None,
            "weeks_observed": (base or {}).get("weeks_observed", 0),
        }

    # complaints: positivo = piorou
    cz = _robust_z(
        float(current_complaints_7d),
        float(base["complaints_median"]) if base.get("complaints_median") is not None else None,
        float(base["complaints_mad"]) if base.get("complaints_mad") is not None else 0,
    )

    # adherence: NEGATIVO = piorou (paciente caiu vs próprio padrão)
    az = None
    if current_adherence_total >= 5:
        az = _robust_z(
            float(current_adherence_pct),
            float(base["adherence_median"]) if base.get("adherence_median") is not None else None,
            float(base["adherence_mad"]) if base.get("adherence_mad") is not None else 0,
        )

    # urgent: positivo = piorou
    uz = _robust_z(
        float(current_urgent_7d),
        float(base["urgent_median"]) if base.get("urgent_median") is not None else None,
        float(base["urgent_mad"]) if base.get("urgent_mad") is not None else 0,
    )

    # Score 0-100 a partir dos z scores
    # complaints e urgent: bonus apenas se z > 0 (piorou); cap em 5σ
    # adherence: bonus apenas se z < 0 (piorou); cap em -5σ
    score = 0.0
    if cz is not None:
        score += max(0.0, min(cz, 5.0)) * 10  # max 50
    if uz is not None:
        score += max(0.0, min(uz, 5.0)) * 12  # max 60
    if az is not None:
        score += max(0.0, min(-az, 5.0)) * 10  # max 50
    score = min(100.0, score)

    return {
        "has_baseline": True,
        "complaints_z": round(cz, 2) if cz is not None else None,
        "adherence_z": round(az, 2) if az is not None else None,
        "urgent_z": round(uz, 2) if uz is not None else None,
        "deviation_score": int(round(score)),
        "weeks_observed": int(base.get("weeks_observed") or 0),
    }


# ────────────────────────────────────────────────────────────────────
# Combinação Fase 1 + Fase 2
# ────────────────────────────────────────────────────────────────────

def combine_scores(phase1_score: int, deviation_score: int | None) -> tuple[int, str]:
    """Combina score absoluto (Fase 1) com bônus do desvio individual.

    Regra:
    - Floor objetivo: phase1_score (Fase 1 nunca decresce o resultado)
    - Bônus: 50% do deviation_score quando paciente desviou MUITO
      (evita dobrar punição quando os dois sinais concordam)
    - Cap em 100
    """
    if deviation_score is None:
        return phase1_score, _level_from_score(phase1_score)
    bonus = int(deviation_score * 0.5)
    combined = min(100, phase1_score + bonus)
    return combined, _level_from_score(combined)


def _level_from_score(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 30:
        return "moderate"
    return "low"


# ────────────────────────────────────────────────────────────────────
# Helpers expostos
# ────────────────────────────────────────────────────────────────────

def get_baseline(patient_id: str) -> dict | None:
    db = get_postgres()
    row = db.fetch_one(
        "SELECT * FROM aia_health_patient_baselines WHERE patient_id = %s",
        (patient_id,),
    )
    if not row:
        return None
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def compute_baseline_for_all_active(tenant_id: str | None = None) -> dict:
    """Recomputa baseline pra todos os pacientes ativos."""
    db = get_postgres()
    where = "active = TRUE"
    params: list = []
    if tenant_id:
        where += " AND tenant_id = %s"
        params.append(tenant_id)
    rows = db.fetch_all(
        f"SELECT id FROM aia_health_patients WHERE {where}", tuple(params),
    )
    n = 0
    sufficient = 0
    for r in rows or []:
        try:
            res = compute_baseline(str(r["id"]))
            n += 1
            if res.get("has_sufficient_data"):
                sufficient += 1
        except Exception:
            logger.exception("baseline_compute_failed pid=%s", r.get("id"))
    return {
        "ok": True, "processed": n,
        "with_sufficient_data": sufficient,
    }
