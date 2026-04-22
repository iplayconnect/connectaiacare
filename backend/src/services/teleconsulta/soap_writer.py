"""SOAP Writer — agente que gera prontuário SOAP a partir da transcrição.

Chamado no estado `documentation` do workflow teleconsultation (ADR-023).
Input: transcrição completa + ficha paciente + vitais recentes.
Output: SOAP estruturado em JSON + confiança do scribe + notas pro médico.

Uso:
    from src.services.teleconsulta.soap_writer import get_soap_writer
    soap = await get_soap_writer().write(
        teleconsultation_id="uuid",
        transcription="dialogo da consulta",
        patient=patient_dict,
        vital_signs_text="texto formatado das ultimas 72h",
        duration_min=18,
    )

Modelo default: Claude Opus 4 (decisão clínica apoia médico em produção).
Pro MVP demo: usa LLMRouter com MODEL_DEEP.
"""
from __future__ import annotations

import json
from typing import Any

from src.prompts.teleconsulta.soap_generation import SYSTEM_PROMPT
from src.services.llm import MODEL_DEEP, get_llm
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SoapWriter:
    def __init__(self):
        self.llm = get_llm()

    async def write(
        self,
        teleconsultation_id: str,
        transcription: str,
        patient: dict[str, Any],
        vital_signs_text: str | None = None,
        duration_min: int | None = None,
    ) -> dict[str, Any]:
        """Gera SOAP JSON estruturado.

        Retorna sempre um dict com chaves subjective/objective/assessment/plan,
        scribe_confidence. Em falha de LLM, retorna fallback com erro gravado.
        """
        if not transcription or not transcription.strip():
            logger.warning(
                "soap_writer_empty_transcription",
                teleconsultation_id=teleconsultation_id,
            )
            return self._empty_fallback("Transcrição vazia — não foi possível gerar SOAP")

        patient_record = {
            "full_name": patient.get("full_name"),
            "nickname": patient.get("nickname"),
            "age": self._calc_age(patient.get("birth_date")),
            "gender": patient.get("gender"),
            "conditions": patient.get("conditions") or [],
            "medications": patient.get("medications") or [],
            "allergies": patient.get("allergies") or [],
            "care_level": patient.get("care_level"),
        }

        payload = (
            "<patient_record>\n"
            f"{json.dumps(patient_record, ensure_ascii=False, indent=2)}\n"
            "</patient_record>\n\n"
            "<vital_signs_recent>\n"
            f"{vital_signs_text or '(sem aferições recentes registradas)'}\n"
            "</vital_signs_recent>\n\n"
            "<transcription>\n"
            f"{transcription.strip()}\n"
            "</transcription>\n\n"
            "<consultation_duration_minutes>\n"
            f"{duration_min or 'desconhecida'}\n"
            "</consultation_duration_minutes>\n"
        )

        try:
            result = self.llm.complete_json(
                system=SYSTEM_PROMPT,
                user=payload,
                model=MODEL_DEEP,
                max_tokens=6144,  # SOAP pode ser longo, vitaminado
                temperature=0.15,  # baixo, mas não zero (precisa fluência na HDA)
            )
        except Exception as exc:
            logger.error(
                "soap_writer_llm_failed",
                teleconsultation_id=teleconsultation_id,
                error=str(exc),
            )
            return self._empty_fallback(f"Erro ao gerar SOAP: {exc}")

        # Validação mínima de estrutura
        result = self._ensure_structure(result)

        logger.info(
            "soap_writer_complete",
            teleconsultation_id=teleconsultation_id,
            confidence=result.get("scribe_confidence", {}).get("overall"),
            has_assessment=bool(result.get("assessment", {}).get("primary_hypothesis")),
        )
        return result

    def _ensure_structure(self, raw: Any) -> dict[str, Any]:
        """Garante que output tem a estrutura mínima esperada.

        LLM pode retornar campos faltando; forçamos defaults pra UI não quebrar.
        """
        if not isinstance(raw, dict):
            return self._empty_fallback("Formato de resposta inválido")

        defaults = {
            "subjective": {
                "chief_complaint": "",
                "history_of_present_illness": "",
                "review_of_systems": {},
                "patient_quotes": [],
            },
            "objective": {
                "vital_signs_reported_in_consult": "",
                "physical_exam_findings": "",
                "lab_results_mentioned": None,
            },
            "assessment": {
                "primary_hypothesis": None,
                "differential_diagnoses": [],
                "active_problems_confirmed": [],
                "new_problems_identified": [],
                "clinical_reasoning": "",
            },
            "plan": {
                "medications": {
                    "continued": [],
                    "adjusted": [],
                    "started": [],
                    "suspended": [],
                },
                "non_pharmacological": [],
                "diagnostic_tests_requested": [],
                "referrals": [],
                "return_follow_up": {
                    "when": "",
                    "modality": "flexível",
                    "trigger_signs": [],
                },
                "patient_education": "",
            },
            "scribe_confidence": {
                "overall": "medium",
                "notes_for_doctor": "Revisar todos os campos antes de assinar.",
            },
        }

        # Deep merge simples — preserva o que LLM trouxe, completa lacunas
        def merge(target: dict, src: dict) -> dict:
            for key, val in target.items():
                if key not in src:
                    src[key] = val
                elif isinstance(val, dict) and isinstance(src.get(key), dict):
                    merge(val, src[key])
            return src

        return merge(defaults, dict(raw))

    def _empty_fallback(self, reason: str) -> dict[str, Any]:
        return {
            "subjective": {
                "chief_complaint": "(a confirmar)",
                "history_of_present_illness": "(não foi abordada nesta consulta)",
                "review_of_systems": {},
                "patient_quotes": [],
            },
            "objective": {
                "vital_signs_reported_in_consult": "",
                "physical_exam_findings": "(exame físico limitado por telemedicina)",
                "lab_results_mentioned": None,
            },
            "assessment": {
                "primary_hypothesis": None,
                "differential_diagnoses": [],
                "active_problems_confirmed": [],
                "new_problems_identified": [],
                "clinical_reasoning": "",
            },
            "plan": {
                "medications": {"continued": [], "adjusted": [], "started": [], "suspended": []},
                "non_pharmacological": [],
                "diagnostic_tests_requested": [],
                "referrals": [],
                "return_follow_up": {"when": "", "modality": "flexível", "trigger_signs": []},
                "patient_education": "",
            },
            "scribe_confidence": {
                "overall": "low",
                "notes_for_doctor": f"⚠️ Geração automática falhou: {reason}. Preencha manualmente.",
            },
            "_error": reason,
        }

    @staticmethod
    def _calc_age(birth_date) -> int | None:
        if not birth_date:
            return None
        try:
            from datetime import datetime
            if isinstance(birth_date, str):
                bd = datetime.strptime(birth_date.split("T")[0], "%Y-%m-%d").date()
            else:
                bd = birth_date
            today = datetime.now().date()
            return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except Exception:
            return None


_soap_writer_instance: SoapWriter | None = None


def get_soap_writer() -> SoapWriter:
    global _soap_writer_instance
    if _soap_writer_instance is None:
        _soap_writer_instance = SoapWriter()
    return _soap_writer_instance
