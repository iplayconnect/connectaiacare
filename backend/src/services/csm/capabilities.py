"""Platform Capabilities — whitelist anti-invenção.

Sofia comercial inventou "monitoramento batimento cardíaco" no log
Douglas (2026-05-02 22:49). Solução: whitelist de capabilities REAIS
da plataforma, injetada no system prompt do commercial agent.

Tabela: aia_health_platform_capabilities (migration 062).
Seeds iniciais: whatsapp_atendimento_24h, voice_call_sofia,
classificacao_relatos_clinicos, alertas_familia,
validacao_medicacao_beers_rename, integracao_tecnosenior.

API:
    capabilities = get_capabilities_service()
    public_list = capabilities.list_for_persona("anonymous")
    block = capabilities.format_for_prompt(persona="anonymous")
    # → "REGRA: você só pode falar destas features:
    #    - atendimento humano 24h pelo WhatsApp
    #    - ligação telefônica com a Sofia (IA conversacional)
    #    ..."

Cache de 5 min em memória pra evitar query a cada turno.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Capability:
    """1 row de aia_health_platform_capabilities."""

    code: str
    label_user: str
    description_full: str
    category: str
    public_facing: bool
    in_production: bool
    requires_consent: bool
    target_personas: list[str]
    notes: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Capability":
        return cls(
            code=row["code"],
            label_user=row["label_user"],
            description_full=row["description_full"],
            category=row["category"],
            public_facing=bool(row.get("public_facing", True)),
            in_production=bool(row.get("in_production", True)),
            requires_consent=bool(row.get("requires_consent", False)),
            target_personas=list(row.get("target_personas") or []),
            notes=row.get("notes"),
        )


_CACHE_TTL_S = 300  # 5 min


class CapabilitiesService:
    """Whitelist de capabilities reais. Cached, multi-tenant safe.

    Phase C v2.5: globals (não tem tenant_id na tabela ainda).
    Phase D futura: per-tenant overrides.
    """

    def __init__(self):
        self._cache: list[Capability] = []
        self._cache_ts: float = 0.0

    # ─── Loader ──────────────────────────────────────────────────

    def _load(self) -> list[Capability]:
        """Lê todas as capabilities do banco. Cache TTL 5 min."""
        now = time.time()
        if self._cache and (now - self._cache_ts) < _CACHE_TTL_S:
            return self._cache
        try:
            rows = get_postgres().fetch_all(
                """SELECT code, label_user, description_full, category,
                          public_facing, in_production, requires_consent,
                          target_personas, notes
                   FROM aia_health_platform_capabilities
                   ORDER BY category, code""",
                (),
            )
        except Exception as exc:
            logger.warning(
                "capabilities_load_failed",
                error=str(exc)[:200],
            )
            # Fallback: cache vazio. Prompt diz "sem dados disponíveis"
            self._cache = []
            self._cache_ts = now
            return []
        self._cache = [Capability.from_row(r) for r in rows]
        self._cache_ts = now
        return self._cache

    def invalidate(self) -> None:
        """Força reload no próximo .list_*()."""
        self._cache = []
        self._cache_ts = 0.0

    # ─── Public API ──────────────────────────────────────────────

    def list_all(self, *, public_only: bool = True, in_production_only: bool = True) -> list[Capability]:
        caps = self._load()
        if public_only:
            caps = [c for c in caps if c.public_facing]
        if in_production_only:
            caps = [c for c in caps if c.in_production]
        return caps

    def list_for_persona(
        self,
        persona: str,
        *,
        public_only: bool = True,
        in_production_only: bool = True,
    ) -> list[Capability]:
        """Capabilities relevantes pra persona dada (anonymous, familia,
        cuidador_pro, paciente_b2c, medico, enfermeiro, admin_tenant,
        gestor_ilpi)."""
        caps = self.list_all(
            public_only=public_only,
            in_production_only=in_production_only,
        )
        # Match: persona aparece em target_personas OR target_personas vazio
        return [
            c for c in caps
            if not c.target_personas or persona in c.target_personas
        ]

    def list_by_category(self, category: str) -> list[Capability]:
        return [c for c in self.list_all() if c.category == category]

    # ─── Prompt formatter ────────────────────────────────────────

    def format_for_prompt(
        self,
        *,
        persona: str = "anonymous",
        max_items: int = 12,
    ) -> str:
        """Bloco pronto pra system prompt do commercial agent.

        Retorna texto com instrução estrita "só fale dessas features"
        + lista numerada de capabilities pra persona.
        """
        caps = self.list_for_persona(persona)
        if not caps:
            return (
                "REGRA: ainda não tenho a lista de features publicada — "
                "se o lead perguntar de feature específica, diga que "
                "vai checar com o time e passar o detalhe."
            )
        lines = [
            "═══════════════════════════════════════════════════════════",
            "FEATURES DA PLATAFORMA — REGRA DE OURO ANTI-INVENÇÃO:",
            "Você só pode mencionar features desta lista. Se o lead",
            "perguntar de algo que NÃO está aqui, responda:",
            '  "Essa feature específica eu vou checar com o time e te',
            '   confirmo — não quero te passar info errada."',
            "NUNCA invente capability que não esteja nesta lista.",
            "───────────────────────────────────────────────────────────",
        ]
        for i, c in enumerate(caps[:max_items], 1):
            consent_flag = " (requer consent LGPD)" if c.requires_consent else ""
            lines.append(f"{i}. {c.label_user}{consent_flag}")
            # Descrição interna (não pra repetir verbatim — pra Sofia
            # entender o que pode dizer)
            desc = c.description_full[:240]
            lines.append(f"   ↳ {desc}")
        lines.append(
            "═══════════════════════════════════════════════════════════"
        )
        return "\n".join(lines)


# Singleton
_instance: Optional[CapabilitiesService] = None


def get_capabilities_service() -> CapabilitiesService:
    global _instance
    if _instance is None:
        _instance = CapabilitiesService()
    return _instance
