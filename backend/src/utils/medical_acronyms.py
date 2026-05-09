"""Glossário de acrônimos médicos — utilitário compartilhado.

Decisão Henrique 2026-05-09: sempre escrever termo completo seguido do
acrônimo entre parênteses na primeira menção. Pessoas fora da área da
saúde (familiares, gestores, operadores) não devem ficar perdidas.

Uso típico:
    from src.utils.medical_acronyms import format_term, glossary_for_prompt

    # Formata individual
    format_term("PA")  # → "Pressão Arterial (PA)"
    format_term("FC")  # → "Frequência Cardíaca (FC)"

    # Bloco pra injetar em prompt
    block = glossary_for_prompt(category="vital_signs")

YAML em src/data/medical_acronyms.yaml é a fonte de verdade.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_GLOSSARY_PATH = Path(__file__).parent.parent / "data" / "medical_acronyms.yaml"


@lru_cache(maxsize=1)
def _load_glossary() -> dict[str, list[dict[str, Any]]]:
    """Carrega YAML 1x (cached). Retorna dict por categoria."""
    if not _GLOSSARY_PATH.exists():
        return {}
    with open(_GLOSSARY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def _flat_index() -> dict[str, dict[str, Any]]:
    """Index plano acrônimo → entry. Tolera variações de case
    (ex: PA, pa, Pa todos → mesma entry)."""
    out: dict[str, dict[str, Any]] = {}
    for category, entries in _load_glossary().items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            ac = (entry.get("acronym") or "").strip()
            if not ac:
                continue
            entry_with_cat = {**entry, "category": category}
            out[ac] = entry_with_cat
            out[ac.lower()] = entry_with_cat
            out[ac.upper()] = entry_with_cat
    return out


def lookup(acronym: str) -> dict[str, Any] | None:
    """Retorna entry do glossário ou None."""
    if not acronym:
        return None
    idx = _flat_index()
    return (
        idx.get(acronym.strip())
        or idx.get(acronym.strip().lower())
        or idx.get(acronym.strip().upper())
    )


def format_term(acronym: str, *, lang: str = "pt") -> str:
    """Retorna 'Termo Completo (ACR)'. Fallback: só o acrônimo se
    desconhecido."""
    entry = lookup(acronym)
    if not entry:
        return acronym
    full = entry.get("full_pt") if lang == "pt" else entry.get("full_en")
    if not full:
        return acronym
    canonical_acronym = entry.get("acronym") or acronym
    return f"{full} ({canonical_acronym})"


def glossary_for_prompt(
    *,
    category: str | None = None,
    lang: str = "pt",
) -> str:
    """Bloco de texto pronto pra injetar em prompt LLM.

    Se category=None, retorna todas. Se category='vital_signs',
    retorna só dessa categoria.

    Exemplo de output:
        Glossário de termos médicos (use sempre 'Termo Completo (ACR)'):
          - PA: Pressão Arterial
          - FC: Frequência Cardíaca
          - ...
    """
    glossary = _load_glossary()
    lines: list[str] = [
        "Glossário de acrônimos (escreva termo completo seguido do "
        "acrônimo entre parênteses na PRIMEIRA menção; subsequentes "
        "podem usar só acrônimo):",
    ]
    categories = [category] if category else list(glossary.keys())
    full_field = "full_pt" if lang == "pt" else "full_en"
    for cat in categories:
        entries = glossary.get(cat) or []
        if not entries:
            continue
        for entry in entries:
            ac = entry.get("acronym")
            full = entry.get(full_field)
            if ac and full:
                lines.append(f"  - {ac}: {full}")
    return "\n".join(lines)


def all_categories() -> list[str]:
    return list(_load_glossary().keys())


def list_acronyms(category: str | None = None) -> list[dict[str, Any]]:
    """Lista entries — útil pra exposição via API."""
    glossary = _load_glossary()
    if category:
        entries = glossary.get(category) or []
        return [{**e, "category": category} for e in entries]
    out: list[dict[str, Any]] = []
    for cat, entries in glossary.items():
        for e in entries:
            out.append({**e, "category": cat})
    return out
