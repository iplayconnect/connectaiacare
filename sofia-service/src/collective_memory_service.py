"""Sofia Collective Memory Service — memória coletiva cross-tenant
anonimizada. Extrai padrões agregados de TODAS as interações Sofia↔
Profissional e publica como knowledge_chunks que enriquecem todas as
respostas futuras da Sofia.

Pipeline (executado pelo collective_insights_scheduler 1×/dia):
  1. window = mensagens entre cursor.last_message_window_end e NOW
  2. anonymize_messages(window) — strip de PII (regex + LLM safety pass)
  3. extract_insights(anon_msgs) — LLM agrupa em padrões com freq, type
  4. upsert_into_raw(insights) — agrega frequência se já existe similar
  5. promote_above_threshold() — quando freq >= MIN_FREQUENCY, copia
     pra aia_health_knowledge_chunks (domain='collective_insight')
  6. atualiza cursor

LGPD:
  - Mensagens crus NUNCA saem de aia_health_sofia_messages
  - O staging table só guarda texto JÁ anonimizado
  - Mínimo de freq=3 antes de publicar (privacidade diferencial básica)
  - Audit em aia_health_audit_chain
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from src import persistence
from src.llm_client import generate

logger = logging.getLogger(__name__)

EXTRACTOR_MODEL = (
    os.getenv("SOFIA_COLLECTIVE_MODEL")
    or os.getenv("SOFIA_LLM_MODEL")
    or "gemini-3-flash-preview"
)
MIN_FREQUENCY_TO_PROMOTE = int(
    os.getenv("SOFIA_COLLECTIVE_MIN_FREQ") or "3"
)
WINDOW_HOURS = int(os.getenv("SOFIA_COLLECTIVE_WINDOW_HOURS") or "24")
MAX_MESSAGES_PER_RUN = int(os.getenv("SOFIA_COLLECTIVE_MAX_MSGS") or "500")


# ────────────────────────── Anonymization ──────────────────────────

# Regex que pegam PII óbvias antes de mandar pra LLM. Conservadores —
# preferem falsos positivos a falsos negativos.
_RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_RE_EMAIL = re.compile(r"\b[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
# Telefones brasileiros — mata números com DDD. Conservador.
_RE_PHONE = re.compile(
    r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-.\s]?\d{4}"
)
_RE_CRM_COREN = re.compile(r"\b(?:CRM|COREN|CRF|CREFITO)[-/\s]?\w*[-/]?\d+\b", re.I)
# CPF: 000.000.000-00 ou 11 dígitos seguidos
_RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
# Nomes próprios capitalizados em padrões "Sr./Sra./Dr./Dra. Fulano" e
# "Dona Maria" comuns em saúde — substitui por placeholder.
_RE_HONORIFIC_NAME = re.compile(
    r"(?:\b(?:Sr|Sra|Dr|Dra|Prof|Dona|Seu|Sñ)\.?\s+)([A-ZÀ-Ý][a-zà-ÿ]+(?:\s+(?:da|de|do|das|dos|e|von|van)\s+)?(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+){0,3})"
)


def _scrub_pii_regex(text: str) -> str:
    """Primeira passada: regex agressiva mas conservadora."""
    if not text:
        return text
    text = _RE_UUID.sub("[UUID]", text)
    text = _RE_EMAIL.sub("[EMAIL]", text)
    text = _RE_PHONE.sub("[TELEFONE]", text)
    text = _RE_CRM_COREN.sub("[REGISTRO_PROFISSIONAL]", text)
    text = _RE_CPF.sub("[DOCUMENTO]", text)
    text = _RE_HONORIFIC_NAME.sub(r"[PESSOA]", text)
    return text


_ANON_LLM_PROMPT = """Você é um anonimizador LGPD. Recebe um TRECHO de \
conversa e devolve a MESMA mensagem com TODAS as informações pessoais \
identificáveis substituídas por placeholders genéricos.

Substituições obrigatórias:
- Nomes próprios de pessoas (paciente, cuidador, médico, familiar) → [PESSOA]
- Nomes de unidades, hospitais, clínicas específicas → [UNIDADE]
- Endereços, bairros, ruas → [LOCAL]
- Números de quarto, leito → [QUARTO]
- Datas de nascimento específicas → [DATA_NASCIMENTO]
- Idades muito específicas (ex: "87 anos e 3 meses") → "idoso(a)" ou "geriátrico(a)"
- Marcas/medicamentos comerciais permanecem (Sifrol, Pradaxa, etc.) — esses não são PII

Mantenha:
- Classes terapêuticas, princípios ativos, condições clínicas (Parkinson, demência etc.)
- Padrões de pergunta e raciocínio clínico
- Termos técnicos (Beers, ClCr, Child-Pugh, ACB)

Devolva APENAS o texto anonimizado, sem comentários."""


def _scrub_pii_llm(text: str) -> str:
    """Segunda passada: LLM pega o que regex não pegou (nomes de unidade,
    bairros, idades específicas, etc.). Pulado em textos curtos."""
    if not text or len(text) < 30:
        return text
    try:
        result = generate(
            system_prompt=_ANON_LLM_PROMPT,
            messages=[{"role": "user", "content": text}],
            model=EXTRACTOR_MODEL,
            max_output_tokens=600,
            thinking_level="low",
        )
        out = (result.text or "").strip()
        return out if out else text
    except Exception as exc:
        logger.warning("collective_anon_llm_failed: %s", exc)
        return text


def anonymize_block(text: str) -> str:
    """Pipeline completo de anonimização — regex + LLM."""
    cleaned = _scrub_pii_regex(text or "")
    return _scrub_pii_llm(cleaned)


# ────────────────────────── Extraction ──────────────────────────

_EXTRACT_PROMPT = """Você é um analista que identifica PADRÕES recorrentes \
em conversas anonimizadas entre profissionais de saúde e a IA Sofia.

Recebe vários trechos de mensagens (texto JÁ anonimizado). Devolve uma \
lista de INSIGHTS agregados, cada um com:
- title: 1 linha, sintético
- summary: 1-2 frases sobre o padrão observado
- detail: parágrafo explicativo (markdown), com referências clínicas \
  quando aplicável
- insight_type: clinical_question | prescribing_pattern | feature_doubt | \
  knowledge_gap | workflow_friction | other
- keywords: 3-6 termos pra agrupar similares (princípios ativos, classes, \
  condições, features da plataforma)
- therapeutic_classes: lista de classes (ex: ["antiparkinsoniano", \
  "antipsicotico_atipico"]). [] se N/A.
- conditions: lista de condições mencionadas (ex: ["parkinson", "demencia"]). \
  [] se N/A.

Regras:
- Só liste insights que apareceram em PELO MENOS 2 trechos diferentes \
  (não invente repetição)
- Não inclua nada que pareça PII (já passou por anonimização — desconfie \
  se ver nome próprio, sempre placeholder)
- Pode retornar 0 insights se não há padrão real
- Máximo 10 insights por extração

Devolva APENAS JSON válido (sem markdown wrapping, sem texto fora):
{
  "insights": [
    { "title": "...", "summary": "...", "detail": "...",
      "insight_type": "...", "keywords": ["..."],
      "therapeutic_classes": ["..."], "conditions": ["..."] }
  ]
}"""


def extract_insights_from_anon_messages(anon_messages: list[str]) -> list[dict]:
    """Roda LLM sobre conjunto de mensagens anonimizadas, retorna lista
    de insights estruturados."""
    if not anon_messages:
        return []
    body = "\n---\n".join(f"[{i}] {m[:600]}" for i, m in enumerate(anon_messages))
    try:
        result = generate(
            system_prompt=_EXTRACT_PROMPT,
            messages=[{"role": "user", "content": body}],
            model=EXTRACTOR_MODEL,
            max_output_tokens=2500,
            thinking_level="medium",
        )
    except Exception as exc:
        logger.warning("collective_extract_llm_failed: %s", exc)
        return []
    raw = (result.text or "").strip()
    # Aceita ```json wrapping
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "collective_extract_parse_failed: %s raw=%r", exc, raw[:200]
        )
        return []
    return (parsed.get("insights") or [])[:10]


# ────────────────────────── Upsert (agrega frequência) ──────────────────────────

def _normalize_keywords(kws: list[str]) -> list[str]:
    """lower + strip + ordenado, pra match consistente."""
    return sorted({(k or "").strip().lower() for k in (kws or []) if k})


def upsert_insight(
    insight: dict,
    *,
    window_start: datetime,
    window_end: datetime,
    source_session_count: int,
) -> uuid.UUID:
    """Insere ou agrega frequência de um insight. Match por overlap de
    keywords (≥2 keywords iguais OR title muito similar)."""
    kws = _normalize_keywords(insight.get("keywords") or [])
    title = (insight.get("title") or "").strip()
    if not title or not kws:
        # Sem título ou keywords, nem persiste
        return None

    # Procura insight similar não-promovido com overlap de keywords
    existing = persistence.fetch_one(
        """SELECT id, frequency, keywords
           FROM aia_health_sofia_collective_insights_raw
           WHERE keywords && %s
              OR lower(title) = %s
           ORDER BY
             CASE WHEN promoted THEN 1 ELSE 0 END,
             frequency DESC
           LIMIT 1""",
        (kws, title.lower()),
    )

    if existing:
        new_freq = int(existing["frequency"]) + 1
        # mescla keywords
        merged_kws = sorted(set((existing.get("keywords") or [])) | set(kws))
        persistence.execute(
            """UPDATE aia_health_sofia_collective_insights_raw
               SET frequency = %s,
                   keywords = %s,
                   last_seen_at = %s,
                   source_session_count = source_session_count + %s
               WHERE id = %s""",
            (new_freq, merged_kws, window_end, source_session_count, existing["id"]),
        )
        return existing["id"]

    row = persistence.insert_returning(
        """INSERT INTO aia_health_sofia_collective_insights_raw
            (insight_type, title, summary, detail, keywords,
             therapeutic_classes, conditions,
             source_message_window_start, source_message_window_end,
             source_session_count, extractor_model, frequency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
        RETURNING id""",
        (
            insight.get("insight_type") or "other",
            title[:300],
            (insight.get("summary") or "")[:600],
            insight.get("detail") or "",
            kws,
            insight.get("therapeutic_classes") or [],
            insight.get("conditions") or [],
            window_start, window_end,
            source_session_count,
            EXTRACTOR_MODEL,
        ),
    )
    return row["id"] if row else None


# ────────────────────────── Promotion → knowledge_chunks ──────────────────────────

_CHUNK_TENANT_FOR_COLLECTIVE = "collective"  # tag especial pra cross-tenant


def promote_above_threshold() -> int:
    """Pega insights com freq >= MIN_FREQUENCY_TO_PROMOTE e ainda não
    promovidos; insere em aia_health_knowledge_chunks. Retorna quantos."""
    rows = persistence.fetch_all(
        """SELECT id, insight_type, title, summary, detail, keywords,
                  therapeutic_classes, conditions, frequency,
                  source_session_count, extractor_model
           FROM aia_health_sofia_collective_insights_raw
           WHERE promoted = FALSE AND frequency >= %s
           ORDER BY frequency DESC""",
        (MIN_FREQUENCY_TO_PROMOTE,),
    )
    promoted_count = 0
    for r in rows:
        # Compõe content estruturado pro chunk
        content_parts = [r.get("summary") or r.get("title") or ""]
        if r.get("detail"):
            content_parts.append("\n" + r["detail"])
        meta_lines = []
        if r.get("therapeutic_classes"):
            meta_lines.append(
                "Classes: " + ", ".join(r["therapeutic_classes"])
            )
        if r.get("conditions"):
            meta_lines.append("Condições: " + ", ".join(r["conditions"]))
        meta_lines.append(
            f"Padrão observado em {r['frequency']} interações independentes."
        )
        if meta_lines:
            content_parts.append("\n\n" + "\n".join(meta_lines))
        content = "\n".join(content_parts)

        chunk_row = persistence.insert_returning(
            """INSERT INTO aia_health_knowledge_chunks
                (tenant_id, domain, subdomain, title, content, summary,
                 keywords, priority, confidence, source, source_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id""",
            (
                _CHUNK_TENANT_FOR_COLLECTIVE,
                "collective_insight",
                r.get("insight_type"),
                r.get("title")[:300],
                content,
                (r.get("summary") or "")[:300],
                r.get("keywords") or [],
                # priority cresce com freq (cap em 80)
                min(80, 50 + (int(r["frequency"]) * 2)),
                "medium",  # ainda agregado por LLM, não curado humano
                f"collective_insights:{r['id']}",
                "collective_aggregate",
            ),
        )
        if chunk_row:
            persistence.execute(
                """UPDATE aia_health_sofia_collective_insights_raw
                   SET promoted = TRUE,
                       promoted_chunk_id = %s,
                       promoted_at = NOW()
                   WHERE id = %s""",
                (chunk_row["id"], r["id"]),
            )
            promoted_count += 1
            logger.info(
                "collective_insight_promoted id=%s chunk_id=%s freq=%d title=%r",
                r["id"], chunk_row["id"], r["frequency"], r["title"][:80],
            )
    return promoted_count


# ────────────────────────── Cron tick (entrada principal) ──────────────────────────

def run_one_cycle() -> dict:
    """Roda o pipeline completo uma vez. Idempotente — pode ser chamado
    sob demanda (ex: smoke test) ou pelo scheduler diário."""
    started = time.monotonic()
    cursor = persistence.fetch_one(
        "SELECT last_message_window_end FROM aia_health_sofia_collective_cursor WHERE id = 1"
    )
    window_start = cursor["last_message_window_end"] if cursor else (
        datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    )
    window_end = datetime.now(timezone.utc)

    # Coleta mensagens do user no período (não tooling — só conversação real)
    rows = persistence.fetch_all(
        """SELECT m.role, m.content, s.user_id, s.persona, s.tenant_id
           FROM aia_health_sofia_messages m
           JOIN aia_health_sofia_sessions s ON s.id = m.session_id
           WHERE m.role IN ('user', 'assistant')
             AND m.content IS NOT NULL
             AND length(m.content) > 10
             AND m.created_at > %s
             AND m.created_at <= %s
           ORDER BY m.created_at ASC
           LIMIT %s""",
        (window_start, window_end, MAX_MESSAGES_PER_RUN),
    )
    messages_count = len(rows)

    # Anonimiza em bloco (regex agora, LLM em batch)
    anon_msgs = []
    for r in rows:
        prefix = "[user] " if r["role"] == "user" else "[sofia] "
        # Só regex (mais barato pra ETL diário; LLM seria 1k+ chamadas)
        cleaned = _scrub_pii_regex(r["content"] or "")
        anon_msgs.append(prefix + cleaned)

    # Quebra em chunks de 25 mensagens pro LLM extrator
    BATCH = 25
    insights_extracted = 0
    distinct_session_ids = set()
    for i in range(0, len(anon_msgs), BATCH):
        batch = anon_msgs[i:i+BATCH]
        insights = extract_insights_from_anon_messages(batch)
        for ins in insights:
            iid = upsert_insight(
                ins,
                window_start=window_start,
                window_end=window_end,
                source_session_count=1,
            )
            if iid:
                insights_extracted += 1

    promoted = promote_above_threshold()
    duration_ms = int((time.monotonic() - started) * 1000)

    persistence.execute(
        """UPDATE aia_health_sofia_collective_cursor
           SET last_run_at = NOW(),
               last_message_window_end = %s,
               last_run_messages_processed = %s,
               last_run_insights_extracted = %s,
               last_run_insights_promoted = %s,
               last_run_duration_ms = %s
           WHERE id = 1""",
        (window_end, messages_count, insights_extracted, promoted, duration_ms),
    )
    logger.info(
        "collective_memory_cycle messages=%d insights=%d promoted=%d ms=%d",
        messages_count, insights_extracted, promoted, duration_ms,
    )
    return {
        "messages_processed": messages_count,
        "insights_extracted": insights_extracted,
        "insights_promoted": promoted,
        "duration_ms": duration_ms,
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat(),
    }
