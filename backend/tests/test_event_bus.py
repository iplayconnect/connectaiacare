"""Tests pra EventBus serialization helpers (lógica pura).

DB/Redis side-effects testados em integration test separado.
"""
from __future__ import annotations

from src.services.event_bus import EventBus


def test_flatten_simple_types():
    flat = EventBus._flatten({
        "tenant_id": "t1",
        "count": 42,
        "active": True,
        "ratio": 3.14,
    })
    assert flat["tenant_id"] == "t1"
    assert flat["count"] == "42"
    assert flat["active"] == "True"
    assert flat["ratio"] == "3.14"


def test_flatten_none_becomes_empty_string():
    flat = EventBus._flatten({"missing": None})
    assert flat["missing"] == ""


def test_flatten_dict_becomes_json():
    flat = EventBus._flatten({
        "payload": {"phone": "5551984928518", "type": "text"},
    })
    # dict → JSON string
    import json
    assert json.loads(flat["payload"]) == {"phone": "5551984928518", "type": "text"}


def test_flatten_list_becomes_json():
    flat = EventBus._flatten({"channels": ["whatsapp", "voice"]})
    import json
    assert json.loads(flat["channels"]) == ["whatsapp", "voice"]


def test_unflatten_simple():
    out = EventBus._unflatten({
        "tenant_id": "t1",
        "count": "42",
        "missing": "",
    })
    assert out["tenant_id"] == "t1"
    assert out["count"] == "42"  # mantém string (sem dica de tipo)
    assert out["missing"] is None


def test_unflatten_json_dict():
    out = EventBus._unflatten({
        "payload": '{"phone":"5551984928518","type":"text"}',
    })
    assert out["payload"] == {"phone": "5551984928518", "type": "text"}


def test_unflatten_json_list():
    out = EventBus._unflatten({
        "channels": '["whatsapp","voice"]',
    })
    assert out["channels"] == ["whatsapp", "voice"]


def test_unflatten_invalid_json_keeps_string():
    out = EventBus._unflatten({"text": "{not valid json"})
    assert out["text"] == "{not valid json"


def test_roundtrip():
    original = {
        "tenant_id": "t1",
        "count": 42,
        "payload": {"nested": {"deep": True}},
        "channels": ["a", "b"],
        "missing": None,
    }
    flat = EventBus._flatten(original)
    rehydrated = EventBus._unflatten(flat)
    assert rehydrated["tenant_id"] == "t1"
    assert rehydrated["count"] == "42"  # numbers viram string (Streams limitação)
    assert rehydrated["payload"] == {"nested": {"deep": True}}
    assert rehydrated["channels"] == ["a", "b"]
    assert rehydrated["missing"] is None
