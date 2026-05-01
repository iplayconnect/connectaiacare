"""Tests pra audit_log_writer redaction helpers."""
from __future__ import annotations

import pytest

from src.services.audit_log_writer import (
    redact_cpf,
    redact_email,
    redact_full_name,
    redact_payload,
    redact_phone,
)


@pytest.mark.parametrize("raw,expected", [
    ("5551984928518", "55519****8518"),
    ("+55 51 99735-4484", "55519****4484"),
    ("51996161700", "55519****1700"),
    (None, None),
    ("12345", "***"),
    ("", None),
])
def test_redact_phone(raw, expected):
    assert redact_phone(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("alex@connectaia.com.br", "a***@connectaia.com.br"),
    ("a@b.com", "a***@b.com"),
    ("@invalido", "***"),
    (None, "***"),
    ("", "***"),
])
def test_redact_email(raw, expected):
    assert redact_email(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("123.456.789-00", "***.***.789-**"),
    ("12345678900", "***.***.789-**"),
    ("12345", "***"),
    (None, None),
])
def test_redact_cpf(raw, expected):
    assert redact_cpf(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Alexandre Veras Fernandes", "A. Fernandes"),
    ("Alexandre", "A***"),
    ("Dr. Henrique Bordin", "D. Bordin"),
    (None, None),
    ("", None),
])
def test_redact_full_name(raw, expected):
    assert redact_full_name(raw) == expected


def test_redact_payload_recursive():
    payload = {
        "phone": "5551984928518",
        "email": "henrique@gmail.com",
        "cpf": "12345678900",
        "full_name": "Henrique Bordin",
        "patient": {
            "name": "Antonia Ferreira",
            "phone": "5551996161700",
        },
        "responsibles": [
            {"name": "Filho Joao", "phone": "5551111111111"},
            {"name": "Filha Maria", "phone": "5552222222222"},
        ],
        "harmless_field": "ok",
        "count": 42,
    }
    redacted = redact_payload(payload)

    assert redacted["phone"] == "55519****8518"
    assert redacted["email"] == "h***@gmail.com"
    assert redacted["cpf"] == "***.***.789-**"
    assert redacted["full_name"] == "H. Bordin"
    assert redacted["patient"]["name"] == "A. Ferreira"
    assert redacted["patient"]["phone"] == "55519****1700"
    assert redacted["responsibles"][0]["name"] == "F. Joao"
    assert redacted["responsibles"][0]["phone"] == "55511****1111"
    assert redacted["harmless_field"] == "ok"
    assert redacted["count"] == 42


def test_redact_payload_handles_none():
    assert redact_payload({}) == {}
    assert redact_payload({"phone": None}) == {"phone": None}
