"""Dose validator — cruzamento determinístico contra dose máxima diária.

Pontos de validação (3 fluxos):
  1. medication_routes.create_medication_schedule (cadastro manual)
  2. medication_routes.confirm_medication_import   (OCR de receita)
  3. teleconsulta_routes.add_prescription           (teleconsulta médica)

Uso típico:
    from src.services import dose_validator
    result = dose_validator.validate(
        medication_name="Aspirina",
        dose="500mg",
        times_of_day=["08:00", "14:00", "20:00"],  # 3×/dia
        route="oral",
        patient=patient_dict,
    )
    # result = {
    #   "ok": False,
    #   "severity": "warning" | "block" | None,
    #   "limits_found": True,
    #   "principle_active": "acido acetilsalicilico",
    #   "computed_daily_dose": {"value": 1500, "unit": "mg"},
    #   "max_daily_dose": {"value": 4000, "unit": "mg"},
    #   "ratio": 0.375,  # 37.5% do limite
    #   "issues": [...]
    # }

Severidade calculada:
    > 2.0× limite + source confidence ≥ 0.9    → "block"
    > 1.5× limite                               → "warning_strong"
    > 1.0× limite OR Beers avoid + paciente 60+ → "warning"
    Sem limite registrado                       → "unknown" (loga, não bloqueia)
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from src.services.postgres import get_postgres

logger = logging.getLogger(__name__)


# ─── Normalização ─────────────────────────────────────────

_SPECIAL_DRUG_CHAR = re.compile(r"[^a-z0-9 ]")
_MULTI_SPACE = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Lowercase, remove acentos e pontuação, collapse spaces."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    no_acc = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = _SPECIAL_DRUG_CHAR.sub(" ", no_acc)
    return _MULTI_SPACE.sub(" ", cleaned).strip()


# Suporta números decimais com ponto OU vírgula (formato brasileiro).
_DOSE_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mg|g|mcg|ug|µg|ml|ui|iu|gota|gotas|cp|comp|comprimido|comprimidos)?",
    re.IGNORECASE,
)

_UNIT_NORMALIZE = {
    "ug": "mcg", "µg": "mcg",
    "iu": "ui",
    "gotas": "gota",
    "comp": "cp", "comprimido": "cp", "comprimidos": "cp",
}

_UNIT_TO_MG = {
    "mg": 1.0,
    "g": 1000.0,
    "mcg": 0.001,
}


@dataclass
class DoseAmount:
    value: float
    unit: str

    def to_mg(self) -> float | None:
        """Converte pra mg quando possível (mg/g/mcg). None pra ml/ui/gota."""
        factor = _UNIT_TO_MG.get(self.unit)
        if factor is None:
            return None
        return self.value * factor


def parse_dose(text: str | None) -> DoseAmount | None:
    """Extrai (valor, unidade) de string tipo '500 mg', '1g', '0.5mg', '40 UI'."""
    if not text:
        return None
    m = _DOSE_PATTERN.search(text)
    if not m:
        return None
    raw_value = m.group(1).replace(",", ".")
    try:
        value = float(raw_value)
    except ValueError:
        return None
    unit_raw = (m.group(2) or "mg").lower()
    unit = _UNIT_NORMALIZE.get(unit_raw, unit_raw)
    return DoseAmount(value=value, unit=unit)


# ─── Lookup ───────────────────────────────────────────────

def resolve_principle_active(name: str) -> str | None:
    """Tenta achar princípio ativo canônico:
      1. Match exato em dose_limits (já é principle_active)
      2. Match em aliases
      3. Fuzzy match em principle_active (ILIKE %name%)
    Retorna o princípio_active normalizado ou None.
    """
    if not name:
        return None
    norm = normalize(name)
    if not norm:
        return None
    pg = get_postgres()

    # 1. Match direto em principle_active
    row = pg.fetch_one(
        "SELECT principle_active FROM aia_health_drug_dose_limits "
        "WHERE principle_active = %s AND active = TRUE LIMIT 1",
        (norm,),
    )
    if row:
        return row["principle_active"]

    # 2. Aliases (case-insensitive)
    row = pg.fetch_one(
        "SELECT principle_active FROM aia_health_drug_aliases "
        "WHERE lower(alias) = lower(%s) LIMIT 1",
        (name,),
    )
    if row:
        return row["principle_active"]
    # tenta também pelo norm
    row = pg.fetch_one(
        "SELECT principle_active FROM aia_health_drug_aliases "
        "WHERE lower(alias) = %s LIMIT 1",
        (norm,),
    )
    if row:
        return row["principle_active"]

    # 3. Fuzzy: principle_active contém ou é contido pelo nome
    row = pg.fetch_one(
        """
        SELECT principle_active FROM aia_health_drug_dose_limits
        WHERE active = TRUE
          AND (principle_active ILIKE %s OR %s ILIKE '%%' || principle_active || '%%')
        ORDER BY length(principle_active) DESC
        LIMIT 1
        """,
        (f"%{norm}%", norm),
    )
    if row:
        return row["principle_active"]
    return None


def get_dose_limit(principle_active: str, route: str, patient_age: int | None) -> dict | None:
    """Retorna o registro de limite mais aplicável."""
    age = patient_age if patient_age is not None else 60
    return get_postgres().fetch_one(
        """
        SELECT id, principle_active, route, max_daily_dose_value, max_daily_dose_unit,
               age_group_min, age_group_max, beers_avoid, beers_rationale,
               source, source_ref, confidence, notes,
               therapeutic_class, narrow_therapeutic_index, nti_monitoring
        FROM aia_health_drug_dose_limits
        WHERE principle_active = %s AND route = %s AND active = TRUE
          AND %s >= age_group_min
          AND (age_group_max IS NULL OR %s <= age_group_max)
        ORDER BY confidence DESC, age_group_min DESC
        LIMIT 1
        """,
        (principle_active, route, age, age),
    )


def get_principle_meta(principle_active: str) -> dict | None:
    """Metadata sem filtro de via/idade — pra duplicidade/polifarmácia."""
    return get_postgres().fetch_one(
        """
        SELECT principle_active, therapeutic_class, narrow_therapeutic_index,
               nti_monitoring, beers_avoid
        FROM aia_health_drug_dose_limits
        WHERE principle_active = %s AND active = TRUE
        ORDER BY confidence DESC LIMIT 1
        """,
        (principle_active,),
    )


def _patient_age(patient: dict | None) -> int | None:
    if not patient:
        return None
    bd = patient.get("birth_date")
    if not bd:
        return None
    if isinstance(bd, str):
        try:
            bd = date.fromisoformat(bd[:10])
        except ValueError:
            return None
    today = date.today()
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


def _times_per_day(times_of_day: list | None, schedule_type: str | None = None) -> int:
    """Conta doses/dia. Default 1 quando inferência incerta."""
    if times_of_day and isinstance(times_of_day, list):
        return max(1, len(times_of_day))
    if schedule_type == "prn":
        return 1  # PRN: assumimos 1 dose como teto, mas sinalizamos
    return 1


# ─── Validation ───────────────────────────────────────────

@dataclass
class DoseIssue:
    severity: str        # "block" | "warning_strong" | "warning" | "info"
    code: str            # "dose_above_limit" | "beers_avoid" | "unknown_drug" ...
    message: str         # texto humano (pt-BR) pra mostrar na UI
    detail: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    ok: bool
    severity: str | None             # max severity dos issues, ou None
    principle_active: str | None
    limit_found: bool
    computed_daily_dose: dict | None
    max_daily_dose: dict | None
    ratio: float | None              # daily / max
    issues: list[DoseIssue]
    source: str | None = None
    source_ref: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "severity": self.severity,
            "principle_active": self.principle_active,
            "limit_found": self.limit_found,
            "computed_daily_dose": self.computed_daily_dose,
            "max_daily_dose": self.max_daily_dose,
            "ratio": round(self.ratio, 3) if self.ratio is not None else None,
            "source": self.source,
            "source_ref": self.source_ref,
            "notes": self.notes,
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message, "detail": i.detail}
                for i in self.issues
            ],
        }


_SEVERITY_RANK = {"info": 0, "warning": 1, "warning_strong": 2, "block": 3}


def _max_severity(issues: list[DoseIssue]) -> str | None:
    if not issues:
        return None
    return max(issues, key=lambda i: _SEVERITY_RANK.get(i.severity, 0)).severity


# ─── Cruzamento ALERGIAS ──────────────────────────────────

def _normalize_allergy(term: str | None) -> str | None:
    """Normaliza alergia + tenta resolver pelo aliases."""
    if not term:
        return None
    norm = normalize(term)
    if not norm:
        return None
    row = get_postgres().fetch_one(
        "SELECT canonical_term FROM aia_health_allergy_aliases WHERE lower(alias) = %s LIMIT 1",
        (norm,),
    )
    if row:
        return row["canonical_term"]
    return norm


def check_allergies(
    principle_active: str | None,
    therapeutic_class: str | None,
    patient_allergies: list | None,
) -> list[DoseIssue]:
    """Bloqueia/avisa baseado em allergy_mappings + cross-reactivity."""
    if not patient_allergies:
        return []
    issues: list[DoseIssue] = []
    pg = get_postgres()
    for raw in patient_allergies:
        term = raw if isinstance(raw, str) else (raw or {}).get("term") or (raw or {}).get("name")
        canonical = _normalize_allergy(term)
        if not canonical:
            continue
        # Match exato por princípio_active OU por classe
        rows = pg.fetch_all(
            """
            SELECT severity, rationale, source, source_ref,
                   affected_principle_active, affected_therapeutic_class
            FROM aia_health_allergy_mappings
            WHERE active = TRUE AND allergy_term = %s
              AND ((affected_principle_active IS NOT NULL AND affected_principle_active = %s)
                OR (affected_therapeutic_class IS NOT NULL AND affected_therapeutic_class = %s))
            """,
            (canonical, principle_active, therapeutic_class),
        )
        for r in rows:
            sev = r["severity"]
            mapped_sev = (
                "block" if sev == "block"
                else "warning_strong" if sev == "warning"
                else "info"
            )
            issues.append(DoseIssue(
                severity=mapped_sev,
                code="allergy_match",
                message=(
                    f"⚠️ Paciente alergia a '{term}'. {r['rationale']} "
                    f"Fonte: {r['source']}."
                ),
                detail={
                    "allergy": term,
                    "matched_via": "principle" if r.get("affected_principle_active") else "class",
                    "source": r["source"],
                },
            ))
    return issues


# ─── Cruzamento DUPLICIDADE TERAPÊUTICA + POLIFARMÁCIA + NTI ──

def _list_active_schedules(patient_id: str | None) -> list[dict]:
    if not patient_id:
        return []
    return get_postgres().fetch_all(
        """
        SELECT id, medication_name
        FROM aia_health_medication_schedules
        WHERE patient_id = %s AND active = TRUE
        """,
        (patient_id,),
    )


def check_duplicate_therapy(
    principle_active: str | None,
    therapeutic_class: str | None,
    patient_id: str | None,
) -> list[DoseIssue]:
    """Detecta 2+ medicamentos da mesma classe ativos pro paciente."""
    if not principle_active or not therapeutic_class or not patient_id:
        return []
    actives = _list_active_schedules(patient_id)
    if not actives:
        return []
    duplicates = []
    for sch in actives:
        existing_principle = resolve_principle_active(sch["medication_name"])
        if not existing_principle or existing_principle == principle_active:
            continue
        meta = get_principle_meta(existing_principle)
        if meta and meta.get("therapeutic_class") == therapeutic_class:
            duplicates.append({
                "name": sch["medication_name"],
                "principle": existing_principle,
            })
    if not duplicates:
        return []
    list_str = ", ".join(d["name"] for d in duplicates)
    return [DoseIssue(
        severity="warning_strong",
        code="duplicate_therapy",
        message=(
            f"⚠️ Duplicidade terapêutica: paciente já usa "
            f"{list_str} (mesma classe: {therapeutic_class}). "
            "Risco de potencialização e efeitos cumulativos."
        ),
        detail={
            "therapeutic_class": therapeutic_class,
            "existing": duplicates,
        },
    )]


def check_polypharmacy(
    patient_id: str | None,
    threshold: int = 5,
) -> list[DoseIssue]:
    """Beers: ≥5 medicamentos simultâneos = warning."""
    if not patient_id:
        return []
    actives = _list_active_schedules(patient_id)
    count = len(actives)
    # +1 pra contar a prescrição que está sendo adicionada agora
    new_total = count + 1
    if new_total < threshold:
        return []
    return [DoseIssue(
        severity="warning",
        code="polypharmacy",
        message=(
            f"Polifarmácia: paciente terá {new_total} medicamentos ativos. "
            "Beers 2023 recomenda revisar prescrições periódicamente "
            f"(≥{threshold} meds). Considere desprescrição."
        ),
        detail={"current_count": count, "after": new_total, "threshold": threshold},
    )]


def check_narrow_therapeutic_index(limit: dict | None) -> list[DoseIssue]:
    """NTI = janela terapêutica estreita (digoxina, varfarina, levotiroxina)."""
    if not limit or not limit.get("narrow_therapeutic_index"):
        return []
    return [DoseIssue(
        severity="warning",
        code="narrow_therapeutic_index",
        message=(
            f"📊 {limit['principle_active'].title()} tem janela terapêutica estreita. "
            f"{limit.get('nti_monitoring') or 'Monitorização sérica/laboratorial obrigatória.'}"
        ),
        detail={
            "principle_active": limit["principle_active"],
            "monitoring": limit.get("nti_monitoring"),
        },
    )]


# ─── Validação central ───────────────────────────────────


def validate(
    *,
    medication_name: str,
    dose: str,
    times_of_day: list | None = None,
    route: str = "oral",
    patient: dict | None = None,
    schedule_type: str | None = None,
) -> ValidationResult:
    """Valida uma prescrição. Retorna ValidationResult."""
    issues: list[DoseIssue] = []
    age = _patient_age(patient)

    principle = resolve_principle_active(medication_name)
    if not principle:
        issues.append(DoseIssue(
            severity="info",
            code="unknown_drug",
            message=(
                f"Não temos limite cadastrado pra '{medication_name}'. "
                "Cuidado clínico recomendado — confira a bula."
            ),
            detail={"input_name": medication_name},
        ))
        return ValidationResult(
            ok=True, severity="info",
            principle_active=None, limit_found=False,
            computed_daily_dose=None, max_daily_dose=None, ratio=None,
            issues=issues,
        )

    parsed_dose = parse_dose(dose)
    if not parsed_dose:
        issues.append(DoseIssue(
            severity="warning",
            code="dose_unparseable",
            message=f"Não consegui interpretar a dose '{dose}'. Use formato '500mg', '1g', '40UI'.",
            detail={"input_dose": dose},
        ))
        return ValidationResult(
            ok=False, severity="warning",
            principle_active=principle, limit_found=False,
            computed_daily_dose=None, max_daily_dose=None, ratio=None,
            issues=issues,
        )

    times = _times_per_day(times_of_day, schedule_type)
    daily = DoseAmount(value=parsed_dose.value * times, unit=parsed_dose.unit)

    limit = get_dose_limit(principle, route, age)

    # Cruzamentos de contexto (rodam mesmo sem limit registrado pra essa via)
    therapeutic_class = (limit or {}).get("therapeutic_class")
    patient_id = (patient or {}).get("id")
    patient_allergies = (patient or {}).get("allergies") or []

    issues.extend(check_allergies(principle, therapeutic_class, patient_allergies))
    issues.extend(check_duplicate_therapy(principle, therapeutic_class, patient_id))
    issues.extend(check_polypharmacy(patient_id))
    issues.extend(check_narrow_therapeutic_index(limit))

    if not limit:
        issues.append(DoseIssue(
            severity="info",
            code="no_limit_for_route",
            message=(
                f"Princípio ativo '{principle}' identificado, mas sem limite "
                f"cadastrado pra via '{route}' nessa faixa etária."
            ),
            detail={"principle_active": principle, "route": route},
        ))
        return ValidationResult(
            ok=True, severity="info",
            principle_active=principle, limit_found=False,
            computed_daily_dose={"value": daily.value, "unit": daily.unit},
            max_daily_dose=None, ratio=None,
            issues=issues,
        )

    max_dose = DoseAmount(
        value=float(limit["max_daily_dose_value"]),
        unit=limit["max_daily_dose_unit"],
    )

    # Beers avoid: alerta SEMPRE em paciente ≥ 60 anos, independente da dose.
    beers_avoid = bool(limit.get("beers_avoid"))
    if beers_avoid and (age is None or age >= 60):
        issues.append(DoseIssue(
            severity="warning_strong",
            code="beers_avoid",
            message=(
                f"⚠️ {principle.title()} consta nos Critérios de Beers como "
                f"medicamento a evitar em idosos. Motivo: "
                f"{limit.get('beers_rationale') or 'risco aumentado em geriatria'}."
            ),
            detail={
                "principle_active": principle,
                "rationale": limit.get("beers_rationale"),
                "source": limit.get("source"),
            },
        ))

    # Cálculo de ratio só se unidades comparáveis
    ratio = None
    daily_mg = daily.to_mg()
    max_mg = max_dose.to_mg()
    if daily.unit == max_dose.unit:
        ratio = daily.value / max_dose.value if max_dose.value else None
    elif daily_mg is not None and max_mg is not None:
        ratio = daily_mg / max_mg if max_mg else None

    if ratio is None:
        issues.append(DoseIssue(
            severity="info",
            code="unit_mismatch",
            message=(
                f"Não consegui comparar unidades: prescrita '{daily.unit}' vs "
                f"limite '{max_dose.unit}'. Confira manualmente."
            ),
            detail={
                "computed_unit": daily.unit,
                "limit_unit": max_dose.unit,
            },
        ))
    else:
        confidence = float(limit.get("confidence") or 0.85)
        excess_pct = round((ratio - 1) * 100, 1) if ratio > 1 else 0
        if ratio > 2.0 and confidence >= 0.9:
            issues.append(DoseIssue(
                severity="block",
                code="dose_above_limit",
                message=(
                    f"⛔ Dose diária ({_fmt(daily)}) é {ratio:.1f}× o limite máximo "
                    f"({_fmt(max_dose)}) — fonte {limit.get('source')}. "
                    f"Excesso {excess_pct}%. Não permitido sem revisão médica."
                ),
                detail={
                    "ratio": ratio,
                    "source": limit.get("source"),
                    "source_ref": limit.get("source_ref"),
                },
            ))
        elif ratio > 1.5:
            issues.append(DoseIssue(
                severity="warning_strong",
                code="dose_above_limit",
                message=(
                    f"⚠️ Dose diária ({_fmt(daily)}) excede o limite "
                    f"({_fmt(max_dose)}) em {excess_pct}%. Fonte: {limit.get('source')}. "
                    "Confirme com o médico."
                ),
                detail={"ratio": ratio, "source": limit.get("source")},
            ))
        elif ratio > 1.0:
            issues.append(DoseIssue(
                severity="warning",
                code="dose_above_limit",
                message=(
                    f"Dose diária ({_fmt(daily)}) está {excess_pct}% acima do "
                    f"limite recomendado ({_fmt(max_dose)}). Fonte: {limit.get('source')}."
                ),
                detail={"ratio": ratio, "source": limit.get("source")},
            ))

    severity = _max_severity(issues)
    blocking = severity == "block"
    return ValidationResult(
        ok=not blocking,
        severity=severity,
        principle_active=principle,
        limit_found=True,
        computed_daily_dose={"value": daily.value, "unit": daily.unit},
        max_daily_dose={"value": max_dose.value, "unit": max_dose.unit},
        ratio=ratio,
        source=limit.get("source"),
        source_ref=limit.get("source_ref"),
        notes=limit.get("notes"),
        issues=issues,
    )


def _fmt(d: DoseAmount) -> str:
    v = int(d.value) if d.value == int(d.value) else d.value
    return f"{v}{d.unit}"
