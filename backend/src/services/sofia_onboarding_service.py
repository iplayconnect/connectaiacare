"""Sofia Onboarding Service — state machine conversacional via WhatsApp.

ADR-026: Onboarding B2C 100% via WhatsApp. Idoso/família conversa com Sofia,
que coleta dados, valida CPF, aceita consent LGPD, e gera link de pagamento.

Estados (state machine sequencial com permissão pra voltar):

    greeting → role_selection → collect_payer_name → collect_payer_cpf
    → collect_beneficiary → collect_conditions → collect_medications
    → collect_contacts → collect_address → plan_selection
    → payment_method → payment_pending → consent_lgpd → active

Cada state handler:
    - Recebe texto/áudio do user
    - Usa LLM (router task='intent_classifier') pra entender intent
    - Atualiza `collected_data` JSONB
    - Move pra próximo state OU repete pedindo clarificação
    - Responde via WhatsApp (Evolution API)

Design:
    - Idempotente: receber mesma mensagem 2x não avança estado
    - Timeout: sessão parada >48h → state='abandoned' (envia "ainda está aí?")
    - Escape valve: user digita "humano" → transfere pra Atente
    - Audio transcrição: se user manda áudio, Deepgram transcreve e processa
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.conversation_history_service import get_conversation_history
from src.services.correction_handler import (
    CorrectionIntent,
    detect as detect_correction,
    friendly_response as correction_response,
)
from src.services.humanizer_service import Chunk, get_humanizer
from src.services.llm_router import get_llm_router
from src.services.low_confidence_handler import get_low_confidence_handler
from src.services.postgres import get_postgres
from src.services.rate_limit_service import get_rate_limiter
from src.services.safety_moderation_service import (
    SafetyResult,
    get_safety_moderation_service,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# State machine — transições permitidas
# ══════════════════════════════════════════════════════════════════

STATES_ORDER = [
    "greeting",
    "role_selection",
    "collect_payer_name",
    "collect_payer_cpf",
    "collect_beneficiary",
    "collect_conditions",
    "collect_medications",
    "collect_contacts",
    "collect_address",
    "plan_selection",
    "payment_method",
    "payment_pending",
    "consent_lgpd",
    "active",
]


# ══════════════════════════════════════════════════════════════════
# Prompts de intent por estado
# ══════════════════════════════════════════════════════════════════

INTENT_SYSTEMS: dict[str, str] = {
    "role_selection": """Você classifica a intenção do usuário numa conversa de onboarding.
Retorne JSON: {"role": "self" | "caregiver" | "family" | "unclear"}

Contexto: perguntamos se a pessoa está se cadastrando pra cuidar dela mesma,
de um ente querido, ou como cuidadora profissional.

Respostas típicas:
- "pra mim" / "pra minha mãe" (family) / "eu cuido" (family ou caregiver se mencionar trabalho)
- "sou enfermeira" (caregiver)
- "pra eu mesmo" (self)""",

    "collect_payer_name": """Extraia nome completo. Retorne JSON:
{"full_name": "Nome Completo", "first_name": "Nome", "valid": true|false}

Se texto não parece nome (muito curto, só números, saudação), valid=false.""",

    "collect_payer_cpf": """Extraia CPF. Retorne JSON:
{"cpf": "000.000.000-00", "valid": true|false, "reason": "..."}

CPF pode vir com ou sem formatação. Validar checksum dígito verificador.
Aceitar "meu cpf é ..." etc.""",

    "collect_beneficiary": """Extraia dados do idoso que será monitorado. Retorne JSON:
{
  "full_name": "Nome Completo",
  "age": 80,
  "gender": "female"|"male"|"unknown",
  "valid": true|false
}

Texto tipo "minha mãe Maria Silva, 82 anos" → extrair tudo.""",

    "plan_selection": """Usuário escolhendo plano. Retorne JSON:
{"plan_sku": "essencial" | "familia" | "premium" | "premium_device" | "ask_more_info" | "unclear"}

Opções pra matchar: "essencial"/"1"/"49" → essencial; "família"/"familia"/"2"/"89" → familia;
"premium"/"3"/"149" → premium; "dispositivo"/"pulseira"/"4"/"199" → premium_device.
Se perguntar "qual é o melhor?" / "me explica" → ask_more_info.""",

    "payment_method": """Usuário escolhendo pagamento. Retorne JSON:
{"method": "credit_card" | "pix" | "unclear"}

Cartão / crédito / cartão de crédito → credit_card.
PIX / pix / qr / qr code → pix.""",

    "consent_lgpd": """Usuário aceitando ou recusando termos LGPD. Retorne JSON:
{"accepted": true|false, "confidence": 0.0-1.0}

Aceita: "sim", "aceito", "concordo", "pode", "ok", "autorizo".
Recusa: "não", "nao", "não aceito", "recuso"."""
}


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class SofiaOnboardingService:
    def __init__(self):
        self.db = get_postgres()
        self.router = get_llm_router()
        self.safety = get_safety_moderation_service()
        self.humanizer = get_humanizer()
        self.history = get_conversation_history()
        self.rate_limiter = get_rate_limiter()
        self.low_confidence = get_low_confidence_handler()

    # ═══════════════════════════════════════════════════════════════
    # Entry point — chamado pelo pipeline ao receber mensagem
    # ═══════════════════════════════════════════════════════════════

    def handle_message(
        self, phone: str, text: str, media_type: str = "text",
    ) -> dict[str, Any]:
        """Processa mensagem na sessão de onboarding.

        Pipeline (ADR-027 Onda A):
            1. Safety input moderation — bloqueia emergências/jailbreak
            2. Correction handler — detecta "espera, não", "cancelar", "humano"
            3. Session state dispatch — lógica de negócio por estado
            4. Safety output moderation — checa resposta antes de enviar
            5. Humanize — variações + chunks + typing delays
            6. Persist — grava inbound + outbound no histórico

        Retorna:
            {
                "reply": "texto concatenado (compat)",
                "chunks": [Chunk, ...] (novo, pra envio com delays),
                "state": "current_state",
                "safety": SafetyResult | None
            }
        """
        session = self._get_or_create_session(phone)
        state = session["state"]
        session_id = str(session["id"])

        # 1. Persiste mensagem inbound no histórico (base pra janela deslizante)
        inbound_msg_id = self.history.record_inbound(
            phone=phone,
            content=text or "",
            channel="whatsapp",
            session_context="onboarding",
            session_id=session_id,
            message_format=media_type,
            metadata={"state_on_receive": state},
        )

        # 2. Safety Layer — INPUT moderation
        safety = self.safety.moderate_input(
            text=text or "",
            phone=phone,
            session_id=session_id,
        )
        if not safety.is_safe and safety.recommended_action in (
            "escalate_human_immediate", "escalate_human", "block",
        ):
            # Marca mensagem como moderada
            if inbound_msg_id:
                self.history.mark_safety(
                    inbound_msg_id, safety_score={"triggers": safety.triggers}
                )
            reply = safety.bot_response_override or (
                "Preciso pausar essa conversa por segurança. "
                "Se for urgência, ligue 190 ou 192."
            )
            return self._build_humanized_result(
                phone=phone, session_id=session_id, state=state,
                reply=reply, safety=safety, skip_variator=True,
            )

        # 2.5. Rate limit por plano (ADR-027 §8.5 — sustentabilidade financeira)
        rate_check = self.rate_limiter.check(
            phone=phone,
            text=text or "",
            safety_triggers=safety.triggers,
            has_active_care_event=False,  # onboarding não tem care event
        )
        if not rate_check.allowed:
            logger.info(
                "onboarding_rate_limited",
                phone=phone, used=rate_check.used, limit=rate_check.limit,
                plan=rate_check.plan,
            )
            return self._build_humanized_result(
                phone=phone, session_id=session_id, state=state,
                reply=rate_check.response or "",
                safety=safety, skip_variator=True,
            )

        # 2.6. Low-confidence categories "nunca inventar" (ADR-027 §8.6)
        lc_decision = self.low_confidence.evaluate(
            text=text or "",
            phone=phone,
            session_id=session_id,
            llm_confidence=None,  # no onboarding é só category-based
            prior_attempts=0,
        )
        if lc_decision.should_handle and lc_decision.degree == 3:
            # Escalação direta pra humano em categorias sensíveis
            logger.info(
                "onboarding_lc_handoff",
                phone=phone, category=lc_decision.category,
            )
            return self._build_humanized_result(
                phone=phone, session_id=session_id, state=state,
                reply=lc_decision.response or "",
                safety=safety, skip_variator=True,
            )

        # 3. Correction handler — intenção de correção/cancelamento
        correction = detect_correction(text or "")
        if correction is not None:
            if correction == CorrectionIntent.HUMAN:
                return self._build_humanized_result(
                    phone=phone, session_id=session_id, state=state,
                    reply=correction_response(correction), safety=safety,
                )
            if correction == CorrectionIntent.CANCEL:
                self._advance_state(session["id"], "abandoned")
                return self._build_humanized_result(
                    phone=phone, session_id=session_id, state="abandoned",
                    reply=correction_response(correction), safety=safety,
                )
            if correction == CorrectionIntent.GO_BACK:
                result = self._handle_go_back(session)
                return self._build_humanized_result(
                    phone=phone, session_id=session_id,
                    state=result.get("state", state),
                    reply=result.get("reply", ""), safety=safety,
                )
            if correction == CorrectionIntent.RETRY_LAST:
                result = self._handle_go_back(session)
                reply = (
                    correction_response(correction) + "\n\n"
                    + (result.get("reply") or "Manda de novo do jeito certo.")
                )
                return self._build_humanized_result(
                    phone=phone, session_id=session_id,
                    state=result.get("state", state),
                    reply=reply, safety=safety,
                )

        # 4. Incrementa contador de mensagens
        self._increment_message_count(session["id"])

        # 5. Dispatch por estado (lógica de negócio)
        handler = getattr(self, f"_handle_{state}", None)
        if not handler:
            logger.warning("onboarding_state_without_handler", state=state)
            return self._build_humanized_result(
                phone=phone, session_id=session_id, state=state,
                reply="Desculpa, algo deu errado. Vamos recomeçar? Me manda 'oi'.",
                safety=safety,
            )

        try:
            handler_result = handler(session, text, media_type)
        except Exception as exc:
            logger.error("onboarding_handler_error", state=state, error=str(exc))
            return self._build_humanized_result(
                phone=phone, session_id=session_id, state=state,
                reply="Tive um probleminha aqui, pode repetir em outras palavras?",
                safety=safety,
            )

        reply = handler_result.get("reply") or ""
        new_state = handler_result.get("state", state)

        return self._build_humanized_result(
            phone=phone, session_id=session_id, state=new_state,
            reply=reply, safety=safety,
            extra=handler_result,
        )

    def _build_humanized_result(
        self,
        *,
        phone: str,
        session_id: str,
        state: str,
        reply: str,
        safety: SafetyResult | None,
        skip_variator: bool = False,
        extra: dict | None = None,
    ) -> dict[str, Any]:
        """Aplica output moderation + humanizer + persiste outbound."""
        # Safety OUTPUT moderation
        out_safety = self.safety.moderate_output(reply)
        if not out_safety.is_safe and out_safety.bot_response_override:
            reply = out_safety.bot_response_override

        # Humanize (chunks + typing delays + variator)
        chunks: list[Chunk]
        if skip_variator:
            # Em emergências / overrides, não varia — texto é canônico
            chunks = [Chunk(
                text=reply,
                typing_delay_seconds=1.5,
                is_first=True,
                is_last=True,
            )] if reply else []
        else:
            chunks = self.humanizer.humanize(reply)

        # Persiste outbound no histórico
        concatenated = "\n\n".join(c.text for c in chunks) if chunks else reply
        if concatenated:
            self.history.record_outbound(
                phone=phone,
                content=concatenated,
                channel="whatsapp",
                session_context="onboarding",
                session_id=session_id,
                processing_agent="sofia_onboarding",
                metadata={
                    "state": state,
                    "chunks_count": len(chunks),
                    "safety_triggers": safety.triggers if safety else [],
                },
            )

        result = {
            "reply": concatenated,
            "chunks": chunks,
            "state": state,
            "safety": safety.triggers if safety else [],
        }
        if extra:
            # preserva chaves extras do handler (ex: intent, buttons)
            for k, v in extra.items():
                if k not in result:
                    result[k] = v
        return result

    # ═══════════════════════════════════════════════════════════════
    # Session management
    # ═══════════════════════════════════════════════════════════════

    def _get_or_create_session(self, phone: str) -> dict:
        row = self.db.fetch_one(
            """
            SELECT id, state, collected_data, created_at, last_message_at,
                   message_count, completed_at, abandoned_at
            FROM aia_health_onboarding_sessions
            WHERE phone = %s AND tenant_id = 'sofiacuida_b2c'
            """,
            (phone,),
        )
        if row and row["state"] not in ("active", "abandoned", "rejected"):
            return row

        # Cria nova sessão (ou reativa abandonada)
        if row:
            # Sessão existe mas está 'active'/'abandoned' → começa outra? NÃO,
            # se active já é cliente. Se abandoned, reabre.
            if row["state"] == "active":
                # Já é assinante — não faz onboarding
                return {**row, "already_active": True}
            # Reabre abandoned
            self.db.execute(
                """
                UPDATE aia_health_onboarding_sessions
                SET state = 'greeting', abandoned_at = NULL,
                    collected_data = '{}'::jsonb, message_count = 0,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (row["id"],),
            )
            return self._get_or_create_session(phone)

        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_onboarding_sessions
                (tenant_id, phone, state, collected_data)
            VALUES ('sofiacuida_b2c', %s, 'greeting', '{}'::jsonb)
            RETURNING id, state, collected_data, created_at, message_count
            """,
            (phone,),
        )
        return row

    def _increment_message_count(self, session_id: str) -> None:
        self.db.execute(
            """
            UPDATE aia_health_onboarding_sessions
            SET message_count = message_count + 1, last_message_at = NOW()
            WHERE id = %s
            """,
            (session_id,),
        )

    def _advance_state(
        self, session_id: str, next_state: str, data_patch: dict | None = None,
    ) -> None:
        if data_patch:
            # Merge no JSONB existente
            self.db.execute(
                """
                UPDATE aia_health_onboarding_sessions
                SET state = %s,
                    collected_data = collected_data || %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (next_state, self.db.json_adapt(data_patch), session_id),
            )
        else:
            self.db.execute(
                "UPDATE aia_health_onboarding_sessions SET state = %s, updated_at = NOW() WHERE id = %s",
                (next_state, session_id),
            )

    # ═══════════════════════════════════════════════════════════════
    # State handlers
    # ═══════════════════════════════════════════════════════════════

    def _handle_greeting(self, session, text, media_type):
        # Ignora texto — só saúda e avança
        self._advance_state(session["id"], "role_selection")
        return {
            "reply": (
                "Olá! 👋 Aqui é a *Sofia*, assistente da ConnectaIACare.\n\n"
                "Estou aqui pra ajudar você a cuidar de quem você ama, com "
                "monitoramento 24h por WhatsApp e uma central humana quando precisar.\n\n"
                "Antes de tudo, me conta: você está se cadastrando pra você mesmo "
                "ou pra monitorar um ente querido (mãe, pai, sogro, etc.)?"
            ),
            "state": "role_selection",
        }

    def _handle_role_selection(self, session, text, media_type):
        intent = self._llm_intent("role_selection", text)
        role = intent.get("role", "unclear")

        if role == "unclear":
            return {
                "reply": (
                    "Me ajuda entender melhor 🤔\n\n"
                    "Responda com uma dessas opções:\n"
                    "👵 *Pra minha mãe/pai/ente querido*\n"
                    "🧑 *Pra mim mesmo*\n"
                    "👩‍⚕️ *Sou cuidador profissional*"
                ),
                "state": "role_selection",
            }

        self._advance_state(
            session["id"], "collect_payer_name",
            data_patch={"role": role},
        )
        if role == "self":
            msg = (
                "Legal que você está cuidando da sua própria saúde! 💙\n\n"
                "Me diga seu nome completo, por favor."
            )
        elif role == "caregiver":
            msg = (
                "Que bacana poder apoiar seu trabalho 👩‍⚕️\n\n"
                "Pra começar, me manda seu nome completo."
            )
        else:
            msg = (
                "Que carinho cuidar da família 💙\n\n"
                "Me diga SEU nome completo (você que está fazendo o cadastro)."
            )
        return {"reply": msg, "state": "collect_payer_name"}

    def _handle_collect_payer_name(self, session, text, media_type):
        intent = self._llm_intent("collect_payer_name", text)
        if not intent.get("valid"):
            return {
                "reply": "Hum, não consegui reconhecer. Pode me mandar seu nome completo (com sobrenome)?",
                "state": "collect_payer_name",
            }
        name = intent["full_name"]
        first = intent.get("first_name") or name.split()[0]
        self._advance_state(
            session["id"], "collect_payer_cpf",
            data_patch={"payer": {"full_name": name, "first_name": first}},
        )
        return {
            "reply": (
                f"Prazer, *{first}*! 🤝\n\n"
                "Agora preciso do seu CPF — é pra vincular a conta "
                "e garantir a segurança dos seus dados."
            ),
            "state": "collect_payer_cpf",
        }

    def _handle_collect_payer_cpf(self, session, text, media_type):
        intent = self._llm_intent("collect_payer_cpf", text)
        if not intent.get("valid"):
            return {
                "reply": (
                    "Esse CPF não bateu 🤔. Pode conferir e me mandar de novo?\n"
                    "_Pode ser com ou sem pontinhos, do jeito que vier mais fácil._"
                ),
                "state": "collect_payer_cpf",
            }
        # Hash SHA-256 do CPF (LGPD — não armazenamos em claro)
        cpf_clean = re.sub(r"\D", "", intent["cpf"])
        cpf_hash = hashlib.sha256(cpf_clean.encode()).hexdigest()
        payer = session["collected_data"].get("payer", {})
        payer["cpf_hash"] = cpf_hash
        payer["cpf_last4"] = cpf_clean[-4:] if len(cpf_clean) >= 4 else ""

        self._advance_state(
            session["id"], "collect_beneficiary",
            data_patch={"payer": payer, "cpf_verified_at": datetime.now(timezone.utc).isoformat()},
        )
        role = session["collected_data"].get("role", "family")
        if role == "self":
            # Idoso se cadastrando — beneficiary é ele mesmo, skip
            return self._skip_to_contacts(session, payer)
        return {
            "reply": (
                "✅ CPF confirmado.\n\n"
                "Agora me conta sobre o ente querido que você vai monitorar:\n"
                "*Nome completo e idade dele(a).*\n\n"
                "Ex: _\"minha mãe Maria Silva, 82 anos\"_"
            ),
            "state": "collect_beneficiary",
        }

    def _handle_collect_beneficiary(self, session, text, media_type):
        intent = self._llm_intent("collect_beneficiary", text)
        if not intent.get("valid"):
            return {
                "reply": "Me ajuda com o nome completo e a idade do(a) idoso(a)?",
                "state": "collect_beneficiary",
            }
        beneficiary = {
            "full_name": intent["full_name"],
            "first_name": intent["full_name"].split()[0],
            "age": intent.get("age"),
            "gender": intent.get("gender"),
        }
        self._advance_state(
            session["id"], "collect_conditions",
            data_patch={"beneficiary": beneficiary},
        )
        return {
            "reply": (
                f"💙 *{beneficiary['first_name']}*, {beneficiary.get('age','?')} anos, anotado.\n\n"
                "Me conta: a senhora/senhor tem algum problema de saúde "
                "já conhecido? Ex: *pressão alta, diabetes, Parkinson, Alzheimer,* "
                "ou qualquer outro.\n\n"
                "_Se não souber ou preferir não informar agora, manda *\"pular\"* "
                "que a gente completa depois._"
            ),
            "state": "collect_conditions",
        }

    def _handle_collect_conditions(self, session, text, media_type):
        text_lower = (text or "").strip().lower()
        skipped = text_lower in ("pular", "skip", "nao sei", "não sei", "n sei", "nenhum", "nenhuma", "nao", "não")
        beneficiary = session["collected_data"].get("beneficiary", {})
        if skipped:
            beneficiary["conditions_raw"] = ""
        else:
            beneficiary["conditions_raw"] = text.strip()[:500]
        self._advance_state(
            session["id"], "collect_medications",
            data_patch={"beneficiary": beneficiary},
        )
        return {
            "reply": (
                "Show 👍\n\n"
                "Agora as *medicações* que toma regularmente. "
                "Você pode:\n"
                "📝 Escrever (ex: _\"Losartana 50mg manhã, Metformina 850mg almoço e jantar\"_)\n"
                "📸 Mandar *foto* da caixa ou receita — a IA lê pra você!\n\n"
                "_Ou manda *\"pular\"* se não tiver medicamento regular._"
            ),
            "state": "collect_medications",
        }

    def _handle_collect_medications(self, session, text, media_type):
        text_lower = (text or "").strip().lower()
        beneficiary = session["collected_data"].get("beneficiary", {})

        if media_type == "image":
            # TODO: integrar OCR — por enquanto marca como foto recebida
            beneficiary["medications_photo_received"] = True
            beneficiary["medications_note"] = "Foto enviada — será processada após cadastro"
        elif text_lower in ("pular", "skip", "nao tem", "não tem", "nenhuma"):
            beneficiary["medications_raw"] = ""
        else:
            beneficiary["medications_raw"] = text.strip()[:1000]

        self._advance_state(
            session["id"], "collect_contacts",
            data_patch={"beneficiary": beneficiary},
        )
        return {
            "reply": (
                "Perfeito 💊\n\n"
                "Agora preciso de *contatos de emergência* — "
                "pessoas que avisamos se algo acontecer.\n\n"
                "Me manda no formato:\n"
                "_Nome - DDD + celular - parentesco_\n\n"
                "Exemplo:\n"
                "_João Silva - 51999998888 - filho_\n"
                "_Teresa - 5133332222 - irmã_\n\n"
                "Pode mandar até 3 contatos numa mensagem só."
            ),
            "state": "collect_contacts",
        }

    def _handle_collect_contacts(self, session, text, media_type):
        beneficiary = session["collected_data"].get("beneficiary", {})
        beneficiary["emergency_contacts_raw"] = (text or "").strip()[:1500]
        self._advance_state(
            session["id"], "collect_address",
            data_patch={"beneficiary": beneficiary},
        )
        return {
            "reply": (
                "Contatos anotados 🤝\n\n"
                "Pra última parte antes do plano: *onde o(a) idoso(a) mora?*\n\n"
                "Me manda só o *CEP* — se quiser já pode completar com rua e número.\n\n"
                "_Ex: \"90010-000, Rua das Flores 123\"_"
            ),
            "state": "collect_address",
        }

    def _handle_collect_address(self, session, text, media_type):
        beneficiary = session["collected_data"].get("beneficiary", {})
        beneficiary["address_raw"] = (text or "").strip()[:500]
        self._advance_state(
            session["id"], "plan_selection",
            data_patch={"beneficiary": beneficiary},
        )
        plans = self._fetch_plans()
        lines = [
            "📋 Tudo certo! Agora escolhemos o plano ideal:\n",
        ]
        for idx, p in enumerate(plans, 1):
            lines.append(
                f"*{idx}. {p['name']}* — R$ {p['price_cents']/100:.2f}/mês\n"
                f"_{p['tagline']}_\n"
            )
        lines.append(
            "\nResponda com o *número* ou *nome* do plano.\n"
            "Se quiser saber mais, me manda _\"me explica melhor\"_."
        )
        return {"reply": "\n".join(lines), "state": "plan_selection"}

    def _handle_plan_selection(self, session, text, media_type):
        intent = self._llm_intent("plan_selection", text)
        sku = intent.get("plan_sku")
        if sku == "ask_more_info":
            plans = self._fetch_plans()
            return {
                "reply": self._build_plans_detailed(plans),
                "state": "plan_selection",
            }
        if sku in ("unclear", None) or sku not in ("essencial", "familia", "premium", "premium_device"):
            return {
                "reply": "Não peguei qual plano. Manda o número (1, 2, 3 ou 4) ou o nome.",
                "state": "plan_selection",
            }

        plan = self._fetch_plan_by_sku(sku)
        self._advance_state(
            session["id"], "payment_method",
            data_patch={"plan_sku": sku, "plan_name": plan["name"], "plan_price_cents": plan["price_cents"]},
        )
        price_str = f"R$ {plan['price_cents']/100:.2f}"
        return {
            "reply": (
                f"Ótima escolha! *{plan['name']}* — {price_str}/mês 🎉\n\n"
                "*Forma de pagamento:*\n\n"
                "💳 *Cartão* — teste grátis de 7 dias + cobrança automática mensal\n"
                "📱 *PIX* — assinatura começa hoje já pagando o 1º mês\n\n"
                "Responda: _cartão_ ou _pix_"
            ),
            "state": "payment_method",
        }

    def _handle_payment_method(self, session, text, media_type):
        intent = self._llm_intent("payment_method", text)
        method = intent.get("method")
        if method not in ("credit_card", "pix"):
            return {
                "reply": "Cartão ou PIX? 💳📱 Qual você prefere?",
                "state": "payment_method",
            }

        self._advance_state(
            session["id"], "payment_pending",
            data_patch={"payment_method": method},
        )
        plan_name = session["collected_data"].get("plan_name", "Plano")

        if method == "credit_card":
            # TODO: integrar Asaas/MP — gera checkout_url real
            msg = (
                f"💳 *Cartão de crédito — {plan_name}*\n\n"
                "Teste grátis de 7 dias! Só cobra no 8º dia se você gostar.\n"
                "Pode cancelar a qualquer momento mandando _\"cancelar\"_ aqui.\n\n"
                "*Link seguro pra cadastrar o cartão:*\n"
                "🔗 https://care.connectaia.com.br/pagamento/[em-breve]\n\n"
                "_(Integração PSP em configuração — por ora, vou ativar você em modo\n"
                "trial demo. A cobrança real começa quando configurarmos o gateway.)_\n\n"
                "Me responde _\"ativar\"_ quando tiver clicado no link."
            )
        else:  # PIX
            msg = (
                f"📱 *PIX — {plan_name}*\n\n"
                "PIX é assinatura imediata — começa hoje já pagando o 1º mês.\n"
                "Todo mês você vai receber um QR novo aqui no WhatsApp.\n\n"
                "*QR code do primeiro pagamento:*\n"
                "🔲 (em breve — integração PSP em configuração)\n\n"
                "Me responde _\"paguei\"_ quando efetuar o pagamento, ou _\"cancelar\"_ se mudou de ideia."
            )

        return {"reply": msg, "state": "payment_pending"}

    def _handle_payment_pending(self, session, text, media_type):
        text_lower = (text or "").strip().lower()
        if text_lower in ("ativar", "paguei", "pago", "ok", "confirmo"):
            self._advance_state(session["id"], "consent_lgpd")
            return {
                "reply": self._build_consent_message(),
                "state": "consent_lgpd",
            }
        return {
            "reply": (
                "Tô aqui esperando 😊\n\n"
                "Assim que confirmar o pagamento, me manda _\"paguei\"_ "
                "ou _\"ativar\"_ pra eu liberar o monitoramento."
            ),
            "state": "payment_pending",
        }

    def _handle_consent_lgpd(self, session, text, media_type):
        intent = self._llm_intent("consent_lgpd", text)
        if intent.get("accepted") is True:
            # FINAL — ativa sessão + cria subscription (stub)
            self._activate(session)
            data = session["collected_data"]
            beneficiary_name = data.get("beneficiary", {}).get("first_name", "seu ente querido")
            return {
                "reply": (
                    "🎉 *Tudo ativado!*\n\n"
                    f"A partir de agora eu acompanho a {beneficiary_name} 24h por dia.\n\n"
                    "Amanhã de manhã (09h) já começamos com o primeiro check-in. "
                    "Se acontecer qualquer coisa urgente antes disso, é só me chamar aqui.\n\n"
                    "_Qualquer dúvida, manda uma mensagem a qualquer hora. Estou aqui._ 💙"
                ),
                "state": "active",
            }
        if intent.get("accepted") is False:
            self._advance_state(session["id"], "rejected", {"reject_reason": "lgpd_refused"})
            return {
                "reply": (
                    "Entendi, sem problema. Sem o consentimento não posso "
                    "começar o monitoramento — é exigido por lei.\n\n"
                    "Se mudar de ideia, é só me chamar. 💙"
                ),
                "state": "rejected",
            }
        return {
            "reply": "Preciso de um *\"aceito\"* ou *\"não aceito\"* clarinho, pode ser?",
            "state": "consent_lgpd",
        }

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _skip_to_contacts(self, session, payer):
        """Quando role=self, beneficiary é o próprio user; skip coleta."""
        beneficiary = {
            "full_name": payer["full_name"],
            "first_name": payer.get("first_name") or payer["full_name"].split()[0],
            "same_as_payer": True,
        }
        self._advance_state(
            session["id"], "collect_conditions",
            data_patch={"beneficiary": beneficiary},
        )
        return {
            "reply": (
                "Entendi, a gente vai cuidar de você mesmo 💙\n\n"
                "Me conta: você tem algum problema de saúde já conhecido? "
                "Ex: pressão alta, diabetes, artrose... (_\"pular\"_ se preferir completar depois)"
            ),
            "state": "collect_conditions",
        }

    def _llm_intent(self, state: str, text: str) -> dict:
        """Chama router com task='intent_classifier' pra classificar texto."""
        system = INTENT_SYSTEMS.get(state, "Você classifica intenção. Retorne JSON.")
        try:
            return self.router.complete_json(
                task="intent_classifier",
                system=system,
                user=text,
            )
        except Exception as exc:
            logger.warning("onboarding_intent_failed", state=state, error=str(exc))
            return {}

    def _fetch_plans(self) -> list[dict]:
        return self.db.fetch_all(
            """
            SELECT sku, name, tagline, price_cents, features
            FROM aia_health_plans
            WHERE tenant_id = 'sofiacuida_b2c' AND active = TRUE
            ORDER BY display_order
            """,
        )

    def _fetch_plan_by_sku(self, sku: str) -> dict:
        return self.db.fetch_one(
            "SELECT * FROM aia_health_plans WHERE sku = %s AND tenant_id = 'sofiacuida_b2c'",
            (sku,),
        )

    def _build_plans_detailed(self, plans: list[dict]) -> str:
        lines = ["📋 *Detalhes dos planos:*\n"]
        for idx, p in enumerate(plans, 1):
            lines.append(f"━━━━━━━━━━━━━━━━━━\n*{idx}. {p['name']}* — R$ {p['price_cents']/100:.2f}/mês")
            for f in p.get("features", [])[:5]:
                lines.append(f"   • {f}")
            lines.append("")
        lines.append("Qual você quer? (*1*, *2*, *3* ou *4*)")
        return "\n".join(lines)

    def _build_consent_message(self) -> str:
        return (
            "📋 *Últimos termos antes de começar:*\n\n"
            "✅ Os dados do(a) idoso(a) serão usados *exclusivamente* pra monitoramento "
            "e cuidado, protegidos pela *LGPD*.\n\n"
            "✅ Você pode *cancelar* a qualquer momento mandando _\"cancelar\"_.\n\n"
            "✅ Em emergência, podemos contatar a família e, se o plano permitir, "
            "acionar a *central Atente 24h*.\n\n"
            "✅ Temos *7 dias de teste grátis* (no cartão) — pode cancelar sem cobrança.\n\n"
            "Me responde *\"aceito\"* pra começar agora, ou _\"não aceito\"_ pra não continuar."
        )

    def _handle_escape_to_human(self, session):
        # Grava flag e escala
        logger.info("onboarding_escape_to_human", session_id=str(session["id"]), phone=session.get("phone"))
        return {
            "reply": (
                "Claro! Vou chamar um atendente humano da nossa central. "
                "Em até alguns minutos alguém aqui responde.\n\n"
                "_(No MVP esta função ainda está em configuração — "
                "por favor aguarde ou ligue pra (51) 4002-8922.)_"
            ),
            "state": session["state"],
        }

    def _handle_go_back(self, session):
        try:
            cur = STATES_ORDER.index(session["state"])
            if cur > 0:
                prev = STATES_ORDER[cur - 1]
                self._advance_state(session["id"], prev)
                return {
                    "reply": "Ok, voltando um passo. Me manda o dado correto, por favor.",
                    "state": prev,
                }
        except ValueError:
            pass
        return {
            "reply": "Já estamos no início. Manda _\"oi\"_ pra começar de novo.",
            "state": session["state"],
        }

    def _activate(self, session) -> None:
        """Cria subscription + marca sessão como active."""
        data = session["collected_data"]
        plan_sku = data.get("plan_sku")
        method = data.get("payment_method", "credit_card")
        payer = data.get("payer", {})
        beneficiary = data.get("beneficiary", {})

        now = datetime.now(timezone.utc)
        trial_ends_at = now + timedelta(days=7) if method == "credit_card" else None

        # Insere subscription (stub — sem PSP real ainda)
        sub = self.db.insert_returning(
            """
            INSERT INTO aia_health_subscriptions
                (tenant_id, plan_sku,
                 payer_subject_type, payer_subject_id, payer_phone, payer_cpf_hash,
                 payer_name, beneficiary_patient_ids,
                 status, payment_method,
                 trial_started_at, trial_ends_at,
                 onboarding_session_id)
            VALUES ('sofiacuida_b2c', %s,
                    'family_member', uuid_generate_v4(), %s, %s,
                    %s, ARRAY[]::uuid[],
                    %s, %s,
                    %s, %s,
                    %s)
            RETURNING id, human_id
            """,
            (
                plan_sku,
                session.get("phone") or data.get("payer_phone", ""),
                payer.get("cpf_hash"),
                payer.get("full_name"),
                "trialing" if method == "credit_card" else "active",
                method,
                now if method == "credit_card" else None,
                trial_ends_at,
                session["id"],
            ),
        )

        self.db.execute(
            """
            UPDATE aia_health_onboarding_sessions
            SET state = 'active',
                completed_at = NOW(),
                subscription_id = %s,
                consent_signed_at = NOW(),
                consent_version = 'v1.0-2026-04'
            WHERE id = %s
            """,
            (sub["id"], session["id"]),
        )
        logger.info(
            "onboarding_activated",
            session_id=str(session["id"]),
            subscription_id=str(sub["id"]),
            plan=plan_sku,
            method=method,
        )


_instance: SofiaOnboardingService | None = None


def get_sofia_onboarding_service() -> SofiaOnboardingService:
    global _instance
    if _instance is None:
        _instance = SofiaOnboardingService()
    return _instance
