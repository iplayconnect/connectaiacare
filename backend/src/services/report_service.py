"""Gestão de relatos (CRUD + timeline do paciente)."""
from __future__ import annotations

from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReportService:
    def __init__(self):
        self.db = get_postgres()

    def create_initial(
        self,
        tenant_id: str,
        caregiver_phone: str,
        caregiver_name_claimed: str | None,
        audio_url: str | None,
        audio_duration_seconds: int | None,
    ) -> dict:
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_reports
                (tenant_id, caregiver_phone, caregiver_name_claimed, audio_url, audio_duration_seconds, status)
            VALUES (%s, %s, %s, %s, %s, 'received')
            RETURNING *
            """,
            (tenant_id, caregiver_phone, caregiver_name_claimed, audio_url, audio_duration_seconds),
        )
        return row

    def update_transcription(self, report_id: str, transcription: str, confidence: float) -> None:
        self.db.execute(
            """
            UPDATE aia_health_reports
            SET transcription = %s, transcription_confidence = %s
            WHERE id = %s
            """,
            (transcription, confidence, report_id),
        )

    def update_extracted_entities(self, report_id: str, entities: dict[str, Any]) -> None:
        self.db.execute(
            "UPDATE aia_health_reports SET extracted_entities = %s WHERE id = %s",
            (self.db.json_adapt(entities), report_id),
        )

    def set_patient_candidate(
        self, report_id: str, patient_id: str, confidence: float
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_reports
            SET patient_id = %s,
                patient_identification_confidence = %s,
                status = 'awaiting_confirmation'
            WHERE id = %s
            """,
            (patient_id, confidence, report_id),
        )

    def confirm_patient(self, report_id: str) -> None:
        self.db.execute(
            "UPDATE aia_health_reports SET status = 'confirmed' WHERE id = %s", (report_id,)
        )

    def save_analysis(
        self,
        report_id: str,
        analysis: dict[str, Any],
        classification: str,
        needs_medical_attention: bool,
    ) -> None:
        self.db.execute(
            """
            UPDATE aia_health_reports
            SET analysis = %s,
                classification = %s,
                needs_medical_attention = %s,
                status = 'analyzed',
                analyzed_at = NOW()
            WHERE id = %s
            """,
            (self.db.json_adapt(analysis), classification, needs_medical_attention, report_id),
        )

    def get_by_id(self, report_id: str) -> dict | None:
        return self.db.fetch_one(
            """
            SELECT r.*,
                   p.full_name AS patient_name,
                   p.photo_url AS patient_photo,
                   p.birth_date AS patient_birth_date,
                   p.care_unit AS patient_care_unit,
                   p.room_number AS patient_room,
                   p.conditions AS patient_conditions,
                   p.medications AS patient_medications
            FROM aia_health_reports r
            LEFT JOIN aia_health_patients p ON p.id = r.patient_id
            WHERE r.id = %s
            """,
            (report_id,),
        )

    def recent_for_patient(self, patient_id: str, limit: int = 10) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT id, transcription, analysis, classification, received_at
            FROM aia_health_reports
            WHERE patient_id = %s AND status = 'analyzed'
            ORDER BY received_at DESC
            LIMIT %s
            """,
            (patient_id, limit),
        )

    def list_recent(self, tenant_id: str, limit: int = 50) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT r.id, r.transcription, r.classification, r.status,
                   r.received_at, r.analyzed_at, r.caregiver_name_claimed,
                   r.audio_url, r.analysis,
                   p.id AS patient_id, p.full_name AS patient_name, p.photo_url AS patient_photo,
                   p.room_number AS patient_room
            FROM aia_health_reports r
            LEFT JOIN aia_health_patients p ON p.id = r.patient_id
            WHERE r.tenant_id = %s
            ORDER BY r.received_at DESC
            LIMIT %s
            """,
            (tenant_id, limit),
        )


_report_instance: ReportService | None = None


def get_report_service() -> ReportService:
    global _report_instance
    if _report_instance is None:
        _report_instance = ReportService()
    return _report_instance
