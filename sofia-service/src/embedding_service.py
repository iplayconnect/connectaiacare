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

EMBED_MODEL = os.getenv("SOFIA_EMBED_MODEL") or "gemini-embedding-001"
EMBED_DIMS = 768  # Matryoshka truncation; vector(768) na tabela
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
        from google.genai import types
        client = _get_genai_client()
        # google-genai 1.73+ aceita config com output_dimensionality
        # (Matryoshka truncation pra dimensão menor — melhor pra pgvector)
        try:
            cfg = types.EmbedContentConfig(output_dimensionality=EMBED_DIMS)
            result = client.models.embed_content(
                model=EMBED_MODEL,
                contents=text[:8000],
                config=cfg,
            )
        except TypeError:
            # Fallback se SDK não aceita config — pega 3072 e trunca
            result = client.models.embed_content(
                model=EMBED_MODEL, contents=text[:8000],
            )
        embeddings = getattr(result, "embeddings", None) or []
        if embeddings:
            values = getattr(embeddings[0], "values", None)
            if values:
                vec = list(values)
                # Trunca caso venha 3072 (matryoshka manual)
                if len(vec) > EMBED_DIMS:
                    vec = vec[:EMBED_DIMS]
                # Re-normaliza após truncation pra preservar cosine
                if len(vec) == EMBED_DIMS:
                    import math
                    norm = math.sqrt(sum(v*v for v in vec))
                    if norm > 0:
                        vec = [v/norm for v in vec]
                return vec
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


# ════════════════════════════════════════════════════════════════
# Cross-patient semantic search (clinical pattern recognition)
# ════════════════════════════════════════════════════════════════
# Caso de uso: médico pergunta "que outros pacientes tiveram esse mesmo
# padrão de queda?" Sofia busca semanticamente em TODOS os pacientes do
# tenant + retorna anonimizado.
#
# RBAC fica fora desta função — caller (tool/endpoint) verifica role.
# Esta função APENAS executa busca + redação. Confiamos no caller.

import hashlib
import re

# Regex de PII genérica (idempotente — não vaza dado novo)
_PHONE_BR = re.compile(
    r"(?:\+?55[\s-]?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}"
)
_EMAIL = re.compile(
    r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"
)
_DATE_FULL = re.compile(
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b"
)
# CPF: 000.000.000-00 ou 00000000000
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def _pii_redact_generic(text: str) -> str:
    """Aplica regex de PII genérica — idempotente."""
    if not text:
        return text or ""
    text = _PHONE_BR.sub("[TEL]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _DATE_FULL.sub("[DATA]", text)
    text = _CPF.sub("[CPF]", text)
    return text


def _pii_redact_patient_specific(
    text: str, full_name: str | None, nickname: str | None
) -> str:
    """Substitui menções específicas ao nome/apelido do paciente.

    Atenção a casos parciais: full_name='Helena Maria da Silva' deve substituir
    também 'Helena', 'Helena Maria', 'D. Helena', 'Dona Helena', etc.
    """
    if not text:
        return text or ""
    tokens_to_redact: set[str] = set()
    for source in (full_name, nickname):
        if not source:
            continue
        # Token completo
        tokens_to_redact.add(source.strip())
        # Cada palavra com >=4 chars (evita "da", "de", "e")
        for word in source.split():
            w = word.strip(",;:.()[]{}'\"")
            if len(w) >= 4 and w[0].isupper():
                tokens_to_redact.add(w)
    if not tokens_to_redact:
        return text
    # Ordena por tamanho desc — substitui mais longos primeiro
    for token in sorted(tokens_to_redact, key=len, reverse=True):
        # Word boundary case-insensitive
        try:
            text = re.sub(
                rf"\b{re.escape(token)}\b",
                "[PACIENTE]",
                text,
                flags=re.IGNORECASE,
            )
        except re.error:
            continue
    return text


def _anonymize_patient_id(patient_id: str, salt: str) -> str:
    """Hash não-reversível pra identificador estável dentro de uma query.
    Usa salt da sessão (random) pra que mesmo paciente não seja
    re-identificável entre queries diferentes."""
    h = hashlib.sha256(f"{salt}:{patient_id}".encode("utf-8")).hexdigest()
    return f"anon-{h[:8]}"


def search_cross_patient(
    query: str,
    *,
    tenant_id: str,
    top_k: int = 10,
    days: int = 90,
    min_similarity: float = 0.5,
) -> dict:
    """Busca semântica CROSS-paciente dentro de um tenant.

    Retorna matches anonimizados:
      - patient_id substituído por hash session-salt
      - PII genérica redacted (telefone, email, CPF, data específica)
      - Nome do paciente (full + nickname) redacted como [PACIENTE]

    Use case: profissional buscando padrão clínico em múltiplos pacientes.
    Caller deve validar RBAC (só medico/enfermeiro/admin).
    """
    qvec = embed_text(query)
    if qvec is None:
        return {"ok": False, "error": "embedding_failed", "matches": []}
    qvec_str = "[" + ",".join(f"{v:.6f}" for v in qvec) + "]"

    # Salt único por query — mesmo paciente fica com ID diferente entre buscas
    import secrets
    session_salt = secrets.token_hex(8)

    # Busca top_k * 3 pra ter espaço pra dedupe + filter
    raw_limit = max(top_k * 3, 30)

    rows = persistence.fetch_all(
        f"""SELECT m.id, m.session_id, m.role, m.content, m.tool_name,
                   m.created_at, s.channel, s.patient_id,
                   p.full_name AS _patient_full_name,
                   p.nickname AS _patient_nickname,
                   1 - (m.embedding <=> %s::vector) AS similarity
            FROM aia_health_sofia_messages m
            JOIN aia_health_sofia_sessions s ON s.id = m.session_id
            LEFT JOIN aia_health_patients p ON p.id = s.patient_id
            WHERE m.embedding IS NOT NULL
              AND m.created_at > NOW() - INTERVAL '{int(days)} days'
              AND s.tenant_id = %s
              AND s.patient_id IS NOT NULL
              AND m.content IS NOT NULL
              AND length(m.content) > 10
            ORDER BY m.embedding <=> %s::vector ASC
            LIMIT %s""",
        (qvec_str, tenant_id, qvec_str, raw_limit),
    )

    # Filtra por similarity mínima + dedupe por (patient_id + similarity bucket)
    seen_buckets: set[tuple[str, int]] = set()
    matches: list[dict] = []
    unique_patients: set[str] = set()

    for r in rows or []:
        sim = float(r.get("similarity") or 0)
        if sim < min_similarity:
            continue
        pid = str(r.get("patient_id") or "")
        if not pid:
            continue
        # Dedupe: 1 match por bucket de similaridade (round to 0.05) por paciente
        bucket = (pid, int(sim * 20))
        if bucket in seen_buckets:
            continue
        seen_buckets.add(bucket)
        unique_patients.add(pid)

        content = str(r.get("content") or "")
        # Redacta PII específica do paciente
        content = _pii_redact_patient_specific(
            content,
            r.get("_patient_full_name"),
            r.get("_patient_nickname"),
        )
        # Redacta PII genérica
        content = _pii_redact_generic(content)

        # Days ago
        days_ago = None
        if r.get("created_at"):
            from datetime import datetime, timezone
            delta = datetime.now(timezone.utc) - r["created_at"]
            days_ago = max(0, int(delta.total_seconds() / 86400))

        matches.append({
            "anonymized_patient_id": _anonymize_patient_id(pid, session_salt),
            "channel": r.get("channel"),
            "role": r.get("role"),
            "content": content,
            "similarity": round(sim, 3),
            "days_ago": days_ago,
        })
        if len(matches) >= top_k:
            break

    return {
        "ok": True,
        "matches": matches,
        "unique_patients": len(unique_patients),
        "total_matches": len(matches),
        "_disclaimer": (
            "Padrões cross-paciente são apoio à reflexão clínica. "
            "Cada caso é único — decida sempre considerando o paciente "
            "específico que você está cuidando."
        ),
    }


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
