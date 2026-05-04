"""Test matriz de routing do sub-agent factory.

Valida que `get_agent_for(is_anonymous, profile, intent)` retorna o agent
correto pra TODAS as combinações relevantes. Roda sem dependências de prod
(SDK Anthropic etc — só importa factory).

Usado pra cobertura de teste antes de mexer no roteamento + smoke pra
garantir que mudanças futuras no factory não quebrem cenários conhecidos.

Uso:
    docker exec connectaiacare-api python /app/scripts/test_agent_routing.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, "/app")

from src.services.sofia_agents.factory import get_agent_for


# Casos: (is_anonymous, profile, intent, expected_agent_name, descrição)
CASES = [
    # ─── Anonymous (sem identidade resolvida) ──────────
    (True,  None, "interesse_servico_b2c",        "commercial", "Lead anônimo B2C interessado"),
    (True,  None, "interesse_servico_b2b",        "commercial", "Lead anônimo B2B"),
    (True,  None, "agendar_demo",                 "commercial", "Anonymous quer agendar demo"),
    (True,  None, "suporte_cliente",              "support",    "Anonymous busca suporte"),
    (True,  None, "spam_abuso",                   "commercial", "Anonymous spam (silenciar)"),
    (True,  None, "unclear",                      "commercial", "Anonymous intent indefinido (clarifica)"),
    (True,  None, None,                           "commercial", "Anonymous sem intent classificado"),

    # ─── Identificados (profile resolvido) ──────────
    # Independente de intent, vão pro pipeline legacy
    (False, "familia",       None,                "passthrough_legacy", "Familiar identificado"),
    (False, "familia",       "interesse_servico_b2c", "passthrough_legacy", "Familiar com pergunta comercial"),
    (False, "cuidador_pro",  None,                "passthrough_legacy", "Cuidador profissional"),
    (False, "cuidador_pro",  "agendar_demo",      "passthrough_legacy", "Cuidador pedindo demo"),
    (False, "medico",        None,                "passthrough_legacy", "Médico identificado"),
    (False, "enfermeiro",    None,                "passthrough_legacy", "Enfermeiro identificado"),
    (False, "paciente_b2c",  None,                "passthrough_legacy", "Paciente B2C identificado"),
    (False, "gestor_ilpi",   None,                "passthrough_legacy", "Gestor ILPI identificado"),
    (False, "admin_tenant",  None,                "passthrough_legacy", "Admin tenant identificado"),
]


def run():
    print("=" * 80)
    print(f"Test matriz routing factory.get_agent_for ({len(CASES)} casos)")
    print("=" * 80)
    print()

    passed = 0
    failed = 0
    for is_anon, profile, intent, expected, desc in CASES:
        agent = get_agent_for(
            is_anonymous=is_anon, profile=profile, intent=intent,
        )
        actual = agent.name
        ok = actual == expected
        status = "✓" if ok else "✗"
        anon_str = "anon" if is_anon else f"id:{profile}"
        intent_str = intent or "<None>"
        print(f"  [{status}] {anon_str:18s} intent={intent_str:25s} → {actual:11s}  ({desc})")
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"       ESPERADO: {expected}")

    print()
    print(f"Result: {passed}/{len(CASES)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run()
