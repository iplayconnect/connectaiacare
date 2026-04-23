"""Safety Moderation Service — pipeline de 4 camadas conforme ADR-027.

Camadas:
    1. Input Moderation — antes do LLM processar user_message
    2. Safety Router   — detecta triggers de emergência (hardcoded)
    3. Agent response — o LLM finalmente responde (fora deste módulo)
    4. Output Moderation — checa resposta do LLM antes de enviar

Triggers de emergência (ordem de criticidade):
    - csam (crítica): conteúdo sexual envolvendo menor
    - suicidal_ideation (emergência): ideação suicida
    - elder_abuse (emergência): violência contra idoso
    - medical_emergency (emergência): emergência médica reportada
    - jailbreak_attempt (warning): tentou trocar persona
    - violence_threat / substance_abuse (warning)

Providers:
    - Regex rápido (local, primeiro filtro)
    - OpenAI Moderation API (gratuito, camada adicional)
    - LLM classifier (opcional, pra casos ambíguos)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════

@dataclass
class SafetyResult:
    """Resultado da moderação — usado por pipeline + agentes."""
    is_safe: bool = True
    severity: str = "info"  # info | warning | critical | emergency
    triggers: list[str] = field(default_factory=list)
    recommended_action: str = "continue"  # continue | warn | escalate | block | mute_bot
    bot_response_override: str | None = None
    detection_source: str = "regex"
    raw_scores: dict = field(default_factory=dict)
    explanation: str = ""


# ══════════════════════════════════════════════════════════════════
# Patterns (Regex — primeira linha de defesa)
# ══════════════════════════════════════════════════════════════════

# Ideação suicida / auto-lesão (pt-BR + sinônimos comuns)
SUICIDAL_PATTERNS = [
    r"\b(me\s+matar|suic[íi]dio|suicidar|tirar\s+minha?\s+vida|me\s+suicid|se\s+matar)\b",
    r"\b(quero\s+morrer|n[ãa]o\s+aguento\s+(mais\s+)?viver|melhor\s+morrer)\b",
    r"\b(n[ãa]o\s+vale\s+a\s+pena\s+viver|n[ãa]o\s+quero\s+(mais\s+)?viver)\b",
    r"\b(vou\s+(me\s+)?matar|vou\s+acabar\s+com\s+tudo)\b",
    r"\bcortar\s+(os\s+)?pulsos?\b",
    r"\b(overdose|me\s+enforcar)\b",
]

# Violência contra idoso / abuso
ELDER_ABUSE_PATTERNS = [
    r"\b(me\s+bate|me\s+agride|me\s+bateu|me\s+bat[ei]|apanho|meu\s+filho\s+me\s+bate)\b",
    r"\b(prende\s+em\s+casa|trancad[oa]|n[ãa]o\s+me\s+deixa\s+sair)\b",
    r"\b(me\s+humilha|me\s+insulta|me\s+grita|me\s+xinga)\b",
    r"\b(levaram\s+meu\s+dinheiro|me\s+roubaram|roubaram\s+(minha\s+)?aposentadoria)\b",
    r"\b(n[ãa]o\s+me\s+d[ãa]\s+comida|n[ãa]o\s+me\s+deixam\s+comer|passo\s+fome)\b",
    r"\b(abandonad[oa]|esqueceram\s+de\s+mim)\b",
]

# Emergências médicas reportadas (ação imediata)
MEDICAL_EMERGENCY_PATTERNS = [
    r"\b(desmaiou|ca[íi]u\s+e\s+n[ãa]o\s+acorda|n[ãa]o\s+responde|perdeu\s+a\s+consci[êe]ncia)\b",
    r"\b(est[áa]\s+(tendo|com)\s+(um\s+)?(infarto|avc|derrame))\b",
    r"\b(n[ãa]o\s+(est[áa]\s+)?respir(a|ando))\b",
    r"\b(sangrando\s+muito|muito\s+sangue)\b",
    r"\b(convuls[ãa]o|convulsionando)\b",
    r"\b(engasgou|engasgando|aspirando)\b",
    r"\b(engol(iu|imos)\s+(muito\s+)?rem[ée]dio|overdose)\b",
]

# Jailbreak / persona break
JAILBREAK_PATTERNS = [
    r"\bignor(e|a|ar)\s+(as\s+)?(instru[çc][õo]es|regras|prompts?)\b",
    r"\byou\s+are\s+now\b",
    r"\b(voc[êe]\s+)?(agora|passa\s+a\s+ser|vai\s+ser)\s+(uma|um)\s+(outr[ao]|nov[ao])\b",
    r"\b(modo\s+)?(dan|developer|jailbreak|sem\s+filtros?|sem\s+restri[çc][õo]es)\b",
    r"\b(finge|finja|pretenda|pretende)\s+(ser|que\s+[ée])\b.{0,50}\b(m[ée]dic|psic[óo]log|advogad)",
    r"\b(me\s+diga|qual\s+[ée])\s+(seu|o)\s+(prompt|system\s+prompt|instru[çc][õo]es\s+de\s+sistema)\b",
    r"\bact\s+as\b|\bimpersonate\b",
    r"\b(mude\s+(a\s+)?(sua\s+)?persona|troque\s+de\s+persona)\b",
]

# Conteúdo sexual envolvendo menor (ZERO tolerância)
CSAM_PATTERNS = [
    # Propositalmente conservadoras — qualquer combinação gera trigger
    r"\b(crian[çc]a|menor|adolescente|pr[ée][- ]?p[úu]ber)\b.{0,80}\b(nu[oa]?|sex|porn|pelad[oa]|masturba)",
    r"\b(sex|porn|masturba|pelad[oa]|nu[oa]?)\b.{0,80}\b(crian[çc]a|menor|adolescente)",
    r"\bcsam\b",
    r"\b(pedofil|pedofili)\b",
    r"\b(abuso\s+(sexual\s+)?(de\s+)?crian[çc]a|estuprar\s+crian[çc]a)\b",
]

# Conteúdo sexual adulto explícito
SEXUAL_ADULT_PATTERNS = [
    r"\b(quero\s+transar|fazer\s+sexo\s+comigo|me\s+manda\s+nudes?)\b",
    r"\b(descreve\s+(uma\s+)?cena\s+(de\s+)?sexo|hist[óo]ria\s+er[óo]tica)\b",
]

# Violência/ódio
HATE_SPEECH_PATTERNS = [
    r"\bmat(e|ar)\s+(todos?\s+)?(os\s+)?(negros?|judeus?|gays?|nordestinos?|pretos?)\b",
    r"\b(raça\s+inferior|genoc[íi]dio)\b",
]

# Referências externas que Sofia pode citar
EXTERNAL_RESOURCES = {
    "cvv": {
        "name": "CVV - Centro de Valorização da Vida",
        "phone": "188",
        "url": "https://cvv.org.br",
        "scope": "Apoio emocional e prevenção do suicídio, 24h gratuito",
    },
    "disque_100": {
        "name": "Disque 100",
        "phone": "100",
        "url": "https://www.gov.br/mdh/pt-br/disque100",
        "scope": "Denúncia de violência contra idosos, crianças e grupos vulneráveis",
    },
    "samu": {
        "name": "SAMU",
        "phone": "192",
        "scope": "Emergência médica",
    },
    "bombeiros": {
        "name": "Bombeiros",
        "phone": "193",
        "scope": "Emergências gerais",
    },
}


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class SafetyModerationService:
    def __init__(self):
        self.db = get_postgres()
        self._openai_client = None

    # ────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ────────────────────────────────────────────────────────────────

    def moderate_input(
        self,
        text: str,
        phone: str | None = None,
        session_id: str | None = None,
        tenant_id: str = "connectaiacare_demo",
    ) -> SafetyResult:
        """Moderação da mensagem do user (input). Decide se segue ou escala."""
        if not text or not text.strip():
            return SafetyResult()

        # 1. Regex local (rápido)
        regex_result = self._check_regex(text)
        if regex_result.severity in ("emergency", "critical"):
            # Crítico → loga imediato, não chama API externa
            self._log_event(
                tenant_id=tenant_id,
                phone=phone,
                session_id=session_id,
                user_message=text,
                result=regex_result,
            )
            return regex_result

        # 2. OpenAI Moderation API (se configurado, só como complemento)
        openai_result = self._check_openai_moderation(text)
        if openai_result and openai_result.severity in ("emergency", "critical"):
            merged = self._merge_results(regex_result, openai_result)
            self._log_event(
                tenant_id=tenant_id, phone=phone, session_id=session_id,
                user_message=text, result=merged,
            )
            return merged

        # 3. Jailbreak / persona break (warning, não bloqueia mas registra)
        if regex_result.triggers or (openai_result and openai_result.triggers):
            merged = self._merge_results(regex_result, openai_result)
            self._log_event(
                tenant_id=tenant_id, phone=phone, session_id=session_id,
                user_message=text, result=merged,
            )
            return merged

        # Tudo limpo
        return SafetyResult(is_safe=True, severity="info", recommended_action="continue")

    def moderate_output(self, bot_text: str) -> SafetyResult:
        """Moderação da resposta do bot antes de enviar ao user."""
        if not bot_text:
            return SafetyResult()

        # Checa prompt leak / violações de persona
        result = SafetyResult()

        # Sofia nunca deve revelar prompt
        prompt_leak_patterns = [
            r"system\s+prompt",
            r"minhas\s+instru[çc][õo]es\s+(de\s+)?sistema",
            r"constitutional\s+rules?",
            r"eu\s+fui\s+programad[ao]\s+para",
            r"modelo\s+de\s+linguagem",
            r"gpt[- ]?[0-9]",
            r"claude[- ]?[0-9]?",
            r"gemini[- ]?[0-9]?",
        ]
        for pattern in prompt_leak_patterns:
            if re.search(pattern, bot_text, re.IGNORECASE):
                result.is_safe = False
                result.severity = "warning"
                result.triggers.append("prompt_leak_attempt")
                result.recommended_action = "replace_with_generic"
                result.bot_response_override = (
                    "Sou a Sofia 💙 e estou aqui pra te ajudar com cuidado "
                    "da sua família. Em que posso ser útil?"
                )
                break

        return result

    # ────────────────────────────────────────────────────────────────
    # Regex layer
    # ────────────────────────────────────────────────────────────────

    def _check_regex(self, text: str) -> SafetyResult:
        text_lower = text.lower()
        result = SafetyResult(detection_source="regex")

        # CSAM — trigger imediato CRÍTICO
        if self._match_any(CSAM_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "critical"
            result.triggers.append("csam")
            result.recommended_action = "block"
            result.bot_response_override = (
                "Não posso ajudar com isso. Se você ou alguém está em risco, "
                "ligue Disque 100 (denúncia) ou 190 (polícia)."
            )
            return result

        # Ideação suicida — emergência humana
        if self._match_any(SUICIDAL_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "emergency"
            result.triggers.append("suicidal_ideation")
            result.recommended_action = "escalate_human_immediate"
            result.bot_response_override = self._build_suicide_response()
            return result

        # Violência contra idoso
        if self._match_any(ELDER_ABUSE_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "emergency"
            result.triggers.append("elder_abuse")
            result.recommended_action = "escalate_human"
            result.bot_response_override = self._build_elder_abuse_response()
            return result

        # Emergência médica
        if self._match_any(MEDICAL_EMERGENCY_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "emergency"
            result.triggers.append("medical_emergency")
            result.recommended_action = "escalate_human_immediate"
            result.bot_response_override = self._build_medical_emergency_response()
            return result

        # Conteúdo sexual adulto → rejeita educadamente
        if self._match_any(SEXUAL_ADULT_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "warning"
            result.triggers.append("sexual_content_adult")
            result.recommended_action = "reject_kindly"
            result.bot_response_override = (
                "Sou a Sofia 💙 — não posso ajudar com isso. "
                "Mas se quiser conversar sobre cuidado ou qualquer outra coisa, "
                "tô aqui."
            )
            return result

        # Hate speech
        if self._match_any(HATE_SPEECH_PATTERNS, text_lower):
            result.is_safe = False
            result.severity = "critical"
            result.triggers.append("hate_speech")
            result.recommended_action = "block"
            result.bot_response_override = (
                "Não posso ajudar com conteúdo assim. Vou encerrar essa conversa."
            )
            return result

        # Jailbreak / prompt injection
        if self._match_any(JAILBREAK_PATTERNS, text_lower):
            result.is_safe = True  # não bloqueia — só registra e mantém persona
            result.severity = "warning"
            result.triggers.append("jailbreak_attempt")
            result.recommended_action = "maintain_persona"
            result.bot_response_override = (
                "Sou a Sofia 💙 — da ConnectaIACare, aqui pra te ajudar com "
                "cuidado da sua família. Em que posso ser útil?"
            )
            return result

        return result

    @staticmethod
    def _match_any(patterns: list[str], text_lower: str) -> bool:
        for p in patterns:
            if re.search(p, text_lower, re.IGNORECASE):
                return True
        return False

    # ────────────────────────────────────────────────────────────────
    # OpenAI Moderation API (complementar, free)
    # ────────────────────────────────────────────────────────────────

    def _check_openai_moderation(self, text: str) -> SafetyResult | None:
        """Chama OpenAI Moderation API se OPENAI_API_KEY disponível."""
        key = os.getenv("OPENAI_API_KEY", "")
        if not key:
            return None

        try:
            if self._openai_client is None:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=key)

            resp = self._openai_client.moderations.create(input=text)
            m = resp.results[0] if resp.results else None
            if not m:
                return None

            result = SafetyResult(detection_source="openai_moderation")
            result.raw_scores = {
                "flagged": m.flagged,
                "categories": m.categories.model_dump() if hasattr(m, "categories") else {},
                "category_scores": m.category_scores.model_dump() if hasattr(m, "category_scores") else {},
            }
            if not m.flagged:
                return result

            # Mapeamento OpenAI categories → nossos triggers
            cats = m.categories.model_dump() if hasattr(m, "categories") else {}
            if cats.get("self-harm") or cats.get("self-harm/intent") or cats.get("self-harm/instructions"):
                result.is_safe = False
                result.severity = "emergency"
                result.triggers.append("suicidal_ideation")
                result.recommended_action = "escalate_human_immediate"
                result.bot_response_override = self._build_suicide_response()
            elif cats.get("sexual/minors"):
                result.is_safe = False
                result.severity = "critical"
                result.triggers.append("csam")
                result.recommended_action = "block"
                result.bot_response_override = (
                    "Não posso ajudar com isso."
                )
            elif cats.get("violence/graphic") or cats.get("violence"):
                result.is_safe = False
                result.severity = "warning"
                result.triggers.append("violence_graphic")
                result.recommended_action = "reject_kindly"
            elif cats.get("hate") or cats.get("hate/threatening"):
                result.is_safe = False
                result.severity = "critical"
                result.triggers.append("hate_speech")
                result.recommended_action = "block"
            elif cats.get("sexual"):
                result.is_safe = False
                result.severity = "warning"
                result.triggers.append("sexual_content_adult")
                result.recommended_action = "reject_kindly"

            return result
        except Exception as exc:
            logger.warning("openai_moderation_failed", error=str(exc))
            return None

    # ────────────────────────────────────────────────────────────────
    # Responses pra emergências
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_suicide_response() -> str:
        cvv = EXTERNAL_RESOURCES["cvv"]
        return (
            "Fico preocupada com você, e quero que saiba que **você não está "
            "sozinho(a)** 💙\n\n"
            "O que você tá sentindo é real, e tem gente treinada pra te escutar "
            "agora mesmo:\n\n"
            f"☎️ *{cvv['name']}* — ligue *{cvv['phone']}* (gratuito, 24h)\n"
            f"🌐 {cvv['url']}\n\n"
            "Também vou avisar nossa equipe pra entrar em contato com você. "
            "Não precisa responder nada agora se não quiser — só sei que estou aqui."
        )

    @staticmethod
    def _build_elder_abuse_response() -> str:
        d100 = EXTERNAL_RESOURCES["disque_100"]
        return (
            "Você me contou algo muito sério, e eu acredito em você 💙\n\n"
            "Ninguém merece passar por isso. Vou te ajudar:\n\n"
            f"☎️ *{d100['name']}* — ligue *{d100['phone']}* "
            "(denúncia anônima, 24h)\n"
            "☎️ *Polícia* — *190* (emergência imediata)\n\n"
            "Também vou avisar nossa central Atente pra te apoiar. "
            "Se estiver em perigo agora, peça ajuda a um vizinho ou saia do lugar."
        )

    @staticmethod
    def _build_medical_emergency_response() -> str:
        samu = EXTERNAL_RESOURCES["samu"]
        return (
            "⚠️ *Isso parece uma emergência médica.*\n\n"
            f"🚑 *Ligue agora para o {samu['name']}: {samu['phone']}*\n\n"
            "Enquanto isso:\n"
            "• Mantenha a pessoa deitada e confortável\n"
            "• Não dê água ou comida\n"
            "• Observe respiração e consciência\n\n"
            "Vou avisar nossa equipe pra te dar suporte agora."
        )

    # ────────────────────────────────────────────────────────────────
    # Utilities
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_results(a: SafetyResult, b: SafetyResult | None) -> SafetyResult:
        if b is None:
            return a
        severities = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}
        winner = a if severities[a.severity] >= severities[b.severity] else b
        # Mescla triggers
        for t in b.triggers:
            if t not in winner.triggers:
                winner.triggers.append(t)
        winner.raw_scores = {**a.raw_scores, **b.raw_scores}
        return winner

    # ────────────────────────────────────────────────────────────────
    # Persist event
    # ────────────────────────────────────────────────────────────────

    def _log_event(
        self,
        tenant_id: str,
        phone: str | None,
        session_id: str | None,
        user_message: str,
        result: SafetyResult,
    ) -> str | None:
        if result.is_safe and not result.triggers:
            return None

        try:
            primary_trigger = result.triggers[0] if result.triggers else "unknown_high_risk"
            actions = []
            if result.recommended_action in ("escalate_human_immediate", "escalate_human"):
                actions.append("atente_notify_queued")
            if result.recommended_action == "block":
                actions.append("blocked")
            if result.recommended_action == "maintain_persona":
                actions.append("persona_maintained")

            row = self.db.insert_returning(
                """
                INSERT INTO aia_health_safety_events
                    (tenant_id, subject_phone, session_id,
                     trigger_type, severity,
                     user_message_preview, moderation_score, detection_source,
                     actions_taken, bot_response_sent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tenant_id, phone, session_id,
                    primary_trigger, result.severity,
                    user_message[:500], self.db.json_adapt(result.raw_scores),
                    result.detection_source,
                    actions, result.bot_response_override,
                ),
            )
            event_id = str(row["id"]) if row else None

            logger.info(
                "safety_event_logged",
                event_id=event_id,
                trigger=primary_trigger,
                severity=result.severity,
                phone_prefix=(phone[:4] if phone else None),
                action=result.recommended_action,
            )
            return event_id
        except Exception as exc:
            # Mesmo se log falhar, não dá rollback no fluxo
            logger.error("safety_event_log_failed", error=str(exc))
            return None


_instance: SafetyModerationService | None = None


def get_safety_moderation_service() -> SafetyModerationService:
    global _instance
    if _instance is None:
        _instance = SafetyModerationService()
    return _instance
