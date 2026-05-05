"""Smoke test do DrugSafetyService (wrapper sobre dose_validator + cascade_detector).

Roda 4 cenários representativos contra dataset existente em prod
(142 drugs, 93 interações, 151 dose_limits, 51 ACB, etc).

NÃO valida correção CLÍNICA — isso é responsabilidade do Henrique
(referência clínica) revisar via `/admin/governance/clinical-rules`.

Pré-requisito: tabelas drug_* populadas (já estão em prod).

Uso:
    docker exec connectaiacare-api python /app/scripts/test_drug_safety.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from src.services.drug_safety_service import get_drug_safety_service


# Patient fictício — sem patient.id (skip cascades). Pra testar
# cascatas de verdade, precisa patient_id real do DB.
PATIENT_GERIATRA = {
    "age": 82,
    "allergies": [],
    "conditions": [],
    "creatinine_mgdl": 1.4,  # ClCr ~50 — função renal limítrofe
}


SCENARIOS = [
    {
        "name": "1_dose_normal_atenolol",
        "description": "Atenolol 50mg 1x/dia em idosa 82a — esperado OK",
        "prescriptions": [
            {"medication_name": "Atenolol", "dose": "50mg", "times_of_day": ["08:00"]},
        ],
        "expectation": "OK ou warning leve sobre função renal",
    },
    {
        "name": "2_diazepam_geriatra_alta_severidade",
        "description": "Diazepam em idosa — Beers avoid + ACB",
        "prescriptions": [
            {"medication_name": "Diazepam", "dose": "5mg", "times_of_day": ["22:00"]},
        ],
        "expectation": "warning_strong (Beers) + ACB score",
    },
    {
        "name": "3_combinacao_serotoninergica",
        "description": "Sertralina + Tramadol — interação major",
        "prescriptions": [
            {"medication_name": "Sertralina", "dose": "50mg", "times_of_day": ["08:00"]},
            {"medication_name": "Tramadol", "dose": "50mg", "times_of_day": ["12:00", "20:00"]},
        ],
        "expectation": "warning_strong com mensagem de síndrome serotoninérgica",
    },
    {
        "name": "4_drug_desconhecido",
        "description": "Drug não cadastrado",
        "prescriptions": [
            {"medication_name": "Pregabalina-XYZ-Inexistente", "dose": "75mg", "times_of_day": ["20:00"]},
        ],
        "expectation": "info: unknown_drug + recomendação revisão",
    },
]


def run():
    svc = get_drug_safety_service()
    print("=" * 78)
    print("Smoke test DrugSafetyService (wrapper) — 4 cenários")
    print("Pipeline: dose_validator (11 checks) + cascade_detector (dim 13)")
    print("=" * 78)

    for sc in SCENARIOS:
        print(f"\n>>> {sc['name']}")
        print(f"    {sc['description']}")
        print(f"    prescriptions: {[p['medication_name'] for p in sc['prescriptions']]}")
        print(f"    age={PATIENT_GERIATRA['age']}")

        review = svc.safety_review_prescriptions(
            sc["prescriptions"], patient=PATIENT_GERIATRA,
        )

        print(f"    max_severity={review['max_severity']}")
        print(f"    requires_human_review={review['requires_human_review']}")
        print(f"    cascades_detected={len(review['cascades'])} (sem patient.id, skip esperado)")

        for i, r in enumerate(review["results"]):
            principle = r.get("principle_active") or "?"
            sev = r.get("severity")
            n_issues = len(r.get("issues", []))
            print(f"    [{i+1}] principle={principle:20s} severity={sev}  issues={n_issues}")
            for issue in r.get("issues", [])[:3]:
                print(f"        - [{issue['severity']:14s}] {issue['code']:30s} {issue['message'][:70]}")
            if n_issues > 3:
                print(f"        ... +{n_issues - 3} issue(s)")
        print(f"    Esperado: {sc['expectation']}")

    print("\n" + "=" * 78)
    print("✅ Smoke rodou. Validação CLÍNICA = revisão Henrique via")
    print("   /admin/governance/clinical-rules (UI já existe).")
    print("=" * 78)


if __name__ == "__main__":
    run()
