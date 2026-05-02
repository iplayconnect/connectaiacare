"""Background worker pra gerar embeddings de aia_health_sofia_messages.

Phase C v2.6 — semantic recall. Sofia persiste mensagens com
embedding=NULL (sofia_persistence.append_message). Este worker pega
batch de mensagens pendentes e popula embedding via EmbeddingService
(text-embedding-004 ou similar, 768 dims).

Uso de produção (Hostinger):
    Loop infinito num thread/timer no sofia-service. Backoff
    exponencial em erro. Concorrente-safe via SELECT ... FOR UPDATE
    SKIP LOCKED.

Uso CLI (manual, debug, backfill):
    python -m src.services.csm.embedding_worker --batch 50

Index suportado:
    idx_sofia_messages_pending_embed (migration 037)
    WHERE embedding IS NULL AND content IS NOT NULL

API principal:
    worker = EmbeddingWorker(batch_size=20)
    n = worker.process_batch()
    # 0 quando não tem mais pendentes; loop pode dormir e tentar de novo

    # Modo daemon
    worker.run_forever(interval_seconds=30)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

from src.services.embedding_service import EMBEDDING_DIM, get_embedding_service
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Tipo de mensagem que vale a pena embedar.
# 'tool' messages (output JSON de tool calls) raramente são úteis pra
# recall semântico — pular pra economizar tokens.
ROLES_TO_EMBED = ("user", "assistant")

# Modelo "vencedor" que vai pra coluna embedding_model.
# Mantido em sync com embedding_service.py default.
DEFAULT_MODEL_NAME = "text-embedding-004"


@dataclass
class WorkerStats:
    processed: int = 0
    skipped_empty: int = 0
    failed: int = 0
    duration_ms: int = 0


class EmbeddingWorker:
    """Background worker pra popular embeddings de sofia_messages."""

    def __init__(
        self,
        *,
        batch_size: int = 20,
        embedding_service=None,
        max_text_len: int = 4000,
    ):
        self.batch_size = batch_size
        self.max_text_len = max_text_len
        self._embed = embedding_service or get_embedding_service()

    # ─── Batch ───────────────────────────────────────────────────

    def fetch_pending(self, limit: int) -> list[dict]:
        """Pega N mensagens sem embedding. SKIP LOCKED pra multi-worker."""
        try:
            return get_postgres().fetch_all(
                """SELECT id, content, role, tenant_id
                   FROM aia_health_sofia_messages
                   WHERE embedding IS NULL
                     AND content IS NOT NULL
                     AND length(content) > 5
                     AND role = ANY(%s::text[])
                   ORDER BY created_at ASC
                   LIMIT %s
                   FOR UPDATE SKIP LOCKED""",
                (list(ROLES_TO_EMBED), limit),
            )
        except Exception as exc:
            logger.warning(
                "embedding_worker_fetch_failed",
                error=str(exc)[:200],
            )
            return []

    def write_embedding(
        self,
        message_id: str,
        embedding: list[float],
        *,
        model_name: str = DEFAULT_MODEL_NAME,
    ) -> bool:
        """Persiste embedding. Idempotente — UPDATE não falha se row
        já tinha valor."""
        if not embedding or len(embedding) != EMBEDDING_DIM:
            return False
        # pgvector aceita formato '[v1,v2,...]'
        vec_str = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
        try:
            get_postgres().execute(
                """UPDATE aia_health_sofia_messages
                   SET embedding = %s::vector,
                       embedding_model = %s,
                       embedded_at = NOW()
                   WHERE id = %s""",
                (vec_str, model_name, message_id),
            )
            return True
        except Exception as exc:
            logger.warning(
                "embedding_worker_write_failed",
                message_id=message_id, error=str(exc)[:200],
            )
            return False

    def process_batch(self) -> WorkerStats:
        """Processa 1 batch. Retorna stats. Roda síncrono."""
        started = time.perf_counter()
        stats = WorkerStats()

        rows = self.fetch_pending(self.batch_size)
        if not rows:
            stats.duration_ms = int((time.perf_counter() - started) * 1000)
            return stats

        for r in rows:
            content = (r.get("content") or "").strip()
            if not content:
                stats.skipped_empty += 1
                continue
            text = content[:self.max_text_len]
            try:
                vec = self._embed.embed(text)
            except Exception as exc:
                logger.warning(
                    "embedding_worker_embed_failed",
                    message_id=r.get("id"), error=str(exc)[:200],
                )
                stats.failed += 1
                continue
            if not vec:
                stats.failed += 1
                continue
            ok = self.write_embedding(str(r["id"]), vec)
            if ok:
                stats.processed += 1
            else:
                stats.failed += 1

        stats.duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "embedding_worker_batch",
            processed=stats.processed,
            skipped=stats.skipped_empty,
            failed=stats.failed,
            duration_ms=stats.duration_ms,
        )
        return stats

    # ─── Daemon loop ────────────────────────────────────────────

    def run_forever(
        self,
        *,
        interval_seconds: float = 30.0,
        backoff_max: float = 300.0,
    ) -> None:
        """Loop infinito. Backoff exponencial em erro consecutivo.

        Para parar: SIGTERM (process inteiro) ou daemon=True quando
        spawnado em thread.
        """
        backoff = interval_seconds
        consecutive_errors = 0
        while True:
            try:
                stats = self.process_batch()
                if stats.failed and not stats.processed:
                    consecutive_errors += 1
                    backoff = min(backoff * 2, backoff_max)
                else:
                    consecutive_errors = 0
                    backoff = interval_seconds
                # Se batch full, loop imediato (provável backlog grande)
                if stats.processed >= self.batch_size:
                    continue
            except Exception as exc:
                consecutive_errors += 1
                backoff = min(backoff * 2, backoff_max)
                logger.exception(
                    "embedding_worker_iter_failed",
                    error=str(exc)[:200],
                    consecutive_errors=consecutive_errors,
                )
            time.sleep(backoff)


# ─── CLI ────────────────────────────────────────────────────────

def main() -> int:
    """Modo CLI pra backfill / debug.

    Uso:
        python -m src.services.csm.embedding_worker --batch 50
        python -m src.services.csm.embedding_worker --daemon --interval 60
    """
    import argparse
    parser = argparse.ArgumentParser(description="Sofia messages embedding worker")
    parser.add_argument("--batch", type=int, default=20)
    parser.add_argument("--daemon", action="store_true",
                        help="Roda como daemon em loop infinito")
    parser.add_argument("--interval", type=float, default=30.0,
                        help="Intervalo entre batches em modo daemon (s)")
    parser.add_argument("--max-iter", type=int, default=0,
                        help="Em modo single-shot, número de batches "
                             "(0=infinito até esgotar)")
    args = parser.parse_args()

    worker = EmbeddingWorker(batch_size=args.batch)

    if args.daemon:
        worker.run_forever(interval_seconds=args.interval)
        return 0

    # Single-shot: roda até esgotar OU max-iter
    total = 0
    iters = 0
    while True:
        stats = worker.process_batch()
        total += stats.processed
        iters += 1
        if stats.processed == 0:
            print(f"[done] no more pending. total={total} iters={iters}")
            break
        if args.max_iter and iters >= args.max_iter:
            print(f"[stop] max-iter reached. total={total}")
            break
    return 0


# Singleton (pra usar de outros services)
_instance: Optional[EmbeddingWorker] = None


def get_embedding_worker() -> EmbeddingWorker:
    global _instance
    if _instance is None:
        _instance = EmbeddingWorker()
    return _instance


if __name__ == "__main__":
    raise SystemExit(main())
