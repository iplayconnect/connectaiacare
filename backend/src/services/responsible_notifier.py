"""Notifica responsável principal do paciente quando há decisão clínica
sensível. Acionado pelo cascade classifier quando:
  - Tier 3 (juiz) é invocado (qualquer caso de discordância T1≠T2)
  - Severity 'critical' (mesmo com agreement T1+T2)
  - Tudo falhou (fallback conservador)

Canal padrão: WhatsApp via Evolution API. Fallback: SMS se Evolution
indisponível (futuro).

Política de mensagem: comunicação humana, sem jargão técnico, sem
pânico. Indica que algo merece atenção e que sistema está acompanhando.
"""
from __future__ import annotations

from typing import Any

from src.services.audit_service import audit_log
from src.services.evolution import EvolutionClient
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Templates por classe + severity (humanos, sem alarmismo desnecessário)
NOTIFICATION_TEMPLATES = {
    "judge_invoked": (
        "Olá {responsible_name}, sou a Sofia da ConnectaIACare. "
        "Recebemos um relato sobre {patient_name} ({event_type}) que "
        "merece sua atenção.\n\n"
        "Resumo: {summary}\n\n"
        "Estamos acompanhando junto à equipe de cuidados. Se precisar, "
        "me responda aqui."
    ),
    "critical_agreement": (
        "Olá {responsible_name}, é a Sofia. {patient_name} pode estar "
        "passando por uma situação crítica:\n\n"
        "{summary}\n\n"
        "Por favor, ligue para a equipe de cuidados ou para o número "
        "de emergência da sua cidade (192/SAMU). Estou aqui se precisar."
    ),
    "all_tiers_failed": (
        "Olá {responsible_name}, é a Sofia. Recebi um relato sobre "
        "{patient_name} mas tive dificuldade em classificar com "
        "segurança. Resumo recebido:\n\n"
        "{summary}\n\n"
        "Por favor, dê uma olhada quando puder."
    ),
}


def get_responsible_for_patient(patient_id: str) -> dict | None:
    """Busca responsável principal do paciente.

    Schema atual: aia_health_patients.responsible jsonb. Aceita 2 formatos:
      - Array: [{name, phone, is_primary}, ...]
      - Object: {name, phone}  (legacy/single)

    Retorna dict {name, phone} do primary OU do primeiro encontrado.
    None se não há responsável cadastrado.
    """
    db = get_postgres()
    try:
        row = db.fetch_one(
            "SELECT responsible FROM aia_health_patients WHERE id = %s",
            (patient_id,),
        )
    except Exception as exc:
        logger.warning("get_responsible_query_failed", error=str(exc))
        return None
    if not row:
        return None
    resp = row.get("responsible")
    if not resp:
        return None

    # Array: pega is_primary=True ou primeiro
    if isinstance(resp, list) and resp:
        primary = next(
            (r for r in resp if isinstance(r, dict) and r.get("is_primary")),
            resp[0],
        )
        if isinstance(primary, dict) and primary.get("phone"):
            return {
                "name": primary.get("name") or "Responsável",
                "phone": primary["phone"],
            }

    # Object: schema legacy single
    if isinstance(resp, dict) and resp.get("phone"):
        return {
            "name": resp.get("name") or "Responsável",
            "phone": resp["phone"],
        }

    return None


def notify_responsible(
    *,
    tenant_id: str,
    patient_id: str | None,
    patient_name: str | None,
    event_type: str,
    classification: str,
    summary: str,
    reason: str,
    cascade_id: str | None = None,
) -> dict:
    """Envia mensagem ao responsável. Retorna status + canal usado.

    reason: 'judge_invoked' | 'critical_agreement' | 'all_tiers_failed'
    """
    if not patient_id:
        return {"sent": False, "reason": "no_patient_id"}

    responsible = get_responsible_for_patient(patient_id)
    if not responsible:
        logger.warning(
            "no_responsible_found_for_patient",
            patient_id=patient_id, reason=reason,
        )
        audit_log(
            action="responsible_notification.skipped",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={"reason": "no_responsible_registered", "trigger": reason},
        )
        return {"sent": False, "reason": "no_responsible"}

    template = NOTIFICATION_TEMPLATES.get(reason, NOTIFICATION_TEMPLATES["judge_invoked"])
    message = template.format(
        responsible_name=responsible["name"].split()[0] if responsible["name"] else "",
        patient_name=patient_name or "o paciente",
        event_type=event_type,
        summary=summary[:300],
    )

    try:
        evo = EvolutionClient()
        evo.send_text(responsible["phone"], message)
        audit_log(
            action="responsible_notification.sent",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={
                "trigger": reason,
                "channel": "whatsapp",
                "phone_masked": _mask_phone(responsible["phone"]),
                "cascade_id": cascade_id,
                "event_type": event_type,
                "classification": classification,
            },
        )
        return {
            "sent": True,
            "channel": "whatsapp",
            "phone": responsible["phone"],
        }
    except Exception as exc:
        logger.exception("responsible_notification_failed")
        audit_log(
            action="responsible_notification.failed",
            tenant_id=tenant_id,
            resource_type="patient", resource_id=patient_id,
            payload={"trigger": reason, "error": str(exc)[:300]},
        )
        return {"sent": False, "reason": "send_error", "error": str(exc)[:200]}


def _mask_phone(phone: str) -> str:
    """Mascara phone pra audit log: 5551XXX9876 → 5551***9876."""
    if not phone or len(phone) < 7:
        return "***"
    return phone[:4] + "***" + phone[-4:]
