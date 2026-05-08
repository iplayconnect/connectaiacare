"""Sync de vital signs (medidas de saúde) pro TotalCare.

Padrão de uso (alinhado com Matheus 2026-05-08):
    1. Sofia detecta medidas via voz/texto/foto
    2. Insere em aia_health_vital_signs (status=pending de confirmação)
    3. Recapitula com cuidador, marca confirmed_by_caregiver_at
    4. Chama sync_pending_for_patient(patient_uuid) → bulk POST
    5. Persiste tecnosenior_measure_id por linha (audit)

All-or-nothing: Tecnosenior rejeita o bulk inteiro se 1 medida falhar
validação deles. Nossa filter_valid_for_persistence já remove valores
fora da faixa fisiológica antes — bulk deve sempre passar nas medidas
intrínsecas. Erros que sobram são extrínsecos (paciente não existe lá,
caretaker errado, etc.) e vêm consolidados num retorno só.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.services.medmonitor_client import get_medmonitor_client
from src.services.postgres import get_postgres
from src.services.tecnosenior_carenote_sync_service import (
    get_tecnosenior_sync,
)

logger = logging.getLogger("connectaiacare.tecnosenior_vital_signs")


# Mapping nosso (LOINC-aligned) → tipos do Tecnosenior. Hoje 1:1, mas
# isolado aqui pra adaptar se Matheus padronizar diferente.
_TYPE_MAP = {
    "heart_rate": "heart_rate",
    "blood_pressure_systolic": "blood_pressure_systolic",
    "blood_pressure_diastolic": "blood_pressure_diastolic",
    "blood_pressure_composite": None,  # composto — quebrar em sys+dia antes
    "blood_glucose": "blood_glucose",
    "temperature": "temperature",
    "weight": "weight",
    "oxygen_saturation": "oxygen_saturation",
    "respiratory_rate": None,  # Tecnosenior não tem ainda — skip
}


class TecnoseniorVitalSignsSyncService:
    def __init__(self):
        self.db = get_postgres()
        self.client = get_medmonitor_client()
        # Reusa CareNote sync pra resolução de patient_id (mesma lógica
        # de cache + lookup por CPF/phone)
        self.carenote_sync = get_tecnosenior_sync()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    # ══════════════════════════════════════════════════════════════════
    # API pública
    # ══════════════════════════════════════════════════════════════════

    def sync_pending_for_patient(
        self,
        patient_uuid: str,
        max_measures: int = 50,
    ) -> dict[str, Any]:
        """Pega todas as medidas confirmadas+não-sincronizadas do paciente
        e faz UM bulk POST. Retorna estatísticas.

        Use case: cuidador acabou de confirmar conjunto via Sofia, agora
        a gente persiste lá.
        """
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}

        # Resolve patient_id no Tecnosenior
        tec_patient_id = self.carenote_sync.resolve_patient_id(patient_uuid)
        if not tec_patient_id:
            return {
                "status": "error",
                "reason": "patient_not_found_in_tecnosenior",
                "patient_uuid": patient_uuid,
            }

        # Pega medidas pendentes (confirmadas + sem tecnosenior_synced_at)
        rows = self.db.fetch_all(
            """SELECT id::text AS id, vital_type, value_numeric,
                      value_secondary, unit, status as clinical_status,
                      measured_at, source, notes
               FROM aia_health_vital_signs
               WHERE patient_id = %s
                 AND confirmed_by_caregiver_at IS NOT NULL
                 AND tecnosenior_synced_at IS NULL
               ORDER BY measured_at ASC
               LIMIT %s""",
            (patient_uuid, max_measures),
        )
        if not rows:
            return {
                "status": "ok",
                "reason": "no_pending_measures",
                "synced_count": 0,
            }

        return self._sync_rows(patient_uuid, tec_patient_id, list(rows))

    def sync_specific_measures(
        self,
        patient_uuid: str,
        vital_signs_ids: list[str],
    ) -> dict[str, Any]:
        """Sincroniza um set específico de IDs (admin/manual mode)."""
        if not self.enabled:
            return {"status": "error", "reason": "client_disabled"}
        if not vital_signs_ids:
            return {"status": "error", "reason": "empty_ids_list"}

        tec_patient_id = self.carenote_sync.resolve_patient_id(patient_uuid)
        if not tec_patient_id:
            return {
                "status": "error",
                "reason": "patient_not_found_in_tecnosenior",
            }

        # Carrega rows mantendo ordem por measured_at (Tecnosenior ordena
        # a resposta por isso)
        placeholders = ",".join(["%s"] * len(vital_signs_ids))
        rows = self.db.fetch_all(
            f"""SELECT id::text AS id, vital_type, value_numeric,
                       value_secondary, unit, status as clinical_status,
                       measured_at, source, notes,
                       tecnosenior_synced_at
                FROM aia_health_vital_signs
                WHERE patient_id = %s AND id IN ({placeholders})
                ORDER BY measured_at ASC""",
            (patient_uuid, *vital_signs_ids),
        )
        if not rows:
            return {"status": "error", "reason": "no_rows_found"}

        # Filtra os já sincronizados (a menos que force seja explícito)
        pending = [r for r in rows if r.get("tecnosenior_synced_at") is None]
        already = len(rows) - len(pending)
        if not pending:
            return {
                "status": "ok",
                "reason": "all_already_synced",
                "already_synced_count": already,
            }
        return self._sync_rows(patient_uuid, tec_patient_id, list(pending))

    # ══════════════════════════════════════════════════════════════════
    # Implementação
    # ══════════════════════════════════════════════════════════════════

    def _sync_rows(
        self,
        patient_uuid: str,
        tec_patient_id: int,
        rows: list[dict],
    ) -> dict[str, Any]:
        """Lógica comum: monta payload, posta, persiste."""
        idempotency_key = str(uuid.uuid4())
        # Mapping local id → measure dict pra correlação após resposta
        measures_payload: list[dict] = []
        local_id_by_position: list[str] = []  # ordem garantida

        for row in rows:
            vt = row.get("vital_type")
            if vt == "blood_pressure_composite":
                # Quebra composite em systolic + diastolic
                if row.get("value_numeric") is not None:
                    measures_payload.append(
                        self._build_measure(row, "blood_pressure_systolic",
                                           row["value_numeric"])
                    )
                    local_id_by_position.append(row["id"])
                if row.get("value_secondary") is not None:
                    measures_payload.append(
                        self._build_measure(row, "blood_pressure_diastolic",
                                           row["value_secondary"])
                    )
                    local_id_by_position.append(row["id"])
                continue

            mapped = _TYPE_MAP.get(vt)
            if not mapped:
                logger.warning(
                    "vital_signs_skipped_unmapped_type id=%s type=%s",
                    row["id"], vt,
                )
                continue
            if row.get("value_numeric") is None:
                continue
            measures_payload.append(
                self._build_measure(row, mapped, row["value_numeric"])
            )
            local_id_by_position.append(row["id"])

        if not measures_payload:
            return {
                "status": "ok",
                "reason": "no_measures_after_mapping",
                "input_rows": len(rows),
            }

        # Cria batch row antes de chamar — pra audit mesmo se request falhar
        batch_id = self.db.fetch_one(
            """INSERT INTO aia_health_vital_signs_sync_batches
                (patient_id, tecnosenior_patient_id, measures_count,
                 idempotency_key, request_payload)
               VALUES (%s, %s, %s, %s, %s::jsonb)
               RETURNING id::text AS id""",
            (
                patient_uuid, tec_patient_id, len(measures_payload),
                idempotency_key,
                self.db.json_adapt({"measures": measures_payload}),
            ),
        )
        batch_uuid = batch_id["id"] if batch_id else None

        # Marca rows com batch_id (pra retry/audit)
        if batch_uuid and local_id_by_position:
            placeholders = ",".join(["%s"] * len(set(local_id_by_position)))
            self.db.execute(
                f"""UPDATE aia_health_vital_signs
                    SET tecnosenior_sync_batch_id = %s
                    WHERE id IN ({placeholders})""",
                (batch_uuid, *set(local_id_by_position)),
            )

        # Dispara o bulk
        result = self.client.create_health_measures_bulk(
            patient_id=tec_patient_id,
            measures=measures_payload,
            idempotency_key=idempotency_key,
            # Já filtramos suspeitas via filter_valid_for_persistence
            # antes de chegar aqui — então skipamos a validação dupla
            # do client pra não perder linhas legítimas.
            skip_physiologic_validation=False,
        )

        if not result:
            self._mark_batch_error(batch_uuid, "remote_post_failed")
            self._mark_rows_error(local_id_by_position, "remote_post_failed")
            return {
                "status": "error",
                "reason": "remote_post_failed",
                "batch_id": batch_uuid,
                "idempotency_key": idempotency_key,
            }

        # Resposta esperada (Matheus 2026-05-08): array ordenado por
        # measured_at, cada item com seu ID. Tolerante a 2 shapes:
        #   { "measures": [{"id": ..., ...}, ...] }
        #   [ {"id": ..., ...}, ... ]
        if isinstance(result, dict) and "measures" in result:
            returned = result["measures"]
        elif isinstance(result, list):
            returned = result
        else:
            returned = []

        # Mapping: como ambos os lados ordenam por measured_at, posição i
        # da resposta corresponde à posição i do payload
        synced_count = 0
        if returned and len(returned) == len(local_id_by_position):
            for i, remote in enumerate(returned):
                if not isinstance(remote, dict):
                    continue
                remote_id = remote.get("id")
                if remote_id is None:
                    continue
                local_id = local_id_by_position[i]
                self.db.execute(
                    """UPDATE aia_health_vital_signs
                       SET tecnosenior_measure_id = %s,
                           tecnosenior_synced_at = NOW(),
                           tecnosenior_sync_error = NULL
                       WHERE id = %s""",
                    (int(remote_id), local_id),
                )
                synced_count += 1
        else:
            logger.warning(
                "vital_signs_bulk_response_mismatch "
                "expected=%d returned=%d shape=%s",
                len(local_id_by_position),
                len(returned) if isinstance(returned, list) else -1,
                type(result).__name__,
            )

        # Atualiza batch row com resultado
        self.db.execute(
            """UPDATE aia_health_vital_signs_sync_batches
               SET measures_succeeded = %s,
                   measures_failed = %s,
                   response_payload = %s::jsonb,
                   completed_at = NOW()
               WHERE id = %s""",
            (
                synced_count,
                len(measures_payload) - synced_count,
                self.db.json_adapt(result),
                batch_uuid,
            ),
        )

        logger.info(
            "vital_signs_bulk_synced patient=%s batch=%s synced=%d/%d",
            patient_uuid, batch_uuid, synced_count, len(measures_payload),
        )
        return {
            "status": "ok",
            "synced_count": synced_count,
            "total_count": len(measures_payload),
            "batch_id": batch_uuid,
            "idempotency_key": idempotency_key,
            "response": result,
        }

    def _build_measure(
        self,
        row: dict,
        mapped_type: str,
        value: Any,
    ) -> dict:
        """Monta dict de uma medida pro payload."""
        out: dict[str, Any] = {
            "type": mapped_type,
            "value": float(value),
            "unit": row.get("unit") or _DEFAULT_UNIT.get(mapped_type, ""),
            "clinical_status": row.get("clinical_status"),
        }
        ma = row.get("measured_at")
        if isinstance(ma, datetime):
            out["measured_at"] = ma.astimezone(timezone.utc).isoformat()
        elif ma:
            out["measured_at"] = str(ma)
        if row.get("source"):
            out["source"] = row["source"]
        # Usa nosso 'notes' como raw_text pra Tecnosenior (audit do
        # texto/transcrição original). Schema deles aceita string opcional.
        if row.get("notes"):
            out["raw_text"] = row["notes"]
        return out

    def _mark_batch_error(
        self, batch_uuid: str | None, reason: str,
    ) -> None:
        if not batch_uuid:
            return
        try:
            self.db.execute(
                """UPDATE aia_health_vital_signs_sync_batches
                   SET sync_error = %s, completed_at = NOW()
                   WHERE id = %s""",
                (reason, batch_uuid),
            )
        except Exception:
            logger.warning("mark_batch_error_failed", exc_info=True)

    def _mark_rows_error(
        self, vital_signs_ids: list[str], reason: str,
    ) -> None:
        if not vital_signs_ids:
            return
        try:
            placeholders = ",".join(["%s"] * len(set(vital_signs_ids)))
            self.db.execute(
                f"""UPDATE aia_health_vital_signs
                    SET tecnosenior_sync_error = %s
                    WHERE id IN ({placeholders})""",
                (reason, *set(vital_signs_ids)),
            )
        except Exception:
            logger.warning("mark_rows_error_failed", exc_info=True)


_DEFAULT_UNIT = {
    "heart_rate": "bpm",
    "blood_pressure_systolic": "mmHg",
    "blood_pressure_diastolic": "mmHg",
    "blood_glucose": "mg/dL",
    "temperature": "°C",
    "weight": "kg",
    "oxygen_saturation": "%",
}


_instance: TecnoseniorVitalSignsSyncService | None = None


def get_tecnosenior_vital_signs_sync() -> TecnoseniorVitalSignsSyncService:
    global _instance
    if _instance is None:
        _instance = TecnoseniorVitalSignsSyncService()
    return _instance
