"""Pattern Detection — detecção de padrões clínicos históricos para um paciente.

Executa 5 minutos após o evento abrir (agendado pelo scheduler). Busca padrões
relevantes no histórico do paciente e gera um **resumo enriquecido** que o sistema
envia ao cuidador como "alerta de padrão".

Três camadas de busca, combinadas:

1. **Tag-based counting** (rápida, 1 query SQL):
   Conta quantos eventos com mesma tag (ex: "queda") ocorreram nos últimos N dias.
   Detecta repetições óbvias: "é a 3ª queda em 15 dias".

2. **Semantic similarity** (pgvector, cosine):
   Embedding do relato atual vs embeddings dos relatos anteriores. Encontra
   situações SEMANTICAMENTE parecidas mesmo quando tags/palavras são diferentes.
   Ex: "caiu do banheiro" e "escorregou indo pro quarto" — semanticamente próximos.

3. **Structured timeline features** (opcional, P1):
   Intervalos entre eventos, progressão de classificação (routine → attention →
   urgent sugere deterioração), medicações ajustadas entre eventos.

Output: dict com keys:
    - has_pattern: bool
    - kind: "recurring_event" | "progressive_severity" | "similar_episode" | "none"
    - headline: str curta pro cuidador ("⚠️ Esta é a 3ª queda em 15 dias")
    - details: list[str] com explicações
    - related_events: list[dict] com eventos comparáveis achados
    - suggested_classification: str | None (pode sugerir escalação)

Zero efeito colateral no DB — só leitura + LLM. Quem salva é o chamador
(orchestrator → CareEventService.update_classification + envia mensagem).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.embedding_service import get_embedding_service
from src.services.llm import MODEL_FAST, get_llm
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Janela default de busca histórica (dias)
DEFAULT_HISTORY_WINDOW_DAYS = 30
# Threshold de similaridade semântica para considerar "episódio parecido"
# Cosine distance (0=idêntico, 1=oposto). pgvector usa <=> operador.
# 0.35 captura similaridade moderada sem muitos falsos-positivos.
SIMILARITY_DISTANCE_THRESHOLD = 0.35
# Quantos eventos similares no máximo
MAX_SIMILAR_EVENTS = 5

PATTERN_SUMMARY_PROMPT = """Você é assistente de enfermagem. Gere UM ALERTA BREVE para WhatsApp sobre o padrão histórico detectado no paciente.

Regras:
- Máximo 3 linhas curtas
- Comece com emoji contextual (⚠️ atenção, 🔴 grave, 📋 informativo)
- Mencione QUANTIDADE + JANELA ("3ª queda em 15 dias")
- Se houver progressão clara de severidade, diga isso
- NUNCA diagnostique — só descreva o padrão
- NUNCA recomende medicação
- Termine sugerindo uma ação prática de observação (não-prescritiva)

<pattern_data>
{pattern_data}
</pattern_data>

<current_event>
{current_event}
</current_event>

Responda APENAS com JSON:
{{
  "headline": "texto curto ≤ 3 linhas, com emoji",
  "severity_cue": "info|attention|alert",
  "observation_suggestion": "sugestão prática de observação em 1 frase"
}}
"""


class PatternDetectionService:
    def __init__(self):
        self.db = get_postgres()
        self.embeddings = get_embedding_service()
        self.llm = get_llm()

    def detect(
        self,
        patient_id: str,
        current_event_id: str,
        current_transcript: str,
        current_event_tags: list[str] | None = None,
        current_classification: str | None = None,
        window_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    ) -> dict[str, Any]:
        """Detecta padrões históricos. Retorna sempre um dict (pode ser has_pattern=False)."""
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        tags = current_event_tags or []

        # --- Camada 1: tag-based counting ---
        tag_matches = self._count_by_tags(patient_id, tags, since, current_event_id)

        # --- Camada 2: semantic similarity ---
        similar = self._find_similar_events(
            patient_id, current_transcript, since, current_event_id
        )

        # --- Camada 3: progressão de severidade ---
        progression = self._detect_severity_progression(
            patient_id, since, current_classification, current_event_id
        )

        has_pattern = (
            bool(tag_matches and tag_matches["count"] >= 2)
            or bool(similar)
            or bool(progression and progression.get("escalating"))
        )

        if not has_pattern:
            return {
                "has_pattern": False,
                "kind": "none",
                "headline": None,
                "details": [],
                "related_events": [],
                "suggested_classification": None,
            }

        kind = self._classify_pattern_kind(tag_matches, similar, progression)
        related_events = self._merge_related_events(tag_matches, similar)
        suggested = self._suggest_classification(
            tag_matches, similar, progression, current_classification
        )

        # LLM gera o headline humano com base nos dados estruturados
        llm_summary = self._generate_headline(
            tag_matches, similar, progression, current_transcript, current_event_tags
        )

        details = self._build_details(tag_matches, similar, progression)

        result = {
            "has_pattern": True,
            "kind": kind,
            "headline": llm_summary.get("headline"),
            "severity_cue": llm_summary.get("severity_cue", "attention"),
            "observation_suggestion": llm_summary.get("observation_suggestion"),
            "details": details,
            "related_events": related_events[:MAX_SIMILAR_EVENTS],
            "tag_count_in_window": tag_matches["count"] if tag_matches else 0,
            "suggested_classification": suggested,
        }
        logger.info(
            "pattern_detected",
            patient_id=patient_id,
            kind=kind,
            tag_count=result["tag_count_in_window"],
            similar_count=len(similar),
            suggested_classification=suggested,
        )
        return result

    # ---------- camadas ----------
    def _count_by_tags(
        self, patient_id: str, tags: list[str], since: datetime, exclude_event_id: str
    ) -> dict[str, Any] | None:
        if not tags:
            return None
        rows = self.db.fetch_all(
            """
            SELECT id, human_id, event_type, event_tags, opened_at,
                   current_classification, summary
            FROM aia_health_care_events
            WHERE patient_id = %s
              AND opened_at >= %s
              AND id <> %s
              AND event_tags && %s::text[]
            ORDER BY opened_at DESC
            LIMIT 20
            """,
            (patient_id, since, exclude_event_id, tags),
        )
        if not rows:
            return None
        return {
            "tags_matched": tags,
            "count": len(rows),
            "events": rows,
            "earliest": rows[-1]["opened_at"],
            "latest": rows[0]["opened_at"],
        }

    def _find_similar_events(
        self, patient_id: str, current_transcript: str, since: datetime, exclude_event_id: str
    ) -> list[dict]:
        """Busca semântica via embedding. Retorna relatos com cosine distance baixa."""
        query_vec = self.embeddings.embed_for_query(current_transcript)
        if not query_vec:
            return []

        # pgvector: operador <=> = cosine distance. ORDER ASC = mais próximo primeiro.
        rows = self.db.fetch_all(
            """
            SELECT r.id AS report_id, r.care_event_id AS event_id,
                   r.transcription, r.analysis, r.classification, r.received_at,
                   (r.embedding <=> %s::vector) AS distance
            FROM aia_health_reports r
            WHERE r.patient_id = %s
              AND r.received_at >= %s
              AND r.embedding IS NOT NULL
              AND (r.care_event_id IS NULL OR r.care_event_id <> %s)
              AND (r.embedding <=> %s::vector) <= %s
            ORDER BY r.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                query_vec, patient_id, since, exclude_event_id,
                query_vec, SIMILARITY_DISTANCE_THRESHOLD,
                query_vec, MAX_SIMILAR_EVENTS,
            ),
        )
        # Normaliza similaridade (1 - distance) pra leitura humana
        for r in rows:
            r["similarity"] = 1.0 - float(r["distance"])
        return rows

    def _detect_severity_progression(
        self, patient_id: str, since: datetime, current_classification: str | None,
        exclude_event_id: str,
    ) -> dict[str, Any] | None:
        rows = self.db.fetch_all(
            """
            SELECT current_classification, opened_at
            FROM aia_health_care_events
            WHERE patient_id = %s AND opened_at >= %s AND id <> %s
            ORDER BY opened_at
            """,
            (patient_id, since, exclude_event_id),
        )
        if len(rows) < 2:
            return None

        rank = {"routine": 1, "attention": 2, "urgent": 3, "critical": 4}
        sequence = [rank.get(r["current_classification"] or "attention", 2) for r in rows]
        if current_classification:
            sequence.append(rank.get(current_classification, 2))

        # Detecta tendência crescente (último > primeiro e diferença ≥ 2 passos)
        escalating = (
            len(sequence) >= 3
            and sequence[-1] > sequence[0]
            and (sequence[-1] - min(sequence[:-1])) >= 1
        )
        return {
            "escalating": escalating,
            "sequence": sequence,
            "events_count": len(rows) + 1,
        }

    # ---------- síntese ----------
    def _classify_pattern_kind(
        self,
        tag_matches: dict | None,
        similar: list[dict],
        progression: dict | None,
    ) -> str:
        if tag_matches and tag_matches["count"] >= 2:
            return "recurring_event"
        if progression and progression.get("escalating"):
            return "progressive_severity"
        if similar:
            return "similar_episode"
        return "none"

    def _merge_related_events(
        self, tag_matches: dict | None, similar: list[dict]
    ) -> list[dict]:
        out: list[dict] = []
        seen_ids: set[str] = set()
        if tag_matches:
            for e in tag_matches["events"]:
                eid = str(e["id"])
                if eid in seen_ids:
                    continue
                out.append({
                    "event_id": eid,
                    "human_id": e.get("human_id"),
                    "opened_at": str(e["opened_at"]),
                    "classification": e.get("current_classification"),
                    "summary": e.get("summary"),
                    "source": "tag_match",
                })
                seen_ids.add(eid)
        for s in similar:
            eid = str(s.get("event_id") or s.get("report_id"))
            if eid in seen_ids:
                continue
            out.append({
                "event_id": eid,
                "report_id": str(s.get("report_id")),
                "opened_at": str(s.get("received_at")),
                "classification": s.get("classification"),
                "similarity": round(s.get("similarity", 0.0), 3),
                "source": "semantic",
            })
            seen_ids.add(eid)
        return out

    def _suggest_classification(
        self,
        tag_matches: dict | None,
        similar: list[dict],
        progression: dict | None,
        current: str | None,
    ) -> str | None:
        rank = {"routine": 1, "attention": 2, "urgent": 3, "critical": 4}
        inverse = {v: k for k, v in rank.items()}
        cur = rank.get(current or "attention", 2)

        # 3+ eventos com mesma tag em 30 dias → subir 1 nível (se não for critical)
        if tag_matches and tag_matches["count"] >= 2 and cur < 4:
            return inverse[min(cur + 1, 4)]
        # Progressão de severidade histórica → subir 1 nível
        if progression and progression.get("escalating") and cur < 4:
            return inverse[min(cur + 1, 4)]
        return None

    def _build_details(
        self, tag_matches: dict | None, similar: list[dict], progression: dict | None
    ) -> list[str]:
        details: list[str] = []
        if tag_matches:
            tags = ", ".join(tag_matches["tags_matched"])
            details.append(
                f"Detectados {tag_matches['count']} eventos anteriores com tag [{tags}] "
                f"no histórico do paciente (janela de busca: 30 dias)."
            )
        if similar:
            details.append(
                f"Encontrei {len(similar)} relato(s) anterior(es) semanticamente parecido(s) "
                f"(similaridade ≥ {int((1 - SIMILARITY_DISTANCE_THRESHOLD) * 100)}%)."
            )
        if progression and progression.get("escalating"):
            details.append(
                "Progressão de severidade detectada: histórico mostra tendência de piora "
                "nos últimos eventos."
            )
        return details

    def _generate_headline(
        self,
        tag_matches: dict | None,
        similar: list[dict],
        progression: dict | None,
        current_transcript: str,
        current_tags: list[str] | None,
    ) -> dict[str, Any]:
        # Estrutura compacta de dados pra LLM
        pattern_data = {
            "tag_counting": {
                "tags": (tag_matches["tags_matched"] if tag_matches else []),
                "count_in_30d": tag_matches["count"] if tag_matches else 0,
                "oldest": str(tag_matches["earliest"]) if tag_matches else None,
                "newest": str(tag_matches["latest"]) if tag_matches else None,
            } if tag_matches else None,
            "similar_episodes": [
                {"similarity_pct": int(s["similarity"] * 100), "when": str(s["received_at"])}
                for s in similar[:3]
            ],
            "progression": progression,
        }
        current_event_summary = {
            "tags": current_tags or [],
            "transcript_excerpt": (current_transcript or "")[:300],
        }

        prompt = PATTERN_SUMMARY_PROMPT.format(
            pattern_data=json.dumps(pattern_data, ensure_ascii=False, indent=2, default=str),
            current_event=json.dumps(current_event_summary, ensure_ascii=False, indent=2),
        )

        try:
            result = self.llm.complete_json(
                system="Você gera alertas clínicos curtos em pt-BR pra WhatsApp.",
                user=prompt,
                model=MODEL_FAST,
                max_tokens=512,
                temperature=0.1,
            )
            if not isinstance(result, dict):
                raise ValueError("resposta não é dict")
            return {
                "headline": result.get("headline") or self._fallback_headline(tag_matches, similar, progression),
                "severity_cue": result.get("severity_cue", "attention"),
                "observation_suggestion": result.get("observation_suggestion"),
            }
        except Exception as exc:
            logger.warning("pattern_headline_llm_failed", error=str(exc))
            return {
                "headline": self._fallback_headline(tag_matches, similar, progression),
                "severity_cue": "attention",
                "observation_suggestion": None,
            }

    def _fallback_headline(
        self,
        tag_matches: dict | None,
        similar: list[dict],
        progression: dict | None,
    ) -> str:
        parts = []
        if tag_matches and tag_matches["count"] >= 2:
            tag = tag_matches["tags_matched"][0] if tag_matches["tags_matched"] else "evento"
            parts.append(
                f"⚠️ {tag_matches['count'] + 1}ª ocorrência de {tag} no histórico em 30 dias"
            )
        elif progression and progression.get("escalating"):
            parts.append("⚠️ Tendência de piora detectada no histórico recente do paciente")
        elif similar:
            parts.append(f"📋 {len(similar)} episódio(s) parecido(s) no histórico")
        return ". ".join(parts) or "📋 Padrão histórico identificado"


_pattern_instance: PatternDetectionService | None = None


def get_pattern_detection_service() -> PatternDetectionService:
    global _pattern_instance
    if _pattern_instance is None:
        _pattern_instance = PatternDetectionService()
    return _pattern_instance
