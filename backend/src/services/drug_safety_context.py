"""Helper compartilhado pra carregar contexto clínico do paciente
antes de safety_review_prescriptions.

Usado em DOIS lugares (Phase C v2.x — unificação canal):
  1. backend/src/services/sofia_tools.py:safety_review_prescriptions
     (tool chamada pelo CareSofiaAgent no WhatsApp)
  2. backend/src/handlers/safety_routes.py:internal_drug_safety_review
     (endpoint HTTP interno chamado por voice-call-service)

Mantém UMA fonte de verdade pro patient_ctx — qualquer mudança (novo
campo clínico cadastrado, lógica de age/idade) reflete nos 3 canais.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_patient_safety_context(
    patient_id: Optional[str],
    tenant_id: Optional[str],
) -> Optional[dict]:
    """Carrega ficha clínica resumida do paciente.

    Retorna dict com keys consumidas por dose_validator + cascade_detector:
      - id, age, gender, conditions, current_medications, allergies,
        creatinine_mgdl, weight_kg

    Returns None se patient_id ausente, paciente não encontrado ou erro
    de DB. Chamador deve seguir best-effort (review sem patient_ctx
    ainda detecta Beers/STOPP/interactions, mas pula cascades e
    renal/hepatic adjustments).
    """
    if not patient_id:
        return None

    try:
        sql = (
            "SELECT id::text AS id, full_name, birth_date, gender, "
            "       conditions, medications, allergies, "
            "       serum_creatinine_mg_dl, weight_kg, height_cm "
            "FROM aia_health_patients WHERE id = %s"
        )
        params: list = [patient_id]
        if tenant_id:
            sql += " AND tenant_id = %s"
            params.append(tenant_id)

        row = get_postgres().fetch_one(sql, tuple(params))
        if not row:
            return None

        age = None
        if row.get("birth_date"):
            bd = row["birth_date"]
            today = date.today()
            age = today.year - bd.year - (
                (today.month, today.day) < (bd.month, bd.day)
            )

        return {
            "id": row["id"],
            "age": age,
            "gender": row.get("gender"),
            "conditions": row.get("conditions") or [],
            "current_medications": row.get("medications") or [],
            "allergies": row.get("allergies") or [],
            "creatinine_mgdl": (
                float(row["serum_creatinine_mg_dl"])
                if row.get("serum_creatinine_mg_dl") else None
            ),
            "weight_kg": (
                float(row["weight_kg"])
                if row.get("weight_kg") else None
            ),
        }
    except Exception as exc:
        logger.warning(
            "patient_safety_context_load_failed",
            patient_id=patient_id, error=str(exc)[:200],
        )
        return None
