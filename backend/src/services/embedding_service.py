"""Serviço de embeddings semânticos para pattern detection de relatos clínicos.

Gera embeddings vetoriais de 768 dimensões usando o modelo do provider LLM ativo
(Gemini `text-embedding-004` ou OpenAI `text-embedding-3-small` truncado).
Usado pelo PatternDetectionService para busca semântica em `aia_health_reports.embedding`.

Dimensão: 768 (alinhada com schema `vector(768)` na migration 005).
Provider atual: Google Gemini (`models/text-embedding-004`).

Por que 768 e não 3072 (large):
- 768 é suficiente para detectar similaridade semântica entre relatos clínicos
  em português (validado em papers de clinical NLP).
- Índice pgvector HNSW fica 4x menor, buscas mais rápidas.
- Upgrade pra 3072 é trivial: altera dim no schema + regenera embeddings.

Cache: não há cache intencional aqui — embeddings são gerados uma única vez por
relato (no ato do salvamento) e persistidos. Buscas subsequentes usam o vetor
armazenado, não chamam o provider.
"""
from __future__ import annotations

from typing import Any

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_DIM = 768


class EmbeddingService:
    def __init__(self):
        self.provider = settings.llm_provider
        self._client = None  # lazy init

    def _ensure_client(self):
        if self._client is not None:
            return self._client

        if self.provider == "gemini":
            if not settings.google_api_key:
                raise RuntimeError("GOOGLE_API_KEY não configurada para embeddings Gemini.")
            import google.generativeai as genai
            genai.configure(api_key=settings.google_api_key)
            self._client = genai
            logger.info("embedding_client_init", provider="gemini", model="text-embedding-004")
        elif self.provider == "anthropic":
            # Anthropic não expõe embeddings; caímos em OpenAI se key estiver presente
            # (comum em stacks Anthropic — OpenAI usado só pra embeddings).
            import openai
            api_key = getattr(settings, "openai_api_key", None) or ""
            if not api_key:
                raise RuntimeError(
                    "LLM_PROVIDER=anthropic não suporta embeddings nativamente. "
                    "Configurar OPENAI_API_KEY pra embeddings ou trocar pra LLM_PROVIDER=gemini."
                )
            self._client = openai.OpenAI(api_key=api_key)
            logger.info("embedding_client_init", provider="openai", model="text-embedding-3-small")
        else:
            raise RuntimeError(f"Provider desconhecido: {self.provider}")

        return self._client

    def embed(self, text: str) -> list[float]:
        """Gera embedding 768-dim do texto.

        Retorna lista de floats. Em falha, retorna lista vazia (caller trata como
        "sem embedding" — pattern detection faz fallback pra busca por tag).
        """
        if not text or not text.strip():
            return []

        text_clean = text.strip()[:8000]  # truncamento defensivo

        try:
            if self.provider == "gemini":
                return self._embed_gemini(text_clean)
            else:
                return self._embed_openai(text_clean)
        except Exception as exc:
            logger.warning("embedding_failed", error=str(exc), text_len=len(text_clean))
            return []

    def _embed_gemini(self, text: str) -> list[float]:
        genai = self._ensure_client()
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",  # otimiza pra busca de similaridade
        )
        # result pode ser dict ou objeto — normaliza
        embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
        if not embedding or len(embedding) != EMBEDDING_DIM:
            logger.warning(
                "gemini_embedding_unexpected_dim",
                got=len(embedding) if embedding else 0,
                expected=EMBEDDING_DIM,
            )
            return []
        return list(embedding)

    def _embed_openai(self, text: str) -> list[float]:
        client = self._ensure_client()
        # text-embedding-3-small retorna 1536 dims, precisamos truncar para 768.
        # OpenAI suporta parâmetro `dimensions` para retornar diretamente na dim pedida.
        result = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            dimensions=EMBEDDING_DIM,
        )
        embedding = result.data[0].embedding
        if len(embedding) != EMBEDDING_DIM:
            logger.warning("openai_embedding_unexpected_dim", got=len(embedding))
            return []
        return list(embedding)

    def embed_for_query(self, text: str) -> list[float]:
        """Variante com task_type=retrieval_query (Gemini) — otimiza busca.
        Para OpenAI é idêntico ao embed normal.
        """
        if not text or not text.strip():
            return []
        try:
            if self.provider == "gemini":
                genai = self._ensure_client()
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text.strip()[:8000],
                    task_type="retrieval_query",
                )
                embedding = result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)
                return list(embedding) if embedding else []
            else:
                return self._embed_openai(text.strip()[:8000])
        except Exception as exc:
            logger.warning("embedding_query_failed", error=str(exc))
            return []


_embedding_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = EmbeddingService()
    return _embedding_instance
