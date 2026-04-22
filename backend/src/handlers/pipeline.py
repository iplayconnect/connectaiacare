"""Orquestrador de Eventos de Cuidado (ADR-018).

Substitui o modelo antigo de "sessão conversacional única" pelo modelo de
CareEvent com ciclo de vida, múltiplos eventos paralelos por cuidador e
escalação hierárquica real.

Fluxo principal:

    Áudio chega
        ↓
    Detecta caregiver (biometria + phone + MedMonitor)
        ↓
    Existe evento ativo deste cuidador? (0..N)
        ├─ Sim, paciente específico mencionado bate → FOLLOW-UP
        ├─ Sim, mas paciente diferente → NOVO EVENTO em paralelo
        └─ Não → NOVO EVENTO
        ↓
    Identifica paciente (local + MedMonitor search)
        ↓
    Confirma com foto/nome (SIM/NÃO)
        ↓
    Abre CareEvent + roda análise clínica
        ↓
    Agenda checkins (t+5min pattern, t+10min status, t+30min closure)
        ↓
    Se classification >= urgent → escalação hierárquica imediata
        ↓
    Scheduler em background dispara checkins + escalações no tempo certo

Texto do cuidador:
    - Em awaiting_patient_confirmation → SIM/NÃO
    - Em evento ativo → answer_followup_text (LLM contextualizado)
    - Nenhum evento → onboarding genérico
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from config.settings import settings
from src.services.analysis_service import get_analysis_service
from src.services.care_event_service import (
    STATUS_AWAITING_ACK, STATUS_AWAITING_STATUS_UPDATE,
    get_care_event_service,
)
from src.services.embedding_service import get_embedding_service
from src.services.escalation_service import get_escalation_service
from src.services.evolution import get_evolution
from src.services.medmonitor_client import get_medmonitor_client
from src.services.patient_service import get_patient_service
from src.services.postgres import get_postgres
from src.services.report_service import get_report_service
from src.services.sofia_voice_client import get_sofia_voice
from src.services.tenant_config_service import get_tenant_config_service
from src.services.transcription import get_transcription
from src.services.voice_biometrics_service import get_voice_biometrics
from src.utils.logger import get_logger

logger = get_logger(__name__)


CLASSIFICATION_EMOJI = {
    "routine": "✅", "attention": "⚠️", "urgent": "🚨", "critical": "🆘",
}
CLASSIFICATION_LABEL_PT = {
    "routine": "ROTINA", "attention": "ATENÇÃO",
    "urgent": "URGENTE", "critical": "CRÍTICO",
}

# Tags clínicas inferíveis a partir de entities/transcrição — input pro pattern detection
DERIVABLE_TAGS_FROM_TEXT = {
    "queda": ["caiu", "queda", "caído", "tombo", "tropeçou"],
    "dispneia": ["falta de ar", "cansaço", "dispneia", "sem ar", "respiração", "ofegante"],
    "dor_toracica": ["dor no peito", "dor torácica", "aperto no peito"],
    "confusao": ["confuso", "desorientad", "agitad", "não reconhece"],
    "febre": ["febre", "febril", "temperatura alta", "quente"],
    "sangramento": ["sangue", "sangrament", "sangrando"],
    "convulsao": ["convulsão", "convulsion", "crise"],
    "engasgo": ["engasg", "aspirar", "aspirou"],
    "dor_abdominal": ["dor na barriga", "dor abdominal", "estômago"],
    "recusa_alimentar": ["não quer comer", "recusa alimentação", "não come"],
    "insonia": ["não dorm", "insônia", "acordad", "noite inteira"],
}


class EldercarePipeline:
    def __init__(self):
        self.evo = get_evolution()
        self.transcriber = get_transcription()
        self.analyzer = get_analysis_service()
        self.patients = get_patient_service()
        self.reports = get_report_service()
        self.sofia_voice = get_sofia_voice()
        self.voice_bio = get_voice_biometrics()
        self.events = get_care_event_service()
        self.escalation = get_escalation_service()
        self.medmonitor = get_medmonitor_client()
        self.tenant_cfg = get_tenant_config_service()
        self.embeddings = get_embedding_service()
        self.db = get_postgres()

    # ==================================================================
    # ENTRY POINT
    # ==================================================================
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

    # ==================================================================
    # ÁUDIO
    # ==================================================================
    def _handle_audio(self, phone: str, data: dict[str, Any]) -> dict[str, Any]:
        """Áudio: transcreve, extrai entidades, identifica paciente, abre/atualiza evento."""
        tenant = settings.tenant_id
        self.evo.set_presence(phone, "composing")
        self.evo.send_text(phone, "🎙️ Recebi seu áudio, estou analisando...")

        # Download áudio
        try:
            audio_bytes = self.evo.download_media_base64(data)
        except Exception as exc:
            logger.error("audio_download_failed", error=str(exc))
            self.evo.send_text(phone, "❌ Não consegui baixar o áudio. Pode tentar de novo?")
            return {"status": "error", "reason": "audio_download_failed"}

        # Cria relato (sem evento ainda — associamos depois)
        duration = (data.get("message", {}).get("audioMessage", {}) or {}).get("seconds")
        report = self.reports.create_initial(
            tenant_id=tenant, caregiver_phone=phone,
            caregiver_name_claimed=None, audio_url=None,
            audio_duration_seconds=duration,
        )
        report_id = report["id"]

        # Biometria (identifica caregiver interno)
        caregiver_id, voice_method = self._identify_caregiver_by_voice(phone, audio_bytes, tenant)
        if caregiver_id:
            self.db.execute(
                "UPDATE aia_health_reports SET caregiver_id = %s, caregiver_voice_method = %s WHERE id = %s",
                (caregiver_id, voice_method, report_id),
            )

        # Transcrição
        try:
            tr = self.transcriber.transcribe_bytes(audio_bytes)
            transcription, confidence = tr["transcript"], tr["confidence"]
        except Exception as exc:
            logger.error("transcription_failed", error=str(exc))
            self.evo.send_text(phone, "❌ Não consegui transcrever o áudio. Tente em local mais silencioso.")
            return {"status": "error", "reason": "transcription_failed"}

        if not transcription:
            self.evo.send_text(phone, "🤔 Não consegui entender. Pode falar mais claramente?")
            return {"status": "error", "reason": "empty_transcription"}

        self.reports.update_transcription(report_id, transcription, confidence)
        entities = self.analyzer.extract_entities(transcription)
        self.reports.update_extracted_entities(report_id, entities)

        # Decide: é follow-up de evento existente, ou novo?
        active_events = self.events.list_active_by_caregiver(tenant, phone)
        patient_name_in_audio = (entities or {}).get("patient_name_mentioned")

        # Tenta match com evento ativo específico (se nome bate com paciente de evento aberto)
        if patient_name_in_audio and active_events:
            matched_event = self._match_active_event_by_name(active_events, patient_name_in_audio)
            if matched_event:
                return self._handle_followup_audio(phone, matched_event, report_id, transcription, entities)

        # Se sem nome e há UM evento ativo → assume follow-up daquele (carrega completo)
        if not patient_name_in_audio and len(active_events) == 1:
            full_event = self.events.get_by_id(str(active_events[0]["id"]))
            if full_event:
                return self._handle_followup_audio(phone, full_event, report_id, transcription, entities)

        # Se sem nome e há MÚLTIPLOS eventos ativos → desambigua
        if not patient_name_in_audio and len(active_events) > 1:
            self.evo.send_text(
                phone,
                "❓ Você tem mais de um paciente em acompanhamento no momento. "
                "Pode dizer o nome do idoso para quem o relato se refere?",
            )
            return {"status": "need_clarification", "reason": "multiple_active_events"}

        # Novo evento: identifica paciente
        if not patient_name_in_audio:
            self.evo.send_text(
                phone,
                "❓ Não identifiquei o nome do idoso no áudio. Pode gravar novamente dizendo o nome dele?",
            )
            return {"status": "need_clarification", "reason": "no_patient_name"}

        patient = self._resolve_patient(tenant, patient_name_in_audio)
        if not patient:
            self.evo.send_text(
                phone,
                f"❓ Entendi que você falou sobre *{patient_name_in_audio}*, mas não encontrei essa pessoa no sistema. Pode confirmar o nome completo?",
            )
            return {"status": "need_clarification", "reason": "patient_not_found"}

        self.reports.set_patient_candidate(
            report_id, patient["id"], float(patient.get("match_score", 0.0))
        )

        # Envia confirmação + sessão temporária esperando SIM/NÃO
        self._send_confirmation(phone, patient)
        # Usa sessão legada (conversation_sessions) apenas como buffer curto de confirmação
        self.db.execute(
            """
            INSERT INTO aia_health_legacy_conversation_sessions (tenant_id, phone, state, context, expires_at)
            VALUES (%s, %s, 'awaiting_patient_confirmation', %s, NOW() + INTERVAL '10 minutes')
            ON CONFLICT (tenant_id, phone) DO UPDATE
                SET state = EXCLUDED.state, context = EXCLUDED.context,
                    expires_at = EXCLUDED.expires_at, updated_at = NOW()
            """,
            (
                tenant, phone,
                self.db.json_adapt({
                    "report_id": str(report_id),
                    "patient_id": str(patient["id"]),
                    "patient_name": patient.get("full_name"),
                    "patient_nickname": patient.get("nickname"),
                    "transcription": transcription,
                    "entities": entities,
                }),
            ),
        )
        return {"status": "awaiting_confirmation", "report_id": str(report_id)}

    # ==================================================================
    # FOLLOW-UP ÁUDIO (evento ativo)
    # ==================================================================
    def _handle_followup_audio(
        self, phone: str, event: dict, report_id: str,
        transcription: str, entities: dict[str, Any],
    ) -> dict[str, Any]:
        tenant = event["tenant_id"]
        patient = self.patients.get_by_id(str(event["patient_id"]))
        if not patient:
            logger.warning("followup_audio_patient_missing", event_id=str(event["id"]))
            # Fallback: trata como novo áudio sem contexto
            self.evo.send_text(phone, "❌ Perdi o contexto do paciente. Pode reenviar mencionando o nome?")
            return {"status": "error", "reason": "patient_missing"}

        patient_ref = patient.get("nickname") or patient.get("full_name")
        self.evo.set_presence(phone, "composing")
        self.evo.send_text(phone, f"🎙️ Mais um relato sobre *{patient_ref}*. Analisando a evolução...")

        # Link report ↔ event
        self.db.execute(
            "UPDATE aia_health_reports SET care_event_id = %s WHERE id = %s",
            (str(event["id"]), report_id),
        )
        self.reports.set_patient_candidate(report_id, patient["id"], 1.0)
        self.reports.confirm_patient(report_id)

        # Registra no histórico do evento
        self.events.append_message(
            str(event["id"]),
            {"role": "caregiver", "kind": "audio", "text": transcription, "report_id": str(report_id)},
        )

        # Análise com histórico acumulado da conversa
        conversation_history = (event.get("context") or {}).get("messages") or []
        history = self.reports.recent_for_patient(patient["id"], limit=5)

        analysis = self.analyzer.analyze(
            transcription, entities, patient, history,
            conversation_history=conversation_history,
        )

        # Detecção de resposta a status_update: se o cuidador confirma que
        # está tudo bem (classificação rotina, sem alertas, sem sintomas novos)
        # E o evento estava aguardando retorno ("awaiting_status_update"),
        # encerra automaticamente como "sem_intercorrencia". Corrige bug em
        # que respostas positivas mantinham o evento aberto para sempre.
        if self._is_reassurance_response(event, analysis, transcription):
            self._mark_checkin_response(event, transcription, analysis.get("classification"))
            self.events.resolve(
                str(event["id"]),
                closed_by=f"caregiver:{phone}",
                closed_reason="sem_intercorrencia",
                closure_notes=(
                    f"Cuidador confirmou melhora/ausência de intercorrência. "
                    f"Relato: {transcription[:280]}"
                ),
            )
            self.reports.save_analysis(
                report_id, analysis, analysis.get("classification", "routine"),
                bool(analysis.get("needs_medical_attention")),
            )
            self.evo.send_text(
                phone,
                f"✅ Que bom saber. Encerrei o acompanhamento do evento #{event['human_id']:04d}. "
                "Se algo mudar, é só me enviar outro áudio que reabro na hora.",
            )
            return {
                "status": "resolved_by_reassurance",
                "event_id": str(event["id"]),
                "report_id": str(report_id),
                "classification": analysis.get("classification"),
                "closed_reason": "sem_intercorrencia",
            }

        # Caso contrário: tratamento normal (atualiza evento, classifica, segue ciclo)
        self._finalize_analysis(
            event=event, patient=patient, report_id=report_id,
            transcription=transcription, analysis=analysis, is_followup=True,
        )
        # Em follow-up não voltamos pra awaiting_ack — se estava em
        # awaiting_status_update e o cuidador trouxe info nova, mantemos o
        # ciclo aberto pra Atente revisar. _finalize_analysis já fez o trabalho
        # de update_classification + send_analysis_summary.
        # Marca que o checkin recebeu resposta (mesmo que não resolvida).
        self._mark_checkin_response(event, transcription, analysis.get("classification"))
        return {
            "status": "analyzed_followup",
            "event_id": str(event["id"]),
            "report_id": str(report_id),
            "classification": analysis.get("classification"),
        }

    # ==================================================================
    # TEXTO
    # ==================================================================
    def _handle_text(self, phone: str, text: str, data: dict[str, Any]) -> dict[str, Any]:
        tenant = settings.tenant_id
        text_lower = (text or "").strip().lower()

        # Primeiro: verifica se há sessão legada (confirmação SIM/NÃO)
        legacy = self.db.fetch_one(
            """
            SELECT state, context FROM aia_health_legacy_conversation_sessions
            WHERE tenant_id = %s AND phone = %s AND expires_at > NOW()
            """,
            (tenant, phone),
        )
        if legacy and legacy["state"] == "awaiting_patient_confirmation":
            return self._handle_confirmation_response(phone, text_lower, legacy["context"])

        # Depois: evento ativo?
        active_events = self.events.list_active_by_caregiver(tenant, phone)
        if not active_events:
            self.evo.send_text(
                phone,
                "👋 Oi! Para registrar um relato sobre um idoso, envie um *áudio*. Eu faço o resto.",
            )
            return {"status": "ok", "reason": "no_active_event"}

        if len(active_events) > 1:
            # Primeiro: tenta casar texto com nome de paciente dos eventos ativos
            matched = self._match_event_by_text_mention(active_events, text_lower)
            if matched:
                return self._handle_followup_text(phone, matched, text)

            # Não conseguiu desambiguar — pergunta com opções legíveis
            options = "\n".join(
                f"• *{(e.get('patient_nickname') or e.get('patient_name') or 'Paciente ' + str(e.get('human_id') or '?'))}*"
                f" (evento #{(e.get('human_id') or 0):04d})"
                for e in active_events[:5]
            )
            self.evo.send_text(
                phone,
                f"❓ Você tem mais de um cuidado em andamento:\n\n{options}\n\n"
                f"Sobre quem é a informação? (pode mencionar o nome ou o apelido)",
            )
            return {"status": "need_clarification", "reason": "multiple_active_events"}

        # Single active event → follow-up textual (carrega evento completo)
        full_event = self.events.get_by_id(str(active_events[0]["id"]))
        if not full_event:
            self.evo.send_text(phone, "❌ Perdi o contexto. Pode reenviar?")
            return {"status": "error", "reason": "event_missing"}
        return self._handle_followup_text(phone, full_event, text)

    def _match_event_by_text_mention(
        self, active_events: list[dict], text_lower: str,
    ) -> dict | None:
        """Procura nome de paciente (full_name/nickname) mencionado no texto.

        Heurística: procura por tokens com >=3 chars do nickname/full_name de cada
        evento ativo dentro do texto do cuidador. Se um único evento matcha, retorna.
        Se múltiplos matcham (raro), retorna None pra forçar nova desambiguação.
        """
        if not text_lower:
            return None
        matches: list[dict] = []
        for e in active_events:
            candidates = [
                (e.get("patient_nickname") or "").lower(),
                (e.get("patient_name") or "").lower(),
            ]
            hit = False
            for cand in candidates:
                if not cand:
                    continue
                # Partes significativas do nome (ignora preposições e palavras curtas)
                parts = [p for p in cand.split() if len(p) >= 3 and p not in {"dos", "das", "dona", "seu", "dom"}]
                if any(p in text_lower for p in parts):
                    hit = True
                    break
            if hit:
                matches.append(e)
        if len(matches) == 1:
            # Carrega detalhes completos do evento (list_active traz só resumo)
            return self.events.get_by_id(str(matches[0]["id"]))
        return None

    def _handle_confirmation_response(
        self, phone: str, text_lower: str, context: dict,
    ) -> dict[str, Any]:
        tenant = settings.tenant_id
        affirmative = any(w in text_lower for w in ["sim", "isso", "confirmo", "correto", "é ele", "é ela"])
        negative = any(w in text_lower for w in ["não", "nao", "errado", "não é", "outro"])

        if negative:
            self.db.execute(
                "DELETE FROM aia_health_legacy_conversation_sessions WHERE tenant_id = %s AND phone = %s",
                (tenant, phone),
            )
            self.evo.send_text(
                phone,
                "👍 Entendi. Pode gravar novamente o áudio com o nome correto do idoso?",
            )
            return {"status": "ok", "reason": "patient_rejected"}

        if not affirmative:
            self.evo.send_text(phone, "Por favor responda *SIM* se é o paciente correto, ou *NÃO* se não for.")
            return {"status": "ok", "reason": "waiting_yes_no"}

        # Confirmado → abre CareEvent
        return self._open_event_from_confirmation(phone, context)

    def _open_event_from_confirmation(
        self, phone: str, context: dict,
    ) -> dict[str, Any]:
        tenant = settings.tenant_id
        report_id = context.get("report_id")
        patient_id = context.get("patient_id")
        transcription = context.get("transcription") or ""
        entities = context.get("entities") or {}

        report = self.reports.get_by_id(report_id)
        patient = self.patients.get_by_id(patient_id)
        if not report or not patient:
            self.evo.send_text(phone, "❌ Ops, perdi o contexto. Pode reenviar o áudio?")
            return {"status": "error", "reason": "context_lost"}

        self.reports.confirm_patient(report_id)

        # Tags derivadas do relato (input pro pattern detection)
        event_tags = self._derive_tags(transcription, entities)

        # Abre evento
        event = self.events.open(
            tenant_id=tenant, patient_id=patient_id, caregiver_phone=phone,
            event_type=event_tags[0] if event_tags else None,
            event_tags=event_tags, initial_report_id=str(report_id),
            initial_transcript=transcription,
        )
        # Link report ↔ event
        self.db.execute(
            "UPDATE aia_health_reports SET care_event_id = %s WHERE id = %s",
            (str(event["id"]), report_id),
        )

        # Limpa sessão legada de confirmação
        self.db.execute(
            "DELETE FROM aia_health_legacy_conversation_sessions WHERE tenant_id = %s AND phone = %s",
            (tenant, phone),
        )

        self.evo.send_text(phone, f"✅ Confirmado. Evento #{event['human_id']:04d} aberto. Analisando o relato agora...")
        self.evo.set_presence(phone, "composing")

        # Análise clínica
        history = self.reports.recent_for_patient(patient_id, limit=5)
        conversation_history = (event.get("context") or {}).get("messages") or []
        analysis = self.analyzer.analyze(
            transcription, entities, patient, history,
            conversation_history=conversation_history,
        )

        self._finalize_analysis(
            event=event, patient=patient, report_id=str(report_id),
            transcription=transcription, analysis=analysis, is_followup=False,
        )
        return {
            "status": "event_opened",
            "event_id": str(event["id"]),
            "classification": analysis.get("classification"),
        }

    # ==================================================================
    # FINALIZAÇÃO COMUM — aplicada tanto na abertura quanto no follow-up
    # ==================================================================
    def _finalize_analysis(
        self,
        event: dict, patient: dict, report_id: str,
        transcription: str, analysis: dict, is_followup: bool,
    ) -> None:
        tenant = event["tenant_id"]
        classification = analysis.get("classification", "attention")
        needs_med = bool(analysis.get("needs_medical_attention"))

        # Persiste análise + classificação
        self.reports.save_analysis(report_id, analysis, classification, needs_med)

        # Gera + salva embedding pra pattern detection futura
        try:
            summary_for_embed = " ".join([
                transcription,
                analysis.get("summary") or "",
                " ".join(analysis.get("symptoms_concerning") or []),
            ])[:4000]
            vec = self.embeddings.embed(summary_for_embed)
            if vec:
                self.db.execute(
                    "UPDATE aia_health_reports SET embedding = %s::vector WHERE id = %s",
                    (vec, report_id),
                )
        except Exception as exc:
            logger.warning("embedding_save_failed", error=str(exc))

        # Atualiza o evento
        self.events.update_classification(
            str(event["id"]), classification,
            reasoning=analysis.get("classification_reasoning"),
        )
        self.events.update_summary(str(event["id"]), analysis.get("summary") or "")
        self.events.update_status(str(event["id"]), STATUS_AWAITING_ACK)

        # Envia resumo ao cuidador
        self._send_analysis_summary(event["caregiver_phone"], event, patient, analysis)
        self.events.append_message(
            str(event["id"]),
            {
                "role": "assistant", "kind": "analysis_summary",
                "summary": analysis.get("summary"),
                "classification": classification,
            },
        )

        # Agenda check-ins timeline (só na abertura — follow-ups já estão no ciclo)
        if not is_followup:
            self._schedule_event_timeline(event, classification)

        # Escalação imediata se urgente/crítico
        if self.escalation.should_escalate(classification):
            self.escalation.escalate_initial(event, patient, classification, analysis)

    # ==================================================================
    # Timeline — pattern_analysis + status_update + closure_check
    # ==================================================================
    def _schedule_event_timeline(self, event: dict, classification: str) -> None:
        tenant = event["tenant_id"]
        timings = self.tenant_cfg.get_timings(tenant, classification)
        now = datetime.now(timezone.utc)

        # Pattern analysis (+5 min default, configurável por classificação)
        if self.tenant_cfg.is_feature_enabled(tenant, "pattern_detection"):
            self.events.schedule_checkin(
                event_id=str(event["id"]), tenant_id=tenant,
                kind="pattern_analysis",
                scheduled_for=now + timedelta(minutes=timings["pattern_analysis_after_min"]),
            )

        # Status update (+10 min)
        if self.tenant_cfg.is_feature_enabled(tenant, "proactive_checkin"):
            self.events.schedule_checkin(
                event_id=str(event["id"]), tenant_id=tenant,
                kind="status_update",
                scheduled_for=now + timedelta(minutes=timings["check_in_after_min"]),
            )

        # Closure check (+30 min)
        self.events.schedule_checkin(
            event_id=str(event["id"]), tenant_id=tenant,
            kind="closure_check",
            scheduled_for=now + timedelta(minutes=timings["closure_decision_after_min"]),
        )

    # ==================================================================
    # FOLLOW-UP TEXTO
    # ==================================================================
    def _handle_followup_text(self, phone: str, event: dict, text: str) -> dict[str, Any]:
        tenant = event["tenant_id"]
        patient = self.patients.get_by_id(str(event["patient_id"]))
        if not patient:
            self.evo.send_text(phone, "❌ Perdi o contexto. Pode reenviar?")
            return {"status": "error", "reason": "patient_missing"}

        # Registra mensagem antes de responder
        self.events.append_message(
            str(event["id"]),
            {"role": "caregiver", "kind": "text", "text": text},
        )

        conversation_history = (event.get("context") or {}).get("messages") or []
        context = event.get("context") or {}
        last_analysis = context.get("last_analysis")

        self.evo.set_presence(phone, "composing")
        result = self.analyzer.answer_followup_text(
            caregiver_text=text, patient=patient,
            conversation_history=conversation_history, last_analysis=last_analysis,
        )

        reply = result.get("reply") or "Ok, registrei."
        self.evo.send_text(phone, reply)
        self.events.append_message(
            str(event["id"]),
            {"role": "assistant", "kind": "text", "text": reply, "intent": result.get("intent")},
        )
        self.events.touch_check_in(str(event["id"]))

        # Se indicou piora: sugere áudio detalhado
        if result.get("should_re_analyze"):
            self.evo.send_text(
                phone,
                "🎙️ Se puder gravar um áudio descrevendo o que mudou, eu atualizo a análise.",
            )

        return {"status": "ok", "reason": "followup_text", "intent": result.get("intent")}

    # ==================================================================
    # IDENTIFICAÇÃO DE PACIENTE (local + MedMonitor)
    # ==================================================================
    def _resolve_patient(self, tenant: str, patient_name: str) -> dict | None:
        """Busca paciente localmente. Se não achar, tenta MedMonitor (TotalCare).

        Se achado no MedMonitor, cria espelho local com external_id + foto.
        """
        # Busca local primeiro (fuzzy + trgm)
        local = self.patients.best_match(tenant, patient_name, threshold=0.5)
        if local:
            return local

        # Fallback: busca MedMonitor (assistidos reais Tecnosenior)
        if not self.medmonitor.enabled:
            return None

        remote_matches = self.medmonitor.list_patients(search=patient_name)
        if not remote_matches:
            return None

        # Pega primeiro match — em produção pode ser ambíguo, aí cuidador desambigua via SIM/NÃO
        remote = remote_matches[0]
        person = remote.get("person") or {}
        full_name = f"{person.get('first_name','').strip()} {person.get('last_name','').strip()}".strip()

        # Espelha no DB local
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_patients
                (tenant_id, external_id, full_name, nickname, birth_date, gender,
                 photo_url, metadata, active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT DO NOTHING
            RETURNING id, full_name, nickname, birth_date, gender, photo_url,
                      care_unit, room_number, care_level, conditions, medications,
                      allergies, responsible
            """,
            (
                tenant, str(remote.get("id")), full_name, person.get("first_name"),
                person.get("birthdate"), person.get("gender"),
                person.get("profile_picture_url"),
                self.db.json_adapt({
                    "source": "medmonitor",
                    "has_vidafone": remote.get("has_vidafone"),
                    "has_gps_location": remote.get("has_gps_location"),
                }),
            ),
        )
        if row:
            row["match_score"] = 0.95  # alta — veio direto da fonte de verdade
            logger.info(
                "patient_mirrored_from_medmonitor",
                tenant_id=tenant, external_id=remote.get("id"), name=full_name,
            )
            return row
        # Se insert falhou (race), busca de novo localmente
        return self.patients.best_match(tenant, full_name, threshold=0.3)

    def _match_active_event_by_name(
        self, active_events: list[dict], name_in_audio: str,
    ) -> dict | None:
        """Heurística simples: match por substring do nickname/full_name."""
        name_lower = (name_in_audio or "").lower().strip()
        if not name_lower:
            return None
        for e in active_events:
            cand = " ".join(
                str(v or "") for v in [e.get("patient_nickname"), e.get("patient_name")]
            ).lower()
            if any(part in cand for part in name_lower.split() if len(part) >= 3):
                # Carrega dados completos do evento (list_active traz campos resumidos)
                return self.events.get_by_id(str(e["id"]))
        return None

    # ==================================================================
    # HELPERS — resposta a status_update (encerramento por reasseguramento)
    # ==================================================================
    # Palavras-chave que sinalizam melhora/ausência de intercorrência.
    # Usadas em combinação com classificação clínica "routine" pra fechar
    # o evento automaticamente quando o cuidador retorna dizendo que está OK.
    REASSURANCE_TERMS = (
        "tudo ok", "tudo bem", "tudo certo", "tudo certinho", "tudo bom",
        "está bem", "esta bem", "está ok", "esta ok", "está bom", "esta bom",
        "melhorou", "melhorando", "dormindo bem", "passou", "já passou",
        "ja passou", "não preciso", "nao preciso", "sem problema",
        "falso alarme", "alarme falso", "foi só susto", "foi so susto",
        "estabilizou", "estável", "estavel", "normalizou", "voltou ao normal",
        "está normal", "esta normal", "se acalmou", "acalmou",
        "reagiu bem", "comeu bem", "bebeu água", "tomou remédio",
        "tomou o remedio", "aceitou o remédio",
    )

    def _is_reassurance_response(
        self, event: dict, analysis: dict, transcription: str,
    ) -> bool:
        """Decide se um follow-up é resposta positiva a check-in de status.

        Critérios (todos verdadeiros):
          1. Evento está `awaiting_status_update` — ou seja, acabamos de
             perguntar "como está?" e o cuidador está respondendo.
          2. Classificação da análise veio como `routine` (mais baixa).
          3. Nenhum alerta gerado + needs_medical_attention = False.
          4. Transcrição contém termo de reasseguramento OU a análise
             explicitamente marcou `resolves_event: True`.

        Ser conservador: se houver QUALQUER sinal de piora, não fecha.
        """
        status = event.get("status")
        if status != STATUS_AWAITING_STATUS_UPDATE:
            return False

        classification = (analysis.get("classification") or "").lower()
        if classification != "routine":
            return False

        if analysis.get("needs_medical_attention"):
            return False

        alerts = analysis.get("alerts") or []
        # Alertas de nível "alto"/"critico" bloqueiam fechamento automático
        blocking = [a for a in alerts if (a.get("level") or "").lower() in ("alto", "critico", "crítico", "high", "critical")]
        if blocking:
            return False

        # LLM pode explicitamente sinalizar
        if analysis.get("resolves_event") is True:
            return True

        # Heurística lexical — barata, funciona pro MVP/demo
        text_lower = (transcription or "").lower()
        if any(term in text_lower for term in self.REASSURANCE_TERMS):
            return True

        return False

    def _mark_checkin_response(
        self, event: dict, response_text: str, classification: str | None,
    ) -> None:
        """Marca o check-in `status_update` pendente como respondido.

        Evita que o scheduler fique ressentando o mesmo check-in porque o
        DB acredita que o cuidador nunca respondeu. Idempotente: pega o
        mais recente com status `sent` e sem `response_received_at`.
        """
        try:
            self.db.execute(
                """
                UPDATE aia_health_care_event_checkins
                SET response_received_at = NOW(),
                    response_text = %s,
                    response_classification = %s,
                    status = 'responded'
                WHERE id = (
                    SELECT id FROM aia_health_care_event_checkins
                    WHERE event_id = %s
                      AND kind IN ('status_update', 'closure_check', 'pattern_analysis')
                      AND status IN ('sent', 'scheduled')
                      AND response_received_at IS NULL
                    ORDER BY scheduled_for DESC
                    LIMIT 1
                )
                """,
                (
                    (response_text or "")[:500],
                    classification,
                    str(event["id"]),
                ),
            )
        except Exception as exc:
            logger.warning(
                "mark_checkin_response_failed",
                event_id=str(event.get("id")),
                error=str(exc),
            )

    # ==================================================================
    # HELPERS
    # ==================================================================
    @staticmethod
    def _derive_tags(transcription: str, entities: dict[str, Any]) -> list[str]:
        text = (transcription or "").lower()
        hits: list[str] = []
        for tag, terms in DERIVABLE_TAGS_FROM_TEXT.items():
            if any(t in text for t in terms):
                hits.append(tag)
        # Se analyzer já extraiu tags, mescla
        extracted = (entities or {}).get("tags") if isinstance(entities, dict) else None
        if isinstance(extracted, list):
            for t in extracted:
                if isinstance(t, str) and t not in hits:
                    hits.append(t)
        return hits

    def _send_confirmation(self, phone: str, patient: dict[str, Any]) -> None:
        age = self._calc_age(patient.get("birth_date"))
        parts = [f"*{patient['full_name']}*"]
        if age:
            parts.append(f"{age} anos")
        if patient.get("care_unit"):
            parts.append(patient["care_unit"])
        if patient.get("room_number"):
            parts.append(f"Quarto {patient['room_number']}")
        caption_header = " · ".join(parts)
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

    def _send_analysis_summary(
        self, phone: str, event: dict, patient: dict, analysis: dict,
    ) -> None:
        classification = analysis.get("classification", "routine")
        emoji = CLASSIFICATION_EMOJI.get(classification, "✅")
        label = CLASSIFICATION_LABEL_PT.get(classification, classification.upper())
        summary = analysis.get("summary", "Relato registrado.")

        human_id = event.get("human_id")
        header = f"Evento #{human_id:04d}" if human_id else "Relato"

        lines = [
            f"{emoji} *{header} — {patient['full_name']}*",
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
            lines.append("💡 *Recomendações imediatas:*")
            for r in recs[:4]:
                lines.append(f"   • {r}")

        if classification in {"urgent", "critical"}:
            lines.append("")
            lines.append("🔔 *Equipe de enfermagem e família foram notificadas automaticamente.*")

        self.evo.send_text(phone, "\n".join(lines))

    def _identify_caregiver_by_voice(
        self, phone: str, audio_bytes: bytes, tenant: str,
    ) -> tuple[str | None, str]:
        try:
            row = self.db.fetch_one(
                "SELECT id FROM aia_health_caregivers WHERE tenant_id = %s AND phone = %s AND active = TRUE",
                (tenant, phone),
            )
            caregiver_by_phone = row["id"] if row else None

            if caregiver_by_phone:
                result = self.voice_bio.verify_1to1(
                    str(caregiver_by_phone), tenant, audio_bytes, sample_rate=0
                )
                if result.get("verified"):
                    return str(caregiver_by_phone), "1:1"
                if result.get("reason") == "not_enrolled":
                    return str(caregiver_by_phone), "phone"

            result = self.voice_bio.identify_1toN(tenant, audio_bytes, sample_rate=0)
            if result.get("identified"):
                return str(result["matched_caregiver_id"]), "1:N"

            if caregiver_by_phone:
                return str(caregiver_by_phone), "phone"
            return None, "none"
        except Exception as exc:
            logger.warning("voice_identify_failed", phone=phone, error=str(exc))
            return None, "none"

    @staticmethod
    def _extract_phone(data: dict) -> str:
        remote = (data.get("key") or {}).get("remoteJid") or ""
        return remote.split("@")[0] if "@" in remote else remote

    @staticmethod
    def _detect_message_type(msg: dict) -> str:
        if msg.get("audioMessage"):
            return "audio"
        if msg.get("conversation") or msg.get("extendedTextMessage"):
            return "text"
        if msg.get("imageMessage"):
            return "image"
        return "unknown"

    @staticmethod
    def _extract_text(msg: dict) -> str:
        if "conversation" in msg:
            return msg["conversation"] or ""
        ext = msg.get("extendedTextMessage") or {}
        return ext.get("text") or ""

    @staticmethod
    def _calc_age(birth_date) -> int | None:
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
