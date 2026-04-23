"""Fixtures comuns pra suite de testes ConnectaIACare.

Estratégia:
    - Banco: MockDB in-memory simulando interface do PostgresService
    - Logger: no-op mock pra não poluir output do pytest
    - Singletons: reset automático entre testes (cada service tem _instance)
    - Sem config real: não carregamos settings.py (evita fail-closed em dev sem .env)

Uso típico:

    def test_something(mock_db, reset_singletons):
        # mock_db simula as queries
        mock_db.add_fetch_one_response({"plan_sku": "premium"}, when_query_contains="subscriptions")
        # serviço vai pegar o mock
        svc = get_rate_limiter()
        ...
"""
from __future__ import annotations

import sys
import types
from collections.abc import Callable
from typing import Any

import pytest


# ══════════════════════════════════════════════════════════════════
# Mock DB (simula PostgresService)
# ══════════════════════════════════════════════════════════════════

class MockDB:
    """Mock do PostgresService com controles explícitos por teste.

    Uso:
        db.fetch_one_response = {"plan_sku": "premium"}
        # ou
        db.set_fetch_one(lambda q, p: {"id": "x"} if "plans" in q else None)
    """

    def __init__(self):
        self.fetch_one_response: Any = None
        self.fetch_all_response: list[dict] = []
        self.insert_returning_response: Any = None
        self.executed_queries: list[tuple[str, tuple]] = []
        self.fetch_one_fn: Callable | None = None
        self.fetch_all_fn: Callable | None = None
        self.insert_returning_fn: Callable | None = None

    # ---- Interface compatível com PostgresService ----
    def execute(self, query: str, params=None) -> None:
        self.executed_queries.append((query, tuple(params or ())))

    def fetch_one(self, query: str, params=None) -> dict | None:
        self.executed_queries.append((query, tuple(params or ())))
        if self.fetch_one_fn:
            return self.fetch_one_fn(query, tuple(params or ()))
        return self.fetch_one_response

    def fetch_all(self, query: str, params=None) -> list[dict]:
        self.executed_queries.append((query, tuple(params or ())))
        if self.fetch_all_fn:
            return self.fetch_all_fn(query, tuple(params or ()))
        return self.fetch_all_response

    def insert_returning(self, query: str, params=None) -> dict | None:
        self.executed_queries.append((query, tuple(params or ())))
        if self.insert_returning_fn:
            return self.insert_returning_fn(query, tuple(params or ()))
        return self.insert_returning_response

    def json_adapt(self, data: Any):
        # Pra testes, retorna o valor como está (não precisa do AsIs de verdade)
        return data

    # ---- Helpers de asserção ----
    def queries_matching(self, substring: str) -> list[tuple[str, tuple]]:
        return [q for q in self.executed_queries if substring.lower() in q[0].lower()]

    def reset(self):
        self.executed_queries.clear()
        self.fetch_one_response = None
        self.fetch_all_response = []
        self.insert_returning_response = None
        self.fetch_one_fn = None
        self.fetch_all_fn = None
        self.insert_returning_fn = None


# ══════════════════════════════════════════════════════════════════
# Mocks de ambientes externos (structlog, psycopg2, etc)
# ══════════════════════════════════════════════════════════════════

def _install_module_mocks() -> None:
    """Injeta mocks de deps externas antes de importar qualquer código src.

    Necessário porque structlog/psycopg2 podem não estar instalados no ambiente
    local de testes, e settings.py pode quebrar sem .env.
    """
    # structlog — logger no-op
    if "structlog" not in sys.modules:
        sl = types.ModuleType("structlog")
        sl.stdlib = types.SimpleNamespace(BoundLogger=object)

        def _noop_logger(*a, **kw):
            def noop(*a2, **kw2):
                return None
            return types.SimpleNamespace(
                info=noop, warning=noop, error=noop, debug=noop,
                bind=lambda **kw: _noop_logger(),
            )
        sl.get_logger = _noop_logger
        sl.configure = lambda **kw: None
        sl.processors = types.SimpleNamespace()
        sys.modules["structlog"] = sl

    # psycopg2 — só precisa dos símbolos importados
    for name in ["psycopg2", "psycopg2.extras", "psycopg2.pool", "psycopg2.extensions"]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["psycopg2.pool"].ThreadedConnectionPool = object
    sys.modules["psycopg2.extras"].register_uuid = lambda: None
    sys.modules["psycopg2.extras"].RealDictCursor = object
    sys.modules["psycopg2.extensions"].AsIs = lambda x: x


_install_module_mocks()


# ══════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db() -> MockDB:
    """Mock do PostgresService in-memory."""
    return MockDB()


@pytest.fixture(autouse=True)
def patch_get_postgres(monkeypatch, mock_db):
    """Substitui get_postgres() em TODOS os services que usam."""
    # Os imports acontecem dentro dos services — precisamos patchar o módulo origem
    import src.services.postgres as postgres_mod
    monkeypatch.setattr(postgres_mod, "get_postgres", lambda: mock_db)

    # E também patchar em cada módulo que já importou get_postgres (cache de import)
    for mod_name in [
        "src.services.safety_moderation_service",
        "src.services.conversation_history_service",
        "src.services.rate_limit_service",
        "src.services.low_confidence_handler",
    ]:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "get_postgres"):
                monkeypatch.setattr(mod, "get_postgres", lambda: mock_db)
    return mock_db


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reseta singletons entre testes (cada service tem _instance=None)."""
    modules_with_singletons = [
        "src.services.humanizer_service",
        "src.services.safety_moderation_service",
        "src.services.conversation_history_service",
        "src.services.message_buffer_service",
        "src.services.rate_limit_service",
        "src.services.low_confidence_handler",
    ]
    for mod_name in modules_with_singletons:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "_instance"):
                setattr(mod, "_instance", None)
    yield
    for mod_name in modules_with_singletons:
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "_instance"):
                setattr(mod, "_instance", None)


@pytest.fixture
def fixed_random(monkeypatch):
    """Usa seed fixo pra reprodutibilidade de testes que usam random."""
    import random
    random.seed(42)
    yield
