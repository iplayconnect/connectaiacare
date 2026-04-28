"""Shift Resolver Service — resolve quem está de plantão agora.

Responsável por reduzir o pool de busca da biometria de voz de 1:N
contra todos os cuidadores do tenant para 1:N pequeno (apenas os
que estão de plantão no horário atual). Insight do panel LLM
(Grok, fase 2) — ver docs/consolidacao_panel_llm.md §4.3.3.

Usado por:
  - voice_biometrics_service.identify_caregiver_in_shift()
  - pipeline.py quando recebe áudio do WhatsApp
  - persona_resolver para escolher o pool de comparação
"""
from __future__ import annotations

import logging
from typing import Any

from src.services.postgres import get_postgres

logger = logging.getLogger("connectaiacare.shift_resolver")


class ShiftResolverService:
    """Resolve plantão atual e cuidadores ativos."""

    def __init__(self, postgres_service=None):
        self.postgres = postgres_service or get_postgres()

    # ══════════════════════════════════════════════════════════════════
    # Plantão atual a partir da hora
    # ══════════════════════════════════════════════════════════════════

    def get_current_shift_name(self, tenant_id: str) -> str | None:
        """Retorna o nome do plantão ativo agora (manhã/tarde/noite ou
        custom), baseado em CURRENT_TIME contra os schedules cadastrados.
        Retorna None se nenhum plantão cobre o horário (gap entre turnos).
        """
        row = self.postgres.fetch_one(
            "SELECT aia_health_current_shift_name(%s) AS shift_name",
            (tenant_id,),
        )
        return row["shift_name"] if row else None

    # ══════════════════════════════════════════════════════════════════
    # Pool de cuidadores ativos no plantão atual
    # ══════════════════════════════════════════════════════════════════

    def list_active_caregivers(
        self,
        tenant_id: str,
        shift_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista cuidadores ativos AGORA — combina schedule fixo +
        override temporário em curso. Pode filtrar por shift_name
        específico ou retornar todos os ativos.

        Cada item:
          {caregiver_id, full_name, phone, phone_type,
           shift_name, source: 'scheduled'|'override'}
        """
        if shift_name:
            rows = self.postgres.fetch_all(
                """
                SELECT caregiver_id::text AS caregiver_id, full_name, phone,
                       phone_type, shift_name, source
                FROM aia_health_active_shift_caregivers
                WHERE tenant_id = %s AND shift_name = %s
                """,
                (tenant_id, shift_name),
            )
        else:
            rows = self.postgres.fetch_all(
                """
                SELECT caregiver_id::text AS caregiver_id, full_name, phone,
                       phone_type, shift_name, source
                FROM aia_health_active_shift_caregivers
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
        return [dict(r) for r in rows or []]

    def list_active_caregiver_ids(
        self,
        tenant_id: str,
        shift_name: str | None = None,
    ) -> list[str]:
        """Versão enxuta — só os IDs. Usada pra filtrar pool de
        biometria 1:N."""
        items = self.list_active_caregivers(tenant_id, shift_name)
        return [it["caregiver_id"] for it in items]

    # ══════════════════════════════════════════════════════════════════
    # Resolução por número de WhatsApp
    # ══════════════════════════════════════════════════════════════════

    def get_phone_type(self, tenant_id: str, phone: str) -> str:
        """Retorna 'personal' | 'shared' | 'unknown' para um número.
        Default 'unknown' se número não está cadastrado.
        """
        row = self.postgres.fetch_one(
            """SELECT phone_type FROM aia_health_caregivers
               WHERE tenant_id = %s AND phone = %s
               LIMIT 1""",
            (tenant_id, phone),
        )
        if not row:
            return "unknown"
        return row.get("phone_type") or "unknown"

    def is_shared_phone(self, tenant_id: str, phone: str) -> bool:
        """Atalho — número compartilhado desativa biometria
        e força pergunta explícita de identidade."""
        return self.get_phone_type(tenant_id, phone) == "shared"

    # ══════════════════════════════════════════════════════════════════
    # Override temporário (cobertura de plantão)
    # ══════════════════════════════════════════════════════════════════

    def register_override(
        self,
        tenant_id: str,
        caregiver_id: str,
        shift_name: str,
        valid_from: str,
        valid_until: str,
        reason: str = "cobertura_temporaria",
        created_by: str = "system",
    ) -> dict[str, Any]:
        """Registra override temporário — usado quando Sofia detecta
        no fallback que cuidador da manhã está cobrindo a tarde, por
        exemplo.
        """
        row = self.postgres.fetch_one(
            """
            INSERT INTO aia_health_shift_overrides (
                tenant_id, caregiver_id, shift_name,
                valid_from, valid_until, reason, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id::text
            """,
            (tenant_id, caregiver_id, shift_name,
             valid_from, valid_until, reason, created_by),
        )
        logger.info(
            "shift_override_registered tenant=%s caregiver=%s "
            "shift=%s reason=%s",
            tenant_id, caregiver_id, shift_name, reason,
        )
        return {"override_id": row["id"] if row else None}

    def list_active_overrides(
        self, tenant_id: str,
    ) -> list[dict[str, Any]]:
        rows = self.postgres.fetch_all(
            """
            SELECT o.id::text AS id, o.caregiver_id::text AS caregiver_id,
                   c.full_name, o.shift_name, o.valid_from,
                   o.valid_until, o.reason, o.created_by
            FROM aia_health_shift_overrides o
            JOIN aia_health_caregivers c ON c.id = o.caregiver_id
            WHERE o.tenant_id = %s
              AND NOW() BETWEEN o.valid_from AND o.valid_until
            ORDER BY o.valid_from DESC
            """,
            (tenant_id,),
        )
        out = []
        for r in rows or []:
            d = dict(r)
            for k in ("valid_from", "valid_until"):
                if d.get(k):
                    d[k] = str(d[k])
            out.append(d)
        return out


_instance: ShiftResolverService | None = None


def get_shift_resolver() -> ShiftResolverService:
    global _instance
    if _instance is None:
        _instance = ShiftResolverService()
    return _instance
