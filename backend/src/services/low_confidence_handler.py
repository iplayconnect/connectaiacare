"""Low-Confidence Handler — protocolo de 3 degraus anti-invenção.

Gap identificado em revisão do ADR-027 (§8.6): em saúde, "não sei" é
infinitamente melhor que resposta errada com confiança. Sofia precisa
ter humildade epistêmica.

Protocolo 3 degraus:

    Degrau 1 — confiança < 0.5 na interpretação
        → Sofia pede esclarecimento ("Deixa eu confirmar se entendi: ...")
        → Se paraphrase razoável, espera correção
        → Se não, vai pro Degrau 2

    Degrau 2 — segunda tentativa falha OU confiança < 0.3
        → Sofia admite limite + oferece reformulação ou áudio
        → "Não peguei direito. Pode tentar de outro jeito?"
        → Se ainda falha, vai pro Degrau 3

    Degrau 3 — terceira falha OU fora do escopo
        → Escalação pra Atente (humano)
        → Cria safety_event com trigger='low_confidence_handoff'

Categorias onde Sofia NUNCA inventa (direto pro Degrau 3):
    - Diagnóstico médico
    - Prescrição / dose
    - Interação medicamentosa fora do PrescriptionValidator
    - Diagnóstico diferencial de sintoma novo
    - Resposta jurídica específica de caso concreto
    - Valores financeiros não-catalogados

Uso:

    lc = get_low_confidence_handler()
    if lc.should_decline(user_text, llm_confidence=0.2):
        response = lc.build_response(phone, degree=...)
        lc.track_attempt(phone, session_id, ...)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Thresholds
# ══════════════════════════════════════════════════════════════════

CONFIDENCE_THRESHOLD_DEGREE_1 = 0.5   # abaixo disso, pede confirmação
CONFIDENCE_THRESHOLD_DEGREE_2 = 0.3   # abaixo disso, admite falha + convida áudio
MAX_ATTEMPTS_BEFORE_HANDOFF = 3       # após 3 tentativas, escala humano

# Regex de categorias "nunca inventar" — match, escala imediato pro Degrau 3
NEVER_INVENT_PATTERNS = [
    # Diagnóstico médico
    (r"\b(isso [ée]|tenho|ela tem)\s+(c[âa]ncer|tumor|avc|derrame|infarto|diabetes|alzheimer|parkinson)\b", "diagnosis"),
    (r"\b(o que\s+(ele|ela|eu)\s+tem\??|qual\s+o?\s+diagn[óo]stico)\b", "diagnosis"),
    # Dose / prescrição
    (r"\bquant[oa]s?\s+(miligramas?|mg|comprimidos?)\s+(de|posso|devo|pode)\b", "dosage"),
    (r"\bposso\s+(aumentar|dobrar|tomar)\s+(a\s+)?(dose|rem[ée]dio)\b", "dosage"),
    (r"\b(aumentar|diminuir|dobrar|reduzir|trocar)\s+(a\s+)?dose\b", "dosage"),
    (r"\bposso\s+tomar\s+\d+\s+(comprimidos?|mg|miligramas?)\b", "dosage"),
    (r"\b(prescreve?|prescri[cç][ãa]o)\s+(pra|para)\s+(mim|mim mesmo|ele|ela)\b", "prescription"),
    # Diagnóstico diferencial
    (r"\bo que\s+(pode\s+)?(ser|estar)\b.{0,30}\b(dor|inchad|febre|toss|cans|confus)", "differential"),
    # Jurídico específico
    (r"\b(posso\s+)?process(ar|o)\b", "legal_specific"),
    (r"\btenho\s+direito\s+a\b", "legal_specific"),
    # Interação medicamentosa fora do catálogo
    (r"\bposso\s+(tomar|misturar|combinar)\s+\w+\s+(com|e)\s+\w+", "drug_interaction"),
]

_NEVER_INVENT_RE = [(re.compile(p, flags=re.IGNORECASE), cat) for p, cat in NEVER_INVENT_PATTERNS]


# ══════════════════════════════════════════════════════════════════
# Result
# ══════════════════════════════════════════════════════════════════

@dataclass
class LowConfidenceDecision:
    should_handle: bool = False
    degree: int = 0                  # 0=pass, 1=clarify, 2=admit, 3=handoff
    category: str = "generic"        # diagnosis | dosage | differential | generic
    response: str | None = None      # resposta pré-formatada
    escalate_to_human: bool = False


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class LowConfidenceHandler:
    def __init__(self):
        self.db = get_postgres()

    # ───────────────────────────────────────────────────────────────
    # Decisão
    # ───────────────────────────────────────────────────────────────

    def evaluate(
        self,
        text: str,
        *,
        phone: str,
        session_id: str | None = None,
        llm_confidence: float | None = None,
        prior_attempts: int = 0,
        paraphrase: str | None = None,
    ) -> LowConfidenceDecision:
        """Decide se Sofia deve pedir esclarecimento, admitir ou escalar.

        Args:
            text: texto do usuário
            phone: número (usado pra track)
            session_id: sessão atual
            llm_confidence: 0..1 de quão confiante o LLM está
            prior_attempts: quantas tentativas seguidas já falharam
            paraphrase: interpretação da Sofia pra pedir confirmação
        """
        # 1. Categoria "nunca inventar" → escalação direta
        category = self._detect_never_invent(text)
        if category:
            self._track_handoff(
                phone=phone, session_id=session_id,
                category=category, attempts=prior_attempts + 1,
                reason="never_invent_category",
            )
            return LowConfidenceDecision(
                should_handle=True,
                degree=3,
                category=category,
                response=self._build_handoff_response(category),
                escalate_to_human=True,
            )

        # 2. Limite de tentativas → escalação
        if prior_attempts >= MAX_ATTEMPTS_BEFORE_HANDOFF - 1:
            self._track_handoff(
                phone=phone, session_id=session_id,
                category="generic", attempts=prior_attempts + 1,
                reason="max_attempts",
            )
            return LowConfidenceDecision(
                should_handle=True,
                degree=3,
                response=self._build_handoff_response("generic"),
                escalate_to_human=True,
            )

        # 3. Confiança muito baixa → Degrau 2 (admite + oferece áudio)
        if llm_confidence is not None and llm_confidence < CONFIDENCE_THRESHOLD_DEGREE_2:
            return LowConfidenceDecision(
                should_handle=True,
                degree=2,
                response=self._build_degree2_response(),
            )

        # 4. Confiança média-baixa → Degrau 1 (pede confirmação via paraphrase)
        if llm_confidence is not None and llm_confidence < CONFIDENCE_THRESHOLD_DEGREE_1:
            return LowConfidenceDecision(
                should_handle=True,
                degree=1,
                response=self._build_degree1_response(paraphrase),
            )

        # 5. OK — confiança suficiente
        return LowConfidenceDecision(should_handle=False)

    # ───────────────────────────────────────────────────────────────
    # Detectores
    # ───────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_never_invent(text: str) -> str | None:
        if not text:
            return None
        for regex, category in _NEVER_INVENT_RE:
            if regex.search(text):
                return category
        return None

    # ───────────────────────────────────────────────────────────────
    # Respostas
    # ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_degree1_response(paraphrase: str | None) -> str:
        if paraphrase:
            return (
                f"Deixa eu confirmar se entendi: você tá falando sobre "
                f"*{paraphrase}*? É isso?"
            )
        return (
            "Não tenho certeza se entendi direito. Pode me contar com "
            "outras palavras pra eu conseguir te ajudar melhor?"
        )

    @staticmethod
    def _build_degree2_response() -> str:
        return (
            "Não peguei direito, me desculpa 💙\n\n"
            "Pode tentar de outro jeito? Se for mais fácil, pode mandar "
            "áudio — às vezes falando fica mais simples que digitar."
        )

    @staticmethod
    def _build_handoff_response(category: str) -> str:
        category_msgs = {
            "diagnosis": (
                "Essa é uma pergunta que só um médico pode responder com "
                "segurança 💙. Vou chamar alguém da nossa equipe pra te "
                "orientar o melhor caminho."
            ),
            "dosage": (
                "Dose de remédio é coisa séria — não posso arriscar uma "
                "resposta errada. Vou chamar nossa equipe clínica agora."
            ),
            "prescription": (
                "Prescrição de medicamento é decisão médica. Vou conectar "
                "você com a nossa equipe pra encaminhar do jeito certo."
            ),
            "differential": (
                "Pra entender o que pode estar acontecendo, preciso que um "
                "médico avalie. Vou chamar nossa equipe pra te orientar."
            ),
            "drug_interaction": (
                "Mistura de remédios precisa ser confirmada pelo médico ou "
                "farmacêutico. Vou chamar alguém do time pra te ajudar."
            ),
            "legal_specific": (
                "Essa é uma pergunta jurídica específica — prefiro chamar "
                "alguém do time que possa te orientar direito."
            ),
            "generic": (
                "Vou pedir pra uma pessoa da nossa equipe te atender — ela "
                "vai entender melhor que eu. Em alguns minutos alguém "
                "aqui responde 🤝"
            ),
        }
        return category_msgs.get(category, category_msgs["generic"])

    # ───────────────────────────────────────────────────────────────
    # Tracking
    # ───────────────────────────────────────────────────────────────

    def _track_handoff(
        self,
        *,
        phone: str,
        session_id: str | None,
        category: str,
        attempts: int,
        reason: str,
        tenant_id: str = "sofiacuida_b2c",
    ) -> None:
        """Grava handoff em aia_health_safety_events (severity='info')."""
        try:
            self.db.execute(
                """
                INSERT INTO aia_health_safety_events
                    (tenant_id, subject_phone, session_id,
                     trigger_type, severity, detection_source,
                     user_message_preview, actions_taken,
                     moderation_score, attempts_count)
                VALUES (%s, %s, %s,
                        'unknown_high_risk', 'info', 'low_confidence_handler',
                        %s, ARRAY['human_handoff_requested']::TEXT[],
                        %s, %s)
                """,
                (
                    tenant_id, phone, session_id,
                    f"[category={category}] reason={reason}",
                    self.db.json_adapt({"category": category, "reason": reason}),
                    attempts,
                ),
            )
            logger.info(
                "low_confidence_handoff",
                phone=phone, category=category, attempts=attempts, reason=reason,
            )
        except Exception as exc:
            logger.warning("low_confidence_track_failed", error=str(exc))


# Singleton
_instance: LowConfidenceHandler | None = None


def get_low_confidence_handler() -> LowConfidenceHandler:
    global _instance
    if _instance is None:
        _instance = LowConfidenceHandler()
    return _instance
