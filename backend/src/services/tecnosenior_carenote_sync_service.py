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

        # closed_reason agora vai como campo nativo (V2 — confirmado com
        # Matheus 2026-05-07). Antes era embutido em content_resume.
        closed_reason = ev.get("closed_reason") if target_status == "CLOSED" else None

        result = self.client.create_care_note_streaming(
            caretaker_id=caretaker_int,
            patient_id=patient_int,
            content=content,
            content_resume=content_resume,
            occurred_at=occurred_iso,
            status=target_status,
            closed_reason=closed_reason,
        )

        if not result or "id" not in result:
            self._mark_error(care_event_id, "remote_create_failed")
            return {
                "status": "error",
                "reason": "remote_create_failed",
                "patient_int": patient_int, "caretaker_int": caretaker_int,
            }

        # Sucesso — grava em sync table (incluindo closed_reason enviado
        # pra audit, e audio_url se já veio inline na criação)
        carenote_id = int(result["id"])
        audio_url_from_response = result.get("audio_url")
        self.db.execute(
            """
            INSERT INTO aia_health_tecnosenior_sync
                (care_event_id, tecnosenior_carenote_id, tecnosenior_status,
                 last_synced_at, last_response_payload,
                 closed_reason_sent, tecnosenior_audio_url,
                 tecnosenior_audio_uploaded_at)
            VALUES (%s, %s, %s, NOW(), %s, %s, %s,
                    CASE WHEN %s IS NOT NULL THEN NOW() ELSE NULL END)
            ON CONFLICT (care_event_id) DO UPDATE SET
                tecnosenior_carenote_id = EXCLUDED.tecnosenior_carenote_id,
                tecnosenior_status = EXCLUDED.tecnosenior_status,
                last_synced_at = NOW(),
                sync_error = NULL,
                last_response_payload = EXCLUDED.last_response_payload,
                closed_reason_sent = COALESCE(EXCLUDED.closed_reason_sent,
                    aia_health_tecnosenior_sync.closed_reason_sent),
                tecnosenior_audio_url = COALESCE(EXCLUDED.tecnosenior_audio_url,
                    aia_health_tecnosenior_sync.tecnosenior_audio_url),
                tecnosenior_audio_uploaded_at = COALESCE(
                    EXCLUDED.tecnosenior_audio_uploaded_at,
                    aia_health_tecnosenior_sync.tecnosenior_audio_uploaded_at)
            """,
            (
                care_event_id, carenote_id, target_status,
                self.db.json_adapt(result),
                closed_reason,
                audio_url_from_response,
                audio_url_from_response,  # pra trigger condicional do NOW()
            ),
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
            "audio_url": audio_url_from_response,
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

    def add_addendum_to_existing(
        self,
        care_event_id: str,
        content: str,
        content_resume: str,
        occurred_at: str | None = None,
        closes_note: bool = False,
        closed_reason: str | None = None,
    ) -> dict[str, Any]:
        """Adiciona um addendum a uma CareNote já criada (cenário 2 —
        streaming).

        Usado quando a Sofia recebe novo report dentro de um care_event
        ainda ativo. Se closes_note=True, manda status=CLOSED no addendum
        (fecha a CareNote pai).

        V2 (confirmado com Matheus 2026-05-07): closed_reason pode ir
        no body do addendum quando closes_note=True. Servidor usa essa
        razão pra fechar a CareNote pai.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        sync = self.db.fetch_one(
            "SELECT tecnosenior_carenote_id, tecnosenior_status "
            "FROM aia_health_tecnosenior_sync WHERE care_event_id = %s",
            (care_event_id,),
        )
        if not sync or not sync.get("tecnosenior_carenote_id"):
            return {
                "status": "error",
                "reason": "carenote_not_synced_yet",
                "hint": "Chame sync_care_event primeiro com status=OPEN",
            }
        if sync.get("tecnosenior_status") == "CLOSED" and not closes_note:
            return {
                "status": "error",
                "reason": "carenote_already_closed",
            }

        carenote_id = int(sync["tecnosenior_carenote_id"])

        # Se closes_note e não veio closed_reason explícito, tenta puxar
        # do care_event (campo nativo)
        if closes_note and not closed_reason:
            ev_row = self.db.fetch_one(
                "SELECT closed_reason FROM aia_health_care_events WHERE id = %s",
                (care_event_id,),
            )
            if ev_row and ev_row.get("closed_reason"):
                closed_reason = ev_row["closed_reason"]

        result = self.client.add_addendum(
            care_note_id=carenote_id,
            content=content,
            content_resume=content_resume,
            occurred_at=occurred_at,
            status="CLOSED" if closes_note else None,
            closed_reason=closed_reason,
        )
        if not result or "id" not in result:
            return {
                "status": "error", "reason": "remote_addendum_failed",
                "carenote_id": carenote_id,
            }

        addendum_id = int(result["id"])
        # Persiste na tabela auxiliar pra audit
        try:
            self.db.execute(
                """
                INSERT INTO aia_health_tecnosenior_addendums
                    (care_event_id, tecnosenior_carenote_id,
                     tecnosenior_addendum_id, content, content_resume,
                     occurred_at, closes_note, last_synced_at,
                     last_response_payload)
                VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()),
                        %s, NOW(), %s)
                """,
                (
                    care_event_id, carenote_id, addendum_id,
                    content, content_resume,
                    occurred_at, closes_note,
                    self.db.json_adapt(result),
                ),
            )
        except Exception as exc:
            logger.warning("addendum_persist_failed: %s", exc)

        # Se fechou a CareNote, atualiza status local + closed_reason
        # enviado (audit do que efetivamente foi pra Tecnosenior)
        if closes_note:
            self.db.execute(
                """UPDATE aia_health_tecnosenior_sync
                   SET tecnosenior_status = 'CLOSED',
                       closed_at_remote = NOW(),
                       closed_reason_sent = COALESCE(%s, closed_reason_sent)
                   WHERE care_event_id = %s""",
                (closed_reason, care_event_id),
            )

        return {
            "status": "ok",
            "tecnosenior_carenote_id": carenote_id,
            "tecnosenior_addendum_id": addendum_id,
            "closes_note": closes_note,
        }

    def open_carenote_for_streaming(
        self, care_event_id: str,
    ) -> dict[str, Any]:
        """Cria CareNote com status=OPEN explícito (forçado), permitindo
        addendums depois. Diferente do sync_care_event que decide
        OPEN/CLOSED baseado em care_events.status.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        existing = self.db.fetch_one(
            "SELECT tecnosenior_carenote_id, tecnosenior_status "
            "FROM aia_health_tecnosenior_sync WHERE care_event_id = %s",
            (care_event_id,),
        )
        if existing and existing.get("tecnosenior_carenote_id"):
            return {
                "status": "already_synced",
                "tecnosenior_carenote_id": existing["tecnosenior_carenote_id"],
                "tecnosenior_status": existing.get("tecnosenior_status"),
            }

        ev = self.db.fetch_one(
            """SELECT id::text AS id, patient_id::text AS patient_id,
                      caregiver_id::text AS caregiver_id, caregiver_phone,
                      summary, reasoning, opened_at, current_classification,
                      event_type, event_tags, closed_reason
               FROM aia_health_care_events WHERE id = %s""",
            (care_event_id,),
        )
        if not ev:
            return {"status": "error", "reason": "event_not_found"}

        from datetime import datetime, timezone as tz
        patient_int = self.resolve_patient_id(ev["patient_id"])
        if not patient_int:
            return {"status": "error", "reason": "patient_not_resolved"}
        caretaker_int = self.resolve_caretaker_id(
            ev.get("caregiver_id"), ev.get("caregiver_phone"),
        )
        if not caretaker_int:
            return {"status": "error", "reason": "caretaker_not_resolved"}

        content = ev.get("reasoning") or ev.get("summary") or "(sem detalhes)"
        content_resume = self._format_resume(ev)
        occurred = ev.get("opened_at")
        occurred_iso = (
            occurred.astimezone(tz.utc).isoformat()
            if isinstance(occurred, datetime) else None
        )
        result = self.client.create_care_note_streaming(
            caretaker_id=caretaker_int, patient_id=patient_int,
            content=content, content_resume=content_resume,
            occurred_at=occurred_iso, status="OPEN",
        )
        if not result or "id" not in result:
            return {"status": "error", "reason": "remote_create_failed"}

        carenote_id = int(result["id"])
        self.db.execute(
            """INSERT INTO aia_health_tecnosenior_sync
                  (care_event_id, tecnosenior_carenote_id, tecnosenior_status,
                   last_synced_at, last_response_payload)
               VALUES (%s, %s, 'OPEN', NOW(), %s)
               ON CONFLICT (care_event_id) DO UPDATE SET
                  tecnosenior_carenote_id = EXCLUDED.tecnosenior_carenote_id,
                  tecnosenior_status = 'OPEN', last_synced_at = NOW(),
                  sync_error = NULL""",
            (care_event_id, carenote_id, self.db.json_adapt(result)),
        )
        logger.info(
            "tecnosenior_carenote_opened care_event=%s carenote_id=%s",
            care_event_id, carenote_id,
        )
        return {
            "status": "ok", "tecnosenior_carenote_id": carenote_id,
            "tecnosenior_status": "OPEN",
            "patient_int": patient_int, "caretaker_int": caretaker_int,
        }

    def get_sync_state(self, care_event_id: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT tecnosenior_carenote_id, tecnosenior_status,
                   last_synced_at, last_sync_attempt_at,
                   sync_error, retry_count,
                   tecnosenior_audio_url, tecnosenior_audio_uploaded_at,
                   closed_reason_sent
            FROM aia_health_tecnosenior_sync WHERE care_event_id = %s
            """,
            (care_event_id,),
        )
        if not row:
            return None
        d = dict(row)
        for k in ("last_synced_at", "last_sync_attempt_at",
                  "tecnosenior_audio_uploaded_at"):
            if d.get(k):
                d[k] = str(d[k])
        return d

    # ══════════════════════════════════════════════════════════════════
    # V2: Upload de mídia pós-criação
    # ══════════════════════════════════════════════════════════════════

    def upload_audio_for_carenote(
        self,
        care_event_id: str,
        audio_bytes: bytes,
        audio_filename: str = "audio.ogg",
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        """Upload de áudio pra CareNote (write-once). Idempotente em
        duas dimensões:
            1. Local: se já temos tecnosenior_audio_url no banco, skip.
            2. Remoto: se servidor retornar 409, marca como já uploaded.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        sync = self.db.fetch_one(
            """SELECT tecnosenior_carenote_id, tecnosenior_audio_url
               FROM aia_health_tecnosenior_sync WHERE care_event_id = %s""",
            (care_event_id,),
        )
        if not sync or not sync.get("tecnosenior_carenote_id"):
            return {"status": "error", "reason": "carenote_not_synced_yet"}
        if sync.get("tecnosenior_audio_url"):
            return {
                "status": "already_uploaded",
                "audio_url": sync["tecnosenior_audio_url"],
            }

        carenote_id = int(sync["tecnosenior_carenote_id"])
        result = self.client.upload_carenote_audio(
            care_note_id=carenote_id,
            audio_bytes=audio_bytes,
            audio_filename=audio_filename,
            content_type=content_type,
        )
        if not result:
            self.db.execute(
                """UPDATE aia_health_tecnosenior_sync
                   SET tecnosenior_audio_upload_error = %s
                   WHERE care_event_id = %s""",
                ("upload_failed", care_event_id),
            )
            return {"status": "error", "reason": "upload_failed"}

        if result.get("_already_uploaded"):
            # 409 — já tinha. Tenta puxar URL via GET na CareNote pra
            # cachear localmente (evita retry).
            self.db.execute(
                """UPDATE aia_health_tecnosenior_sync
                   SET tecnosenior_audio_uploaded_at = NOW(),
                       tecnosenior_audio_upload_error = NULL
                   WHERE care_event_id = %s""",
                (care_event_id,),
            )
            return {"status": "already_uploaded_remote"}

        audio_url = result.get("audio_url")
        self.db.execute(
            """UPDATE aia_health_tecnosenior_sync
               SET tecnosenior_audio_url = %s,
                   tecnosenior_audio_uploaded_at = NOW(),
                   tecnosenior_audio_upload_error = NULL
               WHERE care_event_id = %s""",
            (audio_url, care_event_id),
        )
        logger.info(
            "tecnosenior_carenote_audio_uploaded "
            "care_event=%s carenote_id=%s",
            care_event_id, carenote_id,
        )
        return {"status": "ok", "audio_url": audio_url}

    def upload_audio_for_addendum(
        self,
        care_event_id: str,
        addendum_id: int,
        audio_bytes: bytes,
        audio_filename: str = "audio.ogg",
        content_type: str = "audio/ogg",
    ) -> dict[str, Any]:
        """Upload de áudio pra addendum (write-once)."""
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        # Pega carenote_id via addendums table + valida cache
        addendum_row = self.db.fetch_one(
            """SELECT tecnosenior_carenote_id, tecnosenior_audio_url
               FROM aia_health_tecnosenior_addendums
               WHERE care_event_id = %s AND tecnosenior_addendum_id = %s""",
            (care_event_id, addendum_id),
        )
        if not addendum_row:
            return {"status": "error", "reason": "addendum_not_found"}
        if addendum_row.get("tecnosenior_audio_url"):
            return {
                "status": "already_uploaded",
                "audio_url": addendum_row["tecnosenior_audio_url"],
            }

        carenote_id = int(addendum_row["tecnosenior_carenote_id"])
        result = self.client.upload_addendum_audio(
            care_note_id=carenote_id,
            addendum_id=addendum_id,
            audio_bytes=audio_bytes,
            audio_filename=audio_filename,
            content_type=content_type,
        )
        if not result:
            self.db.execute(
                """UPDATE aia_health_tecnosenior_addendums
                   SET tecnosenior_audio_upload_error = %s
                   WHERE care_event_id = %s AND tecnosenior_addendum_id = %s""",
                ("upload_failed", care_event_id, addendum_id),
            )
            return {"status": "error", "reason": "upload_failed"}

        if result.get("_already_uploaded"):
            self.db.execute(
                """UPDATE aia_health_tecnosenior_addendums
                   SET tecnosenior_audio_uploaded_at = NOW(),
                       tecnosenior_audio_upload_error = NULL
                   WHERE care_event_id = %s AND tecnosenior_addendum_id = %s""",
                (care_event_id, addendum_id),
            )
            return {"status": "already_uploaded_remote"}

        audio_url = result.get("audio") or result.get("audio_url")
        self.db.execute(
            """UPDATE aia_health_tecnosenior_addendums
               SET tecnosenior_audio_url = %s,
                   tecnosenior_audio_uploaded_at = NOW(),
                   tecnosenior_audio_upload_error = NULL
               WHERE care_event_id = %s AND tecnosenior_addendum_id = %s""",
            (audio_url, care_event_id, addendum_id),
        )
        return {"status": "ok", "audio_url": audio_url}

    def upload_photo_for_carenote(
        self,
        care_event_id: str,
        image_bytes: bytes,
        image_filename: str = "photo.jpg",
        content_type: str = "image/jpeg",
        addendum_id: int | None = None,
        local_image_path: str | None = None,
    ) -> dict[str, Any]:
        """Upload de foto. Diferente de áudio:
            • Sem limite (pode mandar várias)
            • Sem 409 (sem write-once)
            • addendum_id opcional pra associar a um addendum específico
              (servidor valida que pertence à CareNote)

        Cada foto enviada vira uma row em aia_health_tecnosenior_photos.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        sync = self.db.fetch_one(
            """SELECT tecnosenior_carenote_id
               FROM aia_health_tecnosenior_sync WHERE care_event_id = %s""",
            (care_event_id,),
        )
        if not sync or not sync.get("tecnosenior_carenote_id"):
            return {"status": "error", "reason": "carenote_not_synced_yet"}

        carenote_id = int(sync["tecnosenior_carenote_id"])

        # Validação: se addendum_id informado, confirma que pertence a
        # essa carenote no nosso banco (defensive — server também valida)
        if addendum_id is not None:
            addendum_row = self.db.fetch_one(
                """SELECT 1 FROM aia_health_tecnosenior_addendums
                   WHERE care_event_id = %s
                     AND tecnosenior_addendum_id = %s
                     AND tecnosenior_carenote_id = %s""",
                (care_event_id, addendum_id, carenote_id),
            )
            if not addendum_row:
                return {
                    "status": "error",
                    "reason": "addendum_not_in_carenote",
                }

        result = self.client.upload_carenote_photo(
            care_note_id=carenote_id,
            image_bytes=image_bytes,
            image_filename=image_filename,
            content_type=content_type,
            addendum_id=addendum_id,
        )
        if not result or "id" not in result:
            return {"status": "error", "reason": "upload_failed"}

        photo_id = int(result["id"])
        remote_url = result.get("image_url")

        try:
            self.db.execute(
                """INSERT INTO aia_health_tecnosenior_photos (
                    care_event_id, tecnosenior_carenote_id,
                    tecnosenior_addendum_id, tecnosenior_photo_id,
                    local_image_path, remote_image_url,
                    content_type, size_bytes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tecnosenior_photo_id) DO NOTHING""",
                (
                    care_event_id, carenote_id, addendum_id, photo_id,
                    local_image_path, remote_url,
                    content_type, len(image_bytes),
                ),
            )
        except Exception as exc:
            logger.warning("photo_persist_failed: %s", exc)

        logger.info(
            "tecnosenior_photo_uploaded "
            "care_event=%s carenote_id=%s photo_id=%s addendum_id=%s",
            care_event_id, carenote_id, photo_id, addendum_id,
        )
        return {
            "status": "ok",
            "tecnosenior_photo_id": photo_id,
            "remote_image_url": remote_url,
        }


_instance: TecnoseniorCareNoteSyncService | None = None


def get_tecnosenior_sync() -> TecnoseniorCareNoteSyncService:
    global _instance
    if _instance is None:
        _instance = TecnoseniorCareNoteSyncService()
    return _instance
