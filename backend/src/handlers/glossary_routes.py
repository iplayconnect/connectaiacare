"""Endpoint público de glossário de acrônimos médicos.

Expõe `backend/src/data/medical_acronyms.yaml` como JSON pra que o
frontend não precise duplicar a lista. Cache server-side via lru_cache
do medical_acronyms.py — load do YAML 1x por processo.

Decisão Henrique 2026-05-09: glossário central é fonte de verdade.
Frontend faz fetch ao montar e tem fallback hardcoded caso API falhe.

Acesso: qualquer usuário logado (super_admin, admin_tenant, medico,
enfermeiro, cuidador_pro, etc.). Não é dado sensível.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from src.utils.medical_acronyms import (
    all_categories,
    list_acronyms,
    lookup,
)

bp = Blueprint("glossary", __name__)


@bp.get("/api/glossary")
def get_glossary():
    """Retorna lista plana de acrônimos.

    Query params:
        category: filtra por uma categoria específica (vital_signs,
            comorbidities, events_acute, functional,
            medications_therapeutics, regulatory, org, care_categories)

    Resposta:
        {
          "status": "ok",
          "count": N,
          "items": [
            {
              "acronym": "PA",
              "full_pt": "Pressão Arterial",
              "full_en": "Blood Pressure",
              "category": "vital_signs",
              "notes": "..." (opcional)
            },
            ...
          ],
          "categories": ["vital_signs", "comorbidities", ...]
        }
    """
    category = request.args.get("category") or None
    items = list_acronyms(category=category)
    return jsonify({
        "status": "ok",
        "count": len(items),
        "items": items,
        "categories": all_categories(),
    })


@bp.get("/api/glossary/<acronym>")
def get_acronym(acronym: str):
    """Lookup individual. Retorna entry ou 404."""
    entry = lookup(acronym)
    if not entry:
        return jsonify({
            "status": "error", "reason": "not_found",
            "acronym": acronym,
        }), 404
    return jsonify({"status": "ok", "entry": entry})
