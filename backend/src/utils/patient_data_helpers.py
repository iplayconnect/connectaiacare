"""Helpers tolerantes pra ler conditions/medications/allergies de paciente.

Decisão Alexandre+Henrique 2026-05-09:
    Schema antigo: campos JSONB são arrays de strings simples
        ["Hipertensão", "Diabetes"]
    Schema novo: arrays de objetos com provenance
        [{"name": "Hipertensão", "source": "self_declared", "declared_at": ...,
          "declared_by_user_id": "...", "verified_by_clinician_at": null}, ...]

    Migração lazy — só converte ao paciente editar. Helpers leem AMBOS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_clinical_item(
    item: Any,
    *,
    default_source: str = "tecnosenior_import",
    default_user_id: str | None = None,
) -> dict[str, Any]:
    """Converte item antigo (string) ou novo (dict) pra formato canônico.

    Item antigo: "Hipertensão" → {name: "Hipertensão", source: ..., ...}
    Item novo: {name, source, ...} → mantém + completa campos faltantes
    """
    if isinstance(item, str):
        return {
            "name": item.strip(),
            "source": default_source,
            "original_source": default_source,
            "declared_at": _now_iso(),
            "declared_by_user_id": default_user_id,
            "verified_by_clinician_at": None,
            "verified_by_user_id": None,
        }

    if not isinstance(item, dict):
        return {
            "name": str(item),
            "source": default_source,
            "original_source": default_source,
            "declared_at": _now_iso(),
            "declared_by_user_id": default_user_id,
            "verified_by_clinician_at": None,
            "verified_by_user_id": None,
        }

    out: dict[str, Any] = {
        "name": (item.get("name") or "").strip(),
        "source": item.get("source") or default_source,
        "original_source": item.get("original_source") or item.get("source") or default_source,
        "declared_at": item.get("declared_at") or _now_iso(),
        "declared_by_user_id": item.get("declared_by_user_id") or default_user_id,
        "verified_by_clinician_at": item.get("verified_by_clinician_at"),
        "verified_by_user_id": item.get("verified_by_user_id"),
    }
    # Preserva campos extras específicos (dose pra medicação, severity pra alergia, etc.)
    for k in ("dose", "frequency", "since", "notes", "severity", "reaction_type",
              "icd10_code", "category", "confirmed_by_self_at"):
        if k in item:
            out[k] = item[k]
    return out


def normalize_clinical_array(
    arr: Any,
    *,
    default_source: str = "tecnosenior_import",
    default_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Aceita array vazio, None, lista de strings, lista de dicts, mix."""
    if not arr:
        return []
    if not isinstance(arr, (list, tuple)):
        return []
    return [
        normalize_clinical_item(it, default_source=default_source, default_user_id=default_user_id)
        for it in arr
    ]


def extract_names(arr: Any) -> list[str]:
    """Lista só os nomes (pra match de cross-validation, prompts, etc.).
    Aceita formato antigo (string) e novo (dict)."""
    if not arr:
        return []
    out: list[str] = []
    for it in arr:
        if isinstance(it, str):
            n = it.strip()
            if n:
                out.append(n)
        elif isinstance(it, dict):
            n = (it.get("name") or "").strip()
            if n:
                out.append(n)
    return out


def has_been_clinically_verified(item: Any) -> bool:
    """True se o item tem verified_by_clinician_at preenchido."""
    if isinstance(item, dict):
        return bool(item.get("verified_by_clinician_at"))
    return False


def filter_by_source(arr: Any, source: str) -> list[dict[str, Any]]:
    """Filtra items por source (ex: só self_declared)."""
    out: list[dict[str, Any]] = []
    for it in arr or []:
        if isinstance(it, dict) and it.get("source") == source:
            out.append(it)
    return out


def merge_items(
    existing: list[Any],
    new_items: list[dict[str, Any]],
    *,
    by_field: str = "name",
) -> list[dict[str, Any]]:
    """Faz merge by-name: items existentes preservam metadata histórica;
    items novos sobrescrevem campos atuais (source, declared_at).

    Útil quando paciente atualiza algo que já existia: a gente
    preserva original_source e adiciona confirmed_by_self_at."""
    existing_norm = normalize_clinical_array(existing)
    by_key: dict[str, dict[str, Any]] = {
        (it.get(by_field) or "").lower(): it for it in existing_norm
    }
    for new in new_items:
        key = (new.get(by_field) or "").lower()
        if key in by_key:
            old = by_key[key]
            # Preserva original_source se já existe
            new["original_source"] = old.get("original_source") or old.get("source")
            # Preserva verifications se não foram desfeitas
            if not new.get("verified_by_clinician_at") and old.get("verified_by_clinician_at"):
                new["verified_by_clinician_at"] = old["verified_by_clinician_at"]
                new["verified_by_user_id"] = old["verified_by_user_id"]
            by_key[key] = new
        else:
            by_key[key] = new
    return list(by_key.values())
