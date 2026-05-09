"""Cross-validation condição × medicamento.

Decisão Alexandre+Henrique 2026-05-09: quando paciente declara
condição mas não lista medicamento esperado, dispara soft prompt.
NÃO bloqueia salvar — paciente confirma motivo (esqueceu / não-medicamentoso /
orientação médica / pular).

Pipeline:
    1. Paciente preenche conditions + medications no wizard
    2. Pra cada condição, busca expectation curada (active=true, approved)
    3. Match texto livre da condição → CID-10 → expectation
    4. Pra cada med na lista do paciente, busca classe terapêutica
    5. Se nenhum med tem classe esperada pela condição → flag mismatch
    6. Retorna lista de prompts pra UI mostrar
"""
from __future__ import annotations

from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger
from src.utils.patient_data_helpers import extract_names

logger = get_logger(__name__)


class ValidationPrompt(dict):
    """Estrutura serializável da resposta. Mantém shape consistente."""


def _normalize(text: str) -> str:
    """Lower + strip pra match case-insensitive."""
    return (text or "").strip().lower()


def _classify_medication_text(med_text: str) -> list[str]:
    """Pega texto livre do medicamento (ex: "Losartana 50mg") e devolve
    lista de classes terapêuticas.

    Retorna [] se não conseguir classificar (texto desconhecido).
    """
    if not med_text:
        return []
    norm = _normalize(med_text)
    db = get_postgres()
    # Match por substring usando match_patterns (cada med tem array de patterns)
    rows = db.fetch_all(
        """SELECT therapeutic_classes
           FROM aia_health_medication_class_dictionary
           WHERE review_status = 'approved'
             AND EXISTS (
                 SELECT 1 FROM unnest(match_patterns) AS pat
                 WHERE %s LIKE '%%' || lower(pat) || '%%'
             )""",
        (norm,),
    )
    classes: set[str] = set()
    for row in rows:
        for c in row.get("therapeutic_classes") or []:
            classes.add(c)
    return list(classes)


def validate_conditions_medications(
    conditions: list[Any],
    medications: list[Any],
) -> list[ValidationPrompt]:
    """Roda a cross-validation.

    Args:
        conditions: lista de condições (formato antigo str ou novo dict)
        medications: lista de medicações (idem)

    Returns:
        Lista de prompts. Vazia se tudo ok.
    """
    condition_names = extract_names(conditions)
    med_names = extract_names(medications)
    if not condition_names:
        return []

    # Classifica medicações em classes terapêuticas
    all_classes: set[str] = set()
    for med in med_names:
        for cls in _classify_medication_text(med):
            all_classes.add(cls)

    # Carrega expectations ativas e aprovadas
    db = get_postgres()
    expectations = db.fetch_all(
        """SELECT id::text AS id, condition_label, cid10_code,
                  condition_match_patterns, expected_therapeutic_classes,
                  prompt_severity, prompt_message, response_options,
                  clinical_rationale
           FROM aia_health_disease_medication_expectations
           WHERE active = TRUE AND review_status = 'approved'""",
    )

    prompts: list[ValidationPrompt] = []
    for exp in expectations:
        patterns = [_normalize(p) for p in (exp.get("condition_match_patterns") or [])]
        # Match: condição declarada bate com algum pattern?
        matched_condition = None
        for cn in condition_names:
            cn_norm = _normalize(cn)
            if any(p and p in cn_norm for p in patterns):
                matched_condition = cn
                break
        if not matched_condition:
            continue

        expected_classes = exp.get("expected_therapeutic_classes") or []
        # Tem alguma classe esperada presente nas medicações?
        has_match = any(c in all_classes for c in expected_classes)
        if has_match:
            continue  # OK — paciente listou medicação compatível

        # Mismatch — emite prompt
        prompts.append(ValidationPrompt({
            "expectation_id": exp["id"],
            "condition_matched": matched_condition,
            "condition_label": exp["condition_label"],
            "cid10_code": exp.get("cid10_code"),
            "expected_classes": expected_classes,
            "found_classes": list(all_classes),
            "severity": exp["prompt_severity"],
            "message": exp["prompt_message"],
            "response_options": exp["response_options"],
            "clinical_rationale": exp["clinical_rationale"],
        }))

    return prompts


def search_cid10(query: str, limit: int = 20) -> list[dict]:
    """Autocomplete CID-10 — search by code OR description.
    Usa pg_trgm pra fuzzy match. Retorna apenas approved."""
    if not query or len(query.strip()) < 2:
        return []
    q = query.strip().lower()
    rows = get_postgres().fetch_all(
        """SELECT code, description_pt, description_layman, category,
                  similarity(search_text, %s) AS score
           FROM aia_health_cid10_curated
           WHERE review_status = 'approved'
             AND (search_text ILIKE %s
                  OR similarity(search_text, %s) > 0.2)
           ORDER BY score DESC, code ASC
           LIMIT %s""",
        (q, f"%{q}%", q, limit),
    )
    return [
        {
            "code": r["code"],
            "description_pt": r["description_pt"],
            "description_layman": r.get("description_layman"),
            "category": r["category"],
            "score": float(r.get("score") or 0),
        }
        for r in rows
    ]


def lookup_medication_class(query: str) -> dict | None:
    """Pra UI explicar 'isso é um IECA usado em HAS' enquanto digita.
    Retorna o primeiro match aprovado, ou None."""
    if not query or len(query.strip()) < 2:
        return None
    q = _normalize(query)
    row = get_postgres().fetch_one(
        """SELECT id::text AS id, active_ingredient, brand_names,
                  therapeutic_classes, main_indications, notes
           FROM aia_health_medication_class_dictionary
           WHERE review_status = 'approved'
             AND EXISTS (
                 SELECT 1 FROM unnest(match_patterns) AS pat
                 WHERE %s LIKE '%%' || lower(pat) || '%%'
             )
           ORDER BY length(active_ingredient) ASC
           LIMIT 1""",
        (q,),
    )
    if not row:
        return None
    return dict(row)
