"""SuperSofiaOrchestrator — coração da Phase C.

Recebe inbound (já desserializado pelo worker), resolve identidade
e tenant, classifica intent (se anônimo), seleciona sub-agent,
executa turno, executa tools, despacha resposta via outbound stream.

Phase C v1: cobre **caminho do lead anônimo** (commercial, support,
unclear). Perfis identificados → PassthroughSofiaAgent retorna
sentinel pra worker chamar pipeline legado (preserva fluxo
clínico atual sem regressão).

Fluxo:

    inbound (worker)
      ↓
    Orchestrator.process()
      ↓
    1. resolve identity (phone) + tenant (instance)
    2. carrega active_context (45min cross-channel)
    3. se anonymous: classify intent
    4. get_agent_for(profile, intent) → sub-agent
    5. agent.process() → AgentResponse (text + tools + handoff)
    6. execute tools sinalizadas (capture_lead etc) — Phase C v1
       executa in-process; Phase C v2 publica em sofia:tools stream
    7. publica response em sofia:outbound (delivery worker manda)
    8. persiste turn em sofia_messages + active_context
    9. retorna dict pro worker ack a stream

Sentinel: se response.next_action == 'passthrough_legacy', o worker
chama pipeline.handle_webhook() do código legado. Garante zero
regressão pra fluxo clínico atual.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Optional

from src.services.active_context import append_turn, load_recent
from src.services.audit_log_writer import write_audit, redact_phone
from src.services.event_bus import Streams, get_event_bus
from src.services.identity_resolver import get_identity_resolver
from src.services.sofia_agents import AgentContext, get_agent_for
from src.services.sofia_tools import execute_tool
from src.services.tenant_resolver import get_tenant_resolver
from src.services.whatsapp_intent_classifier import (
    get_whatsapp_intent_classifier,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Active context loader (Phase C v1: read-only, escrita continua
# no service existente em voice-call-service / sofia-service)
# ──────────────────────────────────────────────────────────────────


# active_context loader/writer movido pra services/active_context.py
# (importado no topo). Mantemos esta função como adapter pra backward
# compat de uso interno; chamadas legadas usam load_recent diretamente.
def _load_active_context(
    *,
    tenant_id: str,
    phone: str,
    user_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    limit: int = 8,
) -> list[dict]:
    """Wrapper sobre active_context.load_recent — mantido pra clareza."""
    return load_recent(
        user_id=user_id, patient_id=patient_id, phone=phone, limit=limit,
    )


# ──────────────────────────────────────────────────────────────────
# Anti-hallucination guardrail (chat-friendly port de voice)
# ──────────────────────────────────────────────────────────────────

import re as _re

_CLINICAL_PATTERNS_CHAT = [
    (_re.compile(r"\b\d{1,3}\s*anos\b", _re.IGNORECASE), "idade"),
    (_re.compile(r"\bpressão\s+(\d{2,3})\s*(por|/|x)\s*\d{2,3}\b", _re.IGNORECASE), "PA"),
    (_re.compile(r"\bglicemia\s+\d{2,3}\b", _re.IGNORECASE), "glicemia"),
    (_re.compile(r"\b(losartana|metformina|sinvastatina|varfarina|gliclazida|enalapril|captopril|omeprazol|amlodipino|atenolol|hidroclorotiazida|aspirina|paracetamol|dipirona|cumadin)\b", _re.IGNORECASE), "medicação"),
    (_re.compile(r"\b(hipertens[ãa]o|diabetes|insufici[êe]ncia|alzheimer|parkinson|dpoc)\b", _re.IGNORECASE), "condição"),
    (_re.compile(r"\b\d+\s*mg\b", _re.IGNORECASE), "dose"),
    (_re.compile(r"\b(alergia|alérgic[ao])\s+(a|à)\b", _re.IGNORECASE), "alergia"),
]


def _is_clinical_narration(text: str) -> Optional[str]:
    """Pra commercial/support agents NÃO é problema falar de
    "idoso" no contexto comercial. Mas se um agent não-clínico
    começar a inventar pressão/medicação/dose específica, é red
    flag.
    """
    if not text or len(text) < 10:
        return None
    for pat, label in _CLINICAL_PATTERNS_CHAT:
        if pat.search(text):
            return label
    return None


# ──────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────


class SuperSofiaOrchestrator:
    def __init__(self) -> None:
        self.identity_resolver = get_identity_resolver()
        self.tenant_resolver = get_tenant_resolver()
        self.intent_classifier = get_whatsapp_intent_classifier()
        self.event_bus = get_event_bus()

    def process(self, inbound: dict) -> dict:
        """Processa 1 evento da stream sofia:inbound.

        Returns dict com:
            status: 'handled' | 'passthrough' | 'silenced' | 'error'
            agent: nome do sub-agent ativado
            next_action: o que o worker deve fazer
            details: dict com metadata
        """
        started = time.perf_counter()
        trace_id = inbound.get("trace_id")
        tenant_id = inbound.get("tenant_id")
        original_event = inbound.get("payload") or {}

        # Extract phone + text do payload Evolution
        phone, text = self._extract_phone_and_text(original_event)
        if not phone:
            return {"status": "error", "reason": "no_phone", "trace_id": trace_id}

        # Tenant resolution (já feita no webhook, mas re-confirma)
        tenant = self.tenant_resolver.by_id(tenant_id) if tenant_id else None
        if not tenant:
            tenant = self.tenant_resolver.central()
            tenant_id = tenant.id

        # Identity resolution
        identity = self.identity_resolver.resolve(phone, tenant_id=tenant_id)
        # Se NÃO casou no tenant específico, tenta global (multi-tenant)
        if identity.is_anonymous:
            global_identity = self.identity_resolver.resolve(phone)
            if not global_identity.is_anonymous:
                identity = global_identity
                tenant = self.tenant_resolver.by_id(identity.primary.tenant_id) or tenant

        # Audit identity_resolved
        write_audit(
            action="identity_resolved",
            actor="sofia",
            tenant_id=tenant.id,
            trace_id=trace_id,
            payload={
                "phone_redacted": redact_phone(phone),
                "is_anonymous": identity.is_anonymous,
                "matches_count": len(identity.matches),
                "primary_profile": (
                    identity.primary.profile if identity.primary else None
                ),
                "primary_tenant": (
                    identity.primary.tenant_id if identity.primary else None
                ),
            },
        )

        # Active context (read-only por enquanto)
        active_msgs = _load_active_context(
            tenant_id=tenant.id,
            phone=phone,
            user_id=(identity.primary.user_id if identity.primary else None),
            patient_id=(identity.primary.patient_id if identity.primary else None),
        )

        # Intent classification (só pra anônimos OU se inbound for de
        # phone identificado mas a primeira msg parece comercial)
        classified_intent = None
        if identity.is_anonymous and text:
            ir = self.intent_classifier.classify(
                text,
                tenant_id=tenant.id,
                trace_id=trace_id,
            )
            classified_intent = {
                "intent": ir.intent,
                "confidence": ir.confidence,
                "reasoning": ir.reasoning,
            }
            write_audit(
                action="intent_classified",
                actor="sofia",
                tenant_id=tenant.id,
                trace_id=trace_id,
                payload=classified_intent,
            )

        # Build agent context
        ctx = AgentContext(
            phone=phone,
            tenant=tenant,
            identity_match=identity.primary,
            trace_id=trace_id,
            session_id=None,  # Phase C v1: não cria session aqui
            sub_agent="",  # preenchido após resolve
            inbound_text=text or "",
            active_context_messages=active_msgs,
            metadata={"classified_intent": classified_intent},
        )

        # Resolve sub-agent
        agent = get_agent_for(
            is_anonymous=identity.is_anonymous,
            profile=identity.primary.profile if identity.primary else None,
            intent=classified_intent.get("intent") if classified_intent else None,
        )
        ctx.sub_agent = agent.name

        # Process turn (sub-agent decides texto/tool/handoff)
        try:
            response = agent.time_turn(agent.process)(ctx)
        except Exception as exc:
            logger.exception(
                "orchestrator_agent_failed",
                trace_id=trace_id, agent=agent.name, error=str(exc)[:200],
            )
            return {
                "status": "error",
                "reason": "agent_exception",
                "agent": agent.name,
                "trace_id": trace_id,
                "error": str(exc)[:200],
            }

        # Phase C v1: passthrough → worker chama pipeline legado
        if response.next_action == "passthrough_legacy":
            return {
                "status": "passthrough",
                "agent": agent.name,
                "trace_id": trace_id,
            }

        # Anti-hallucination guardrail (post-LLM, pre-send)
        had_valid_tool = any(
            t.get("status") not in ("pending_phase_c4",)
            and (t.get("ok") in (True, None))
            for t in response.tools_called
        )
        if response.text:
            clinical_pattern = _is_clinical_narration(response.text)
            if clinical_pattern and not had_valid_tool and agent.name in ("commercial", "support"):
                logger.warning(
                    "hallucination_suspected_skip_send",
                    trace_id=trace_id,
                    agent=agent.name,
                    pattern=clinical_pattern,
                    text_preview=response.text[:200],
                )
                # Substitui por mensagem segura
                response.text = (
                    "Recebi sua mensagem! Pra te ajudar melhor, pode me "
                    "contar um pouco mais sobre o contexto? (seu nome, "
                    "se é pra você ou pra alguém da família, e o que "
                    "você gostaria de saber sobre a ConnectaIACare). 🙏"
                )
                response.metadata["hallucination_replaced"] = clinical_pattern

        # Execute tools chamadas pelo agent (Phase C v1: in-process)
        tool_results: list[dict] = []
        for tool_call in response.tools_called:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args") or {}
            if tool_call.get("status") == "pending_phase_c4":
                # v1: actually execute now since registry está pronto
                tr = execute_tool(
                    tool_name,
                    tool_args,
                    tenant_id=tenant.id,
                    trace_id=trace_id,
                )
                tool_results.append({
                    "name": tool_name,
                    "ok": tr.ok,
                    "idempotent_skip": tr.idempotent_skip,
                    "data": tr.data,
                    "error": tr.error,
                })

        # ─── Persistir turn em active_context (memória cross-channel) ───
        # Bug fix 2026-05-02: sem isso Sofia esquece nome entre turnos.
        # User msg primeiro (cronológico), depois resposta da Sofia.
        identity_user_id = (
            identity.primary.user_id if identity.primary else None
        )
        identity_patient_id = (
            identity.primary.patient_id if identity.primary else None
        )
        if text:
            append_turn(
                tenant_id=tenant.id,
                role="user",
                content=text,
                channel="whatsapp",
                user_id=identity_user_id,
                patient_id=identity_patient_id,
                phone=phone,
            )
        if response.text:
            append_turn(
                tenant_id=tenant.id,
                role="assistant",
                content=response.text,
                channel="whatsapp",
                user_id=identity_user_id,
                patient_id=identity_patient_id,
                phone=phone,
            )
        # Tool calls bem-sucedidas também viram contexto (Sofia "lembra"
        # que chamou capture_lead no turno passado).
        for tr in tool_results:
            if tr.get("ok"):
                append_turn(
                    tenant_id=tenant.id,
                    role="tool",
                    content=f"tool {tr.get('name')} ok",
                    channel="whatsapp",
                    user_id=identity_user_id,
                    patient_id=identity_patient_id,
                    phone=phone,
                    tool_name=tr.get("name"),
                )

        # Despacha resposta de texto via outbound stream
        if response.text:
            try:
                self.event_bus.publish(Streams.OUTBOUND, {
                    "tenant_id": tenant.id,
                    "trace_id": trace_id,
                    "phone": phone,
                    "message_type": "text",
                    "text": response.text,
                    "metadata": {
                        "sub_agent": agent.name,
                        "next_action": response.next_action,
                    },
                })
            except Exception as exc:
                logger.exception(
                    "orchestrator_outbound_publish_failed",
                    trace_id=trace_id, error=str(exc)[:200],
                )

        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "status": "handled",
            "agent": agent.name,
            "trace_id": trace_id,
            "next_action": response.next_action,
            "tools_called": tool_results,
            "duration_ms": duration_ms,
            "is_anonymous": identity.is_anonymous,
            "intent": classified_intent,
        }

    # ── Helpers ──

    @staticmethod
    def _extract_phone_and_text(event: dict) -> tuple[Optional[str], Optional[str]]:
        """Extrai (phone, text) do payload Evolution."""
        if not isinstance(event, dict):
            return None, None
        data = event.get("data") or event
        key = data.get("key") if isinstance(data, dict) else None
        phone = None
        if isinstance(key, dict):
            jid = key.get("remoteJid")
            if jid and "@" in jid:
                phone = jid.split("@")[0]

        msg = data.get("message") if isinstance(data, dict) else None
        text = None
        if isinstance(msg, dict):
            text = msg.get("conversation")
            if not text and isinstance(msg.get("extendedTextMessage"), dict):
                text = msg["extendedTextMessage"].get("text")
        return phone, text


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_instance: Optional[SuperSofiaOrchestrator] = None


def get_super_sofia_orchestrator() -> SuperSofiaOrchestrator:
    global _instance
    if _instance is None:
        _instance = SuperSofiaOrchestrator()
    return _instance
