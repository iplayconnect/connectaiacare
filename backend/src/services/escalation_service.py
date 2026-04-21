"""Escalation Service — orquestra notificações hierárquicas de um care_event (ADR-020).

Árvore de escalação definida por tenant_config.escalation_policy (dict por classificação).
Ex: policy["critical"] = ["central", "nurse", "doctor", "family_1", "family_2", "family_3"]

Para cada nível, o serviço:
1. Resolve o contato (phone, nome) a partir do tenant_config ou patient.responsible
2. Envia WhatsApp via Evolution (sempre) + opcionalmente dispara ligação Sofia Voice
3. Registra em aia_health_escalation_log via CareEventService.record_escalation
4. Agenda check-in de "post_escalation" após escalation_levelN_wait_min min
5. Se o nível não responder no prazo, o scheduler chama next_level()

API pública:
    escalate_initial(event, patient, classification, analysis)
    escalate_next_level(event, reason="no_answer")
    should_escalate(event, classification) → bool
    resolve_contact(tenant_id, patient, target_role) → {name, phone, relationship?}

Integrações reais (não mockado, ADR-020):
- WhatsApp: Evolution API (central + nurse + doctor + familiares)
- Voice: Sofia Voice (familiares níveis 2/3) — chamada real
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.care_event_service import get_care_event_service
from src.services.evolution import get_evolution
from src.services.sofia_voice_client import get_sofia_voice
from src.services.tenant_config_service import get_tenant_config_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Roles que usam ligação de voz Sofia em vez de (ou além de) WhatsApp
ROLES_WITH_VOICE_CALL = {"family_1", "family_2", "family_3"}

# Classificações que PRECISAM escalar
ESCALATING_CLASSIFICATIONS = {"urgent", "critical"}


class EscalationService:
    def __init__(self):
        self.events = get_care_event_service()
        self.evo = get_evolution()
        self.sofia = get_sofia_voice()
        self.tenant_cfg = get_tenant_config_service()

    # ---------- decisão ----------
    def should_escalate(self, classification: str | None) -> bool:
        return (classification or "").lower() in ESCALATING_CLASSIFICATIONS

    # ---------- resolução de contato ----------
    def resolve_contact(
        self, tenant_id: str, patient: dict, target_role: str
    ) -> dict[str, Any] | None:
        """Resolve name+phone do target_role, com fallbacks.

        central/nurse/doctor vêm do tenant_config (contatos da casa).
        Se patient.responsible.nurse_override existir, nurse override cai nele.
        family_1/2/3 vêm de patient.responsible.family[] com level=N.
        """
        if target_role in ("central", "nurse", "doctor"):
            contacts = self.tenant_cfg.get_contacts(tenant_id)
            # Override específico do paciente para nurse
            if target_role == "nurse":
                nurse_ovr = (patient.get("responsible") or {}).get("nurse_override")
                if isinstance(nurse_ovr, dict) and nurse_ovr.get("phone"):
                    return {
                        "name": nurse_ovr.get("name") or contacts["nurse"].get("name"),
                        "phone": nurse_ovr["phone"],
                        "relationship": "Enfermeira",
                    }
            return contacts.get(target_role)

        if target_role.startswith("family_"):
            level_str = target_role.split("_", 1)[1]
            try:
                level = int(level_str)
            except ValueError:
                return None
            return self._pick_family_by_level(patient, level)

        return None

    @staticmethod
    def _pick_family_by_level(patient: dict, level: int) -> dict[str, Any] | None:
        """Busca contato familiar por nível. Suporta schema rico e legacy."""
        responsible = patient.get("responsible") or {}

        # Schema rico: responsible.family[] com {name, phone, relationship, level}
        family = responsible.get("family")
        if isinstance(family, list):
            candidates = [f for f in family if isinstance(f, dict) and f.get("level") == level]
            if candidates:
                c = candidates[0]
                return {
                    "name": c.get("name"),
                    "phone": c.get("phone"),
                    "relationship": c.get("relationship"),
                }

        # Legacy: responsible no topo {name, phone, relationship} = level 1
        if level == 1 and responsible.get("phone"):
            return {
                "name": responsible.get("name"),
                "phone": responsible.get("phone"),
                "relationship": responsible.get("relationship"),
            }
        return None

    # ---------- orquestração ----------
    def escalate_initial(
        self,
        event: dict,
        patient: dict,
        classification: str,
        analysis: dict | None = None,
    ) -> list[dict]:
        """Inicia escalação: contata os níveis disparáveis "paralelos" (central, nurse).

        Níveis em paralelo = central + nurse (ambos no WhatsApp, imediatos).
        Se classification=critical, doctor também entra paralelo.
        Familiares (family_1, family_2, family_3) vão em cascata via
        `escalate_next_level` disparado pelo scheduler se não houver resposta.

        Retorna lista de dicts com escalation_id + target_role + status.
        """
        tenant_id = event["tenant_id"]
        policy = self.tenant_cfg.get_escalation_policy(tenant_id, classification)
        if not policy:
            logger.info("escalation_policy_empty", classification=classification)
            return []

        # Primeiro burst: níveis institucionais (central, nurse, doctor)
        institutional = [r for r in policy if r in ("central", "nurse", "doctor")]
        results: list[dict] = []

        for role in institutional:
            contact = self.resolve_contact(tenant_id, patient, role)
            if not contact or not contact.get("phone"):
                logger.warning(
                    "escalation_target_missing_contact",
                    event_id=str(event["id"]),
                    target_role=role,
                )
                continue
            outcome = self._dispatch(event, patient, role, contact, classification, analysis)
            results.append(outcome)

        # Agenda escalação p/ família nível 1 se policy inclui e nenhuma institucional respondeu
        has_family_in_policy = any(r.startswith("family_") for r in policy)
        if has_family_in_policy:
            timings = self.tenant_cfg.get_timings(tenant_id, classification)
            wait_min = timings.get("escalation_level1_wait_min", 5)
            scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=wait_min)
            checkin_id = self.events.schedule_checkin(
                event_id=str(event["id"]),
                tenant_id=tenant_id,
                kind="post_escalation",
                scheduled_for=scheduled_for,
                channel="whatsapp",  # canal do dispatch final que roda ao t+wait
            )
            logger.info(
                "family_escalation_scheduled",
                event_id=str(event["id"]),
                wait_min=wait_min,
                checkin_id=checkin_id,
            )

        return results

    def escalate_next_level(
        self, event: dict, patient: dict, classification: str, analysis: dict | None = None
    ) -> dict | None:
        """Chamado pelo scheduler quando nenhuma resposta veio no nível anterior.

        Descobre qual é o próximo nível (family_1 → family_2 → family_3) baseado
        no que já foi registrado em escalation_log.
        """
        tenant_id = event["tenant_id"]
        existing = self.events.list_escalations_for_event(str(event["id"]))
        already = {e["target_role"] for e in existing}

        policy = self.tenant_cfg.get_escalation_policy(tenant_id, classification)
        next_role: str | None = None
        for role in policy:
            if role.startswith("family_") and role not in already:
                next_role = role
                break

        if not next_role:
            logger.info(
                "no_more_escalation_levels",
                event_id=str(event["id"]),
                already_contacted=sorted(already),
            )
            return None

        contact = self.resolve_contact(tenant_id, patient, next_role)
        if not contact or not contact.get("phone"):
            logger.warning(
                "family_contact_missing",
                event_id=str(event["id"]), target_role=next_role,
            )
            # Tenta pular pro próximo
            return self._skip_and_retry(event, patient, classification, analysis, next_role)

        outcome = self._dispatch(event, patient, next_role, contact, classification, analysis)

        # Agenda próximo nível se houver
        timings = self.tenant_cfg.get_timings(tenant_id, classification)
        level = int(next_role.split("_", 1)[1])
        wait_min = timings.get(f"escalation_level{min(level + 1, 3)}_wait_min", 10)
        scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=wait_min)
        self.events.schedule_checkin(
            event_id=str(event["id"]),
            tenant_id=tenant_id,
            kind="post_escalation",
            scheduled_for=scheduled_for,
            channel="internal",
        )
        return outcome

    def _skip_and_retry(
        self, event: dict, patient: dict, classification: str, analysis: dict | None,
        skipped_role: str,
    ) -> dict | None:
        """Pula role sem contato, tenta o próximo nivelamente."""
        # Registra "skipped" no log pra rastreabilidade
        self.events.record_escalation(
            event_id=str(event["id"]),
            tenant_id=event["tenant_id"],
            target_role=skipped_role,
            target_name=None,
            target_phone="-",
            channel="skipped",
            message_content=f"Contato ausente para {skipped_role} — pulando para próximo nível.",
        )
        return self.escalate_next_level(event, patient, classification, analysis)

    # ---------- execução da notificação ----------
    def _dispatch(
        self,
        event: dict,
        patient: dict,
        target_role: str,
        contact: dict,
        classification: str,
        analysis: dict | None = None,
    ) -> dict:
        """Envia WhatsApp (sempre) + ligação Sofia Voice (se aplicável)."""
        tenant_id = event["tenant_id"]
        target_name = contact.get("name")
        target_phone = contact.get("phone") or ""

        # Gera conteúdo adaptado ao papel
        message = self._build_whatsapp_message(event, patient, target_role, contact, classification, analysis)

        # Envia WhatsApp
        try:
            evo_result = self.evo.send_text(target_phone, message)
            evo_status = "sent" if evo_result else "failed"
            external_ref = (evo_result or {}).get("key", {}).get("id") if isinstance(evo_result, dict) else None
        except Exception as exc:
            logger.error("whatsapp_escalation_failed", role=target_role, phone=target_phone, error=str(exc))
            evo_status = "failed"
            external_ref = None

        # Registra no log antes da ligação (pra pegar o ID)
        escalation_id = self.events.record_escalation(
            event_id=str(event["id"]),
            tenant_id=tenant_id,
            target_role=target_role,
            target_name=target_name,
            target_phone=target_phone,
            channel="whatsapp",
            message_content=message,
            external_ref=external_ref,
        )

        # Voz — familiares nível 1/2/3
        call_result = None
        if target_role in ROLES_WITH_VOICE_CALL and self.tenant_cfg.is_feature_enabled(
            tenant_id, "sofia_voice_calls"
        ):
            try:
                script = self._build_voice_script(event, patient, target_role, contact, classification, analysis)
                call_result = self.sofia.place_call(
                    phone=target_phone,
                    script=script,
                    patient_context={
                        "patient_name": patient.get("full_name"),
                        "patient_nickname": patient.get("nickname"),
                        "classification": classification,
                        "event_id": str(event["id"]),
                    },
                )
                # Registra segundo entry (voz) no log
                self.events.record_escalation(
                    event_id=str(event["id"]),
                    tenant_id=tenant_id,
                    target_role=target_role,
                    target_name=target_name,
                    target_phone=target_phone,
                    channel="voice",
                    message_content=script[:500],
                    external_ref=(call_result or {}).get("call_id"),
                )
            except Exception as exc:
                logger.error("sofia_call_escalation_failed", role=target_role, error=str(exc))

        logger.info(
            "escalation_dispatched",
            event_id=str(event["id"]),
            target_role=target_role,
            target_phone=target_phone,
            whatsapp_status=evo_status,
            voice_attempted=call_result is not None,
        )
        return {
            "escalation_id": escalation_id,
            "target_role": target_role,
            "target_name": target_name,
            "target_phone": target_phone,
            "whatsapp_status": evo_status,
            "voice_call_attempted": call_result is not None,
        }

    # ---------- templates ----------
    @staticmethod
    def _build_whatsapp_message(
        event: dict, patient: dict, target_role: str, contact: dict,
        classification: str, analysis: dict | None,
    ) -> str:
        patient_name = patient.get("full_name") or patient.get("nickname") or "paciente"
        care_unit = patient.get("care_unit") or "SPA"
        summary = (analysis or {}).get("summary") or event.get("summary") or "observação clínica relevante"
        cls_label = {
            "critical": "🆘 CRÍTICO", "urgent": "🚨 URGENTE",
            "attention": "⚠️ ATENÇÃO", "routine": "ROTINA",
        }.get(classification, classification.upper())

        greeting_by_role = {
            "central": f"*{cls_label}* — Central de atendimento\n\n",
            "nurse": f"*{cls_label}* — Enfermagem\n\n",
            "doctor": f"*{cls_label}* — Avaliação médica\n\n",
            "family_1": f"Olá{(', ' + (contact.get('name') or '')) if contact.get('name') else ''} 💙\n\n",
            "family_2": f"Olá{(', ' + (contact.get('name') or '')) if contact.get('name') else ''} 💙\n\n",
            "family_3": f"Olá{(', ' + (contact.get('name') or '')) if contact.get('name') else ''} 💙\n\n",
        }
        greeting = greeting_by_role.get(target_role, f"*{cls_label}*\n\n")

        body_by_role = {
            "central": (
                f"Evento #{event.get('human_id'):04d} aberto em *{care_unit}*.\n"
                f"Paciente: *{patient_name}*\n"
                f"Classificação: {cls_label}\n\n"
                f"📋 {summary}\n\n"
                f"Favor confirmar recebimento e encaminhar ao plantão."
            ),
            "nurse": (
                f"Paciente *{patient_name}* ({care_unit}) precisa de avaliação.\n\n"
                f"{cls_label}\n"
                f"📋 {summary}\n\n"
                f"Por favor, confirmar ao receber e avaliar presencialmente."
            ),
            "doctor": (
                f"Solicitação de avaliação médica — paciente *{patient_name}* ({care_unit}).\n\n"
                f"{cls_label}\n"
                f"📋 {summary}\n\n"
                f"Equipe de enfermagem já acionada. Favor retornar ao plantão."
            ),
        }
        family_body = (
            f"Aqui é a assistente ConnectaIACare, do cuidado de *{patient_name}*.\n\n"
            f"Houve uma situação agora que achamos importante te avisar com calma:\n\n"
            f"📋 {summary}\n\n"
            f"A equipe do {care_unit} já foi acionada e está atendendo. "
            f"Vou te avisar novamente quando tivermos mais informações. "
            f"Se quiser, pode responder aqui mesmo. 💙"
        )

        body = body_by_role.get(target_role, family_body)
        return greeting + body

    @staticmethod
    def _build_voice_script(
        event: dict, patient: dict, target_role: str, contact: dict,
        classification: str, analysis: dict | None,
    ) -> str:
        patient_name = patient.get("full_name") or "seu familiar"
        patient_nickname = patient.get("nickname") or patient_name
        care_unit = patient.get("care_unit") or "instituição"
        relationship = contact.get("relationship") or "familiar"
        contact_name = contact.get("name") or "oi"
        summary = (analysis or {}).get("summary") or "uma observação clínica importante"
        cls_natural = {
            "critical": "crítica", "urgent": "de atenção imediata",
            "attention": "de atenção", "routine": "de rotina",
        }.get(classification, "relevante")

        return (
            f"Você é a ConnectaIACare, assistente de cuidado do {care_unit}. "
            f"Você está ligando para {contact_name}, {relationship} de {patient_name} "
            f"({patient_nickname}), com tom calmo, acolhedor e pausado. Fale devagar, "
            f"sem criar pânico, mas com clareza.\n\n"
            f"Situação: classificação {cls_natural}. {summary}\n\n"
            f"Script:\n"
            f"1. Cumprimente pelo nome: 'Olá {contact_name}, aqui é a ConnectaIACare, "
            f"   assistente de cuidado do(a) {patient_nickname}.'\n"
            f"2. Explique que houve uma situação {cls_natural} no plantão.\n"
            f"3. Resuma em 1-2 frases: {summary}\n"
            f"4. Informe: 'A equipe de enfermagem já foi acionada e está cuidando do(a) {patient_nickname}.'\n"
            f"5. Pergunte: 'Tem alguma informação recente sobre ele(a) que você queira me passar? "
            f"   Alguma mudança de medicação ou algo que aconteceu esses dias?'\n"
            f"6. Ofereça: 'Posso te passar para a equipe humana se desejar.'\n"
            f"7. Se a pessoa estiver tranquila, encerre com: 'Vou manter você informado(a) "
            f"   conforme surgirem novidades. Obrigado(a).'\n"
            f"8. Se a pessoa estiver nervosa, acolha e ofereça transferência imediata."
        )


_escalation_instance: EscalationService | None = None


def get_escalation_service() -> EscalationService:
    global _escalation_instance
    if _escalation_instance is None:
        _escalation_instance = EscalationService()
    return _escalation_instance
