"""Orquestrador do pipeline de relato do cuidador.

Fluxo:
    1. Recebe áudio via WhatsApp → salva relato inicial
    2. Transcreve com Deepgram
    3. Extrai entidades com Claude Haiku (rápido)
    4. Busca paciente no DB por fuzzy matching
    5. Envia WhatsApp de confirmação com foto + nome
    6. [aguarda confirmação SIM]
    7. Analisa com Claude Opus + histórico
    8. Salva análise + classifica
    9. Responde ao cuidador com resumo
    10. Se critical/urgent → dispara ligação Sofia Voice (opcional)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from config.settings import settings
from src.services.analysis_service import get_analysis_service
from src.services.evolution import get_evolution
from src.services.patient_service import get_patient_service
from src.services.postgres import get_postgres
from src.services.report_service import get_report_service
from src.services.session_manager import get_session_manager
from src.services.sofia_voice_client import get_sofia_voice
from src.services.transcription import get_transcription
from src.services.voice_biometrics_service import get_voice_biometrics
from src.utils.logger import get_logger

logger = get_logger(__name__)


CLASSIFICATION_EMOJI = {
    "routine": "✅",
    "attention": "⚠️",
    "urgent": "🚨",
    "critical": "🆘",
}

CLASSIFICATION_LABEL_PT = {
    "routine": "ROTINA",
    "attention": "ATENÇÃO",
    "urgent": "URGENTE",
    "critical": "CRÍTICO",
}


class EldercarePipeline:
    def __init__(self):
        self.evo = get_evolution()
        self.transcriber = get_transcription()
        self.analyzer = get_analysis_service()
        self.patients = get_patient_service()
        self.reports = get_report_service()
        self.sessions = get_session_manager()
        self.sofia_voice = get_sofia_voice()
        self.voice_bio = get_voice_biometrics()
        self.db = get_postgres()

    # ---------- Entry point ----------
    def handle_webhook(self, event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("event") or event.get("type")
        data = event.get("data", event)

        if event_type not in {"messages.upsert", "message.upsert", "MESSAGES_UPSERT"}:
            logger.debug("event_ignored", event_type=event_type)
            return {"status": "ignored", "reason": "event_type_not_handled"}

        key = data.get("key", {})
        if key.get("fromMe"):
            return {"status": "ignored", "reason": "from_me"}

        phone = self._extract_phone(data)
        message = data.get("message", {})
        msg_type = self._detect_message_type(message)

        logger.info("message_received", phone=phone, type=msg_type)

        if msg_type == "audio":
            return self._handle_audio(phone, data)
        elif msg_type == "text":
            return self._handle_text(phone, self._extract_text(message), data)
        else:
            self.evo.send_text(
                phone,
                "👋 Olá! Para registrar um relato sobre um idoso, envie um áudio contando sobre o paciente.",
            )
            return {"status": "ok", "reason": "unsupported_message_type"}

    # ---------- Áudio = novo relato ----------
    def _handle_audio(self, phone: str, data: dict[str, Any]) -> dict[str, Any]:
        tenant = settings.tenant_id
        self.evo.set_presence(phone, "composing")

        self.evo.send_text(phone, "🎙️ Recebi seu áudio, estou analisando...")

        try:
            audio_bytes = self.evo.download_media_base64(data)
            logger.info("audio_downloaded", bytes=len(audio_bytes))
        except Exception as exc:
            logger.error("audio_download_failed", error=str(exc))
            self.evo.send_text(phone, "❌ Não consegui baixar o áudio. Pode tentar de novo?")
            return {"status": "error", "reason": "audio_download_failed"}

        duration = (data.get("message", {}).get("audioMessage", {}) or {}).get("seconds")
        report = self.reports.create_initial(
            tenant_id=tenant,
            caregiver_phone=phone,
            caregiver_name_claimed=None,
            audio_url=None,
            audio_duration_seconds=duration,
        )
        report_id = report["id"]

        # ---------- Biometria de voz (identificação do cuidador) ----------
        caregiver_id, voice_method = self._identify_caregiver_by_voice(phone, audio_bytes, tenant)
        if caregiver_id:
            self.db.execute(
                """
                UPDATE aia_health_reports
                SET caregiver_id = %s, caregiver_voice_method = %s
                WHERE id = %s
                """,
                (caregiver_id, voice_method, report_id),
            )

        try:
            result = self.transcriber.transcribe_bytes(audio_bytes)
            transcription = result["transcript"]
            confidence = result["confidence"]
        except Exception as exc:
            logger.error("transcription_failed", error=str(exc))
            self.evo.send_text(phone, "❌ Não consegui transcrever o áudio. Tente gravar em local mais silencioso.")
            return {"status": "error", "reason": "transcription_failed"}

        if not transcription:
            self.evo.send_text(phone, "🤔 Não consegui entender o áudio. Pode falar mais claramente?")
            return {"status": "error", "reason": "empty_transcription"}

        self.reports.update_transcription(report_id, transcription, confidence)

        entities = self.analyzer.extract_entities(transcription)
        self.reports.update_extracted_entities(report_id, entities)

        patient_name = entities.get("patient_name_mentioned")
        if not patient_name:
            self.evo.send_text(
                phone,
                "❓ Não identifiquei o nome do idoso no áudio. Pode gravar novamente dizendo o nome dele?",
            )
            return {"status": "need_clarification", "reason": "no_patient_name"}

        patient = self.patients.best_match(tenant, patient_name, threshold=0.5)
        if not patient:
            self.evo.send_text(
                phone,
                f"❓ Entendi que você falou sobre *{patient_name}*, mas não encontrei essa pessoa no sistema. Pode confirmar o nome completo?",
            )
            return {"status": "need_clarification", "reason": "patient_not_found"}

        self.reports.set_patient_candidate(
            report_id, patient["id"], float(patient.get("match_score", 0.0))
        )

        self._send_confirmation(phone, patient)
        self.sessions.set(
            tenant,
            phone,
            state="awaiting_patient_confirmation",
            context={"report_id": str(report_id), "patient_id": str(patient["id"])},
        )

        return {"status": "awaiting_confirmation", "report_id": str(report_id)}

    # ---------- Texto = resposta do cuidador ----------
    def _handle_text(self, phone: str, text: str, data: dict[str, Any]) -> dict[str, Any]:
        tenant = settings.tenant_id
        session = self.sessions.get(tenant, phone)
        text_lower = (text or "").strip().lower()

        if not session:
            self.evo.send_text(
                phone,
                "👋 Oi! Para registrar um relato sobre um idoso, envie um *áudio* contando como ele está. Eu faço o resto.",
            )
            return {"status": "ok", "reason": "no_active_session"}

        state = session["state"]
        context = session["context"]

        if state == "awaiting_patient_confirmation":
            affirmative = any(w in text_lower for w in ["sim", "isso", "confirmo", "correto", "é ele", "é ela"])
            negative = any(w in text_lower for w in ["não", "nao", "errado", "não é", "outro"])

            if affirmative:
                return self._on_patient_confirmed(phone, context)
            if negative:
                self.sessions.clear(tenant, phone)
                self.evo.send_text(
                    phone,
                    "👍 Entendi. Pode gravar novamente o áudio com o nome correto do idoso, por favor?",
                )
                return {"status": "ok", "reason": "patient_rejected"}

            self.evo.send_text(phone, "Por favor responda *SIM* se é o paciente correto, ou *NÃO* se não for.")
            return {"status": "ok", "reason": "waiting_yes_no"}

        return {"status": "ok", "reason": "unknown_state"}

    # ---------- Após confirmação, analisa ----------
    def _on_patient_confirmed(self, phone: str, context: dict[str, Any]) -> dict[str, Any]:
        tenant = settings.tenant_id
        report_id = context.get("report_id")
        patient_id = context.get("patient_id")

        report = self.reports.get_by_id(report_id)
        patient = self.patients.get_by_id(patient_id)
        if not report or not patient:
            self.evo.send_text(phone, "❌ Ops, perdi o contexto desse relato. Pode reenviar o áudio?")
            self.sessions.clear(tenant, phone)
            return {"status": "error", "reason": "context_lost"}

        self.reports.confirm_patient(report_id)
        self.evo.send_text(phone, "✅ Confirmado. Analisando o relato agora, um momento...")
        self.evo.set_presence(phone, "composing")

        transcription = report.get("transcription") or ""
        entities = report.get("extracted_entities") or {}
        history = self.reports.recent_for_patient(patient_id, limit=5)

        analysis = self.analyzer.analyze(transcription, entities, patient, history)

        classification = analysis.get("classification", "routine")
        needs_med = bool(analysis.get("needs_medical_attention"))
        self.reports.save_analysis(report_id, analysis, classification, needs_med)

        self._send_analysis_summary(phone, patient, analysis)

        if classification in {"urgent", "critical"} and patient.get("responsible"):
            self._try_proactive_call(patient, analysis, classification)

        self.sessions.clear(tenant, phone)
        return {"status": "analyzed", "classification": classification, "report_id": str(report_id)}

    # ---------- Helpers de envio WhatsApp ----------
    def _send_confirmation(self, phone: str, patient: dict[str, Any]) -> None:
        age = self._calc_age(patient.get("birth_date"))
        caption_parts = [f"*{patient['full_name']}*"]
        if age:
            caption_parts.append(f"{age} anos")
        if patient.get("care_unit"):
            caption_parts.append(patient["care_unit"])
        if patient.get("room_number"):
            caption_parts.append(f"Quarto {patient['room_number']}")
        caption_header = " · ".join(caption_parts)
        caption = (
            f"📋 Você está relatando sobre:\n\n{caption_header}\n\n"
            f"Responda *SIM* para confirmar ou *NÃO* se for outra pessoa."
        )

        photo = patient.get("photo_url")
        if photo:
            try:
                self.evo.send_media(phone, photo, caption=caption)
                return
            except Exception as exc:
                logger.warning("confirmation_photo_failed", error=str(exc))
        self.evo.send_text(phone, caption)

    def _send_analysis_summary(self, phone: str, patient: dict[str, Any], analysis: dict[str, Any]) -> None:
        classification = analysis.get("classification", "routine")
        emoji = CLASSIFICATION_EMOJI.get(classification, "✅")
        label = CLASSIFICATION_LABEL_PT.get(classification, classification.upper())

        summary = analysis.get("summary", "Relato registrado.")
        lines = [
            f"{emoji} *Relato registrado — {patient['full_name']}*",
            "",
            f"📊 *Resumo:* {summary}",
            "",
            f"🏷️ *Classificação:* {label}",
        ]

        reason = analysis.get("classification_reasoning")
        if reason:
            lines.append(f"   _{reason}_")

        alerts = analysis.get("alerts") or []
        urgent_alerts = [a for a in alerts if a.get("level") in {"alto", "critico"}]
        if urgent_alerts:
            lines.append("")
            lines.append("🔔 *Alertas:*")
            for a in urgent_alerts[:3]:
                lines.append(f"   • {a.get('title','')}: {a.get('description','')}")

        recs = analysis.get("recommendations_caregiver") or []
        if recs:
            lines.append("")
            lines.append("💡 *Recomendações para você:*")
            for r in recs[:4]:
                lines.append(f"   • {r}")

        if analysis.get("needs_medical_attention"):
            lines.append("")
            lines.append("👩‍⚕️ *Equipe de enfermagem foi notificada.*")

        self.evo.send_text(phone, "\n".join(lines))

    # ---------- Ligação proativa Sofia Voice ----------
    def _try_proactive_call(
        self, patient: dict[str, Any], analysis: dict[str, Any], classification: str
    ) -> None:
        responsible = patient.get("responsible") or {}
        phone = responsible.get("phone")
        if not phone:
            return

        patient_name = patient["full_name"]
        summary = analysis.get("summary", "")
        label = CLASSIFICATION_LABEL_PT.get(classification, classification.upper())

        script = (
            f"Você é a ConnectaIACare, assistente de cuidado do SPA. Ligue para {responsible.get('name','familiar')} "
            f"({responsible.get('relationship','responsável')} de {patient_name}) com tom calmo, acolhedor e pausado.\n\n"
            f"Situação: {label}. {summary}\n\n"
            f"Script da ligação:\n"
            f"1. Cumprimente pelo nome: 'Olá {responsible.get('name','')}, aqui é a ConnectaIACare, assistente de cuidado do seu familiar {patient_name}.'\n"
            f"2. Explique que houve uma observação relevante no plantão.\n"
            f"3. Resuma a observação em 1-2 frases curtas.\n"
            f"4. Informe que a equipe de enfermagem já foi acionada e está atendendo.\n"
            f"5. Pergunte se há algo que você precisa saber sobre o paciente (ex: alergia recente, preferência).\n"
            f"6. Ofereça passar a ligação para a equipe humana se desejar.\n"
            f"7. Encerre com tranquilidade."
        )

        self.sofia_voice.place_call(
            phone=phone,
            script=script,
            patient_context={"patient_name": patient_name, "classification": classification},
        )

    # ---------- Biometria de voz ----------
    def _identify_caregiver_by_voice(
        self, phone: str, audio_bytes: bytes, tenant: str
    ) -> tuple[str | None, str]:
        """Tenta identificar o cuidador por voz.

        Estratégia:
        1. Busca caregiver com phone cadastrado → tenta 1:1
        2. Se 1:1 falhar ou phone desconhecido → 1:N no tenant
        3. Se nada → caregiver_id=None, method='none'

        Returns: (caregiver_id | None, method: '1:1'|'1:N'|'phone'|'none')
        """
        try:
            row = self.db.fetch_one(
                "SELECT id FROM aia_health_caregivers WHERE tenant_id = %s AND phone = %s AND active = TRUE",
                (tenant, phone),
            )
            caregiver_by_phone = row["id"] if row else None

            # Tentar 1:1 se temos candidato por phone
            if caregiver_by_phone:
                result = self.voice_bio.verify_1to1(
                    str(caregiver_by_phone), tenant, audio_bytes, sample_rate=0
                )
                if result.get("verified"):
                    return str(caregiver_by_phone), "1:1"
                if result.get("reason") == "not_enrolled":
                    # Sem enrollment: confia no phone como fallback
                    return str(caregiver_by_phone), "phone"

            # 1:N — busca em todos os cuidadores do tenant
            result = self.voice_bio.identify_1toN(tenant, audio_bytes, sample_rate=0)
            if result.get("identified"):
                return str(result["matched_caregiver_id"]), "1:N"

            # Se temos phone mas biometria falhou: ainda usa phone como identidade fraca
            if caregiver_by_phone:
                return str(caregiver_by_phone), "phone"

            return None, "none"
        except Exception as exc:
            logger.warning("voice_identify_failed phone=%s error=%s", phone, exc)
            if caregiver_by_phone := self._caregiver_by_phone_fallback(phone, tenant):
                return str(caregiver_by_phone), "phone"
            return None, "none"

    def _caregiver_by_phone_fallback(self, phone: str, tenant: str) -> str | None:
        try:
            row = self.db.fetch_one(
                "SELECT id FROM aia_health_caregivers WHERE tenant_id = %s AND phone = %s AND active = TRUE",
                (tenant, phone),
            )
            return str(row["id"]) if row else None
        except Exception:
            return None

    # ---------- Utils ----------
    def _extract_phone(self, data: dict) -> str:
        remote = (data.get("key") or {}).get("remoteJid") or ""
        return remote.split("@")[0] if "@" in remote else remote

    def _detect_message_type(self, msg: dict) -> str:
        if msg.get("audioMessage"):
            return "audio"
        if msg.get("conversation") or msg.get("extendedTextMessage"):
            return "text"
        if msg.get("imageMessage"):
            return "image"
        return "unknown"

    def _extract_text(self, msg: dict) -> str:
        if "conversation" in msg:
            return msg["conversation"] or ""
        ext = msg.get("extendedTextMessage") or {}
        return ext.get("text") or ""

    def _calc_age(self, birth_date) -> int | None:
        if not birth_date:
            return None
        try:
            if isinstance(birth_date, str):
                bd = datetime.strptime(birth_date.split("T")[0], "%Y-%m-%d").date()
            else:
                bd = birth_date
            today = datetime.now().date()
            return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except Exception:
            return None


_pipeline_instance: EldercarePipeline | None = None


def get_pipeline() -> EldercarePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = EldercarePipeline()
    return _pipeline_instance
