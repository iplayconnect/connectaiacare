"""Conexão PostgreSQL + utilitários de query."""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterable

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PostgresService:
    # Pool size dimensionado pra gunicorn 2 workers × 16 threads = 32
    # threads concorrentes por container. maxconn=20 dá margem pra
    # ~75% das threads em I/O DB ao mesmo tempo. 2 workers × 20 = 40
    # conexões totais ao Postgres por container. Postgres default
    # max_connections=100, então api+sofia+frontend cabem sem estourar.
    def __init__(self, dsn: str | None = None, minconn: int = 2, maxconn: int = 20):
        self.dsn = dsn or settings.database_url
        self._pool = ThreadedConnectionPool(minconn, maxconn, self.dsn)
        psycopg2.extras.register_uuid()

    @contextmanager
    def get_cursor(self, commit: bool = True):
        conn = self._pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            yield cursor
            if commit:
                conn.commit()
            cursor.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def execute(self, query: str, params: Iterable[Any] | None = None) -> None:
        with self.get_cursor() as cur:
            cur.execute(query, params or ())

    def fetch_one(self, query: str, params: Iterable[Any] | None = None) -> dict | None:
        # commit=True por default: SELECT-only e um commit é no-op, mas
        # várias rotas usam fetch_one para INSERT/UPDATE/DELETE ... RETURNING
        # (operator_routes, admin_quick_replies, tenant_escalation,
        # patient_service.create, etc.). Sem commit, a mutação fica numa
        # transação pendurada na conexão e é rollback-ada quando outra
        # request usa a mesma conexão e dispara exceção. Foi a causa raiz
        # do "patient_not_found" reportado pelo Henrique em 2026-05-18.
        with self.get_cursor(commit=True) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: Iterable[Any] | None = None) -> list[dict]:
        # Mesma razão de fetch_one: commit=True por default. Codebase
        # não usa transações explícitas (BEGIN), então commitar SELECT
        # vazio é no-op seguro.
        with self.get_cursor(commit=True) as cur:
            cur.execute(query, params or ())
            return [dict(r) for r in cur.fetchall()]

    def insert_returning(self, query: str, params: Iterable[Any] | None = None) -> dict | None:
        with self.get_cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None

    def json_adapt(self, data: Any) -> psycopg2.extensions.AsIs:
        return psycopg2.extras.Json(data)

    def close(self) -> None:
        self._pool.closeall()


_postgres_instance: PostgresService | None = None


def get_postgres() -> PostgresService:
    global _postgres_instance
    if _postgres_instance is None:
        _postgres_instance = PostgresService()
        logger.info("postgres_initialized", dsn_host=settings.database_url.split("@")[-1])
    return _postgres_instance
