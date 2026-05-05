"""DrugSafetyService — API alto-nível de farmacovigilância pra Sofia/agents.

⚠️  Essa classe é um WRAPPER FINO sobre os módulos canônicos do sistema:
    - dose_validator.validate()    — 11 checks integrados (dose, alergia,
                                     duplicate_therapy, polypharmacy, narrow
                                     therapeutic index, drug_interactions
                                     com time_separation, condition_contra,
                                     anticholinergic_burden ACB, fall_risk
                                     STOPP, renal/hepatic adjustments, vital
                                     constraints).
    - cascade_detector.detect_cascades() — dimensão 13 (prescrição em cascata).

Cobertura no DB hoje (auditoria 2026-05-05):
    142 drugs únicos · 93 interações ativas · 151 dose limits · 51 ACB ·
    38 fall risk · 45 renal · 166 hepatic · 10 cascatas · 109 aliases.
    Sources: anvisa, beers_2023, lexicomp, stockleys, fda, sbgg, manual.

Quando NÃO usar este wrapper:
    - Pra ler/editar regras clínicas diretamente: use endpoints
      /api/clinical-rules/* (CRUD admin) — clinical_rules_routes.py.
    - Pra criar prescrição: medication_routes.py já chama validate()
      automaticamente. Este wrapper é pra contextos consultivos
      (Sofia conversa com cuidador, sub-agent clínico, etc).

API pública (estável):

    svc = get_drug_safety_service()

    # 1. Review uma prescrição candidate (single med + paciente)
    result = svc.evaluate_prescription(
        medication_name="Atenolol",
        dose="50mg",
        times_of_day=["08:00"],
        route="oral",
        patient={"id": "...", "age": 82, "allergies": [...], ...},
    )
    # → ValidationResult com 11 checks rodados

    # 2. Review uma LISTA de meds candidate juntas (cuidador relata)
    review = svc.safety_review_prescriptions(
        prescriptions=[
            {"medication_name": "Atenolol", "dose": "50mg", "times_of_day": ["08:00"]},
            {"medication_name": "Diazepam", "dose": "5mg", "times_of_day": ["22:00"]},
        ],
        patient={"id": "...", "age": 82, "conditions": ["dementia"]},
    )
    # → dict {results: [...], cascades: [...], max_severity: "warning_strong",
    #         requires_human_review: True/False}

    # 3. Detectar cascatas pra paciente já em tratamento
    cascades = svc.detect_cascades_for_patient(patient_id)
    # → idêntico a cascade_detector.detect_cascades()

Esse wrapper NÃO duplica lógica clínica — apenas oferece superfície
limpa pra Sofia consumir. Curadoria, fontes e scoring continuam
em dose_validator + tabelas aia_health_drug_*.
"""
from __future__ import annotations

from typing import Any, Optional

from src.services import cascade_detector, dose_validator
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DrugSafetyService:
    """Wrapper alto-nível sobre o pipeline farmacológico canonical."""

    # ───────────────────────────────────────────────────────────
    # 1. Validação de UMA prescrição (delega 100% pro dose_validator)
    # ───────────────────────────────────────────────────────────

    def evaluate_prescription(
        self,
        *,
        medication_name: str,
        dose: str,
        times_of_day: Optional[list] = None,
        route: str = "oral",
        patient: Optional[dict] = None,
        schedule_type: Optional[str] = None,
    ) -> dose_validator.ValidationResult:
        """Roda os 11 checks do dose_validator pra uma prescrição candidate.

        Args:
            medication_name: nome (genérico ou comercial). Sistema resolve
                via aia_health_drug_aliases (109 mappings).
            dose: ex "50mg", "1g", "40UI".
            times_of_day: lista de horários ["08:00", "20:00"]. Usado pra
                calcular dose diária + detectar conflitos temporais com
                outras meds (time_separation_minutes).
            route: "oral" (default), "iv", "im", "topical", etc.
            patient: dict com id, age, allergies, conditions, vitals
                recentes (pra check_vital_constraints), creatinina/Cockcroft.
            schedule_type: "fixed" | "as_needed" — pra times_per_day calc.

        Returns:
            ValidationResult com .ok, .severity, .issues (lista) e
            metadata (principle_active, limit, source).
        """
        return dose_validator.validate(
            medication_name=medication_name,
            dose=dose,
            times_of_day=times_of_day,
            route=route,
            patient=patient,
            schedule_type=schedule_type,
        )

    # ───────────────────────────────────────────────────────────
    # 2. Review de UMA LISTA de prescrições (orquestrador)
    # ───────────────────────────────────────────────────────────

    def safety_review_prescriptions(
        self,
        prescriptions: list[dict],
        *,
        patient: Optional[dict] = None,
    ) -> dict:
        """Avalia N prescrições candidatas + cascatas do paciente.

        Útil quando cuidador relata múltiplas medicações de uma vez
        (foto da caixa, lista oral). Sofia usa esse método pra obter
        visão consolidada antes de responder ao cuidador.

        Args:
            prescriptions: lista de dicts com keys:
                medication_name (req), dose (req),
                times_of_day, route, schedule_type (opcionais).
            patient: contexto do paciente (id, age, allergies, conditions,
                vitals). patient.id é usado pra detect_cascades.

        Returns:
            dict com:
              results: [ValidationResult.to_dict() pra cada prescription]
              cascades: list de cascatas detectadas (vazio se sem patient.id)
              max_severity: maior severity entre todos os issues
                (block > warning_strong > warning > info)
              has_block_or_strong: bool — tem issue crítico que justifica
                handoff humano imediato
              requires_human_review: bool — Sofia deve sempre alertar
                + escalar quando True (block, warning_strong, ou cascata
                contraindicated/major)
              meta: contagens pra observabilidade
        """
        results = []
        for p in prescriptions or []:
            try:
                vr = self.evaluate_prescription(
                    medication_name=p.get("medication_name") or "",
                    dose=p.get("dose") or "",
                    times_of_day=p.get("times_of_day"),
                    route=p.get("route") or "oral",
                    patient=patient,
                    schedule_type=p.get("schedule_type"),
                )
                results.append(vr.to_dict())
            except Exception as exc:
                logger.warning(
                    "drug_safety_review_failed_one",
                    medication=p.get("medication_name"),
                    error=str(exc)[:200],
                )
                results.append({
                    "ok": False,
                    "severity": "warning",
                    "principle_active": None,
                    "limit_found": False,
                    "issues": [{
                        "severity": "warning",
                        "code": "evaluation_error",
                        "message": (
                            f"Não consegui avaliar '{p.get('medication_name')}' "
                            f"agora. Recomendo revisão clínica."
                        ),
                        "detail": {"input": p, "error": str(exc)[:120]},
                    }],
                })

        # Cascatas só fazem sentido com paciente identificado
        cascades = []
        patient_id = (patient or {}).get("id")
        if patient_id:
            try:
                cascade_result = cascade_detector.detect_cascades(str(patient_id))
                if cascade_result.get("ok"):
                    cascades = cascade_result.get("cascades_detected") or []
            except Exception as exc:
                logger.warning(
                    "drug_safety_cascades_failed",
                    patient_id=patient_id, error=str(exc)[:200],
                )

        # Severidade máxima agregada
        max_sev = self._max_severity_overall(results, cascades)
        has_block_or_strong = max_sev in ("block", "warning_strong")
        # Política conservadora: SEMPRE escalar se tem cascade major+ ou
        # qualquer issue >= warning_strong em prescription nova
        requires_review = (
            has_block_or_strong
            or any(c.get("severity") in ("contraindicated", "major") for c in cascades)
        )

        return {
            "results": results,
            "cascades": cascades,
            "max_severity": max_sev,
            "has_block_or_strong": has_block_or_strong,
            "requires_human_review": requires_review,
            "meta": {
                "prescriptions_evaluated": len(results),
                "cascades_detected": len(cascades),
                "patient_id": patient_id,
            },
        }

    # ───────────────────────────────────────────────────────────
    # 3. Cascatas pra paciente em tratamento (delega 100%)
    # ───────────────────────────────────────────────────────────

    def detect_cascades_for_patient(self, patient_id: str) -> dict:
        """Detecta cascatas de prescrição pro paciente.

        Equivalente direto a cascade_detector.detect_cascades(patient_id).
        Mantido aqui pra Sofia ter API uniforme (1 service em vez de 2).

        Returns:
            dict com cascades_detected, meds_count, etc.
            Ver cascade_detector.detect_cascades() pra schema completo.
        """
        return cascade_detector.detect_cascades(patient_id)

    # ───────────────────────────────────────────────────────────
    # Helpers internos
    # ───────────────────────────────────────────────────────────

    _SEV_RANK = {
        None: -1,
        "info": 0,
        "warning": 1,
        "warning_strong": 2,
        "block": 3,
    }
    _CASCADE_SEV_RANK = {
        None: -1,
        "minor": 0,
        "moderate": 1,
        "major": 2,
        "contraindicated": 3,
    }

    def _max_severity_overall(
        self,
        results: list[dict],
        cascades: list[dict],
    ) -> Optional[str]:
        """Severidade máxima entre todos os issues + cascatas.

        Retorna em escala dose_validator (block > warning_strong > warning > info)
        — mapeia cascade severity pra esse domínio:
          contraindicated → block
          major           → warning_strong
          moderate        → warning
          minor           → info
        """
        max_rank = -1
        max_sev = None
        for r in results:
            for issue in r.get("issues", []) or []:
                rank = self._SEV_RANK.get(issue.get("severity"), -1)
                if rank > max_rank:
                    max_rank = rank
                    max_sev = issue.get("severity")
        for c in cascades:
            csev = c.get("severity")
            mapped = {
                "contraindicated": "block",
                "major": "warning_strong",
                "moderate": "warning",
                "minor": "info",
            }.get(csev)
            if mapped:
                rank = self._SEV_RANK.get(mapped, -1)
                if rank > max_rank:
                    max_rank = rank
                    max_sev = mapped
        return max_sev


_instance: Optional[DrugSafetyService] = None


def get_drug_safety_service() -> DrugSafetyService:
    global _instance
    if _instance is None:
        _instance = DrugSafetyService()
    return _instance
