"""Patient Summary Service — reformula SOAP médico em linguagem simples.

O SOAP é técnico (jargão clínico, CID-10). O paciente e o familiar precisam
entender o que aconteceu + o que fazer. Usa Claude Sonnet pra traduzir sem
perder informação clínica relevante.

Princípios do prompt:
    - Linguagem 8ª série do ensino fundamental
    - Sem inventar achados; só reformula
    - Tom acolhedor mas direto
    - Destaca ações ("o que fazer agora") vs diagnóstico
    - Nunca promete cura ou dá garantias absolutas
"""
from __future__ import annotations

import json
from typing import Any

from src.services.llm import MODEL_FAST, get_llm
from src.utils.logger import get_logger

logger = get_logger(__name__)


SYSTEM = """Você reformula prontuários médicos (formato SOAP) em linguagem simples pro paciente idoso/familiar entender.

REGRAS INVIOLÁVEIS:
1. NÃO adicione informação que não esteja no SOAP. Só reformula o que está lá.
2. Linguagem nível 8ª série — evite jargão, siglas, latim. Quando precisar de termo técnico, explique entre parênteses.
3. Tom humano, acolhedor, mas DIRETO. Sem eufemismos vagos tipo "algumas situações". Seja claro: "a médica avaliou X".
4. NUNCA prometa cura ou dê garantias ("você vai melhorar" ou "isso resolve"). Use "pode ajudar a melhorar", "normalmente funciona".
5. Foque em AÇÕES concretas ao final. O que o paciente/cuidador FAZ hoje? Amanhã?
6. Se tiver sinais de alerta, deixe MUITO visível.
7. Nunca contradiga o médico. Se SOAP disse X, você traduz X, não julga.
8. Se o SOAP estiver muito vazio ("não foi abordado nesta consulta"), deixe claro que aquele item não foi tratado, não invente.
"""


USER_TEMPLATE = """<soap_medico>
{soap_json}
</soap_medico>

<prescricao>
{prescription_json}
</prescricao>

<paciente>
{patient_info}
</paciente>

<medico>
{doctor_name} — {doctor_specialty}
</medico>

Tarefa: produza um resumo em JSON **exato** nesse formato:

{{
  "greeting": "Frase curta cumprimentando (usar 1o nome do paciente se tiver)",
  "what_happened": "2-3 frases: o que o médico avaliou. Qual foi a conclusão principal (sem CID, só descrição).",
  "main_findings": ["bullet 1", "bullet 2"],
  "what_to_do_now": [
    {{"action": "o que fazer", "detail": "explicação curta"}}
  ],
  "medications_explained": [
    {{"name": "nome do medicamento (como está na receita)",
      "why": "pra que serve, em 1 frase",
      "how_to_take": "como tomar em linguagem do dia-a-dia",
      "important": "qualquer atenção importante (efeito, alimentos, outros remédios)"}}
  ],
  "warning_signs": [
    "sinal que exige voltar ao médico ou ir ao hospital imediatamente"
  ],
  "next_appointment": "quando retornar, em linguagem direta. Se não foi marcado, diga 'conforme orientação do médico'.",
  "supportive_message": "1-2 frases finais acolhedoras. Sem pieguice."
}}

IMPORTANTE: se o SOAP tem seções vazias tipo "não foi abordado nesta consulta", reflita isso (ex: "o médico não entrou em detalhes sobre X nesta consulta"). Não invente.
"""


class PatientSummaryService:
    def __init__(self):
        self.llm = get_llm()

    def generate(
        self,
        soap: dict,
        prescription: list[dict],
        patient: dict,
        doctor_name: str,
        doctor_specialty: str = "Geriatria",
    ) -> dict[str, Any]:
        patient_info = {
            "first_name": self._first_name(patient.get("full_name")),
            "nickname": patient.get("nickname"),
            "age": self._calc_age(patient.get("birth_date")),
        }

        try:
            result = self.llm.complete_json(
                system=SYSTEM,
                user=USER_TEMPLATE.format(
                    soap_json=json.dumps(soap or {}, ensure_ascii=False, indent=2)[:6000],
                    prescription_json=json.dumps(prescription or [], ensure_ascii=False, indent=2)[:3000],
                    patient_info=json.dumps(patient_info, ensure_ascii=False),
                    doctor_name=doctor_name,
                    doctor_specialty=doctor_specialty,
                ),
                model=MODEL_FAST,
                max_tokens=2500,
                temperature=0.3,
            )
            if not isinstance(result, dict):
                return self._fallback(patient, doctor_name)

            # Garantias defensivas
            result.setdefault("greeting", f"Olá, {patient_info['first_name'] or 'paciente'}!")
            result.setdefault("what_happened", "A teleconsulta foi realizada.")
            result.setdefault("main_findings", [])
            result.setdefault("what_to_do_now", [])
            result.setdefault("medications_explained", [])
            result.setdefault("warning_signs", [])
            result.setdefault("next_appointment", "Conforme orientação do médico.")
            result.setdefault(
                "supportive_message",
                "Qualquer dúvida, entre em contato com a central de cuidadores.",
            )
            return result
        except Exception as exc:
            logger.error("patient_summary_failed", error=str(exc))
            return self._fallback(patient, doctor_name)

    @staticmethod
    def _first_name(full_name: str | None) -> str | None:
        if not full_name:
            return None
        return full_name.strip().split()[0] if full_name.strip() else None

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

    def _fallback(self, patient: dict, doctor_name: str) -> dict:
        return {
            "greeting": f"Olá, {self._first_name(patient.get('full_name')) or ''}!",
            "what_happened": f"Sua teleconsulta com {doctor_name} foi finalizada.",
            "main_findings": [],
            "what_to_do_now": [],
            "medications_explained": [],
            "warning_signs": [
                "Em caso de piora súbita, procure atendimento imediato ou entre em contato com a central.",
            ],
            "next_appointment": "Conforme orientação do médico.",
            "supportive_message": "Qualquer dúvida, chame a central de cuidadores.",
            "_fallback": True,
        }


_instance: PatientSummaryService | None = None


def get_patient_summary_service() -> PatientSummaryService:
    global _instance
    if _instance is None:
        _instance = PatientSummaryService()
    return _instance
