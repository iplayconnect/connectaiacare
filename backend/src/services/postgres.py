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
    def __init__(self, dsn: str | None = None, minconn: int = 1, maxconn: int = 10):
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
        with self.get_cursor(commit=False) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: Iterable[Any] | None = None) -> list[dict]:
        with self.get_cursor(commit=False) as cur:
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
