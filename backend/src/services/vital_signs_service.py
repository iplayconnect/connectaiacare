"""Serviço de sinais vitais / aferições.

Suporta:
- Leitura de histórico com filtro por tipo, janela temporal
- Última medição por tipo (para header cards do prontuário)
- Classificação automática baseada nas ranges (populacional ou por paciente)
- Preparação para integração MedMonitor (Fase 2 MONITOR)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


VITAL_TYPES = {
    "blood_pressure_composite",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "heart_rate",
    "temperature",
    "oxygen_saturation",
    "blood_glucose",
    "respiratory_rate",
    "weight",
}


# Unidades padrão por tipo
DEFAULT_UNITS = {
    "blood_pressure_systolic": "mmHg",
    "blood_pressure_diastolic": "mmHg",
    "blood_pressure_composite": "mmHg",
    "heart_rate": "bpm",
    "temperature": "celsius",
    "oxygen_saturation": "percent",
    "blood_glucose": "mg/dl",
    "respiratory_rate": "rpm",
    "weight": "kg",
}


# Labels em pt-BR (para UI e prompt da IA)
VITAL_LABELS_PT = {
    "blood_pressure_composite": "Pressão arterial",
    "blood_pressure_systolic": "Pressão sistólica",
    "blood_pressure_diastolic": "Pressão diastólica",
    "heart_rate": "Frequência cardíaca",
    "temperature": "Temperatura",
    "oxygen_saturation": "Saturação O₂ (SpO₂)",
    "blood_glucose": "Glicemia",
    "respiratory_rate": "Frequência respiratória",
    "weight": "Peso",
}


class VitalSignsService:
    def __init__(self):
        self.db = get_postgres()

    # ──────────────────────────────────────────────────────────────
    # Leitura
    # ──────────────────────────────────────────────────────────────

    def list_by_patient(
        self,
        patient_id: str,
        vital_type: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Lista medições de um paciente com filtros opcionais."""
        where = ["patient_id = %s"]
        params: list[Any] = [patient_id]

        if vital_type:
            where.append("vital_type = %s")
            params.append(vital_type)
        if since:
            where.append("measured_at >= %s")
            params.append(since)

        params.append(limit)

        query = f"""
            SELECT id, patient_id, vital_type, value_numeric, value_secondary,
                   unit, status, source, device_id, measured_by, notes,
                   loinc_code, measured_at, received_at
            FROM aia_health_vital_signs
            WHERE {' AND '.join(where)}
            ORDER BY measured_at DESC
            LIMIT %s
        """
        return self.db.fetch_all(query, tuple(params))

    def last_by_type(self, patient_id: str) -> dict[str, dict | None]:
        """Retorna a última medição de cada tipo para um paciente.

        Usado no "header cards" do prontuário ("PA · 128/82 · hoje 08:00").
        """
        rows = self.db.fetch_all(
            """
            SELECT DISTINCT ON (vital_type)
                vital_type, value_numeric, value_secondary, unit, status,
                measured_at, source
            FROM aia_health_vital_signs
            WHERE patient_id = %s
            ORDER BY vital_type, measured_at DESC
            """,
            (patient_id,),
        )
        result: dict[str, dict | None] = {vt: None for vt in VITAL_TYPES}
        for r in rows:
            result[r["vital_type"]] = r
        return result

    def timeseries(
        self,
        patient_id: str,
        vital_type: str,
        days: int = 7,
    ) -> list[dict]:
        """Série temporal para gráfico sparkline (últimos N dias)."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return self.list_by_patient(patient_id, vital_type=vital_type, since=since, limit=1000)

    def summary_for_prontuario(self, patient_id: str) -> dict[str, Any]:
        """Sumário pronto para o Prontuário longitudinal.

        Retorna:
            {
                "last_readings": { vital_type: {value, status, measured_at, trend} },
                "alerts_24h": int,
                "total_measurements_7d": int,
            }
        """
        last = self.last_by_type(patient_id)

        alerts_row = self.db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM aia_health_vital_signs
            WHERE patient_id = %s
              AND measured_at >= NOW() - INTERVAL '24 hours'
              AND status IN ('urgent', 'critical')
            """,
            (patient_id,),
        )

        total_row = self.db.fetch_one(
            """
            SELECT COUNT(*) AS n
            FROM aia_health_vital_signs
            WHERE patient_id = %s
              AND measured_at >= NOW() - INTERVAL '7 days'
            """,
            (patient_id,),
        )

        # Trend simples: compara última medição vs média dos últimos 7 dias
        for vt, reading in last.items():
            if reading is None:
                continue
            trend_row = self.db.fetch_one(
                """
                SELECT AVG(value_numeric) AS avg_val
                FROM aia_health_vital_signs
                WHERE patient_id = %s AND vital_type = %s
                  AND measured_at >= NOW() - INTERVAL '7 days'
                  AND measured_at < NOW() - INTERVAL '1 day'
                """,
                (patient_id, vt),
            )
            avg_val = trend_row and trend_row.get("avg_val")
            if avg_val is not None and reading.get("value_numeric") is not None:
                delta = float(reading["value_numeric"]) - float(avg_val)
                reading["trend_vs_7d_avg"] = round(delta, 2)
                reading["trend_direction"] = (
                    "up" if delta > 0.05 * float(avg_val)
                    else "down" if delta < -0.05 * float(avg_val)
                    else "stable"
                )

        return {
            "last_readings": last,
            "alerts_24h": alerts_row["n"] if alerts_row else 0,
            "total_measurements_7d": total_row["n"] if total_row else 0,
        }

    # ──────────────────────────────────────────────────────────────
    # Classificação (usada na ingestão manual ou via MedMonitor)
    # ──────────────────────────────────────────────────────────────

    def classify(
        self,
        patient_id: str | None,
        vital_type: str,
        value: float,
        value_secondary: float | None = None,
    ) -> str:
        """Classifica uma medição contra ranges (paciente-específicas ou default)."""
        # Busca range do paciente primeiro; fallback para default
        row = self.db.fetch_one(
            """
            SELECT routine_min, routine_max, attention_min, attention_max,
                   urgent_min, urgent_max
            FROM aia_health_vital_ranges
            WHERE vital_type = %s AND (patient_id = %s OR patient_id IS NULL)
            ORDER BY patient_id NULLS LAST
            LIMIT 1
            """,
            (vital_type, patient_id),
        )
        if not row:
            return "routine"

        # PA composite usa systolic para classificação primária
        return self._classify_value(
            value,
            row["routine_min"], row["routine_max"],
            row["attention_min"], row["attention_max"],
            row["urgent_min"], row["urgent_max"],
        )

    @staticmethod
    def _classify_value(val, r_min, r_max, a_min, a_max, u_min, u_max) -> str:
        val = float(val)
        if val < float(u_min) or val > float(u_max):
            return "critical"
        if val < float(a_min) or val > float(a_max):
            return "urgent"
        if val < float(r_min) or val > float(r_max):
            return "attention"
        return "routine"


_instance: VitalSignsService | None = None


def get_vital_signs_service() -> VitalSignsService:
    global _instance
    if _instance is None:
        _instance = VitalSignsService()
    return _instance
