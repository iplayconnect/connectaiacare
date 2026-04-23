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
from src.prompts.followup_answer import SYSTEM_PROMPT as FOLLOWUP_SYSTEM
from src.prompts.patient_extraction import SYSTEM_PROMPT as EXTRACTION_SYSTEM
from src.services.llm_router import get_llm_router
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
        self.router = get_llm_router()
        self.reports = get_report_service()

    def extract_entities(self, transcription: str) -> dict[str, Any]:
        if not transcription.strip():
            return {"patient_name_mentioned": None, "confidence": 0.0}
        try:
            # ADR-025: task='intent_classifier' → GPT-5.4 nano (barato, rápido)
            return self.router.complete_json(
                task="intent_classifier",
                system=EXTRACTION_SYSTEM,
                user=f"Transcrição do áudio do cuidador:\n\n{transcription}",
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
        conversation_history: list[dict] | None = None,
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

        # Histórico conversacional na sessão atual (últimas trocas com o cuidador).
        # Permite ao LLM entender evolução ("piorou", "melhorou", "agora apareceu X")
        # em vez de tratar cada mensagem como isolada. Ver ADR-017.
        conversation_block = ""
        if conversation_history:
            conversation_lines = _format_conversation(conversation_history)
            conversation_block = (
                "\n<conversation_history>\n"
                "Trocas recentes com este cuidador nesta sessão (da mais antiga para a mais nova).\n"
                "Use isto para detectar evolução clínica: o paciente melhorou ou piorou desde o último relato? Os sintomas são contínuos ou novos? A classificação atual deve escalar se houver deterioração.\n\n"
                f"{conversation_lines}\n"
                "</conversation_history>\n"
            )

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
            f"{conversation_block}"
        )

        try:
            # ADR-025: task='clinical_analysis' → GPT-5.4 mini (alto volume, bom custo)
            result = self.router.complete_json(
                task="clinical_analysis",
                system=CLINICAL_SYSTEM,
                user=user_payload,
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

    def answer_followup_text(
        self,
        caregiver_text: str,
        patient: dict[str, Any],
        conversation_history: list[dict] | None = None,
        last_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Responde pergunta/comentário livre do cuidador no contexto da sessão.

        Usado quando a sessão está em `active_with_patient` e o cuidador envia
        TEXTO (não áudio). Ex: "ela acabou de piorar", "quando devo checar de novo?",
        "ela aceitou tomar o remédio agora".

        Retorna um dict com ao menos:
            - reply: str (resposta curta e direta para enviar via WhatsApp)
            - intent: "clinical_update"|"question"|"status_report"|"other"
            - should_re_analyze: bool (se o texto indica mudança clínica relevante,
              o pipeline pode gerar um novo relato + análise)
        """
        patient_context = {
            "full_name": patient.get("full_name"),
            "nickname": patient.get("nickname"),
            "conditions": patient.get("conditions") or [],
            "medications": patient.get("medications") or [],
            "allergies": patient.get("allergies") or [],
            "care_level": patient.get("care_level"),
        }

        try:
            vitals_text = get_vital_signs_service().format_for_prompt(
                patient_id=str(patient.get("id")), hours=24
            )
        except Exception:
            vitals_text = "Indisponível no momento."

        conversation_lines = _format_conversation(conversation_history or [])
        last_analysis_compact = ""
        if last_analysis:
            last_analysis_compact = json.dumps(
                {
                    "summary": last_analysis.get("summary"),
                    "classification": last_analysis.get("classification"),
                    "classification_reasoning": last_analysis.get("classification_reasoning"),
                    "recommendations_caregiver": (last_analysis.get("recommendations_caregiver") or [])[:3],
                },
                ensure_ascii=False,
                indent=2,
            )

        user_payload = (
            "<patient_record>\n"
            f"{json.dumps(patient_context, ensure_ascii=False, indent=2)}\n"
            "</patient_record>\n\n"
            "<vital_signs_last_24h>\n"
            f"{vitals_text}\n"
            "</vital_signs_last_24h>\n\n"
            "<conversation_history>\n"
            f"{conversation_lines or '(sem trocas anteriores)'}\n"
            "</conversation_history>\n\n"
            "<last_analysis>\n"
            f"{last_analysis_compact or '(nenhuma análise anterior nesta sessão)'}\n"
            "</last_analysis>\n\n"
            "<caregiver_message>\n"
            f"{caregiver_text}\n"
            "</caregiver_message>\n"
        )

        try:
            # ADR-025: task='followup_answer' → GPT-5.4 mini
            result = self.router.complete_json(
                task="followup_answer",
                system=FOLLOWUP_SYSTEM,
                user=user_payload,
            )
        except Exception as exc:
            logger.error("followup_answer_failed", error=str(exc))
            return {
                "reply": "Entendi. Estou registrando a informação. Se for algo que exija atenção, me diga para analisar em detalhe.",
                "intent": "other",
                "should_re_analyze": False,
                "_error": str(exc),
            }

        # Validação mínima
        if not isinstance(result, dict) or "reply" not in result:
            return {
                "reply": "Ok, registrei. Me avise se precisar de algo.",
                "intent": "other",
                "should_re_analyze": False,
            }
        result.setdefault("intent", "other")
        result.setdefault("should_re_analyze", False)
        logger.info(
            "followup_answered",
            intent=result.get("intent"),
            should_re_analyze=result.get("should_re_analyze"),
        )
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


def _format_conversation(messages: list[dict]) -> str:
    """Formata mensagens da sessão como diálogo legível para o LLM.

    Cada linha: [HH:MM] Papel (tipo): texto
    - Papel: Cuidador | Sistema
    - Tipo omitido se = text; áudios aparecem como "(áudio transcrito)".
    - Resumos de sistema aparecem como "(resumo/classificação)".

    Defensivo contra mensagens mal-formadas — qualquer item sem 'text' vira '...'.
    """
    lines: list[str] = []
    for m in messages:
        ts = (m.get("timestamp") or "")
        # Extrai HH:MM do ISO timestamp se possível
        hhmm = ""
        if "T" in ts:
            try:
                hhmm = ts.split("T")[1][:5]
            except Exception:
                hhmm = ""
        role_raw = (m.get("role") or "").lower()
        role = {"caregiver": "Cuidador", "assistant": "Sistema"}.get(role_raw, "Desconhecido")
        kind = (m.get("kind") or "text").lower()
        text = (m.get("text") or m.get("transcript") or m.get("summary") or "").strip()
        if not text:
            text = "..."

        kind_label = ""
        if kind == "audio":
            kind_label = " (áudio transcrito)"
        elif kind in ("analysis_summary", "summary"):
            kind_label = " (resumo/classificação)"
        elif kind == "confirmation":
            kind_label = " (confirmação)"

        prefix = f"[{hhmm}] " if hhmm else ""
        lines.append(f"{prefix}{role}{kind_label}: {text}")

    return "\n".join(lines)


_analysis_instance: AnalysisService | None = None


def get_analysis_service() -> AnalysisService:
    global _analysis_instance
    if _analysis_instance is None:
        _analysis_instance = AnalysisService()
    return _analysis_instance
