"""Motor de análise clínica do relato com classificação de urgência."""
from __future__ import annotations

import json
from typing import Any

from src.prompts.clinical_analysis import SYSTEM_PROMPT as CLINICAL_SYSTEM
from src.prompts.patient_extraction import SYSTEM_PROMPT as EXTRACTION_SYSTEM
from src.services.llm import MODEL_DEEP, MODEL_FAST, get_llm
from src.services.report_service import get_report_service
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisService:
    def __init__(self):
        self.llm = get_llm()
        self.reports = get_report_service()

    def extract_entities(self, transcription: str) -> dict[str, Any]:
        if not transcription.strip():
            return {"patient_name_mentioned": None, "confidence": 0.0}
        try:
            return self.llm.complete_json(
                system=EXTRACTION_SYSTEM,
                user=f"Transcrição do áudio do cuidador:\n\n{transcription}",
                model=MODEL_FAST,
                max_tokens=1024,
                temperature=0.0,
            )
        except Exception as exc:
            logger.error("entity_extraction_failed", error=str(exc))
            return {"patient_name_mentioned": None, "confidence": 0.0, "error": str(exc)}

    def analyze(
        self,
        transcription: str,
        entities: dict[str, Any],
        patient: dict[str, Any],
        recent_reports: list[dict],
    ) -> dict[str, Any]:
        patient_context = {
            "full_name": patient.get("full_name"),
            "birth_date": str(patient.get("birth_date")) if patient.get("birth_date") else None,
            "conditions": patient.get("conditions") or [],
            "medications": patient.get("medications") or [],
            "allergies": patient.get("allergies") or [],
            "care_level": patient.get("care_level"),
            "care_unit": patient.get("care_unit"),
            "room_number": patient.get("room_number"),
        }

        history_compact = []
        for r in recent_reports[:5]:
            history_compact.append(
                {
                    "when": str(r.get("received_at")) if r.get("received_at") else None,
                    "summary": (r.get("analysis") or {}).get("summary"),
                    "classification": r.get("classification"),
                    "key_symptoms": (r.get("analysis") or {}).get("symptoms_new"),
                }
            )

        user_payload = {
            "transcription": transcription,
            "extracted_entities": entities,
            "patient": patient_context,
            "recent_reports_history": history_compact,
        }

        try:
            result = self.llm.complete_json(
                system=CLINICAL_SYSTEM,
                user=json.dumps(user_payload, ensure_ascii=False, indent=2),
                model=MODEL_DEEP,
                max_tokens=2048,
                temperature=0.1,
            )
            logger.info(
                "analysis_complete",
                classification=result.get("classification"),
                alerts=len(result.get("alerts", [])),
            )
            return result
        except Exception as exc:
            logger.error("analysis_failed", error=str(exc))
            return {
                "summary": "Erro ao processar análise.",
                "classification": "attention",
                "alerts": [
                    {
                        "level": "medio",
                        "title": "Falha na análise automática",
                        "description": "A análise IA falhou. Revisar relato manualmente.",
                    }
                ],
                "needs_medical_attention": True,
                "error": str(exc),
            }


_analysis_instance: AnalysisService | None = None


def get_analysis_service() -> AnalysisService:
    global _analysis_instance
    if _analysis_instance is None:
        _analysis_instance = AnalysisService()
    return _analysis_instance
