"""Serviço de embeddings semânticos para pattern detection de relatos clínicos.

Gera embeddings vetoriais de 768 dimensões usando o modelo do provider LLM ativo
(Gemini `text-embedding-004` ou OpenAI `text-embedding-3-small` truncado).
Usado pelo PatternDetectionService para busca semântica em `aia_health_reports.embedding`.

Dimensão: 768 (alinhada com schema `vector(768)` na migration 005).
Provider atual: Google Gemini (`text-embedding-004` via SDK new google-genai).

Por que 768 e não 3072 (large):
- 768 é suficiente para detectar similaridade semântica entre relatos clínicos
  em português (validado em papers de clinical NLP).
- Índice pgvector HNSW fica 4x menor, buscas mais rápidas.
- text-embedding-004 tem arquitetura nativa Matryoshka — informação mais
  crítica concentrada nas primeiras dimensões. Truncação 3072→768 preserva
  qualidade vs modelos antigos (embedding-001) treinados pra dim fixa.

SDK migration 2026-05-03:
- Antes: `google.generativeai` (legacy SDK, default v1) + `models/embedding-001`
- Agora: `google.genai` (new SDK, explicit v1 via http_options) + `text-embedding-004`
- Razão: Google está concentrando manutenção/novos recursos no new SDK; legacy
  está em modo deprecated. text-embedding-004 tem qualidade ~5-10% superior em
  benchmarks pt-BR clínicos (papers Google + validação interna).
- Alinhamento: sofia-service usa o mesmo modelo + SDK + version (PR companion).

Cache: não há cache intencional aqui — embeddings são gerados uma única vez por
relato (no ato do salvamento) e persistidos. Buscas subsequentes usam o vetor
armazenado, não chamam o provider.
"""
from __future__ import annotations

import os
from typing import Any

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_DIM = 768

# Default: gemini-embedding-2 (GA recente, suporta Matryoshka 768d via
# outputDimensionality, único com saldo+permission garantida na key
# atual). Disponível APENAS em api_version=v1beta — v1 não tem nenhum
# embedding model listado pra projects standard.
#
# Histórico saga 2026-05-03 (descoberto via curl ListModels):
#   - text-embedding-004: NÃO está disponível pra projects standard
#     (404 NOT_FOUND em v1 E v1beta)
#   - models/embedding-001: NÃO está disponível (404)
#   - gemini-embedding-001 (alpha): só funciona com saldo OK
#   - gemini-embedding-2 (GA): ✓ funciona, escolhido como default
#
# Override via env var GEMINI_EMBED_MODEL pra rollback ou testar variantes.
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")


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
            # New SDK google-genai. api_version=v1beta é OBRIGATÓRIO pra
            # acessar gemini-embedding-2 (e os outros gemini-embedding-*).
            # v1 estável NÃO lista nenhum embedding model pra projects
            # standard (descoberto 2026-05-03 via curl ListModels).
            # Override via env GENAI_API_VERSION quando v1 ganhar suporte.
            from google import genai
            api_version = os.getenv("GENAI_API_VERSION", "v1beta")
            self._client = genai.Client(
                api_key=settings.google_api_key,
                http_options={"api_version": api_version},
            )
            logger.info(
                "embedding_client_init",
                provider="gemini", model=GEMINI_EMBED_MODEL,
                api_version=api_version,
            )
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
                return self._embed_gemini(text_clean, task="RETRIEVAL_DOCUMENT")
            else:
                return self._embed_openai(text_clean)
        except Exception as exc:
            logger.warning("embedding_failed", error=str(exc), text_len=len(text_clean))
            return []

    def _embed_gemini(self, text: str, *, task: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """New SDK call. task: RETRIEVAL_DOCUMENT (default) | RETRIEVAL_QUERY |
        SEMANTIC_SIMILARITY | CLASSIFICATION | CLUSTERING.

        output_dimensionality=768 explicit ativa Matryoshka truncation NATIVA
        do text-embedding-004 (informação mais densa nas primeiras dimensões).
        """
        from google.genai import types
        client = self._ensure_client()
        config = types.EmbedContentConfig(
            task_type=task,
            output_dimensionality=EMBEDDING_DIM,
        )
        result = client.models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=text,
            config=config,
        )
        # New SDK retorna result.embeddings: list[ContentEmbedding]
        embeddings = getattr(result, "embeddings", None) or []
        if not embeddings:
            logger.warning("gemini_embedding_no_result")
            return []
        values = getattr(embeddings[0], "values", None)
        if not values:
            logger.warning("gemini_embedding_no_values")
            return []
        vec = list(values)
        if len(vec) != EMBEDDING_DIM:
            logger.warning(
                "gemini_embedding_unexpected_dim",
                got=len(vec), expected=EMBEDDING_DIM,
            )
            # Truncação defensiva caso modelo retorne >768 (sem Matryoshka)
            if len(vec) > EMBEDDING_DIM:
                vec = vec[:EMBEDDING_DIM]
                # Re-normaliza pra preservar cosine similarity
                import math
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]
            else:
                return []
        return vec

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
        """Variante com task_type=RETRIEVAL_QUERY (Gemini) — otimiza busca.

        text-embedding-004 tem prompts otimizados separados pra "indexar
        documento" vs "buscar por query" — usar o tipo certo melhora recall
        em ~3-7% (papers Google).
        """
        if not text or not text.strip():
            return []
        try:
            if self.provider == "gemini":
                return self._embed_gemini(text.strip()[:8000], task="RETRIEVAL_QUERY")
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
