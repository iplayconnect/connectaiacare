"""Knowledge Base Service — RAG vetorizado para Sofia.

Pivot da Onda B (ADR-027). Alimenta:
    - Agente de objeções (busca argumentos por similaridade)
    - Respostas contextuais em onboarding / companion
    - Futuro: agentes especialistas (Onda D)

API principal:

    kb = get_knowledge_base()

    # Ingestão (chamada pelo seeder)
    kb.upsert_chunk(
        domain="plans",
        subdomain="plano_premium",
        title="Plano Premium — R$ 149,90/mês",
        content="...",
        keywords=["premium", "149", "teleconsulta"],
        applies_to_plans=["premium"],
    )

    # Busca semântica (chamada pelo agente objeções)
    results = kb.search(
        query="é muito caro",
        domain="pricing_objections",
        top_k=3,
        min_similarity=0.55,
    )
    # → List[KnowledgeResult]

    # Resposta final montada:
    context = kb.format_for_prompt(results)
    # texto pra injetar no system/user prompt do LLM

Estrutura:
    - Embeddings 768-dim (via embedding_service, Gemini ou OpenAI)
    - Ranking: cosine similarity + boost lexical (keywords) + priority field
    - Telemetria: log de retrievals em aia_health_kb_retrieval_log
      (detecta gaps, calibra ranking)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.services.embedding_service import get_embedding_service
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_TENANT = "sofiacuida_b2c"
DEFAULT_TOP_K = 3
DEFAULT_MIN_SIMILARITY = 0.55
FALLBACK_MIN_SIMILARITY = 0.40   # abaixo disso, considera "não achou"


@dataclass
class KnowledgeResult:
    id: str
    domain: str
    subdomain: str | None
    title: str
    content: str
    summary: str | None
    similarity: float
    priority: int
    keywords: list[str] = field(default_factory=list)
    source_type: str | None = None
    confidence: str = "high"


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class KnowledgeBaseService:
    def __init__(self):
        self.db = get_postgres()
        self.embeddings = get_embedding_service()

    # ═══════════════════════════════════════════════════════════════
    # Ingestão
    # ═══════════════════════════════════════════════════════════════

    def upsert_chunk(
        self,
        *,
        domain: str,
        title: str,
        content: str,
        subdomain: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        applies_to_plans: list[str] | None = None,
        applies_to_roles: list[str] | None = None,
        priority: int = 50,
        confidence: str = "high",
        source: str | None = None,
        source_type: str = "internal_curated",
        tenant_id: str = DEFAULT_TENANT,
    ) -> str:
        """Upsert de chunk (regenera embedding sempre).

        Returns:
            UUID do chunk.
        """
        # Gera embedding do content (truncado se muito longo)
        embed_input = f"{title}\n\n{content}"
        embedding = self.embeddings.embed(embed_input)
        if not embedding:
            logger.warning(
                "kb_embed_failed_using_null",
                domain=domain, title=title[:50],
            )
            embedding_str = None
        else:
            embedding_str = self._format_vector(embedding)

        # Procura chunk existente (mesmo tenant + domain + subdomain + title)
        # pra upsert ao invés de duplicar
        existing = self.db.fetch_one(
            """
            SELECT id FROM aia_health_knowledge_chunks
            WHERE tenant_id = %s AND domain = %s AND title = %s
              AND (subdomain IS NOT DISTINCT FROM %s)
            LIMIT 1
            """,
            (tenant_id, domain, title, subdomain),
        )

        if existing:
            self.db.execute(
                """
                UPDATE aia_health_knowledge_chunks
                SET content = %s,
                    summary = %s,
                    embedding = %s::vector,
                    keywords = %s,
                    applies_to_plans = %s,
                    applies_to_roles = %s,
                    priority = %s,
                    confidence = %s,
                    source = %s,
                    source_type = %s,
                    version = version + 1,
                    active = TRUE,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    content, summary, embedding_str,
                    keywords or [],
                    applies_to_plans or [],
                    applies_to_roles or [],
                    priority, confidence, source, source_type,
                    existing["id"],
                ),
            )
            return str(existing["id"])

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_knowledge_chunks
                (tenant_id, domain, subdomain, title, content, summary,
                 embedding, keywords, applies_to_plans, applies_to_roles,
                 priority, confidence, source, source_type)
            VALUES (%s, %s, %s, %s, %s, %s,
                    %s::vector, %s, %s, %s,
                    %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id, domain, subdomain, title, content, summary,
                embedding_str,
                keywords or [],
                applies_to_plans or [],
                applies_to_roles or [],
                priority, confidence, source, source_type,
            ),
        )
        return str(row["id"]) if row else ""

    def deactivate_chunk(self, chunk_id: str) -> None:
        self.db.execute(
            "UPDATE aia_health_knowledge_chunks SET active = FALSE WHERE id = %s",
            (chunk_id,),
        )

    # ═══════════════════════════════════════════════════════════════
    # Busca semântica
    # ═══════════════════════════════════════════════════════════════

    def search(
        self,
        query: str,
        *,
        domain: str | None = None,
        subdomain: str | None = None,
        plan_filter: str | None = None,
        role_filter: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        tenant_id: str = DEFAULT_TENANT,
        session_id: str | None = None,
        phone: str | None = None,
        log: bool = True,
    ) -> list[KnowledgeResult]:
        """Busca chunks por similaridade cosine + filtros estruturais.

        Args:
            query: texto da pergunta/dúvida
            domain: filtra por domínio específico (plans, compliance, etc)
            subdomain: filtra por subdomínio específico
            plan_filter: só retorna chunks que se aplicam a este plano
            role_filter: só retorna chunks que se aplicam a este role
            top_k: quantos resultados trazer
            min_similarity: corta resultados abaixo desse score
            log: grava retrieval no log de telemetria
        """
        if not query or not query.strip():
            return []

        t_start = time.time()

        # Gera embedding da query
        query_embedding = self.embeddings.embed_for_query(query)
        if not query_embedding:
            logger.warning("kb_search_no_embedding", query=query[:80])
            return []

        query_vec_str = self._format_vector(query_embedding)

        # Monta WHERE dinâmico
        where_clauses = [
            "tenant_id = %s",
            "active = TRUE",
            "embedding IS NOT NULL",
        ]
        params: list[Any] = [tenant_id]

        if domain:
            where_clauses.append("domain = %s")
            params.append(domain)
        if subdomain:
            where_clauses.append("subdomain = %s")
            params.append(subdomain)
        if plan_filter:
            where_clauses.append(
                "(applies_to_plans = '{}' OR %s = ANY(applies_to_plans))"
            )
            params.append(plan_filter)
        if role_filter:
            where_clauses.append(
                "(applies_to_roles = '{}' OR %s = ANY(applies_to_roles))"
            )
            params.append(role_filter)

        # Busca com cosine distance (1 - similarity; <=> operador pgvector)
        # priority adiciona boost pequeno (valor 0-100 convertido em 0-0.1)
        query_sql = f"""
            SELECT id, domain, subdomain, title, content, summary,
                   keywords, priority, confidence, source_type,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM aia_health_knowledge_chunks
            WHERE {' AND '.join(where_clauses)}
            ORDER BY
                (1 - (embedding <=> %s::vector)) + (priority / 1000.0) DESC
            LIMIT %s
        """

        params_full = [query_vec_str] + params + [query_vec_str, top_k * 2]  # 2x pra filtrar por min_similarity depois

        rows = self.db.fetch_all(query_sql, tuple(params_full))

        # Filtra por min_similarity
        results: list[KnowledgeResult] = []
        for r in rows:
            sim = float(r.get("similarity", 0.0))
            if sim < min_similarity:
                continue
            results.append(KnowledgeResult(
                id=str(r["id"]),
                domain=r["domain"],
                subdomain=r.get("subdomain"),
                title=r["title"],
                content=r["content"],
                summary=r.get("summary"),
                similarity=sim,
                priority=int(r.get("priority", 50)),
                keywords=list(r.get("keywords") or []),
                source_type=r.get("source_type"),
                confidence=r.get("confidence", "high"),
            ))
            if len(results) >= top_k:
                break

        latency_ms = int((time.time() - t_start) * 1000)

        # Telemetria — sempre grava pra calibração
        if log:
            try:
                self._log_retrieval(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    phone=phone,
                    query=query,
                    domain=domain,
                    embedding_str=query_vec_str,
                    results=results,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                logger.debug("kb_retrieval_log_failed", error=str(exc))

        logger.info(
            "kb_search",
            query=query[:80], domain=domain,
            results=len(results),
            top_sim=round(results[0].similarity, 3) if results else 0,
            latency_ms=latency_ms,
        )
        return results

    # ═══════════════════════════════════════════════════════════════
    # Formatação pra prompt
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def format_for_prompt(results: list[KnowledgeResult]) -> str:
        """Converte resultados em texto pra injetar no prompt LLM.

        Formato:
            CONTEXTO DA BASE DE CONHECIMENTO:
            [1] <título>
            <content resumido>

            [2] ...
        """
        if not results:
            return ""

        lines = ["CONTEXTO DA BASE DE CONHECIMENTO:"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n[{i}] {r.title}")
            # Trunca conteúdo pra não explodir o prompt (800 chars/chunk é um bom meio)
            content = r.content.strip()
            if len(content) > 800:
                content = content[:800] + "..."
            lines.append(content)
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════
    # Consultas utilitárias
    # ═══════════════════════════════════════════════════════════════

    def list_by_domain(
        self,
        domain: str,
        *,
        tenant_id: str = DEFAULT_TENANT,
        active_only: bool = True,
    ) -> list[dict]:
        where = ["tenant_id = %s", "domain = %s"]
        params = [tenant_id, domain]
        if active_only:
            where.append("active = TRUE")
        return self.db.fetch_all(
            f"""
            SELECT id, domain, subdomain, title, summary, priority, confidence, active
            FROM aia_health_knowledge_chunks
            WHERE {' AND '.join(where)}
            ORDER BY priority DESC, title ASC
            """,
            tuple(params),
        )

    def count_by_domain(self, tenant_id: str = DEFAULT_TENANT) -> dict[str, int]:
        rows = self.db.fetch_all(
            """
            SELECT domain, COUNT(*) AS n
            FROM aia_health_knowledge_chunks
            WHERE tenant_id = %s AND active = TRUE
            GROUP BY domain
            """,
            (tenant_id,),
        )
        return {r["domain"]: int(r["n"]) for r in rows}

    # ═══════════════════════════════════════════════════════════════
    # Telemetria
    # ═══════════════════════════════════════════════════════════════

    def _log_retrieval(
        self,
        *,
        tenant_id: str,
        session_id: str | None,
        phone: str | None,
        query: str,
        domain: str | None,
        embedding_str: str | None,
        results: list[KnowledgeResult],
        latency_ms: int,
    ) -> None:
        top_sim = results[0].similarity if results else 0.0
        fallback = len(results) == 0 or top_sim < FALLBACK_MIN_SIMILARITY
        chunk_ids = [r.id for r in results]
        self.db.execute(
            """
            INSERT INTO aia_health_kb_retrieval_log
                (tenant_id, subject_phone, session_id,
                 query_text, query_domain, query_embedding,
                 chunks_returned, top_similarity, fallback_triggered,
                 latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
            """,
            (
                tenant_id, phone, session_id,
                query[:1000], domain, embedding_str,
                chunk_ids, top_sim, fallback, latency_ms,
            ),
        )

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _format_vector(vec: list[float]) -> str:
        """Formata lista pro formato aceito por pgvector: '[0.1,0.2,...]'."""
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


# Singleton
_instance: KnowledgeBaseService | None = None


def get_knowledge_base() -> KnowledgeBaseService:
    global _instance
    if _instance is None:
        _instance = KnowledgeBaseService()
    return _instance
