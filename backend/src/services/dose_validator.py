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
        SELECT id, medication_name, times_of_day
        FROM aia_health_medication_schedules
        WHERE patient_id = %s AND active = TRUE
        """,
        (patient_id,),
    )


def _times_to_minutes(times: list | None) -> list[int]:
    """Converte ['08:00','14:00'] ou [datetime.time(...)] em minutos do dia."""
    if not times:
        return []
    out: list[int] = []
    for t in times:
        try:
            if hasattr(t, "hour") and hasattr(t, "minute"):
                out.append(t.hour * 60 + t.minute)
            elif isinstance(t, str):
                parts = t.strip().split(":")
                hh = int(parts[0])
                mm = int(parts[1]) if len(parts) > 1 else 0
                out.append(hh * 60 + mm)
        except Exception:
            continue
    return out


def _min_circular_diff(a_minutes: list[int], b_minutes: list[int]) -> int | None:
    """Menor diferença em minutos entre qualquer par de horários (24h cíclico)."""
    if not a_minutes or not b_minutes:
        return None
    best = None
    for a in a_minutes:
        for b in b_minutes:
            d = abs(a - b)
            d = min(d, 1440 - d)  # circular: 23:00 vs 01:00 = 2h
            if best is None or d < best:
                best = d
    return best


def _format_minutes(m: int) -> str:
    if m % 60 == 0:
        return f"{m // 60}h"
    return f"{m // 60}h{m % 60:02d}"


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


# ─── Cruzamento DRUG-DRUG INTERACTIONS ────────────────────

# Mapeia severity da tabela → severity do issue
_INTERACTION_SEVERITY_MAP = {
    "contraindicated": "block",
    "major": "warning_strong",
    "moderate": "warning",
    "minor": "info",
}


def _query_interactions_pair(
    a_principle: str | None,
    a_class: str | None,
    b_principle: str | None,
    b_class: str | None,
) -> list[dict]:
    """Busca interações pra um par. Suporta 4 combinações principle/class."""
    pg = get_postgres()
    rows: list[dict] = []
    # principle × principle (lex-ordenado a < b)
    if a_principle and b_principle:
        ord_a, ord_b = sorted([a_principle, b_principle])
        rows.extend(pg.fetch_all(
            """
            SELECT severity, mechanism, clinical_effect, recommendation,
                   source, source_ref, confidence,
                   principle_a, principle_b, class_a, class_b,
                   time_separation_minutes, separation_strategy, food_warning
            FROM aia_health_drug_interactions
            WHERE active = TRUE
              AND ((principle_a = %s AND principle_b = %s)
                OR (principle_a = %s AND principle_b = %s))
            """,
            (ord_a, ord_b, ord_b, ord_a),
        ))
    # principle × class (testa as duas direções)
    if a_principle and b_class:
        rows.extend(pg.fetch_all(
            """
            SELECT severity, mechanism, clinical_effect, recommendation,
                   source, source_ref, confidence,
                   principle_a, principle_b, class_a, class_b,
                   time_separation_minutes, separation_strategy, food_warning
            FROM aia_health_drug_interactions
            WHERE active = TRUE
              AND ((principle_a = %s AND class_b = %s)
                OR (class_a = %s AND principle_b = %s))
            """,
            (a_principle, b_class, b_class, a_principle),
        ))
    if a_class and b_principle:
        rows.extend(pg.fetch_all(
            """
            SELECT severity, mechanism, clinical_effect, recommendation,
                   source, source_ref, confidence,
                   principle_a, principle_b, class_a, class_b,
                   time_separation_minutes, separation_strategy, food_warning
            FROM aia_health_drug_interactions
            WHERE active = TRUE
              AND ((principle_a = %s AND class_b = %s)
                OR (class_a = %s AND principle_b = %s))
            """,
            (b_principle, a_class, a_class, b_principle),
        ))
    # class × class
    if a_class and b_class:
        ord_a, ord_b = sorted([a_class, b_class])
        rows.extend(pg.fetch_all(
            """
            SELECT severity, mechanism, clinical_effect, recommendation,
                   source, source_ref, confidence,
                   principle_a, principle_b, class_a, class_b,
                   time_separation_minutes, separation_strategy, food_warning
            FROM aia_health_drug_interactions
            WHERE active = TRUE
              AND ((class_a = %s AND class_b = %s)
                OR (class_a = %s AND class_b = %s))
            """,
            (ord_a, ord_b, ord_b, ord_a),
        ))
    # Dedupe por (mechanism, source)
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        key = (r["mechanism"], r["source"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def check_drug_interactions(
    new_principle: str | None,
    new_class: str | None,
    new_med_name: str,
    patient_id: str | None,
    new_times_of_day: list | None = None,
) -> list[DoseIssue]:
    """Cruza nova prescrição com schedules ativos do paciente.

    Para interações com `time_separation_minutes`:
      - Compara horários da nova prescrição vs schedule existente.
      - Se diff >= threshold → SILENCIA (resolvido por espaçamento).
      - Se diff < threshold → emite warning específico de espaçamento.
    Para interações sistêmicas (sem time_separation) → comportamento original.
    """
    if not new_principle and not new_class:
        return []
    if not patient_id:
        return []
    actives = _list_active_schedules(patient_id)
    if not actives:
        return []
    issues: list[DoseIssue] = []
    seen_pairs: set[tuple] = set()
    new_minutes = _times_to_minutes(new_times_of_day or [])

    for sch in actives:
        existing_principle = resolve_principle_active(sch["medication_name"])
        if not existing_principle:
            continue
        # Não cruza com ele mesmo (já tratado por duplicate_therapy)
        if existing_principle == new_principle:
            continue
        existing_meta = get_principle_meta(existing_principle)
        existing_class = (existing_meta or {}).get("therapeutic_class")
        rows = _query_interactions_pair(
            new_principle, new_class, existing_principle, existing_class,
        )
        for r in rows:
            sig = (existing_principle, r["mechanism"])
            if sig in seen_pairs:
                continue
            seen_pairs.add(sig)
            mapped = _INTERACTION_SEVERITY_MAP.get(r["severity"], "warning")
            label_existing = sch["medication_name"]
            sep_min = r.get("time_separation_minutes")

            # ── Caso 1: interação resolvível por espaçamento ──
            if sep_min:
                existing_minutes = _times_to_minutes(sch.get("times_of_day"))
                diff = _min_circular_diff(new_minutes, existing_minutes)
                if diff is not None and diff >= sep_min:
                    # Bem espaçado — silencia (informativo apenas pra audit)
                    issues.append(DoseIssue(
                        severity="info",
                        code="time_separation_ok",
                        message=(
                            f"✅ {new_med_name} × {label_existing}: já espaçados "
                            f"({_format_minutes(diff)} de diferença, mínimo "
                            f"{_format_minutes(sep_min)}). Sem alerta necessário."
                        ),
                        detail={
                            "existing": label_existing,
                            "diff_minutes": diff,
                            "required_minutes": sep_min,
                        },
                    ))
                    continue
                # Não espaçados o suficiente → emite warning específico
                strategy = r.get("separation_strategy") or "any"
                strategy_text = ""
                if strategy == "a_first":
                    first = r.get("principle_a") or r.get("class_a")
                    if first == new_principle:
                        strategy_text = f" Tome {new_med_name} primeiro, depois {label_existing}."
                    else:
                        strategy_text = f" Tome {label_existing} primeiro, depois {new_med_name}."
                elif strategy == "b_first":
                    second = r.get("principle_b") or r.get("class_b")
                    if second == new_principle:
                        strategy_text = f" Tome {label_existing} primeiro, depois {new_med_name}."
                    else:
                        strategy_text = f" Tome {new_med_name} primeiro, depois {label_existing}."
                food_extra = f" {r['food_warning']}" if r.get("food_warning") else ""
                # Mantém severity moderada/major mas com mensagem orientada
                msg_severity = "warning_strong" if r["severity"] in ("major","contraindicated") else "warning"
                issues.append(DoseIssue(
                    severity=msg_severity,
                    code="time_separation_required",
                    message=(
                        f"⏰ {new_med_name} × {label_existing}: "
                        f"{r['clinical_effect']} "
                        f"Espaçar pelo menos {_format_minutes(sep_min)}.{strategy_text}"
                        f"{food_extra} Fonte: {r['source']}."
                    ),
                    detail={
                        "existing": label_existing,
                        "current_diff_minutes": diff,
                        "required_minutes": sep_min,
                        "strategy": strategy,
                        "mechanism": r["mechanism"],
                        "source": r["source"],
                    },
                ))
                continue

            # ── Caso 2: interação sistêmica (sem espaçamento possível) ──
            issues.append(DoseIssue(
                severity=mapped,
                code="drug_interaction",
                message=(
                    f"💊 Interação ({r['severity']}): "
                    f"{new_med_name} × {label_existing} — {r['clinical_effect']} "
                    f"Conduta: {r['recommendation']} "
                    f"Fonte: {r['source']}."
                ),
                detail={
                    "existing": label_existing,
                    "existing_principle": existing_principle,
                    "new_principle": new_principle,
                    "mechanism": r["mechanism"],
                    "severity_raw": r["severity"],
                    "source": r["source"],
                    "source_ref": r.get("source_ref"),
                    "confidence": float(r.get("confidence") or 0.85),
                },
            ))
    return issues


# ─── F3: CONTRAINDICAÇÃO POR CONDIÇÃO ─────────────────────

def _normalize_condition(term: str | None) -> str | None:
    """Normaliza termo de condição via aliases (asma bronquica → asma)."""
    if not term:
        return None
    norm = normalize(term)
    if not norm:
        return None
    row = get_postgres().fetch_one(
        "SELECT canonical_term FROM aia_health_condition_aliases "
        "WHERE lower(alias) = %s LIMIT 1",
        (norm,),
    )
    if row:
        return row["canonical_term"]
    return norm


def _patient_condition_terms(patient: dict | None) -> list[str]:
    """Extrai lista de condições normalizadas. Suporta:
      • patient.conditions = [{"description": "Asma", "code": "J45"}, ...]
      • patient.conditions = ["Asma", "DPOC", ...]
    """
    if not patient:
        return []
    raw = patient.get("conditions") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            term = _normalize_condition(item)
        elif isinstance(item, dict):
            term = _normalize_condition(
                item.get("description") or item.get("name") or item.get("code")
            )
        else:
            term = None
        if term:
            out.append(term)
    return out


_CONDITION_SEVERITY_MAP = {
    "contraindicated": "block",
    "warning": "warning_strong",
    "caution": "warning",
}


def check_condition_contraindications(
    principle: str | None,
    therapeutic_class: str | None,
    patient: dict | None,
) -> list[DoseIssue]:
    """Cruza condições do paciente com tabela de contraindicações."""
    if not principle and not therapeutic_class:
        return []
    conditions = _patient_condition_terms(patient)
    if not conditions:
        return []
    pg = get_postgres()
    issues: list[DoseIssue] = []
    seen: set[tuple] = set()
    for cond in conditions:
        rows = pg.fetch_all(
            """
            SELECT condition_term, severity, rationale, recommendation,
                   source, source_ref, affected_principle_active,
                   affected_therapeutic_class
            FROM aia_health_condition_contraindications
            WHERE active = TRUE AND condition_term = %s
              AND ((affected_principle_active IS NOT NULL AND affected_principle_active = %s)
                OR (affected_therapeutic_class IS NOT NULL AND affected_therapeutic_class = %s))
            """,
            (cond, principle, therapeutic_class),
        )
        for r in rows:
            sig = (cond, r["severity"], r["rationale"][:40])
            if sig in seen:
                continue
            seen.add(sig)
            mapped = _CONDITION_SEVERITY_MAP.get(r["severity"], "warning")
            issues.append(DoseIssue(
                severity=mapped,
                code="condition_contraindicated",
                message=(
                    f"🩺 Paciente tem '{cond}' — {r['rationale']} "
                    f"Conduta: {r['recommendation']} Fonte: {r['source']}."
                ),
                detail={
                    "condition": cond,
                    "severity_raw": r["severity"],
                    "matched_via": "principle" if r.get("affected_principle_active") else "class",
                    "source": r["source"],
                },
            ))
    return issues


# ─── F3: ANTICHOLINERGIC BURDEN SCORE ─────────────────────

def check_anticholinergic_burden(
    new_principle: str | None,
    patient_id: str | None,
) -> list[DoseIssue]:
    """Soma score do paciente (existente + novo). ≥3 = warning."""
    if not patient_id:
        return []
    pg = get_postgres()
    actives = _list_active_schedules(patient_id)
    burdens = []
    for sch in actives:
        existing_principle = resolve_principle_active(sch["medication_name"])
        if not existing_principle:
            continue
        row = pg.fetch_one(
            "SELECT burden_score FROM aia_health_drug_anticholinergic_burden "
            "WHERE principle_active = %s AND active = TRUE",
            (existing_principle,),
        )
        if row and row["burden_score"] > 0:
            burdens.append((existing_principle, sch["medication_name"], row["burden_score"]))

    new_score = 0
    if new_principle:
        row = pg.fetch_one(
            "SELECT burden_score FROM aia_health_drug_anticholinergic_burden "
            "WHERE principle_active = %s AND active = TRUE",
            (new_principle,),
        )
        if row:
            new_score = int(row["burden_score"])

    total = sum(b[2] for b in burdens) + new_score
    if total < 3:
        return []
    sev = "warning_strong" if total >= 5 else "warning"
    components = [f"{name}({score})" for _, name, score in burdens]
    if new_score > 0:
        components.append(f"NOVO ({new_score})")
    return [DoseIssue(
        severity=sev,
        code="anticholinergic_burden",
        message=(
            f"🧠 Carga anticolinérgica acumulada: {total} pontos "
            f"({', '.join(components)}). Score ≥3 aumenta risco de delirium "
            "e queda em idoso (Boustani 2008)."
        ),
        detail={"total": total, "components": [
            {"principle": p, "name": n, "score": s} for p, n, s in burdens
        ], "new_score": new_score},
    )]


# ─── F3: FALL RISK SCORE ──────────────────────────────────

def check_fall_risk(
    new_principle: str | None,
    new_class: str | None,
    patient: dict | None,
) -> list[DoseIssue]:
    """Soma score de queda (existente + novo). ≥3 = warning, ≥5 = strong."""
    patient_id = (patient or {}).get("id")
    if not patient_id:
        return []
    pg = get_postgres()
    actives = _list_active_schedules(patient_id)

    def lookup_score(p: str | None, c: str | None) -> int:
        if not p and not c:
            return 0
        row = pg.fetch_one(
            """
            SELECT fall_risk_score FROM aia_health_drug_fall_risk
            WHERE active = TRUE
              AND (principle_active = %s OR therapeutic_class = %s)
            ORDER BY (principle_active = %s) DESC
            LIMIT 1
            """,
            (p, c, p),
        )
        return int(row["fall_risk_score"]) if row else 0

    components = []
    total = 0
    for sch in actives:
        existing_principle = resolve_principle_active(sch["medication_name"])
        existing_meta = get_principle_meta(existing_principle) if existing_principle else None
        existing_class = (existing_meta or {}).get("therapeutic_class")
        score = lookup_score(existing_principle, existing_class)
        if score > 0:
            components.append((sch["medication_name"], score))
            total += score

    new_score = lookup_score(new_principle, new_class)
    total_with_new = total + new_score

    # Bonus +2 se paciente tem histórico de queda registrado
    has_fall_history = "historico_queda" in _patient_condition_terms(patient)
    if has_fall_history:
        total_with_new += 2

    if total_with_new < 3:
        return []
    sev = "warning_strong" if total_with_new >= 5 else "warning"
    parts = [f"{name}({score})" for name, score in components]
    if new_score > 0:
        parts.append(f"NOVO ({new_score})")
    if has_fall_history:
        parts.append("histórico de queda (+2)")
    return [DoseIssue(
        severity=sev,
        code="fall_risk",
        message=(
            f"⚠️ Risco de queda acumulado: {total_with_new} pontos "
            f"({', '.join(parts) or 'soma de classes'}). "
            "Score ≥3 = atenção (STOPP 2023). Considerar desprescrição "
            "ou redução de doses."
        ),
        detail={"total": total_with_new, "components": components,
                "new_score": new_score, "fall_history": has_fall_history},
    )]


# ─── F4: AJUSTE RENAL (Cockcroft-Gault) ────────────────────

def calc_clcr_cockcroft_gault(
    age: int | None,
    weight_kg: float | None,
    serum_creatinine_mg_dl: float | None,
    is_female: bool = False,
) -> float | None:
    """Cockcroft-Gault em mL/min. None se faltar dado."""
    if not age or not weight_kg or not serum_creatinine_mg_dl:
        return None
    if serum_creatinine_mg_dl <= 0:
        return None
    clcr = ((140 - age) * float(weight_kg)) / (72.0 * float(serum_creatinine_mg_dl))
    if is_female:
        clcr *= 0.85
    return round(clcr, 1)


_RENAL_ACTION_MAP = {
    "avoid":              ("block",          "❌ NÃO usar"),
    "reduce_50pct":       ("warning_strong", "Reduzir dose 50%"),
    "reduce_75pct":       ("warning",        "Reduzir dose 25%"),
    "increase_interval":  ("warning_strong", "Aumentar intervalo entre doses"),
    "monitor":            ("warning",        "Monitorizar resposta + creatinina"),
    "no_adjustment":      (None, None),
}


def check_renal_adjustment(
    principle: str | None,
    patient: dict | None,
) -> list[DoseIssue]:
    """Calcula ClCr Cockcroft-Gault e busca regra de ajuste renal."""
    if not principle:
        return []
    age = _patient_age(patient)
    weight = (patient or {}).get("weight_kg")
    cr = (patient or {}).get("serum_creatinine_mg_dl")
    is_female = ((patient or {}).get("gender") or "").upper() == "F"

    clcr = calc_clcr_cockcroft_gault(age, weight, cr, is_female)
    if clcr is None:
        return [DoseIssue(
            severity="info",
            code="renal_adjust_no_data",
            message=(
                "Sem dados suficientes pra calcular ClCr (idade + peso + "
                "creatinina). Ajuste renal não verificado."
            ),
            detail={
                "missing": [
                    k for k, v in {
                        "age": age, "weight_kg": weight,
                        "serum_creatinine": cr,
                    }.items() if not v
                ]
            },
        )]

    rule = get_postgres().fetch_one(
        """
        SELECT clcr_min, clcr_max, action, rationale, source
        FROM aia_health_drug_renal_adjustments
        WHERE principle_active = %s AND active = TRUE
          AND %s >= clcr_min
          AND (clcr_max IS NULL OR %s < clcr_max)
        ORDER BY clcr_min DESC LIMIT 1
        """,
        (principle, clcr, clcr),
    )
    if not rule:
        return []
    sev, label = _RENAL_ACTION_MAP.get(rule["action"], (None, None))
    if not sev:
        return []
    return [DoseIssue(
        severity=sev,
        code="renal_adjustment",
        message=(
            f"🩺 ClCr calculado: {clcr} mL/min. {label} para {principle}: "
            f"{rule['rationale']} Fonte: {rule['source']}."
        ),
        detail={
            "clcr": clcr,
            "action": rule["action"],
            "principle": principle,
            "source": rule["source"],
        },
    )]


# ─── F5: AJUSTE HEPÁTICO (Child-Pugh) ────────────────────

# Severidade hepática inferida via conditions+aliases (sem campo
# estruturado nessa fase). Aliases mapeiam termos livres pra:
#   child_a (leve), child_b (moderada), child_c (grave),
#   hepatopatia_unspecified (sem qualificador → assume leve + warning).
_HEPATIC_SEVERITY_TERMS = {
    "child_a", "child_b", "child_c", "hepatopatia_unspecified",
}

# Termos genéricos de hepatopatia (sem qualificador) que tratamos como
# 'hepatopatia_unspecified' (regra mais conservadora + warning).
_HEPATIC_GENERIC_FALLBACK = {"hepatopatia"}


def _patient_hepatic_severity(patient: dict | None) -> str | None:
    """Examina conditions e retorna 'child_a'|'child_b'|'child_c'|
    'hepatopatia_unspecified'|None. Mais grave vence."""
    terms = set(_patient_condition_terms(patient))
    if not terms:
        return None
    # Ordem de prioridade: c > b > a > unspecified
    if "child_c" in terms:
        return "child_c"
    if "child_b" in terms:
        return "child_b"
    if "child_a" in terms:
        return "child_a"
    if "hepatopatia_unspecified" in terms:
        return "hepatopatia_unspecified"
    if terms & _HEPATIC_GENERIC_FALLBACK:
        return "hepatopatia_unspecified"
    return None


_HEPATIC_ACTION_MAP = {
    "avoid":             ("block",          "❌ NÃO usar"),
    "reduce_50pct":      ("warning_strong", "Reduzir dose 50%"),
    "reduce_75pct":      ("warning_strong", "Reduzir dose 75%"),
    "increase_interval": ("warning_strong", "Aumentar intervalo"),
    "caution_monitor":   ("warning",        "Usar com cautela + monitorização"),
    "no_adjustment":     (None, None),
}

_HEPATIC_LABEL = {
    "child_a": "Hepatopatia leve (Child-Pugh A)",
    "child_b": "Hepatopatia moderada (Child-Pugh B)",
    "child_c": "Hepatopatia grave (Child-Pugh C)",
    "hepatopatia_unspecified": "Hepatopatia (gravidade não especificada — assumindo leve)",
}


def check_hepatic_adjustment(
    principle: str | None,
    patient: dict | None,
) -> list[DoseIssue]:
    """Aplica regra de ajuste hepático conforme Child-Pugh do paciente."""
    if not principle:
        return []
    severity_class = _patient_hepatic_severity(patient)
    if not severity_class:
        return []

    rule = get_postgres().fetch_one(
        """
        SELECT severity_class, action, rationale, source, source_ref
        FROM aia_health_drug_hepatic_adjustments
        WHERE principle_active = %s AND severity_class = %s AND active = TRUE
        ORDER BY confidence DESC LIMIT 1
        """,
        (principle, severity_class),
    )
    issues: list[DoseIssue] = []

    # Quando paciente tem hepatopatia sem severidade especificada,
    # alertamos pra confirmar Child-Pugh independente da regra.
    if severity_class == "hepatopatia_unspecified":
        issues.append(DoseIssue(
            severity="info",
            code="hepatic_severity_unknown",
            message=(
                "🩺 Paciente tem hepatopatia mas a gravidade Child-Pugh "
                "não está especificada nas conditions. Assumindo "
                "compensada (leve). Cadastre 'cirrose Child A/B/C' ou "
                "'hepatopatia leve/moderada/grave' pra precisão."
            ),
            detail={"hepatic_severity": severity_class},
        ))

    if not rule:
        return issues

    sev, label = _HEPATIC_ACTION_MAP.get(rule["action"], (None, None))
    if not sev:
        return issues

    issues.append(DoseIssue(
        severity=sev,
        code="hepatic_adjustment",
        message=(
            f"🩺 {_HEPATIC_LABEL[severity_class]}. {label} para {principle}: "
            f"{rule['rationale']} Fonte: {rule['source']}."
        ),
        detail={
            "principle": principle,
            "severity_class": severity_class,
            "action": rule["action"],
            "source": rule["source"],
        },
    ))
    return issues


# ─── F4: SINAIS VITAIS ↔ MEDICAÇÃO ──────────────────────

_VITAL_OP = {
    "lt": lambda x, t: x < t,
    "le": lambda x, t: x <= t,
    "gt": lambda x, t: x > t,
    "ge": lambda x, t: x >= t,
}


def _latest_vitals(patient_id: str | None, window_minutes: int) -> dict | None:
    """Retorna dict com bp_systolic, bp_diastolic, heart_rate,
    temperature_celsius, oxygen_saturation, glucose_mg_dl. Busca em
    aia_health_vital_signs (modelo EAV: vital_type+value_numeric).

    Mapping vital_type → field:
        blood_pressure_composite → bp_systolic (value_numeric) +
                                   bp_diastolic (value_secondary)
        heart_rate              → heart_rate
        temperature             → temperature_celsius
        oxygen_saturation       → oxygen_saturation
        blood_glucose           → glucose_mg_dl
    Retorna a leitura mais recente de cada tipo dentro da janela.
    """
    if not patient_id:
        return None
    rows = get_postgres().fetch_all(
        """
        SELECT vital_type, value_numeric, value_secondary, measured_at
        FROM aia_health_vital_signs
        WHERE patient_id = %s
          AND measured_at >= NOW() - (%s || ' minutes')::interval
          AND vital_type IN ('blood_pressure_composite','heart_rate',
                             'temperature','oxygen_saturation','blood_glucose')
        ORDER BY measured_at DESC
        """,
        (patient_id, str(window_minutes)),
    )
    if not rows:
        return None
    out: dict = {}
    most_recent_at = None
    for r in rows:
        vt = r["vital_type"]
        if vt == "blood_pressure_composite":
            out.setdefault("bp_systolic", float(r["value_numeric"]))
            if r.get("value_secondary") is not None:
                out.setdefault("bp_diastolic", float(r["value_secondary"]))
        elif vt == "heart_rate":
            out.setdefault("heart_rate", float(r["value_numeric"]))
        elif vt == "temperature":
            out.setdefault("temperature_celsius", float(r["value_numeric"]))
        elif vt == "oxygen_saturation":
            out.setdefault("oxygen_saturation", float(r["value_numeric"]))
        elif vt == "blood_glucose":
            out.setdefault("glucose_mg_dl", float(r["value_numeric"]))
        if most_recent_at is None:
            most_recent_at = r["measured_at"]
    if most_recent_at is not None:
        out["recorded_at"] = most_recent_at
    return out or None


def check_vital_constraints(
    principle: str | None,
    therapeutic_class: str | None,
    patient: dict | None,
) -> list[DoseIssue]:
    """Cruza vitais recentes com regras drug_vital_constraints."""
    patient_id = (patient or {}).get("id")
    if not patient_id or (not principle and not therapeutic_class):
        return []
    pg = get_postgres()
    rules = pg.fetch_all(
        """
        SELECT principle_active, therapeutic_class, vital_field, operator,
               threshold, window_minutes, severity, rationale, recommendation,
               source, confidence
        FROM aia_health_drug_vital_constraints
        WHERE active = TRUE
          AND ((principle_active IS NOT NULL AND principle_active = %s)
            OR (therapeutic_class IS NOT NULL AND therapeutic_class = %s))
        """,
        (principle, therapeutic_class),
    )
    if not rules:
        return []
    issues: list[DoseIssue] = []
    # Cache de vitais por janela diferente
    vitals_cache: dict[int, dict | None] = {}
    for r in rules:
        window = int(r["window_minutes"])
        if window not in vitals_cache:
            vitals_cache[window] = _latest_vitals(patient_id, window)
        vitals = vitals_cache[window]
        if not vitals:
            continue
        field = r["vital_field"]
        value = vitals.get(field)
        if value is None:
            continue
        op = _VITAL_OP.get(r["operator"])
        if not op or not op(float(value), float(r["threshold"])):
            continue
        sev_map = {"block": "block", "warning_strong": "warning_strong", "warning": "warning"}
        issues.append(DoseIssue(
            severity=sev_map[r["severity"]],
            code="vital_constraint",
            message=(
                f"📈 Vital recente {field}={value} {r['operator']} {r['threshold']} — "
                f"{r['rationale']} Conduta: {r['recommendation']} "
                f"Fonte: {r['source']}."
            ),
            detail={
                "vital": field,
                "value": float(value),
                "threshold": float(r["threshold"]),
                "operator": r["operator"],
                "recorded_at": vitals.get("recorded_at").isoformat() if vitals.get("recorded_at") else None,
                "source": r["source"],
            },
        ))
    return issues


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
    issues.extend(check_drug_interactions(
        principle, therapeutic_class, medication_name, patient_id,
        new_times_of_day=times_of_day,
    ))
    issues.extend(check_condition_contraindications(principle, therapeutic_class, patient))
    issues.extend(check_anticholinergic_burden(principle, patient_id))
    issues.extend(check_fall_risk(principle, therapeutic_class, patient))
    issues.extend(check_renal_adjustment(principle, patient))
    issues.extend(check_hepatic_adjustment(principle, patient))
    issues.extend(check_vital_constraints(principle, therapeutic_class, patient))

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
