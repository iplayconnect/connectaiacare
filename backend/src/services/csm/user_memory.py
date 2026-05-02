"""User Memory Writeback — memória cross-session de usuários identificados.

Phase C v2.7. Resolve problema "Sofia esquece tudo após 1h" pra users
autenticados (não anônimos): periodicamente um LLM (Haiku/fast) lê as
últimas N mensagens da sessão e atualiza:

  • summary TEXT (~500-800 chars, narrativa)
  • key_facts JSONB (preferências, tópicos em aberto, padrões)

Tabela: aia_health_sofia_user_memory (migration 031, já existe).

Quando rodar:
  • Cada 10 mensagens novas (configurável)
  • Ao fechar sessão (close_reason='timeout' ou 'handoff')
  • Manual via CLI (--user-id)

Quando NÃO rodar:
  • user.sofia_memory_enabled = FALSE (LGPD opt-out)
  • Anônimos (CSM cuida via lead_data)

Uso no orchestrator:
    if state.user_id and turns_since_last_summary >= 10:
        get_user_memory_writer().summarize(user_id, tenant_id)

Best-effort: falha não bloqueia turn.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Quantidade de mensagens novas pra disparar re-sumário
SUMMARIZE_EVERY_N = 10
# Janela de mensagens consideradas no sumário
RECENT_MESSAGES_WINDOW = 30
# Cap do summary final
MAX_SUMMARY_CHARS = 800


@dataclass
class UserMemorySnapshot:
    user_id: str
    tenant_id: str
    summary: Optional[str] = None
    key_facts: dict[str, Any] = None
    messages_at_last_summary: int = 0
    total_messages: int = 0
    last_summarized_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "UserMemorySnapshot":
        kf = row.get("key_facts")
        if isinstance(kf, str):
            try:
                kf = json.loads(kf)
            except Exception:
                kf = {}
        return cls(
            user_id=str(row["user_id"]),
            tenant_id=row["tenant_id"],
            summary=row.get("summary"),
            key_facts=kf or {},
            messages_at_last_summary=int(row.get("messages_at_last_summary") or 0),
            total_messages=int(row.get("total_messages") or 0),
            last_summarized_at=(
                row["last_summarized_at"].isoformat()
                if row.get("last_summarized_at") else None
            ),
        )

    def for_prompt(self) -> str:
        """Bloco resumido pra system prompt da próxima sessão."""
        if not self.summary and not self.key_facts:
            return ""
        lines = []
        if self.summary:
            lines.append(f"MEMÓRIA_PERSISTENTE:\n  {self.summary}")
        if self.key_facts:
            facts_str = "; ".join(
                f"{k}={v}" for k, v in list(self.key_facts.items())[:8]
            )
            lines.append(f"FATOS_CHAVE: {facts_str}")
        return "\n".join(lines)


class UserMemoryWriter:
    """Lê últimas N mensagens + memory atual → LLM resume → grava."""

    def __init__(self, *, llm=None):
        self._llm = llm  # injetable pra testes

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        from src.services.llm import get_llm
        return get_llm()

    # ─── Carrega snapshot atual ──────────────────────────────────

    def load(self, user_id: str) -> Optional[UserMemorySnapshot]:
        try:
            row = get_postgres().fetch_one(
                """SELECT user_id, tenant_id, summary, key_facts,
                          messages_at_last_summary, total_messages,
                          last_summarized_at
                   FROM aia_health_sofia_user_memory
                   WHERE user_id = %s""",
                (user_id,),
            )
        except Exception as exc:
            logger.warning("user_memory_load_failed", error=str(exc)[:200])
            return None
        return UserMemorySnapshot.from_row(row) if row else None

    # ─── Trigger logic ───────────────────────────────────────────

    def should_summarize(self, user_id: str) -> bool:
        """True se usuário tem N+ mensagens novas desde último sumário."""
        snap = self.load(user_id)
        try:
            row = get_postgres().fetch_one(
                """SELECT COUNT(*) AS c FROM aia_health_sofia_messages m
                   JOIN aia_health_sofia_sessions s ON s.id = m.session_id
                   WHERE s.user_id = %s
                     AND role IN ('user','assistant')""",
                (user_id,),
            )
        except Exception as exc:
            logger.warning("user_memory_count_failed", error=str(exc)[:200])
            return False
        if not row:
            return False
        total = int(row.get("c") or 0)
        if not snap:
            return total >= SUMMARIZE_EVERY_N
        return (total - snap.messages_at_last_summary) >= SUMMARIZE_EVERY_N

    # ─── Recent messages ─────────────────────────────────────────

    def _fetch_recent_messages(self, user_id: str, limit: int) -> list[dict]:
        try:
            rows = get_postgres().fetch_all(
                """SELECT m.role, m.content, m.created_at
                   FROM aia_health_sofia_messages m
                   JOIN aia_health_sofia_sessions s ON s.id = m.session_id
                   WHERE s.user_id = %s
                     AND m.role IN ('user','assistant')
                     AND m.content IS NOT NULL
                   ORDER BY m.created_at DESC
                   LIMIT %s""",
                (user_id, limit),
            )
        except Exception as exc:
            logger.warning(
                "user_memory_recent_msgs_failed", error=str(exc)[:200],
            )
            return []
        return list(reversed(rows))  # cronológico

    # ─── Summarize ───────────────────────────────────────────────

    def summarize(
        self,
        user_id: str,
        tenant_id: str,
        *,
        force: bool = False,
    ) -> Optional[UserMemorySnapshot]:
        """Pipeline: load atual → fetch recent → LLM gera novo
        summary + key_facts → upsert.

        Returns: snapshot novo (ou None se falhou / nada pra summarizar).
        """
        if not force and not self.should_summarize(user_id):
            return None

        recent = self._fetch_recent_messages(user_id, RECENT_MESSAGES_WINDOW)
        if not recent:
            return None

        existing = self.load(user_id)
        existing_summary = (existing.summary if existing else None) or ""
        existing_facts = (existing.key_facts if existing else {}) or {}

        # Monta texto pro LLM: summary anterior + transcript recente
        transcript_lines = []
        for m in recent:
            role_label = "USUÁRIO" if m["role"] == "user" else "SOFIA"
            content = (m.get("content") or "")[:300]
            transcript_lines.append(f"[{role_label}] {content}")
        transcript = "\n".join(transcript_lines)

        system = (
            "Você atualiza a memória persistente da Sofia sobre um usuário "
            "específico. Seu output é um JSON com:\n"
            '  • "summary": string em PT-BR de até 800 caracteres '
            "narrando o contexto atual do usuário (papel, casos em aberto, "
            "preferências, padrões observados). Tom factual, sem floreio.\n"
            '  • "key_facts": objeto com chaves curtas e valores curtos. '
            "Exemplos de chaves: role_context, preferences, ongoing_topics, "
            "key_patients, concerns, communication_style.\n\n"
            "Regras:\n"
            "  • PRESERVE fatos do summary anterior se ainda relevantes.\n"
            "  • REMOVA tópicos resolvidos/concluídos.\n"
            "  • NUNCA invente dado que não esteja no transcript.\n"
            "  • Mantenha LGPD: não exponha CPF/dados sensíveis no summary."
        )
        user = (
            f"SUMMARY ANTERIOR ({len(existing_summary)} chars):\n"
            f"{existing_summary or '(vazio - 1ª vez)'}\n\n"
            f"FATOS ANTERIORES:\n"
            f"{json.dumps(existing_facts, ensure_ascii=False)[:1500]}\n\n"
            f"TRANSCRIPT RECENTE ({len(recent)} msgs):\n{transcript}"
        )

        try:
            from src.services.llm import MODEL_FAST
            llm = self._get_llm()
            raw = llm.complete_json(
                system=system,
                user=user,
                model=MODEL_FAST,
                max_tokens=1024,
                temperature=0.3,
            )
        except Exception as exc:
            logger.warning(
                "user_memory_llm_failed",
                user_id=user_id, error=str(exc)[:200],
            )
            return None

        if not isinstance(raw, dict):
            return None

        new_summary = (raw.get("summary") or "").strip()[:MAX_SUMMARY_CHARS]
        new_facts = raw.get("key_facts") or {}
        if not isinstance(new_facts, dict):
            new_facts = {}
        # Trunca string-valued facts pra não inflar
        for k, v in list(new_facts.items()):
            if isinstance(v, str) and len(v) > 200:
                new_facts[k] = v[:200]

        # Conta total atual
        total_count = self._fetch_total_messages(user_id)

        ok = self._upsert(
            user_id=user_id,
            tenant_id=tenant_id,
            summary=new_summary,
            key_facts=new_facts,
            total_messages=total_count,
        )
        if not ok:
            return None
        return self.load(user_id)

    def _fetch_total_messages(self, user_id: str) -> int:
        try:
            row = get_postgres().fetch_one(
                """SELECT COUNT(*) AS c FROM aia_health_sofia_messages m
                   JOIN aia_health_sofia_sessions s ON s.id = m.session_id
                   WHERE s.user_id = %s
                     AND role IN ('user','assistant')""",
                (user_id,),
            )
            return int(row.get("c") or 0) if row else 0
        except Exception:
            return 0

    def _upsert(
        self,
        *,
        user_id: str,
        tenant_id: str,
        summary: str,
        key_facts: dict,
        total_messages: int,
    ) -> bool:
        try:
            get_postgres().execute(
                """INSERT INTO aia_health_sofia_user_memory (
                    user_id, tenant_id, summary, key_facts,
                    messages_at_last_summary, total_messages,
                    summary_model, last_summarized_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    summary = EXCLUDED.summary,
                    key_facts = EXCLUDED.key_facts,
                    messages_at_last_summary = EXCLUDED.messages_at_last_summary,
                    total_messages = EXCLUDED.total_messages,
                    summary_model = EXCLUDED.summary_model,
                    last_summarized_at = NOW()""",
                (
                    user_id, tenant_id, summary,
                    json.dumps(key_facts),
                    total_messages, total_messages,
                    "claude-haiku-4-5",
                ),
            )
            return True
        except Exception as exc:
            logger.warning(
                "user_memory_upsert_failed",
                user_id=user_id, error=str(exc)[:200],
            )
            return False

    # ─── Helper pra orchestrator ────────────────────────────────

    def maybe_summarize_async(
        self,
        user_id: Optional[str],
        tenant_id: str,
    ) -> None:
        """Fire-and-forget pra orchestrator chamar ao final do turno.

        Phase C v2.7: chamada síncrona com try/catch ampla. Phase D
        futura: enfileira em event_bus pra worker dedicado processar.
        """
        if not user_id:
            return
        try:
            self.summarize(user_id, tenant_id)
        except Exception as exc:
            logger.warning(
                "user_memory_async_failed",
                user_id=user_id, error=str(exc)[:200],
            )


# Singleton
_instance: Optional[UserMemoryWriter] = None


def get_user_memory_writer() -> UserMemoryWriter:
    global _instance
    if _instance is None:
        _instance = UserMemoryWriter()
    return _instance
