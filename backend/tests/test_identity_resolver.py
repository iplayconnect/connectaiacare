"""Tests pra IdentityResolver — phone normalization + match selection.

Foca em lógica pura (normalização, variantes, primary selection).
DB lookups testados em integration test separado.
"""
from __future__ import annotations

import pytest

from src.services.identity_resolver import (
    Identity,
    IdentityMatch,
    IdentityResolver,
    normalize_phone_e164_br,
    phone_variants_for_match,
)


# ──────────────────────────────────────────────────────────────────
# normalize_phone_e164_br
# ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    # Formatos limpos
    ("5551999482737", "5551999482737"),
    ("555199482737", "555199482737"),
    # Com DDI explícito +
    ("+5551999482737", "5551999482737"),
    ("+55 51 99948-2737", "5551999482737"),
    # Sem DDI (BR assumido)
    ("51999482737", "5551999482737"),
    ("(51) 9 9948-2737", "5551999482737"),
    ("51 99948 2737", "5551999482737"),
    # Fixo c/ DDD
    ("5132456789", "555132456789"),
    # Inválido (curto demais)
    ("12345", None),
    ("", None),
    (None, None),
    # Só símbolos
    ("---", None),
    # Inválido (longo demais)
    ("99999999999999999999", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone_e164_br(raw) == expected


# ──────────────────────────────────────────────────────────────────
# phone_variants_for_match
# ──────────────────────────────────────────────────────────────────


def test_variants_13_digits_includes_without_9():
    """Móvel completo (13 dígitos) deve ter variante sem o 9."""
    variants = phone_variants_for_match("5551999482737")
    assert "5551999482737" in variants
    assert "555199482737" in variants  # sem o 9 do DDD


def test_variants_12_digits_includes_with_9():
    """Móvel sem 9 (12 dígitos) deve ter variante com 9."""
    variants = phone_variants_for_match("555199482737")
    assert "555199482737" in variants
    assert "5551999482737" in variants


def test_variants_no_duplicates():
    variants = phone_variants_for_match("5551999482737")
    assert len(variants) == len(set(variants))


# ──────────────────────────────────────────────────────────────────
# Primary selection
# ──────────────────────────────────────────────────────────────────


def _resolver():
    """Resolver sem DB hits (não chama lookup)."""
    return IdentityResolver()


def test_select_primary_empty_returns_none():
    assert _resolver()._select_primary([]) is None


def test_select_primary_single_match():
    m = IdentityMatch(
        tenant_id="t1", profile="medico", source="users.phone",
        confidence=1.0, full_name="Dr. Henrique",
    )
    assert _resolver()._select_primary([m]) is m


def test_select_primary_higher_confidence_wins():
    weak = IdentityMatch(
        tenant_id="t1", profile="familia", source="patients.responsible",
        confidence=0.75,
    )
    strong = IdentityMatch(
        tenant_id="t2", profile="medico", source="users.phone",
        confidence=1.00,
    )
    primary = _resolver()._select_primary([weak, strong])
    assert primary is strong


def test_select_primary_tie_breaks_by_last_active():
    older = IdentityMatch(
        tenant_id="t1", profile="medico", source="users.phone",
        confidence=1.00, last_active_at="2024-01-01T00:00:00+00:00",
    )
    newer = IdentityMatch(
        tenant_id="t2", profile="medico", source="users.phone",
        confidence=1.00, last_active_at="2026-04-01T00:00:00+00:00",
    )
    primary = _resolver()._select_primary([older, newer])
    assert primary is newer


def test_select_primary_handles_null_last_active():
    a = IdentityMatch(
        tenant_id="t1", profile="medico", source="users.phone",
        confidence=1.00, last_active_at=None,
    )
    b = IdentityMatch(
        tenant_id="t2", profile="medico", source="users.phone",
        confidence=1.00, last_active_at="2026-04-01T00:00:00+00:00",
    )
    primary = _resolver()._select_primary([a, b])
    assert primary is b  # b tem last_active, vence empate


# ──────────────────────────────────────────────────────────────────
# Identity dataclass roundtrip
# ──────────────────────────────────────────────────────────────────


def test_identity_dict_roundtrip_anonymous():
    identity = Identity(phone="5551999482737", matches=[], primary=None, is_anonymous=True)
    d = identity.to_dict()
    rehydrated = Identity.from_dict(d)
    assert rehydrated.phone == "5551999482737"
    assert rehydrated.matches == []
    assert rehydrated.primary is None
    assert rehydrated.is_anonymous is True


def test_identity_dict_roundtrip_with_matches():
    m = IdentityMatch(
        tenant_id="t1", profile="medico", source="users.phone",
        confidence=1.0, user_id="abc", full_name="Dr. X",
    )
    identity = Identity(phone="5551999482737", matches=[m], primary=m, is_anonymous=False)
    d = identity.to_dict()
    rehydrated = Identity.from_dict(d)
    assert rehydrated.phone == identity.phone
    assert len(rehydrated.matches) == 1
    assert rehydrated.matches[0].profile == "medico"
    assert rehydrated.primary is not None
    assert rehydrated.primary.user_id == "abc"
    assert rehydrated.is_anonymous is False
