"""Serviço de embeddings semânticos para pattern detection de relatos clínicos.

Gera embeddings vetoriais de 768 dimensões usando o modelo do provider LLM ativo.

Auth modes (auto-detectado via env, prioridade: Vertex > Gemini API):
  1. **Vertex AI** (recomendado pra produção):
     - Setar GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
     - Acesso a text-embedding-005 (sucessor do 004), text-embedding-large,
       multilingual-002, multimodalembedding etc.
     - SA + IAM granular, Cloud Logging audit, suporte enterprise.
  2. **Gemini API** (fallback / dev):
     - Setar GOOGLE_API_KEY=AIza...
     - Acesso limitado: gemini-embedding-{001,2,2-preview} apenas.
     - Single API key, sem audit log GCP.

Default models por mode:
  - Vertex:    text-embedding-005 (GA, Matryoshka nativo, mais novo)
  - Gemini API: gemini-embedding-2 (GA, único Matryoshka disponível na API standard)

Override via env GEMINI_EMBED_MODEL pra forçar modelo específico.

Dimensão: 768 (alinhada com schema vector(768) na migration 005). text-embedding-005
e gemini-embedding-2 retornam até 3072 nativo — truncamos via outputDimensionality
(Matryoshka — informação mais densa nas primeiras dimensões, sem perda significativa).

Cache: não há cache intencional aqui — embeddings são gerados uma única vez por
relato (no ato do salvamento) e persistidos. Buscas subsequentes usam o vetor
armazenado, não chamam o provider.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

EMBEDDING_DIM = 768


def _detect_gemini_mode() -> str:
    """Decide entre 'vertex' e 'gemini_api' baseado em env vars disponíveis.

    Vertex tem prioridade — se houver SA key file válido, usa. Caso contrário,
    cai pra API key tradicional. Permite migração gradual: você pode setar
    GOOGLE_APPLICATION_CREDENTIALS num único container pra testar Vertex
    enquanto outros ficam no Gemini API.
    """
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path and Path(sa_path).is_file():
        return "vertex"
    return "gemini_api"


# Default model varia por mode. Override via GEMINI_EMBED_MODEL pra forçar.
def _default_model_for_mode(mode: str) -> str:
    if mode == "vertex":
        return "text-embedding-005"  # sucessor do 004, GA, Matryoshka nativo
    return "gemini-embedding-2"      # único Matryoshka GA na Gemini API standard


GEMINI_EMBED_MODEL = os.getenv(
    "GEMINI_EMBED_MODEL",
    _default_model_for_mode(_detect_gemini_mode()),
)


class EmbeddingService:
    def __init__(self):
        self.provider = settings.llm_provider
        self._client = None  # lazy init
        self._mode: Optional[str] = None  # 'vertex' | 'gemini_api' (gemini só)

    def _ensure_client(self):
        if self._client is not None:
            return self._client

        if self.provider == "gemini":
            self._init_gemini_client()
        elif self.provider == "anthropic":
            self._init_openai_fallback()
        else:
            raise RuntimeError(f"Provider desconhecido: {self.provider}")

        return self._client

    def _init_gemini_client(self):
        """Inicializa client google-genai detectando auto entre Vertex e Gemini API."""
        from google import genai

        mode = _detect_gemini_mode()
        if mode == "vertex":
            project = os.getenv("GOOGLE_CLOUD_PROJECT", "connectaiacare-prod")
            location = os.getenv("VERTEX_LOCATION", "us-central1")
            self._client = genai.Client(
                vertexai=True, project=project, location=location,
            )
            self._mode = "vertex"
            logger.info(
                "embedding_client_init",
                provider="gemini", mode="vertex",
                project=project, location=location,
                model=GEMINI_EMBED_MODEL,
            )
        else:
            # Gemini API standard (api_version v1beta — única que aceita
            # gemini-embedding-* via embedContent endpoint)
            if not settings.google_api_key:
                raise RuntimeError(
                    "Sem auth Vertex (GOOGLE_APPLICATION_CREDENTIALS) nem "
                    "GOOGLE_API_KEY. Configurar 1 dos 2 pra usar embeddings Gemini."
                )
            api_version = os.getenv("GENAI_API_VERSION", "v1beta")
            self._client = genai.Client(
                api_key=settings.google_api_key,
                http_options={"api_version": api_version},
            )
            self._mode = "gemini_api"
            logger.info(
                "embedding_client_init",
                provider="gemini", mode="gemini_api",
                api_version=api_version,
                model=GEMINI_EMBED_MODEL,
            )

    def _init_openai_fallback(self):
        """Anthropic não tem embeddings — cai pra OpenAI quando disponível."""
        import openai
        api_key = getattr(settings, "openai_api_key", None) or ""
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic não suporta embeddings nativamente. "
                "Configurar OPENAI_API_KEY pra embeddings ou trocar pra LLM_PROVIDER=gemini."
            )
        self._client = openai.OpenAI(api_key=api_key)
        self._mode = "openai"
        logger.info(
            "embedding_client_init",
            provider="openai", model="text-embedding-3-small",
        )

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
        do text-embedding-005 / gemini-embedding-2 (informação mais densa nas
        primeiras dimensões — preserva qualidade).
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

        text-embedding-005 / gemini-embedding-2 têm prompts otimizados separados
        pra "indexar documento" vs "buscar por query" — usar o tipo certo melhora
        recall em ~3-7% (papers Google).
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
