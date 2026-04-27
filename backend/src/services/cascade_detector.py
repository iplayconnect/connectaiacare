"""Detector de cascatas de prescrição (dimensão 13 do motor).

Para cada paciente, varre as cascatas ativas em aia_health_drug_cascades e
verifica se as medicações ativas dele se encaixam no padrão A+C ou A+B+C.

Match logic:
  Para cada drug_x da cascata (A, B opcional, C):
    paciente bate se ALGUMA das suas medicações ativas:
      - tem principle_active dentro de drug_x_principles, OU
      - tem therapeutic_class dentro de drug_x_classes

  Cascata dispara se:
    pattern='a_and_c'   → bateu em A E em C (B não importa)
    pattern='a_b_and_c' → bateu em A E em B E em C

Exclusões:
  Se cascade.exclusion_conditions tem icd_codes que match em
  patient.conditions, a cascata é SUPRIMIDA (paciente tem indicação real
  pra C, não é cascata).

Output:
  Lista de matches com cascade detalhe + quais medicações do paciente
  bateram em A/B/C (pra explicação clínica).
"""
from __future__ import annotations

import json
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ────────────────────────────────────────────────────────────────────
# Class lookup pra medicações do paciente
# ────────────────────────────────────────────────────────────────────

def _load_principle_to_class_map() -> dict[str, str]:
    """Carrega mapping principle_active → therapeutic_class do motor.

    Cacheable em memória (mudança rara). Por enquanto recarrega por chamada.
    """
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT DISTINCT principle_active, therapeutic_class
           FROM aia_health_drug_dose_limits
           WHERE therapeutic_class IS NOT NULL"""
    )
    return {
        _norm(r["principle_active"]): r["therapeutic_class"]
        for r in (rows or [])
        if r.get("principle_active")
    }


def _norm(s: str | None) -> str:
    if not s:
        return ""
    return s.strip().lower()


def _resolve_alias(name: str, db) -> str:
    """Tenta resolver alias → principle_active canônico.

    Olha em aia_health_drug_aliases. Se não achar, retorna o nome
    normalizado (assumindo que já é o principle).
    """
    norm = _norm(name)
    if not norm:
        return ""
    row = db.fetch_one(
        """SELECT principle_active FROM aia_health_drug_aliases
           WHERE lower(alias) = %s LIMIT 1""",
        (norm,),
    )
    if row and row.get("principle_active"):
        return _norm(row["principle_active"])
    return norm


# ────────────────────────────────────────────────────────────────────
# Coleta de medicações ativas do paciente
# ────────────────────────────────────────────────────────────────────

def _gather_patient_meds(patient_id: str) -> list[dict]:
    """Retorna lista de [{principle, class, schedule_id, medication_name}]
    a partir de aia_health_medication_schedules ativos."""
    db = get_postgres()
    pmap = _load_principle_to_class_map()

    rows = db.fetch_all(
        """SELECT id, medication_name, dose
           FROM aia_health_medication_schedules
           WHERE patient_id = %s AND active = TRUE""",
        (patient_id,),
    )
    out: list[dict] = []
    for r in rows or []:
        # Extrai principle do medication_name. Pode ser comercial; tenta alias.
        med_name = _norm(r.get("medication_name"))
        principle = _resolve_alias(med_name, db)
        therapeutic_class = pmap.get(principle)
        out.append({
            "schedule_id": str(r["id"]),
            "medication_name": r.get("medication_name"),
            "principle": principle,
            "class": therapeutic_class,
            "dose": r.get("dose"),
        })
    return out


# ────────────────────────────────────────────────────────────────────
# Match individual (uma cascata × meds do paciente)
# ────────────────────────────────────────────────────────────────────

def _meds_matching(
    meds: list[dict],
    principles_target: list[str],
    classes_target: list[str],
) -> list[dict]:
    """Retorna meds que batem em pelo menos um principle OR class."""
    p_set = {_norm(p) for p in (principles_target or []) if p}
    c_set = {_norm(c) for c in (classes_target or []) if c}
    out: list[dict] = []
    for m in meds:
        if m["principle"] and m["principle"] in p_set:
            out.append(m)
            continue
        if m["class"] and _norm(m["class"]) in c_set:
            out.append(m)
    return out


def _has_exclusion_match(
    cascade: dict,
    patient_conditions: list[dict] | None,
) -> bool:
    """Se exclusion_conditions tem icd_codes e paciente tem alguma condição
    com esse code, suprime a cascata."""
    excl = cascade.get("exclusion_conditions")
    if not excl:
        return False
    if isinstance(excl, str):
        try:
            excl = json.loads(excl)
        except Exception:
            return False
    icd_codes = excl.get("icd_codes") or []
    if not icd_codes or not patient_conditions:
        return False
    icd_set = {_norm(code) for code in icd_codes if code}
    for cond in patient_conditions:
        if not isinstance(cond, dict):
            continue
        code = _norm(cond.get("code") or cond.get("icd10") or "")
        if not code:
            continue
        # Match prefixo: "G20" exclui "G20.0", "G20.1", etc
        for excl_code in icd_set:
            if code == excl_code or code.startswith(f"{excl_code}."):
                return True
    return False


# ────────────────────────────────────────────────────────────────────
# Detecção principal
# ────────────────────────────────────────────────────────────────────

def detect_cascades(patient_id: str) -> dict:
    """Roda detecção de cascatas pra um paciente. Retorna dict com:
        - patient_id
        - meds_count: int
        - cascades_detected: list[dict] com cada match
    """
    db = get_postgres()

    patient = db.fetch_one(
        "SELECT id, conditions FROM aia_health_patients WHERE id = %s",
        (patient_id,),
    )
    if not patient:
        return {"ok": False, "error": "patient_not_found"}

    conditions = patient.get("conditions") or []
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except Exception:
            conditions = []

    meds = _gather_patient_meds(patient_id)
    if len(meds) < 2:
        return {
            "ok": True, "patient_id": patient_id,
            "meds_count": len(meds), "cascades_detected": [],
        }

    cascades = db.fetch_all(
        """SELECT * FROM aia_health_drug_cascades
           WHERE active = TRUE
           ORDER BY
             CASE severity
               WHEN 'contraindicated' THEN 0
               WHEN 'major' THEN 1
               WHEN 'moderate' THEN 2
               ELSE 3
             END, name"""
    )

    detected: list[dict] = []
    for c in cascades or []:
        a_match = _meds_matching(
            meds, c.get("drug_a_principles") or [],
            c.get("drug_a_classes") or [],
        )
        if not a_match:
            continue

        c_match = _meds_matching(
            meds, c.get("drug_c_principles") or [],
            c.get("drug_c_classes") or [],
        )
        if not c_match:
            continue

        b_match: list[dict] = []
        if c["match_pattern"] == "a_b_and_c":
            b_match = _meds_matching(
                meds, c.get("drug_b_principles") or [],
                c.get("drug_b_classes") or [],
            )
            if not b_match:
                continue

        # Cascata bateu — checa exclusão
        if _has_exclusion_match(dict(c), conditions):
            logger.info(
                "cascade_excluded_by_condition cascade=%s patient=%s",
                c["name"], patient_id,
            )
            continue

        detected.append({
            "cascade_id": str(c["id"]),
            "name": c["name"],
            "severity": c["severity"],
            "match_pattern": c["match_pattern"],
            "adverse_effect": c["adverse_effect"],
            "explanation": c["cascade_explanation"],
            "recommendation": c["recommendation"],
            "alternative": c.get("alternative"),
            "matched_drugs": {
                "a": [_drug_brief(m) for m in a_match],
                "b": [_drug_brief(m) for m in b_match] if b_match else None,
                "c": [_drug_brief(m) for m in c_match],
            },
            "source": c["source"],
            "source_ref": c.get("source_ref"),
            "confidence": float(c.get("confidence") or 0.85),
        })

    return {
        "ok": True,
        "patient_id": patient_id,
        "meds_count": len(meds),
        "cascades_detected": detected,
    }


def _drug_brief(med: dict) -> dict:
    return {
        "schedule_id": med["schedule_id"],
        "medication_name": med["medication_name"],
        "principle": med["principle"],
        "class": med["class"],
    }


# ────────────────────────────────────────────────────────────────────
# List all cascades (for admin viewer)
# ────────────────────────────────────────────────────────────────────

def list_cascades() -> list[dict]:
    db = get_postgres()
    rows = db.fetch_all(
        """SELECT id, name, severity, match_pattern,
                  drug_a_principles, drug_a_classes,
                  drug_b_principles, drug_b_classes,
                  drug_c_principles, drug_c_classes,
                  adverse_effect, cascade_explanation,
                  recommendation, alternative, exclusion_conditions,
                  source, source_ref, confidence, active
           FROM aia_health_drug_cascades
           ORDER BY active DESC, severity, name"""
    )
    out: list[dict] = []
    for r in rows or []:
        d = dict(r)
        d["id"] = str(d["id"])
        d["confidence"] = float(d.get("confidence") or 0.85)
        out.append(d)
    return out
