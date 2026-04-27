"""Embedding service — gera vetores semânticos pra messages histórico
da Sofia (Gemini text-embedding-004) e habilita recall semântico.

Estratégia:
  - Worker batch processa messages com embedding NULL (a cada 60s)
  - Gera embedding via Gemini text-embedding-004 (768d)
  - Persiste em aia_health_sofia_messages.embedding (vector)

Tool recall_semantic faz cosine similarity search pra "lembrei quando
falamos sobre X?" — retorna top-K mensagens passadas relevantes do
mesmo paciente (ou cross-paciente quando user é profissional).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from typing import Any

from src import persistence

logger = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("SOFIA_EMBED_MODEL") or "text-embedding-004"
BATCH_SIZE = int(os.getenv("SOFIA_EMBED_BATCH", "20"))
TICK_INTERVAL_SEC = int(os.getenv("SOFIA_EMBED_TICK_SEC", "60"))
LOCK_KEY = 8731029471


def _get_genai_client():
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY required for embeddings")
    return genai.Client(api_key=api_key)


def embed_text(text: str) -> list[float] | None:
    """Sincronous embedding pra um texto. Retorna 768d ou None se falhar."""
    if not text or len(text.strip()) < 3:
        return None
    try:
        client = _get_genai_client()
        # google-genai 0.6+ tem embed_content
        result = client.models.embed_content(
            model=EMBED_MODEL,
            contents=text[:8000],  # limit input
        )
        # SDK retorna .embeddings[0].values (lista[float])
        embeddings = getattr(result, "embeddings", None) or []
        if embeddings:
            values = getattr(embeddings[0], "values", None)
            if values:
                return list(values)
        # Fallback formats
        emb = getattr(result, "embedding", None)
        if emb:
            return list(emb)
    except Exception as exc:
        logger.warning("embed_failed: %s", exc)
    return None


def embed_pending_batch(limit: int = BATCH_SIZE) -> int:
    """Pega N messages sem embedding e gera. Retorna quantas processou."""
    rows = persistence.fetch_all(
        """SELECT id, role, content, tool_name
           FROM aia_health_sofia_messages
           WHERE embedding IS NULL AND content IS NOT NULL
             AND length(content) >= 10
           ORDER BY created_at ASC LIMIT %s""",
        (limit,),
    )
    processed = 0
    for r in rows:
        # Compõe texto pro embedding (inclui contexto de role)
        prefix = f"[{r['role']}]"
        if r.get("tool_name"):
            prefix += f" [{r['tool_name']}]"
        text = f"{prefix} {r['content']}"
        vec = embed_text(text)
        if vec is None:
            # Marca pra evitar retry imediato (embed falhou)
            continue
        # PG aceita vector como string '[v1,v2,...]'
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
        persistence.execute(
            """UPDATE aia_health_sofia_messages
               SET embedding = %s::vector, embedding_model = %s,
                   embedded_at = NOW()
               WHERE id = %s""",
            (vec_str, EMBED_MODEL, r["id"]),
        )
        processed += 1
    if processed:
        logger.info("embedded_batch processed=%d", processed)
    return processed


def search_semantic(
    query: str,
    *,
    patient_id: str | None = None,
    user_id: str | None = None,
    top_k: int = 5,
    days: int = 90,
) -> list[dict]:
    """Busca top-K mensagens semanticamente similares ao query.
    Filtra por patient_id (preferencial) ou user_id (sessions desse user)."""
    qvec = embed_text(query)
    if qvec is None:
        return []
    qvec_str = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"

    where_parts = ["m.embedding IS NOT NULL",
                   f"m.created_at > NOW() - INTERVAL '{int(days)} days'"]
    params: list = [qvec_str]
    if patient_id:
        where_parts.append("s.patient_id = %s")
        params.append(patient_id)
    elif user_id:
        where_parts.append("s.user_id = %s")
        params.append(user_id)
    else:
        # Sem escopo → não retorna nada (segurança)
        return []
    params.append(top_k)

    rows = persistence.fetch_all(
        f"""SELECT m.id, m.session_id, m.role, m.content, m.tool_name,
                   m.created_at, s.channel,
                   1 - (m.embedding <=> %s::vector) AS similarity
            FROM aia_health_sofia_messages m
            JOIN aia_health_sofia_sessions s ON s.id = m.session_id
            WHERE {' AND '.join(where_parts)}
            ORDER BY m.embedding <=> %s::vector ASC
            LIMIT %s""",
        # query vector aparece duas vezes (similarity + ORDER BY)
        tuple([qvec_str] + params[1:-1] + [qvec_str, params[-1]]),
    )
    return rows


# ─────── Worker batch ───────

class EmbeddingWorker:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_id = f"{socket.gethostname()}-{os.getpid()}"

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="embedding-worker", daemon=True,
        )
        self._thread.start()
        logger.info(
            "embedding_worker_started worker_id=%s tick=%ds batch=%d model=%s",
            self._worker_id, TICK_INTERVAL_SEC, BATCH_SIZE, EMBED_MODEL,
        )

    def _try_lock(self) -> bool:
        row = persistence.fetch_one(
            "SELECT pg_try_advisory_lock(%s) AS got", (LOCK_KEY,),
        )
        return bool(row and row.get("got"))

    def _release_lock(self):
        try:
            persistence.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        except Exception:
            pass

    def _loop(self):
        self._stop.wait(20)  # delay no boot
        while not self._stop.is_set():
            try:
                if self._try_lock():
                    try:
                        embed_pending_batch()
                    finally:
                        self._release_lock()
            except Exception as exc:
                logger.error("embedding_worker_tick_error: %s", exc)
            self._stop.wait(TICK_INTERVAL_SEC)


_singleton: EmbeddingWorker | None = None


def get_worker() -> EmbeddingWorker:
    global _singleton
    if _singleton is None:
        _singleton = EmbeddingWorker()
    return _singleton
