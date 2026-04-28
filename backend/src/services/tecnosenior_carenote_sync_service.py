"""Tecnosenior Care Notes Sync — orquestra envio de care_events
nossos pra CareNotes/Addendums do TotalCare.

Resolve mapping UUID↔INT via lookup por phone (Matheus 2026-04-28)
ou CPF (após Matheus subir endpoint 2026-04-29). Cacheia ID resolvido
em aia_health_patients.tecnosenior_patient_id e
aia_health_caregivers.tecnosenior_caretaker_id.

Idempotency local (Matheus ainda não tem header nativo):
- aia_health_tecnosenior_sync.care_event_id é UNIQUE
- Antes de POST, verifica se já existe linha de sync com
  tecnosenior_carenote_id != NULL → reusa
- Em caso de falha de rede, retry usa o estado salvo
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.services.medmonitor_client import get_medmonitor_client
from src.services.postgres import get_postgres

logger = logging.getLogger("connectaiacare.tecnosenior_sync")


class TecnoseniorCareNoteSyncService:
    """Orquestrador de envio CareNote pro TotalCare."""

    def __init__(self):
        self.db = get_postgres()
        self.client = get_medmonitor_client()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    # ══════════════════════════════════════════════════════════════════
    # Resolução de IDs (UUID → INT)
    # ══════════════════════════════════════════════════════════════════

    def resolve_patient_id(self, patient_uuid: str) -> int | None:
        """Resolve patient_uuid (nosso) → tecnosenior_patient_id (deles).

        Cascata:
        1. Cache local (aia_health_patients.tecnosenior_patient_id)
        2. Lookup remoto por CPF (se temos CPF do paciente)
        3. Lookup remoto por phone (se temos phone do paciente)

        Retorna None se não encontrou — caller decide o que fazer
        (geralmente: marca sync_error e retry depois).
        """
        row = self.db.fetch_one(
            "SELECT tecnosenior_patient_id, cpf FROM aia_health_patients "
            "WHERE id = %s",
            (patient_uuid,),
        )
        if not row:
            return None
        if row.get("tecnosenior_patient_id"):
            return int(row["tecnosenior_patient_id"])

        # Tenta CPF se temos
        if row.get("cpf"):
            patient = self.client.find_patient_by_cpf(row["cpf"])
            if patient and "id" in patient:
                self._cache_patient_id(patient_uuid, int(patient["id"]))
                return int(patient["id"])

        # Fallback: phone do contato responsable (responsible JSONB)
        # ou outro caminho — pra POC usa caregiver_phone que reportou
        # mais recentemente sobre esse paciente.
        recent_phone = self.db.fetch_one(
            "SELECT caregiver_phone FROM aia_health_care_events "
            "WHERE patient_id = %s ORDER BY opened_at DESC LIMIT 1",
            (patient_uuid,),
        )
        if recent_phone and recent_phone.get("caregiver_phone"):
            patient = self.client.find_patient_by_phone(
                recent_phone["caregiver_phone"]
            )
            if patient and "id" in patient:
                self._cache_patient_id(patient_uuid, int(patient["id"]))
                return int(patient["id"])

        return None

    def resolve_caretaker_id(
        self, caregiver_uuid: str | None, phone: str | None,
    ) -> int | None:
        """Resolve cuidador. Aceita UUID nosso ou phone direto.

        Cascata: cache → CPF (se temos no caregiver) → phone.
        """
        cached_id = None
        cpf = None
        phone_local = phone

        if caregiver_uuid:
            row = self.db.fetch_one(
                "SELECT tecnosenior_caretaker_id, cpf, phone FROM aia_health_caregivers "
                "WHERE id = %s",
                (caregiver_uuid,),
            )
            if row:
                cached_id = row.get("tecnosenior_caretaker_id")
                cpf = row.get("cpf")
                phone_local = phone_local or row.get("phone")

        if cached_id:
            return int(cached_id)

        if cpf:
            ct = self.client.find_caretaker_by_cpf(cpf)
            if ct and "id" in ct:
                if caregiver_uuid:
                    self._cache_caretaker_id(caregiver_uuid, int(ct["id"]))
                return int(ct["id"])

        if phone_local:
            ct = self.client.find_caretaker_by_phone(phone_local)
            if ct and "id" in ct:
                if caregiver_uuid:
                    self._cache_caretaker_id(caregiver_uuid, int(ct["id"]))
                return int(ct["id"])

        return None

    def _cache_patient_id(self, patient_uuid: str, tec_id: int) -> None:
        try:
            self.db.execute(
                "UPDATE aia_health_patients "
                "SET tecnosenior_patient_id = %s WHERE id = %s",
                (tec_id, patient_uuid),
            )
        except Exception as exc:
            logger.warning("cache_patient_id_failed error=%s", exc)

    def _cache_caretaker_id(self, caregiver_uuid: str, tec_id: int) -> None:
        try:
            self.db.execute(
                "UPDATE aia_health_caregivers "
                "SET tecnosenior_caretaker_id = %s WHERE id = %s",
                (tec_id, caregiver_uuid),
            )
        except Exception as exc:
            logger.warning("cache_caretaker_id_failed error=%s", exc)

    # ══════════════════════════════════════════════════════════════════
    # Envio
    # ══════════════════════════════════════════════════════════════════

    def sync_care_event(
        self, care_event_id: str, force: bool = False,
    ) -> dict[str, Any]:
        """Sincroniza um care_event nosso → CareNote no TotalCare.

        Estratégia simples (cenário 4 — bulk CLOSED se já resolvido,
        ou cenário 1 one-off pro POC):
        - Se care_event.status in (resolved, expired) → cria CareNote
          com status=CLOSED (cenário 1).
        - Se ainda OPEN → cria CareNote OPEN, addendums seguem por
          chamadas separadas no fluxo normal (sprint próximo).

        Args:
          care_event_id: UUID do nosso aia_health_care_events.id
          force: True ignora idempotency (re-envia mesmo já sincronizado)

        Retorna dict com status, error?, tecnosenior_carenote_id?, etc.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        # Idempotência local: já enviado?
        existing = self.db.fetch_one(
            "SELECT tecnosenior_carenote_id, tecnosenior_status, sync_error "
            "FROM aia_health_tecnosenior_sync WHERE care_event_id = %s",
            (care_event_id,),
        )
        if existing and existing.get("tecnosenior_carenote_id") and not force:
            return {
                "status": "already_synced",
                "tecnosenior_carenote_id": existing["tecnosenior_carenote_id"],
                "tecnosenior_status": existing.get("tecnosenior_status"),
            }

        # Carrega care_event
        ev = self.db.fetch_one(
            """
            SELECT id::text AS id, patient_id::text AS patient_id,
                   caregiver_id::text AS caregiver_id,
                   caregiver_phone, status, summary, reasoning,
                   opened_at, resolved_at, current_classification,
                   event_type, event_tags, closed_reason
            FROM aia_health_care_events
            WHERE id = %s
            """,
            (care_event_id,),
        )
        if not ev:
            return {"status": "error", "reason": "event_not_found"}

        # Resolve IDs do lado deles
        patient_int = self.resolve_patient_id(ev["patient_id"])
        if not patient_int:
            self._mark_error(care_event_id, "patient_not_resolved")
            return {
                "status": "error",
                "reason": "patient_not_found_in_tecnosenior",
                "patient_uuid": ev["patient_id"],
            }

        caretaker_int = self.resolve_caretaker_id(
            ev.get("caregiver_id"), ev.get("caregiver_phone"),
        )
        if not caretaker_int:
            self._mark_error(care_event_id, "caretaker_not_resolved")
            return {
                "status": "error",
                "reason": "caretaker_not_found_in_tecnosenior",
                "phone": ev.get("caregiver_phone"),
            }

        # Monta content + content_resume
        content = ev.get("reasoning") or ev.get("summary") or "(sem detalhes)"
        content_resume = self._format_resume(ev)

        # occurred_at do evento
        occurred = ev.get("opened_at")
        occurred_iso = (
            occurred.astimezone(timezone.utc).isoformat()
            if isinstance(occurred, datetime)
            else None
        )

        # Decide status
        ev_status = ev.get("status") or ""
        target_status = (
            "CLOSED" if ev_status in ("resolved", "expired") else "OPEN"
        )

        result = self.client.create_care_note_streaming(
            caretaker_id=caretaker_int,
            patient_id=patient_int,
            content=content,
            content_resume=content_resume,
            occurred_at=occurred_iso,
            status=target_status,
        )

        if not result or "id" not in result:
            self._mark_error(care_event_id, "remote_create_failed")
            return {
                "status": "error",
                "reason": "remote_create_failed",
                "patient_int": patient_int, "caretaker_int": caretaker_int,
            }

        # Sucesso — grava em sync table
        carenote_id = int(result["id"])
        self.db.execute(
            """
            INSERT INTO aia_health_tecnosenior_sync
                (care_event_id, tecnosenior_carenote_id, tecnosenior_status,
                 last_synced_at, last_response_payload)
            VALUES (%s, %s, %s, NOW(), %s)
            ON CONFLICT (care_event_id) DO UPDATE SET
                tecnosenior_carenote_id = EXCLUDED.tecnosenior_carenote_id,
                tecnosenior_status = EXCLUDED.tecnosenior_status,
                last_synced_at = NOW(),
                sync_error = NULL,
                last_response_payload = EXCLUDED.last_response_payload
            """,
            (care_event_id, carenote_id, target_status,
             self.db.json_adapt(result)),
        )
        logger.info(
            "tecnosenior_sync_ok care_event=%s carenote_id=%s status=%s",
            care_event_id, carenote_id, target_status,
        )
        return {
            "status": "ok",
            "tecnosenior_carenote_id": carenote_id,
            "tecnosenior_status": target_status,
            "patient_int": patient_int,
            "caretaker_int": caretaker_int,
        }

    def _mark_error(self, care_event_id: str, reason: str) -> None:
        try:
            self.db.execute(
                """
                INSERT INTO aia_health_tecnosenior_sync
                    (care_event_id, sync_error, last_sync_attempt_at,
                     retry_count)
                VALUES (%s, %s, NOW(), 1)
                ON CONFLICT (care_event_id) DO UPDATE SET
                    sync_error = EXCLUDED.sync_error,
                    last_sync_attempt_at = NOW(),
                    retry_count = aia_health_tecnosenior_sync.retry_count + 1
                """,
                (care_event_id, reason),
            )
        except Exception as exc:
            logger.warning("mark_error_failed error=%s", exc)

    def _format_resume(self, ev: dict) -> str:
        """Monta content_resume no formato fixo do doc Matheus:
        [CLASSE_PRINCIPAL · SUBCLASSE]

        Resumo: ...
        Severidade: ...
        Tags: ...
        """
        parts = []
        # Tag principal (1ª da lista) como classe
        tags = ev.get("event_tags") or []
        ev_type = ev.get("event_type") or (tags[0] if tags else "RELATO")
        parts.append(f"[{ev_type.upper()}]")
        if ev.get("summary"):
            parts.append(f"\nResumo: {ev['summary']}")
        if ev.get("current_classification"):
            parts.append(f"Severidade: {ev['current_classification']}")
        if tags and len(tags) > 1:
            parts.append(f"Tags: {', '.join(tags)}")
        if ev.get("closed_reason"):
            parts.append(f"Encerramento: {ev['closed_reason']}")
        return "\n".join(parts)

    # ══════════════════════════════════════════════════════════════════
    # Status / Inspeção
    # ══════════════════════════════════════════════════════════════════

    def get_sync_state(self, care_event_id: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT tecnosenior_carenote_id, tecnosenior_status,
                   last_synced_at, last_sync_attempt_at,
                   sync_error, retry_count
            FROM aia_health_tecnosenior_sync WHERE care_event_id = %s
            """,
            (care_event_id,),
        )
        if not row:
            return None
        d = dict(row)
        for k in ("last_synced_at", "last_sync_attempt_at"):
            if d.get(k):
                d[k] = str(d[k])
        return d


_instance: TecnoseniorCareNoteSyncService | None = None


def get_tecnosenior_sync() -> TecnoseniorCareNoteSyncService:
    global _instance
    if _instance is None:
        _instance = TecnoseniorCareNoteSyncService()
    return _instance
