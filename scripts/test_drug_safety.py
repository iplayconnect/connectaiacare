"""Smoke test do DrugSafetyService.

Roda 5 cenários clínicos comuns em geriatria contra o KG MVP populado
pelo import_drug_safety_mvp.py. Valida cobertura e formato de retorno.

NÃO valida correção CLÍNICA — isso é responsabilidade do Henrique
(referência clínica) revisar o dataset MVP antes de qualquer ativação.

Pré-requisito: rodar `import_drug_safety_mvp.py` antes (popula DB).

Uso:
    docker exec connectaiacare-api python /app/scripts/test_drug_safety.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")

from src.services.drug_safety_service import get_drug_safety_service


SCENARIOS = [
    {
        "name": "1_polifarmacia_geriatra",
        "description": "Idosa 82a com demência, tomando 4 drugs comuns",
        "medications": [
            "Diazepam 5mg à noite",
            "Atenolol 50mg manhã",
            "Losartana 50mg manhã",
            "Ibuprofeno 600mg quando dor",
        ],
        "patient_age": 82,
        "conditions": ["dementia"],
        "expectations": [
            "deve flagear Diazepam (avoid_in_elderly + categoria benzo)",
            "deve flagear interação Losartana+Ibuprofeno (triple whammy renal)",
        ],
    },
    {
        "name": "2_combinacao_perigosa_serotoninergica",
        "description": "Combinação ISRS + Tramadol — risco serotoninérgico",
        "medications": [
            "Sertralina 50mg",
            "Tramadol 50mg quando dor",
        ],
        "patient_age": 75,
        "conditions": [],
        "expectations": [
            "deve achar interação Sertralina+Tramadol (major, serotoninérgica)",
        ],
    },
    {
        "name": "3_benzo_opioide_depressao_respiratoria",
        "description": "Risco de depressão respiratória — black box FDA",
        "medications": [
            "Clonazepam 2mg",
            "Codeína 30mg",
        ],
        "patient_age": 78,
        "conditions": [],
        "expectations": [
            "deve achar interação Clonazepam+Codeína OU avisar gap se interação não no MVP",
        ],
    },
    {
        "name": "4_drug_desconhecido",
        "description": "Drug não cadastrado — testa policy de gaps",
        "medications": [
            "Pregabalina 75mg",  # não está no MVP
            "Atenolol 50mg",
        ],
        "patient_age": 80,
        "conditions": [],
        "expectations": [
            "Pregabalina deve aparecer em gaps[]",
            "Atenolol deve aparecer em recognized[]",
            "requires_human_review deve ser True",
        ],
    },
    {
        "name": "5_caso_seguro",
        "description": "Combinação relativamente segura",
        "medications": [
            "Metformina 850mg",
            "Sinvastatina 20mg",
            "Levotiroxina 50mcg",
        ],
        "patient_age": 70,
        "conditions": [],
        "expectations": [
            "0 Beers flags severas",
            "0 interações major/contraindicated",
            "requires_human_review pode ser True (MVP padrão) mas has_high_severity False",
        ],
    },
]


def run():
    svc = get_drug_safety_service()
    print("=" * 78)
    print("Smoke test DrugSafetyService — 5 cenários geriátricos")
    print("=" * 78)

    for sc in SCENARIOS:
        print(f"\n>>> {sc['name']}")
        print(f"    {sc['description']}")
        print(f"    medications: {sc['medications']}")
        print(f"    age={sc['patient_age']} conditions={sc['conditions']}")

        review = svc.safety_review(
            sc["medications"],
            patient_age=sc["patient_age"],
            conditions=sc["conditions"],
            tenant_id="_test_smoke",
        )

        print(f"    Recognized ({len(review['recognized'])}): "
              f"{[d['generic_name'] for d in review['recognized']]}")
        print(f"    Gaps ({len(review['gaps'])}): {review['gaps']}")
        print(f"    Beers flags ({len(review['beers_flags'])}):")
        for f in review["beers_flags"]:
            print(f"      - {f['drug_name']}: {f['category']} (severity={f['severity']}) — {f['rationale'][:80]}...")
        print(f"    Interactions ({len(review['interactions'])}):")
        for i in review["interactions"]:
            print(f"      - {i['drug_a_name']} ↔ {i['drug_b_name']}: {i['severity']} — {i['description'][:80]}...")
        print(f"    has_high_severity={review['has_high_severity']}  "
              f"requires_human_review={review['requires_human_review']}")
        print("    Esperado:")
        for e in sc["expectations"]:
            print(f"      • {e}")

    print("\n" + "=" * 78)
    print("✅ Smoke test rodou. Validação CLÍNICA dos resultados é tarefa do Henrique.")
    print("=" * 78)


if __name__ == "__main__":
    run()
