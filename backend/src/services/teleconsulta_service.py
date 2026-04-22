"""Serviço de teleconsulta via LiveKit (ADR-012).

Cria salas LiveKit associadas a um care_event, gera tokens JWT para os
participantes (médico e paciente/familiar) e retorna URLs de entrada.

Arquitetura (MVP demo):
    - Reusa LiveKit da Hostinger (key dedicada `connectaiacare`)
    - Sala nasce com nome `care-event-{human_id}-{uuid8}`
    - Metadata da sala marca origem + patient_id + event_id (auditoria)
    - Token de participante tem TTL de 2h e permissões mínimas
    - Quando consulta termina, estado do care_event vai pra `resolved` com
      closed_reason="teleconsulta_realizada"

Pós-MVP (roadmap):
    - Gravação S3 (egress LiveKit) com retenção conforme ANS 465/2021
    - Transcrição ao vivo via Deepgram streaming
    - Prontuário pós-consulta via LLM (adaptação do analysis_service)
    - Salas recorrentes para follow-up de crônicos
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from livekit import api as lk_api

from config.settings import settings
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Duração máxima do token de participante (cobre consulta + buffer)
PARTICIPANT_TOKEN_TTL_HOURS = 2

# Metadata chave usada pra filtrar webhooks/gravações deste produto
ROOM_METADATA_SOURCE = "connectaiacare"


class TeleconsultaService:
    def __init__(self):
        self.db = get_postgres()
        self.enabled = bool(
            settings.livekit_api_key and settings.livekit_api_secret
        )
        if not self.enabled:
            logger.warning(
                "teleconsulta_disabled",
                reason="LIVEKIT_API_KEY/SECRET ausentes no .env",
            )

    # ---------- criação de sala ----------
    async def create_consultation_room(
        self,
        event_id: str,
        human_id: int | None,
        patient_id: str,
        patient_name: str,
        initiator_role: str = "doctor",
        initiator_name: str | None = None,
    ) -> dict[str, Any]:
        """Cria sala LiveKit pra teleconsulta + gera tokens do médico e paciente.

        Retorna dict:
            - room_name: identificador único
            - room_sid: ID interno LiveKit
            - doctor_token: JWT pro profissional
            - patient_token: JWT pro paciente/familiar
            - doctor_url: URL completa do médico (frontend sala + token)
            - patient_url: URL compacta pra enviar via WhatsApp
            - ws_url: endpoint WebSocket LiveKit (para clients JS)
            - expires_at: ISO timestamp
        """
        if not self.enabled:
            raise RuntimeError("Teleconsulta não configurada — defina LIVEKIT_API_KEY/SECRET")

        short_id = str(uuid.uuid4())[:8]
        room_name = f"care-{(human_id or 0):04d}-{short_id}"

        # Cria a sala via LiveKit API (garante que existe e tem metadata correto)
        lk_client = lk_api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        try:
            room = await lk_client.room.create_room(
                lk_api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,        # 5 min sem participantes → sala destruída
                    max_participants=6,       # médico + paciente + família (2) + gravador + 1 slot
                    metadata=(
                        f'{{"source":"{ROOM_METADATA_SOURCE}",'
                        f'"event_id":"{event_id}",'
                        f'"patient_id":"{patient_id}",'
                        f'"created_at":"{datetime.now(timezone.utc).isoformat()}"}}'
                    ),
                )
            )
        except Exception as exc:
            logger.error("livekit_create_room_failed", error=str(exc), event_id=event_id)
            raise
        finally:
            await lk_client.aclose()

        # Gera tokens para os 2 participantes iniciais
        expires_at = datetime.now(timezone.utc) + timedelta(hours=PARTICIPANT_TOKEN_TTL_HOURS)

        doctor_identity = f"doctor-{initiator_role}-{short_id}"
        doctor_token = self._make_token(
            room_name,
            identity=doctor_identity,
            display_name=initiator_name or "Profissional",
            can_publish=True,
            can_subscribe=True,
        )

        patient_identity = f"patient-{patient_id[:8]}"
        patient_token = self._make_token(
            room_name,
            identity=patient_identity,
            display_name=patient_name,
            can_publish=True,
            can_subscribe=True,
        )

        # URLs completas que frontend usa pra entrar
        # /consulta/[room_name]?token=XXX é a rota do Next que recebe e conecta via livekit-client
        front_base = settings.public_base_url.replace("demo.", "care.")
        doctor_url = f"{front_base}/consulta/{room_name}?role=doctor&token={doctor_token}"
        patient_url = f"{front_base}/consulta/{room_name}?role=patient&token={patient_token}"

        # Registra a consulta no care_event (campo context.teleconsulta)
        self._persist_to_event(event_id, {
            "room_name": room_name,
            "room_sid": getattr(room, "sid", None),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "doctor_identity": doctor_identity,
            "patient_identity": patient_identity,
            "expires_at": expires_at.isoformat(),
        })

        # Cria registro em aia_health_teleconsultations (ADR-023)
        # Permite rastrear state machine completa + SOAP + prescrição + FHIR
        teleconsultation_id = self._create_teleconsultation_record(
            event_id=event_id,
            patient_id=patient_id,
            room_name=room_name,
            room_sid=getattr(room, "sid", None),
            doctor_name=initiator_name,
            doctor_role=initiator_role,
        )

        logger.info(
            "teleconsulta_room_created",
            event_id=event_id,
            room_name=room_name,
            patient_id=patient_id,
            initiator_role=initiator_role,
        )

        return {
            "room_name": room_name,
            "room_sid": getattr(room, "sid", None),
            "teleconsultation_id": teleconsultation_id,
            "doctor_token": doctor_token,
            "patient_token": patient_token,
            "doctor_url": doctor_url,
            "patient_url": patient_url,
            "ws_url": settings.livekit_ws_url,
            "expires_at": expires_at.isoformat(),
        }

    def _make_token(
        self,
        room_name: str,
        identity: str,
        display_name: str,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        """Gera JWT LiveKit para 1 participante com permissões mínimas."""
        token = lk_api.AccessToken(
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        token.with_identity(identity).with_name(display_name).with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
                can_publish_data=True,  # permite chat + presença
            )
        ).with_ttl(timedelta(hours=PARTICIPANT_TOKEN_TTL_HOURS))
        return token.to_jwt()

    def _persist_to_event(self, event_id: str, teleconsulta_data: dict) -> None:
        """Grava metadata da consulta no context JSONB do care_event."""
        # Merge idempotente: context.teleconsulta = {...}
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET context = jsonb_set(
                    COALESCE(context, '{}'::jsonb),
                    '{teleconsulta}',
                    %s::jsonb,
                    true
                ),
                updated_at = NOW()
            WHERE id = %s
            """,
            (self.db.json_adapt(teleconsulta_data), event_id),
        )

    def _create_teleconsultation_record(
        self,
        event_id: str,
        patient_id: str,
        room_name: str,
        room_sid: str | None,
        doctor_name: str | None,
        doctor_role: str,
    ) -> str:
        """Cria registro em aia_health_teleconsultations (ADR-023).

        Busca persona médica demo (Dra. Ana Silva) no DB.
        Estado inicial: `scheduling` (médico acabou de clicar iniciar).
        """
        # Busca médico (por nome se informado, senão o demo default)
        doctor_row = None
        if doctor_name:
            doctor_row = self.db.fetch_one(
                "SELECT id, full_name, crm_number FROM aia_health_doctors "
                "WHERE tenant_id = %s AND full_name = %s AND active = TRUE LIMIT 1",
                (settings.tenant_id, doctor_name),
            )
        if not doctor_row:
            doctor_row = self.db.fetch_one(
                "SELECT id, full_name, crm_number FROM aia_health_doctors "
                "WHERE tenant_id = %s AND is_demo = TRUE AND active = TRUE LIMIT 1",
                (settings.tenant_id,),
            )

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_teleconsultations (
                tenant_id, care_event_id, patient_id, doctor_id,
                doctor_name_snapshot, doctor_crm_snapshot,
                state, livekit_room_name, livekit_room_sid, started_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'scheduling', %s, %s, NOW()
            )
            RETURNING id
            """,
            (
                settings.tenant_id,
                event_id,
                patient_id,
                doctor_row["id"] if doctor_row else None,
                doctor_row["full_name"] if doctor_row else doctor_name,
                doctor_row["crm_number"] if doctor_row else None,
                room_name,
                room_sid,
            ),
        )
        logger.info(
            "teleconsultation_record_created",
            teleconsultation_id=str(row["id"]),
            room_name=room_name,
        )
        return str(row["id"])

    # ---------- leitura e atualização de sessão ----------
    def get_by_id(self, teleconsultation_id: str) -> dict | None:
        return self.db.fetch_one(
            """
            SELECT t.*, p.full_name AS patient_full_name,
                   p.nickname AS patient_nickname, p.birth_date AS patient_birth_date,
                   p.gender AS patient_gender, p.care_unit AS patient_care_unit,
                   p.room_number AS patient_room, p.photo_url AS patient_photo,
                   p.conditions AS patient_conditions, p.medications AS patient_medications,
                   p.allergies AS patient_allergies
            FROM aia_health_teleconsultations t
            JOIN aia_health_patients p ON p.id = t.patient_id
            WHERE t.id = %s
            """,
            (teleconsultation_id,),
        )

    def get_by_room_name(self, room_name: str) -> dict | None:
        row = self.db.fetch_one(
            "SELECT id FROM aia_health_teleconsultations WHERE livekit_room_name = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (room_name,),
        )
        return self.get_by_id(str(row["id"])) if row else None

    def get_by_event(self, event_id: str) -> dict | None:
        row = self.db.fetch_one(
            "SELECT id FROM aia_health_teleconsultations WHERE care_event_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (event_id,),
        )
        return self.get_by_id(str(row["id"])) if row else None

    def update_state(self, teleconsultation_id: str, new_state: str) -> None:
        valid = {
            "scheduling", "pre_check", "consent_recording", "identity_verification",
            "active", "closing", "documentation", "signed", "closed",
        }
        if new_state not in valid:
            raise ValueError(f"state inválido: {new_state}")
        self.db.execute(
            "UPDATE aia_health_teleconsultations SET state = %s, updated_at = NOW() WHERE id = %s",
            (new_state, teleconsultation_id),
        )

    def set_transcription(
        self, teleconsultation_id: str, transcription: str, duration_seconds: int | None = None
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_teleconsultations
            SET transcription_full = %s,
                transcription_duration_seconds = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (transcription, duration_seconds, teleconsultation_id),
        )

    def set_soap(self, teleconsultation_id: str, soap: dict) -> None:
        self.db.execute(
            "UPDATE aia_health_teleconsultations SET soap = %s, updated_at = NOW() WHERE id = %s",
            (self.db.json_adapt(soap), teleconsultation_id),
        )

    def set_prescription(self, teleconsultation_id: str, prescription: list[dict]) -> None:
        self.db.execute(
            "UPDATE aia_health_teleconsultations SET prescription = %s, updated_at = NOW() WHERE id = %s",
            (self.db.json_adapt(prescription), teleconsultation_id),
        )

    def set_fhir_bundle(self, teleconsultation_id: str, bundle: dict) -> None:
        self.db.execute(
            "UPDATE aia_health_teleconsultations SET fhir_bundle = %s, updated_at = NOW() WHERE id = %s",
            (self.db.json_adapt(bundle), teleconsultation_id),
        )

    def mark_signed(
        self,
        teleconsultation_id: str,
        doctor_name: str,
        doctor_crm: str | None,
        signature_method: str = "mock",
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_teleconsultations
            SET state = 'signed',
                signed_at = NOW(),
                signed_by_doctor_name = %s,
                signed_by_doctor_crm = %s,
                signature_method = %s,
                ended_at = COALESCE(ended_at, NOW()),
                updated_at = NOW()
            WHERE id = %s
            """,
            (doctor_name, doctor_crm, signature_method, teleconsultation_id),
        )

    # ---------- utilitários de sala em andamento ----------
    async def list_participants(self, room_name: str) -> list[dict]:
        """Lista participantes atuais da sala (útil pro dashboard)."""
        lk_client = lk_api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        try:
            response = await lk_client.room.list_participants(
                lk_api.ListParticipantsRequest(room=room_name)
            )
            return [
                {
                    "identity": p.identity,
                    "name": p.name,
                    "joined_at": p.joined_at,
                    "state": p.state,
                }
                for p in (response.participants or [])
            ]
        except Exception as exc:
            logger.warning("livekit_list_participants_failed", error=str(exc))
            return []
        finally:
            await lk_client.aclose()

    async def end_consultation(
        self,
        event_id: str,
        room_name: str,
        closure_notes: str | None = None,
    ) -> None:
        """Encerra a sala LiveKit + marca no care_event."""
        lk_client = lk_api.LiveKitAPI(
            url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
        try:
            await lk_client.room.delete_room(
                lk_api.DeleteRoomRequest(room=room_name)
            )
        except Exception as exc:
            logger.warning("livekit_delete_room_failed", error=str(exc), room=room_name)
        finally:
            await lk_client.aclose()

        # Marca no care_event
        self.db.execute(
            """
            UPDATE aia_health_care_events
            SET context = jsonb_set(
                    COALESCE(context, '{}'::jsonb),
                    '{teleconsulta,ended_at}',
                    to_jsonb(NOW()::text),
                    true
                ),
                updated_at = NOW()
            WHERE id = %s
            """,
            (event_id,),
        )
        logger.info("teleconsulta_ended", event_id=event_id, room_name=room_name)


_teleconsulta_instance: TeleconsultaService | None = None


def get_teleconsulta_service() -> TeleconsultaService:
    global _teleconsulta_instance
    if _teleconsulta_instance is None:
        _teleconsulta_instance = TeleconsultaService()
    return _teleconsulta_instance
