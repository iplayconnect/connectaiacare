"""Gerenciamento e matching de pacientes."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from uuid import UUID

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _serialize_row(row: dict | None) -> dict | None:
    """Converte tipos não-JSON-serializáveis (datetime, time, date, UUID) pra
    string. Necessário porque migration 040 adicionou colunas TIME em
    aia_health_patients (preferred_call_window_*) que Flask jsonify não sabe
    serializar nativamente."""
    if not row:
        return row
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):  # datetime, date, time → ISO 8601 string
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
    return out


class PatientService:
    def __init__(self):
        self.db = get_postgres()

    def get_by_id(self, patient_id: str) -> dict | None:
        row = self.db.fetch_one(
            "SELECT * FROM aia_health_patients WHERE id = %s AND active = TRUE", (patient_id,)
        )
        return _serialize_row(row)

    def list_all(self, tenant_id: str) -> list[dict]:
        rows = self.db.fetch_all(
            "SELECT * FROM aia_health_patients WHERE tenant_id = %s AND active = TRUE ORDER BY full_name",
            (tenant_id,),
        )
        return [_serialize_row(r) for r in (rows or [])]

    def search_by_name(self, tenant_id: str, query: str, limit: int = 5) -> list[dict]:
        """Busca paciente por nome com fuzzy matching.

        Estratégia:
        1. Tenta similarity via pg_trgm (rápido).
        2. Ranqueia resultados por SequenceMatcher em Python (mais preciso).
        """
        if not query:
            return []

        q_norm = _normalize(query)

        rows = self.db.fetch_all(
            """
            SELECT *, similarity(full_name, %s) AS sim
            FROM aia_health_patients
            WHERE tenant_id = %s
              AND active = TRUE
              AND (
                full_name ILIKE '%%' || %s || '%%'
                OR nickname ILIKE '%%' || %s || '%%'
                OR similarity(full_name, %s) > 0.15
              )
            ORDER BY sim DESC NULLS LAST
            LIMIT %s
            """,
            (query, tenant_id, query, query, query, limit * 3),
        )

        scored: list[tuple[float, dict]] = []
        for r in rows:
            name_norm = _normalize(r.get("full_name") or "")
            nick_norm = _normalize(r.get("nickname") or "")
            score_name = SequenceMatcher(None, q_norm, name_norm).ratio()
            score_nick = SequenceMatcher(None, q_norm, nick_norm).ratio() if nick_norm else 0.0
            if q_norm and (q_norm in name_norm or (nick_norm and q_norm in nick_norm)):
                score_name = max(score_name, 0.85)
            score = max(score_name, score_nick)
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [{**r, "match_score": round(s, 3)} for s, r in scored[:limit]]

    def best_match(self, tenant_id: str, query: str, threshold: float = 0.55) -> dict | None:
        if not query:
            return None
        results = self.search_by_name(tenant_id, query, limit=3)
        if not results:
            return None
        top = results[0]
        if top.get("match_score", 0) < threshold:
            return None
        return top


_patient_instance: PatientService | None = None


def get_patient_service() -> PatientService:
    global _patient_instance
    if _patient_instance is None:
        _patient_instance = PatientService()
    return _patient_instance
