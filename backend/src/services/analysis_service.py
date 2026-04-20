"""Motor de análise clínica do relato com classificação de urgência.

Hardening incorporado:
- Payload em tags XML (alinhado com prompt) — mitiga prompt injection
- Pós-validação: palavras-gatilho de emergência forçam escalação mínima para
  'attention' com alerta, mesmo se o LLM classificar como 'routine' (defesa em
  profundidade contra prompt injection + viés de baixa classificação).
- Validação de enum da classification contra allowlist.
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.prompts.clinical_analysis import SYSTEM_PROMPT as CLINICAL_SYSTEM
from src.prompts.patient_extraction import SYSTEM_PROMPT as EXTRACTION_SYSTEM
from src.services.llm import MODEL_DEEP, MODEL_FAST, get_llm
from src.services.report_service import get_report_service
from src.services.vital_signs_service import get_vital_signs_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_CLASSIFICATIONS = {"routine", "attention", "urgent", "critical"}

# Palavras-gatilho de emergência — se aparecerem na transcrição e o LLM classificar
# como routine/attention, forçamos escalação com alerta adicional.
# Match considera variações morfológicas (regex word boundary case-insensitive).
EMERGENCY_KEYWORDS = {
    "queda": "possível trauma/fratura, especialmente em anticoagulados",
    "caiu": "possível trauma/fratura, especialmente em anticoagulados",
    "caído": "possível trauma/fratura, especialmente em anticoagulados",
    "sangramento": "sangramento ativo requer avaliação imediata",
    "sangrando": "sangramento ativo requer avaliação imediata",
    "sangue": "presença de sangue requer avaliação",
    "desmaio": "perda de consciência em idoso é emergência",
    "desmaiou": "perda de consciência em idoso é emergência",
    "convulsão": "convulsão requer acionamento imediato",
    "convulsionou": "convulsão requer acionamento imediato",
    "inconsciente": "perda de consciência requer acionamento imediato",
    "não responde": "nível de consciência alterado",
    "dor no peito": "possível síndrome coronariana aguda",
    "dor torácica": "possível síndrome coronariana aguda",
    "falta de ar severa": "dispneia severa requer avaliação",
    "não consegue respirar": "dispneia severa requer avaliação",
    "engasgou": "possível aspiração/obstrução de via aérea",
    "engasgando": "possível aspiração/obstrução de via aérea",
    "avc": "suspeita de AVC requer protocolo tempo-dependente",
    "derrame": "suspeita de AVC requer protocolo tempo-dependente",
    "boca torta": "possível AVC (paresia facial)",
    "braço não mexe": "possível AVC (hemiparesia)",
}


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

        # Buscar sinais vitais das últimas 24h (MedMonitor-ready)
        # Integração ADR-014: LLM cruza sintomas do relato com vitais objetivos.
        try:
            vitals_text = get_vital_signs_service().format_for_prompt(
                patient_id=str(patient.get("id")), hours=24
            )
        except Exception as exc:
            logger.warning("vitals_fetch_failed", error=str(exc))
            vitals_text = "Indisponível no momento."

        # Payload em formato de tags XML — alinha com regras invioláveis do prompt
        # que separa informação (dentro das tags) de instruções (do sistema).
        # Ver SECURITY.md §4 (Prompt Injection).
        user_payload = (
            "<transcription>\n"
            f"{transcription}\n"
            "</transcription>\n\n"
            "<entities>\n"
            f"{json.dumps(entities, ensure_ascii=False, indent=2)}\n"
            "</entities>\n\n"
            "<patient_record>\n"
            f"{json.dumps(patient_context, ensure_ascii=False, indent=2)}\n"
            "</patient_record>\n\n"
            "<vital_signs_last_24h>\n"
            f"{vitals_text}\n"
            "</vital_signs_last_24h>\n\n"
            "<recent_history>\n"
            f"{json.dumps(history_compact, ensure_ascii=False, indent=2)}\n"
            "</recent_history>\n"
        )

        try:
            result = self.llm.complete_json(
                system=CLINICAL_SYSTEM,
                user=user_payload,
                model=MODEL_DEEP,
                max_tokens=2048,
                temperature=0.1,
            )
        except Exception as exc:
            logger.error("analysis_failed", error=str(exc))
            return self._fallback_result(str(exc))

        # Validação pós-LLM — defesa em profundidade contra prompt injection
        # e viés de baixa classificação.
        result = self._post_validate(result, transcription)

        logger.info(
            "analysis_complete",
            classification=result.get("classification"),
            alerts=len(result.get("alerts", [])),
            escalated=result.get("_escalated_by_keywords", False),
        )
        return result

    def _post_validate(self, result: dict[str, Any], transcription: str) -> dict[str, Any]:
        """Pós-valida output do LLM.

        1. Força classification a ser enum válido; inválido → attention (conservador).
        2. Se transcrição tem keyword de emergência E classification é routine/attention,
           escala para urgent e adiciona alerta visível.
        """
        classification = result.get("classification", "attention")
        if classification not in ALLOWED_CLASSIFICATIONS:
            logger.warning(
                "invalid_classification_forced", original=classification, forced="attention"
            )
            classification = "attention"
            result["classification"] = classification

        # Detecção de keyword de emergência
        trans_lower = (transcription or "").lower()
        hits: list[tuple[str, str]] = []
        for kw, reason in EMERGENCY_KEYWORDS.items():
            # Match case-insensitive com word boundary quando possível
            if " " in kw:
                if kw in trans_lower:
                    hits.append((kw, reason))
            else:
                if re.search(rf"\b{re.escape(kw)}\b", trans_lower):
                    hits.append((kw, reason))

        if hits and classification in {"routine", "attention"}:
            # Escala para urgent e adiciona alerta de guarda
            logger.warning(
                "emergency_keyword_escalation",
                original_classification=classification,
                keywords=[h[0] for h in hits],
            )
            result["classification"] = "urgent"
            result["_escalated_by_keywords"] = True
            existing_alerts = result.get("alerts") or []
            kw_list = ", ".join(h[0] for h in hits[:3])
            reason_list = "; ".join(h[1] for h in hits[:3])
            existing_alerts.insert(
                0,
                {
                    "level": "alto",
                    "title": "Palavras de alerta detectadas no relato",
                    "description": f"Relato menciona: {kw_list}. {reason_list}. Escalação automática para urgent — revisão humana obrigatória.",
                    "clinical_reasoning": (
                        "Guarda de segurança: quando o relato contém sinais clássicos de emergência "
                        "e a classificação inicial foi baixa, a plataforma escala automaticamente "
                        "por princípio de precaução. Médico/enfermeiro deve validar."
                    ),
                },
            )
            result["alerts"] = existing_alerts
            result["needs_medical_attention"] = True

        return result

    def _fallback_result(self, error: str) -> dict[str, Any]:
        return {
            "summary": "Erro ao processar análise automática. Revisão manual necessária.",
            "classification": "attention",
            "alerts": [
                {
                    "level": "medio",
                    "title": "Falha na análise automática",
                    "description": "O motor de análise IA falhou. Revisar relato manualmente.",
                }
            ],
            "needs_medical_attention": True,
            "_error": error,
        }


_analysis_instance: AnalysisService | None = None


def get_analysis_service() -> AnalysisService:
    global _analysis_instance
    if _analysis_instance is None:
        _analysis_instance = AnalysisService()
    return _analysis_instance
