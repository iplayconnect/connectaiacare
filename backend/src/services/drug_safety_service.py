"""DrugSafetyService — Knowledge Graph farmacológico pra cuidado geriátrico.

⚠️  AVISO CLÍNICO IMPORTANTE:
Este serviço é MVP open-source. Cobertura ~30 drugs prioritários (Beers
2023 + Anvisa top BR). NÃO substitui parecer médico. Sofia DEVE indicar
quando informação não está no banco e escalar pra humano.

API pública:
    svc = get_drug_safety_service()

    # Lookup por nome (genérico ou comercial)
    drug = svc.lookup_drug("Atenolol")            # ou "Tenoblock"
    drug = svc.lookup_drug("ATENOLOL")            # case-insensitive
    drug = svc.lookup_drug("atenolol", record_gap_if_missing=True)

    # Beers Criteria flags pra um drug
    flags = svc.check_beers_for_drug(drug["id"], patient_age=80, conditions=["dementia"])

    # Interações entre N drugs (canonicaliza par a par)
    interactions = svc.check_interactions([drug_a_id, drug_b_id, drug_c_id])

    # Review completo de uma lista de medicamentos
    review = svc.safety_review(
        ["Atenolol 50mg", "Diazepam 5mg", "Sertralina 50mg"],
        patient_age=82, conditions=["dementia", "falls_history"],
    )
    # → {flags: [...], interactions: [...], gaps: [...], summary: "..."}

Policy de gaps:
    Quando lookup_drug() não acha o medicamento, opcional record_gap=True
    salva em aia_health_drug_lookup_gaps pra priorizar curadoria.
    Sofia deve responder com hedge ("não tenho info confiável sobre X")
    e escalar pra humano se relato envolve drug não-cadastrado em
    contexto crítico.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_drug_name(name: str) -> str:
    """Lowercase + remove acentos. Pra match resiliente entre 'Atenolol',
    'ATENOLOL', 'atenolol'. Brand names também passam por isso quando
    armazenados (mas no array brand_names mantemos forma original)."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name.strip())
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower()


def _extract_drug_name_from_mention(raw: str) -> str:
    """Extrai nome de drug de menção informal.

    'Atenolol 50mg'              → 'Atenolol'
    'tomou losartana 25 mg'      → 'losartana'
    'ela toma diazepam pra dor'  → 'diazepam'

    Heurística simples — primeira palavra com letra maiúscula OU primeiro
    token >= 4 chars. Pra casos complexos, LLM (Med-Gemini) deveria
    pré-processar e extrair entidades farmacológicas estruturadas.
    """
    if not raw:
        return ""
    # Remove dose/unidade pra simplificar
    import re
    cleaned = re.sub(r"\b\d+\s*(mg|mcg|g|ml|ui|comp|gota[s]?)\b", "", raw, flags=re.IGNORECASE)
    # Pega primeira palavra com >=4 chars que parece drug name
    tokens = [t for t in re.split(r"[\s,;.()]+", cleaned) if len(t) >= 4]
    return tokens[0] if tokens else raw.strip()


class DrugSafetyService:
    """Knowledge Graph queries pra farmacovigilância em geriatria."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            self._db = get_postgres()
        return self._db

    # ─── LOOKUP ────────────────────────────────────────────────

    def lookup_drug(
        self,
        name_or_brand: str,
        *,
        record_gap_if_missing: bool = False,
        tenant_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Busca drug por generic_name OR brand_names. Case-insensitive.

        Args:
            name_or_brand: pode ser generic ("Atenolol") ou brand ("Atenol",
                "Tenoblock"). Aceita menção informal ("ela toma atenolol pra pressão")
                — extrai o nome via heurística simples.
            record_gap_if_missing: se True E não achar, registra em
                aia_health_drug_lookup_gaps pra priorização de curadoria.

        Returns:
            dict com colunas de aia_health_drug_catalog OR None se não achou.
        """
        if not name_or_brand:
            return None

        # Tenta primeiro nome direto, depois extração heurística
        candidates = [name_or_brand.strip()]
        extracted = _extract_drug_name_from_mention(name_or_brand)
        if extracted and extracted != name_or_brand.strip():
            candidates.append(extracted)

        db = self._get_db()
        for candidate in candidates:
            normalized = _normalize_drug_name(candidate)
            if not normalized or len(normalized) < 3:
                continue
            # Match exato em generic_name_normalized
            row = db.fetch_one(
                """SELECT id::text, rxnorm_cui, atc_code, generic_name,
                          generic_name_normalized, brand_names,
                          therapeutic_class, pharmacologic_class,
                          is_psychotropic, is_controlled,
                          source, source_ref, requires_clinical_review, notes
                   FROM aia_health_drug_catalog
                   WHERE generic_name_normalized = %s""",
                (normalized,),
            )
            if row:
                return row
            # Match em brand_names (array contains, case-sensitive — brands têm caps)
            row = db.fetch_one(
                """SELECT id::text, rxnorm_cui, atc_code, generic_name,
                          generic_name_normalized, brand_names,
                          therapeutic_class, pharmacologic_class,
                          is_psychotropic, is_controlled,
                          source, source_ref, requires_clinical_review, notes
                   FROM aia_health_drug_catalog
                   WHERE EXISTS (
                       SELECT 1 FROM unnest(brand_names) AS b
                       WHERE LOWER(b) = LOWER(%s)
                   )""",
                (candidate,),
            )
            if row:
                return row

        # Não achou — registra gap se solicitado
        if record_gap_if_missing:
            self._record_gap(name_or_brand, tenant_id=tenant_id)
        return None

    def _record_gap(self, raw_mention: str, *, tenant_id: Optional[str] = None):
        """Registra ou incrementa contador de drug perguntado mas ausente."""
        try:
            normalized = _normalize_drug_name(_extract_drug_name_from_mention(raw_mention))
            if not normalized or len(normalized) < 2:
                return
            self._get_db().execute(
                """INSERT INTO aia_health_drug_lookup_gaps
                       (raw_drug_mention, normalized_query, tenant_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (normalized_query, tenant_id) DO UPDATE
                     SET occurrences = aia_health_drug_lookup_gaps.occurrences + 1,
                         last_seen = NOW()""",
                (raw_mention[:200], normalized, tenant_id),
            )
        except Exception as exc:
            logger.warning("drug_gap_record_failed", error=str(exc)[:120])

    # ─── BEERS CRITERIA ────────────────────────────────────────

    def check_beers_for_drug(
        self,
        drug_id: str,
        *,
        patient_age: Optional[int] = None,
        conditions: Optional[list[str]] = None,
    ) -> list[dict]:
        """Retorna flags Beers aplicáveis a um drug, filtradas por contexto.

        Args:
            drug_id: UUID do drug (de lookup_drug)
            patient_age: pra filtrar (Beers aplica ≥65 — abaixo disso filtra
                category='avoid_in_elderly'; outras categories continuam relevantes)
            conditions: lista normalizada (ex: ['dementia', 'CKD', 'falls_history'])
                — flags com 'avoid_with_condition' são filtradas pra match.

        Returns:
            list de flags ordenadas por severity (high → low).
        """
        flags = self._get_db().fetch_all(
            """SELECT id::text, category, severity, evidence_quality,
                      recommendation_strength, rationale, clinical_consequences,
                      conditions, alternatives, source_ref
               FROM aia_health_beers_flags
               WHERE drug_id = %s
               ORDER BY CASE severity
                   WHEN 'high' THEN 1
                   WHEN 'moderate' THEN 2
                   WHEN 'low' THEN 3
               END""",
            (drug_id,),
        )
        if not flags:
            return []

        # Filtros contextuais
        result = []
        conditions_set = set((conditions or []))
        for f in flags:
            cat = f.get("category")
            # Beers "avoid_in_elderly" só relevante se ≥65 anos
            if cat == "avoid_in_elderly" and patient_age is not None and patient_age < 65:
                continue
            # "avoid_with_condition" — só inclui se paciente tem condition match
            if cat == "avoid_with_condition" and f.get("conditions"):
                if not (conditions_set & set(f["conditions"])):
                    continue
            result.append(f)
        return result

    # ─── INTERACTIONS ──────────────────────────────────────────

    def check_interactions(self, drug_ids: list[str]) -> list[dict]:
        """Retorna interações entre cada par (i, j) com i < j na lista.

        Canonicaliza par a par antes de query (drug_a_id < drug_b_id no schema).

        Args:
            drug_ids: lista de UUIDs (mín 2 pra ter interações)

        Returns:
            list de interações com severity, description, clinical_management,
            ordenadas por severity (contraindicated → minor).
        """
        if not drug_ids or len(drug_ids) < 2:
            return []

        # Gera todos os pares canonicalizados (a < b) sem duplicar
        pairs: set[tuple[str, str]] = set()
        for i, a in enumerate(drug_ids):
            for b in drug_ids[i + 1:]:
                if a == b:
                    continue
                # Canonical: menor UUID primeiro
                lo, hi = (a, b) if a < b else (b, a)
                pairs.add((lo, hi))
        if not pairs:
            return []

        # Query batch — psycopg2 aceita VALUES com listas
        rows = []
        for lo, hi in pairs:
            r = self._get_db().fetch_one(
                """SELECT i.id::text, i.severity, i.mechanism_type,
                          i.description, i.clinical_management, i.onset,
                          i.documentation, i.source, i.source_ref,
                          a.generic_name AS drug_a_name,
                          b.generic_name AS drug_b_name
                   FROM aia_health_drug_interactions i
                   JOIN aia_health_drug_catalog a ON a.id = i.drug_a_id
                   JOIN aia_health_drug_catalog b ON b.id = i.drug_b_id
                   WHERE i.drug_a_id = %s AND i.drug_b_id = %s""",
                (lo, hi),
            )
            if r:
                rows.append(r)

        # Ordena por severity
        sev_order = {"contraindicated": 0, "major": 1, "moderate": 2, "minor": 3}
        rows.sort(key=lambda r: sev_order.get(r.get("severity"), 99))
        return rows

    # ─── REVIEW INTEGRADO ──────────────────────────────────────

    def safety_review(
        self,
        medication_mentions: list[str],
        *,
        patient_age: Optional[int] = None,
        conditions: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> dict:
        """Review completo de uma lista de medicamentos (mentions informais).

        Faz lookup → Beers flags → interações de uma vez. Resultado pronto
        pra prompt da Sofia (alimentar contexto antes de gerar resposta).

        Args:
            medication_mentions: lista de strings informais
                (ex: ['Atenolol 50mg', 'tomou diazepam ontem'])
            patient_age: opcional, melhora filtros Beers
            conditions: lista normalizada (ex: ['dementia'])
            tenant_id: pra registro de gaps por tenant

        Returns:
            dict {
                'recognized': [...drugs encontrados],
                'gaps': [...mentions que não bateram em nada],
                'beers_flags': [...com drug name],
                'interactions': [...],
                'has_high_severity': bool,
                'requires_human_review': bool,
            }
        """
        recognized = []
        gaps = []
        for mention in medication_mentions:
            drug = self.lookup_drug(
                mention, record_gap_if_missing=True, tenant_id=tenant_id,
            )
            if drug:
                recognized.append({"mention": mention, **drug})
            else:
                gaps.append(mention)

        # Beers flags (pra cada drug recognized)
        beers = []
        for d in recognized:
            flags = self.check_beers_for_drug(
                d["id"], patient_age=patient_age, conditions=conditions,
            )
            for f in flags:
                beers.append({"drug_name": d["generic_name"], **f})

        # Interactions (entre os drugs recognized)
        interactions = self.check_interactions([d["id"] for d in recognized])

        # Severity bookkeeping
        has_high = (
            any(f["severity"] == "high" for f in beers)
            or any(i["severity"] in ("contraindicated", "major") for i in interactions)
        )
        # Sempre precisa review humano em MVP — flag forte
        requires_review = (
            has_high
            or len(gaps) > 0  # gap = drug desconhecido = precisa humano
            or any(d.get("requires_clinical_review") for d in recognized)
        )

        return {
            "recognized": recognized,
            "gaps": gaps,
            "beers_flags": beers,
            "interactions": interactions,
            "has_high_severity": has_high,
            "requires_human_review": requires_review,
        }


_instance: Optional[DrugSafetyService] = None


def get_drug_safety_service() -> DrugSafetyService:
    global _instance
    if _instance is None:
        _instance = DrugSafetyService()
    return _instance
