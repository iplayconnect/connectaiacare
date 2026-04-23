"""Prescription Validator — valida interações, alergias e posologia de prescrição.

MVP demo: **mocked com estrutura real** (arquitetura pronta pra Vidaas/
ICP-Brasil quando integração acontecer).

Valida 4 dimensões:
    1. Interação medicamentosa (este medicamento + medicações ativas do paciente)
    2. Alergia (este medicamento + lista de alergias do paciente)
    3. Dose usual geriátrica (dose proposta dentro da faixa)
    4. Contraindicação por condição (ex: AINE + IC, betabloqueador + DPOC grave)

Base de conhecimento: LLM com prompt estruturado (suficiente pra demo).
Pós-demo: integrar com base formal (Beers Criteria API, RxNorm, ANVISA).
"""
from __future__ import annotations

import json
from typing import Any

from src.services.llm_router import get_llm_router
from src.utils.logger import get_logger

logger = get_logger(__name__)


PROMPT = """Você é um farmacologista clínico especializado em geriatria, apoiando médicos na validação de prescrições.

Sua missão: revisar 1 medicamento proposto e identificar RISCOS de:
1. Interação medicamentosa com medicações em uso
2. Alergia/hipersensibilidade
3. Dose fora da faixa usual para idosos
4. Contraindicação por condição clínica
5. Flag de Critérios de Beers (medicações potencialmente inapropriadas em idosos)

# REGRAS INVIOLÁVEIS

1. Você NÃO substitui o médico. Você LEVANTA QUESTÕES para revisão.
2. Se tiver dúvida, sinalize — é melhor falso positivo que falso negativo em saúde.
3. Sua resposta deve ser acionável: o médico precisa saber O QUÊ fazer, não só O QUÊ é o risco.
4. Use vocabulário médico padrão brasileiro. Jamais prescreva, só apoie.

# Entradas

<proposed_prescription>
{proposed_prescription_json}
</proposed_prescription>

<patient_context>
{patient_context_json}
</patient_context>

# Output JSON estrito

{{
  "validation_status": "approved" | "approved_with_warnings" | "rejected",
  "severity": "none" | "low" | "moderate" | "high" | "critical",
  "issues": [
    {{
      "type": "interaction" | "allergy" | "dose" | "contraindication" | "beers_criteria",
      "severity": "low" | "moderate" | "high" | "critical",
      "description": "descrição clara do risco em 1-2 frases",
      "involved_medications": ["nome do medicamento em uso que interage"],
      "recommendation": "ação sugerida ao médico (ex: 'considerar dose inicial menor', 'monitorar função renal em 7 dias', 'evitar combinação — alternativa: X')",
      "reasoning": "racional clínico do risco em 1-2 frases"
    }}
  ],
  "beers_match": {{
    "is_potentially_inappropriate": true | false,
    "category": "(se aplicável — ex: 'benzodiazepínicos', 'anti-histamínicos 1a geração')",
    "justification": "por que é flagged pelos Critérios de Beers"
  }},
  "dose_assessment": {{
    "within_usual_range": true | false,
    "geriatric_adjustment_note": "(se dose precisa ajuste por idade/função renal)"
  }},
  "overall_recommendation": "resumo de 1 frase ao médico (ex: 'Seguro prescrever', 'Prescrever com cautela e monitoramento', 'Alta complexidade — reconsiderar alternativa')"
}}

# Princípios

- Em idoso, **clearance renal cai** — dose ajustada é frequentemente necessária.
- **Polifarmácia** (5+ medicações) aumenta risco exponencialmente. Flag se paciente já tem muitas medicações.
- **Critérios de Beers** são padrão — sempre consultar mentalmente ao propor benzodiazepínicos, anti-histamínicos 1a geração, antipsicóticos, certos anticolinérgicos.
- **Interações perigosas clássicas** em idoso: AINE + anticoagulante (sangramento), IECA + AINE (IRA), diurético + IECA + AINE (tripla ameaça), opioide + benzo (depressão respiratória), digital + diurético de alça (toxicidade).
"""


class PrescriptionValidator:
    def __init__(self):
        self.router = get_llm_router()

    async def validate(
        self,
        medication: str,
        dose: str,
        schedule: str,
        duration: str | None,
        indication: str | None,
        patient: dict[str, Any],
    ) -> dict[str, Any]:
        """Valida prescrição proposta para paciente. Retorna relatório estruturado."""
        proposed = {
            "medication": medication,
            "dose": dose,
            "schedule": schedule,
            "duration": duration or "não especificada",
            "indication": indication or "não informada",
        }
        patient_context = {
            "age": self._calc_age(patient.get("birth_date")),
            "gender": patient.get("gender"),
            "care_level": patient.get("care_level"),
            "conditions": patient.get("conditions") or [],
            "medications_current": patient.get("medications") or [],
            "allergies": patient.get("allergies") or [],
        }

        user_payload = PROMPT.format(
            proposed_prescription_json=json.dumps(proposed, ensure_ascii=False, indent=2),
            patient_context_json=json.dumps(patient_context, ensure_ascii=False, indent=2),
        )

        try:
            # ADR-025: task='prescription_validator' → Claude Sonnet 4
            result = self.router.complete_json(
                task="prescription_validator",
                system="Você é um farmacologista clínico geriátrico rigoroso e conservador.",
                user=user_payload,
            )
        except Exception as exc:
            logger.error("prescription_validator_failed", error=str(exc))
            return self._fallback(medication, str(exc))

        # Normalização defensiva
        if not isinstance(result, dict):
            return self._fallback(medication, "Resposta inválida do validador")

        result.setdefault("validation_status", "approved_with_warnings")
        result.setdefault("severity", "low")
        result.setdefault("issues", [])
        result.setdefault("beers_match", {"is_potentially_inappropriate": False})
        result.setdefault("dose_assessment", {"within_usual_range": True})
        result.setdefault(
            "overall_recommendation",
            "Validação automática — revisar clinicamente antes de assinar.",
        )

        # Metadata pra auditoria
        result["_meta"] = {
            "validator": "connectaia_mocked_v1",
            "note": "Validação por LLM. Pós-demo: integrar com base formal Beers/RxNorm/ANVISA.",
        }

        logger.info(
            "prescription_validated",
            medication=medication,
            status=result.get("validation_status"),
            severity=result.get("severity"),
            issues_count=len(result.get("issues", [])),
        )
        return result

    def _fallback(self, medication: str, reason: str) -> dict[str, Any]:
        return {
            "validation_status": "approved_with_warnings",
            "severity": "moderate",
            "issues": [{
                "type": "validation_unavailable",
                "severity": "moderate",
                "description": f"Validação automática indisponível: {reason}",
                "involved_medications": [],
                "recommendation": "Revisar prescrição manualmente — checar Beers Criteria, interações com medicações em uso e função renal antes de assinar.",
                "reasoning": "Serviço de validação retornou erro; segurança exige revisão humana.",
            }],
            "beers_match": {"is_potentially_inappropriate": False},
            "dose_assessment": {"within_usual_range": True},
            "overall_recommendation": "⚠️ Validação automática falhou — revisar manualmente antes de assinar.",
            "_meta": {"validator": "fallback", "error": reason},
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


_validator_instance: PrescriptionValidator | None = None


def get_prescription_validator() -> PrescriptionValidator:
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = PrescriptionValidator()
    return _validator_instance
