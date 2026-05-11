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

    # ──────────────────────────────────────────────────────────────
    # Create — paciente novo do zero (não importado)
    # ──────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        tenant_id: str,
        full_name: str,
        nickname: str | None = None,
        cpf: str | None = None,
    ) -> dict | None:
        """Cria paciente "stub" mínimo. Usado pelo botão "Novo paciente"
        antes de abrir o wizard de cadastro completo, que vai preencher
        o resto via /api/patients/<id>/registration/save.

        CPF é normalizado pra dígitos. Conditions/medications/allergies
        ficam em '[]' e serão preenchidos pelo wizard.
        """
        import re as _re
        cpf_clean = _re.sub(r"\D", "", cpf) if cpf else None
        if cpf_clean == "":
            cpf_clean = None

        row = self.db.fetch_one(
            """INSERT INTO aia_health_patients
                (tenant_id, full_name, nickname, cpf,
                 conditions, medications, allergies,
                 active, created_at, updated_at)
               VALUES (%s, %s, %s, %s,
                       '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                       TRUE, NOW(), NOW())
               RETURNING *""",
            (tenant_id, full_name.strip(), (nickname or None), cpf_clean),
        )
        return _serialize_row(row)

    # ──────────────────────────────────────────────────────────────
    # Update — campos editáveis pelo painel admin
    # ──────────────────────────────────────────────────────────────
    # Whitelist explícita pra evitar update de tenant_id/id/created_at
    # via mass-assignment.
    EDITABLE_FIELDS = {
        "full_name", "nickname", "birth_date", "gender",
        "photo_url", "photo_local_path",
        "care_unit", "room_number", "care_level",
        "conditions", "medications", "allergies", "responsible",
        "metadata",
        # Campos novos (migrations 053, 054)
        "preferred_form_of_address", "is_self_reporting", "cpf",
        # Mapping Tecnosenior — só super_admin deveria mexer em
        # produção; por enquanto liberamos no PATCH e a UI controla.
        "tecnosenior_patient_id",
    }

    JSONB_FIELDS = {
        "conditions", "medications", "allergies",
        "responsible", "metadata",
    }

    def update(
        self, patient_id: str, fields: dict[str, object],
    ) -> dict | None:
        """UPDATE explícito por id. Filtra fields whitelist + serializa
        JSONB. Retorna o paciente atualizado ou None se não existir.

        Aceita CPF com ou sem máscara — normaliza pra dígitos.
        """
        sets: list[str] = []
        params: list[object] = []
        import json as _json
        import re as _re

        for k, v in (fields or {}).items():
            if k not in self.EDITABLE_FIELDS:
                continue
            if k == "cpf" and v is not None:
                # Remove caracteres não-dígitos (Matheus aceita do lado dele,
                # nós já guardamos limpo pra match consistente)
                v = _re.sub(r"\D", "", str(v))
                if not v:
                    v = None
            if k in self.JSONB_FIELDS and v is not None:
                v = self.db.json_adapt(v) if hasattr(self.db, "json_adapt") \
                    else _json.dumps(v)
            sets.append(f"{k} = %s")
            params.append(v)

        if not sets:
            return self.get_by_id(patient_id)

        sets.append("updated_at = NOW()")
        params.append(patient_id)
        sql = (
            f"UPDATE aia_health_patients SET {', '.join(sets)} "
            f"WHERE id = %s RETURNING *"
        )
        row = self.db.fetch_one(sql, tuple(params))
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
