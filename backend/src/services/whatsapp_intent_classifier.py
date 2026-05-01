"""WhatsApp intent classifier — primeira mensagem de phone anônimo.

5 buckets de saída:

    interesse_servico_b2c — idoso ou família querendo conhecer plano
                            (ex: "quero saber sobre o cuidado da
                            minha mãe", "como funciona pra idoso?")

    interesse_servico_b2b — gestor de ILPI / clínica / hospital /
                            healthtech / parceiro comercial
                            (ex: "sou diretor de uma ILPI...",
                            "quero conhecer pra meu hospital")

    agendar_demo          — pedido explícito de demo/reunião/
                            apresentação
                            (ex: "podemos agendar uma demo?",
                            "quero ver uma apresentação")

    suporte_cliente       — quem já é cliente cadastrado MAS não foi
                            resolvido pelo IdentityResolver (phone
                            errado, conta nova, etc.)
                            (ex: "minha conta não tá funcionando",
                            "esqueci minha senha")

    spam_abuso            — propaganda, links suspeitos, mensagem
                            ofensiva, automação cruzada
                            (ex: "ganhe R$10k em 24h!", links de
                            phishing, etc.)

    unclear               — não conseguiu classificar com confiança
                            >0.6 → Super Sofia faz pergunta
                            clarificadora aberta

DeepSeek V4-Flash. ~$0.001/call. Latência <2s p95.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from src.services.llm_router import get_llm_router
from src.services.llm_cost_tracker import get_llm_cost_tracker
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────

INTENT_BUCKETS = {
    "interesse_servico_b2c",
    "interesse_servico_b2b",
    "agendar_demo",
    "suporte_cliente",
    "spam_abuso",
    "unclear",
}

CONFIDENCE_THRESHOLD = 0.60


# ──────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────


@dataclass
class IntentResult:
    intent: str
    confidence: float
    reasoning: str
    duration_ms: int
    raw: dict

    @property
    def is_uncertain(self) -> bool:
        return self.confidence < CONFIDENCE_THRESHOLD or self.intent == "unclear"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "duration_ms": self.duration_ms,
            "is_uncertain": self.is_uncertain,
        }


# ──────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um classificador de intenção pra Sofia, IA da plataforma ConnectaIACare (cuidados de idosos com IA + atendimento humano 24/7).

TAREFA: classificar a primeira mensagem de uma pessoa que escreveu no WhatsApp e cujo número NÃO está cadastrado na plataforma.

CATEGORIAS (escolha EXATAMENTE UMA):

1. **interesse_servico_b2c** — pessoa física querendo conhecer/contratar pra ELA mesma OU pra um familiar idoso. Sinais:
   - "quero saber pra minha mãe / meu pai / meu avô"
   - "quanto custa pra cuidar de um idoso"
   - "como funciona pra idoso solo"
   - linguagem coloquial pessoal

2. **interesse_servico_b2b** — gestor de organização (ILPI, clínica, hospital, plano de saúde, healthtech, partner). Sinais:
   - "sou diretor / gerente / dono de [empresa]"
   - "queremos implantar pra nossa ILPI / hospital"
   - "vocês fazem white-label?"
   - linguagem corporativa

3. **agendar_demo** — pedido explícito de demonstração / reunião / apresentação. Sinais:
   - "podemos agendar uma demo?"
   - "quero ver uma apresentação"
   - "marcar uma call"
   - "quando vocês podem mostrar?"

4. **suporte_cliente** — alguém que CLARAMENTE já usa a plataforma mas o número não foi reconhecido (conta nova, phone trocado, problema técnico). Sinais:
   - "minha conta não funciona"
   - "esqueci minha senha"
   - "não consigo entrar"
   - "o app travou"
   - mencionar features específicas da plataforma (Sofia, alertas, etc.)

5. **spam_abuso** — propaganda comercial não-relacionada, links suspeitos, ofensa, mensagem automatizada. Sinais:
   - "ganhe X em Y dias"
   - links de phishing / bit.ly suspeitos
   - palavrão / ofensa direta
   - mensagem 100% genérica de marketing massa

6. **unclear** — não tem sinal forte o suficiente pra classificar com confiança ≥0.6. PREFIRA esta opção a um chute errado. Sofia vai fazer pergunta clarificadora.

SAÍDA: JSON estrito. Apenas estes campos:
{
  "intent": "<uma das 6 categorias>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1 frase explicando a escolha>"
}

CONFIDENCE:
- 1.0 = sinal inequívoco (ex: "sou diretor da ILPI XYZ, queremos conhecer")
- 0.8 = bem provável (ex: "como funciona pra meu pai?")
- 0.6 = limítrofe mas razoável
- <0.6 = escolha "unclear" e seja honesto

IMPORTANTE: NUNCA invente intent quando ambíguo. "Oi" sozinho = unclear, NÃO interesse_servico_b2c."""


# ──────────────────────────────────────────────────────────────────
# Classifier
# ──────────────────────────────────────────────────────────────────


class WhatsAppIntentClassifier:
    def __init__(self) -> None:
        self.router = get_llm_router()
        self.cost_tracker = get_llm_cost_tracker()

    def classify(
        self,
        message: str,
        *,
        tenant_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> IntentResult:
        """Classifica mensagem em 1 dos 6 buckets. Retorna IntentResult.

        Em caso de falha total (LLM router raise), retorna unclear
        com confidence 0.0 — Super Sofia decide a partir daí.
        """
        if not message or not message.strip():
            return IntentResult(
                intent="unclear",
                confidence=0.0,
                reasoning="empty message",
                duration_ms=0,
                raw={"_skipped": "empty"},
            )

        started = time.perf_counter()
        try:
            result = self.router.complete_json(
                task="whatsapp_intent_classifier",
                system=SYSTEM_PROMPT,
                user=f"Mensagem do usuário no WhatsApp:\n\n{message[:2000]}",
            )
        except Exception as exc:
            logger.exception(
                "whatsapp_intent_classifier_failed",
                trace_id=trace_id, error=str(exc)[:200],
            )
            return IntentResult(
                intent="unclear",
                confidence=0.0,
                reasoning=f"llm_router_failed: {str(exc)[:120]}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                raw={"_error": str(exc)[:300]},
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        intent = (result.get("intent") or "unclear").lower().strip()
        if intent not in INTENT_BUCKETS:
            logger.warning(
                "whatsapp_intent_invalid_bucket",
                got=intent, trace_id=trace_id,
            )
            intent = "unclear"

        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reasoning = str(result.get("reasoning", ""))[:500]

        # Cost tracking
        provider = result.get("_provider")
        model = result.get("_model_used", "").split("/", 1)[-1]
        # Note: complete_json não retorna tokens — pricing aproximada
        # via len. Atualizar quando router expor usage.
        approx_input_tokens = len(message) // 3 + len(SYSTEM_PROMPT) // 3
        approx_output_tokens = len(reasoning) // 3 + 20
        if provider and model:
            try:
                self.cost_tracker.record(
                    provider=provider,
                    model=model,
                    task="whatsapp_intent_classifier",
                    prompt_tokens=approx_input_tokens,
                    completion_tokens=approx_output_tokens,
                    duration_ms=duration_ms,
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    session_id=session_id,
                )
            except Exception as exc:
                logger.warning("cost_track_failed", error=str(exc))

        return IntentResult(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            duration_ms=duration_ms,
            raw=result,
        )


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_instance: Optional[WhatsAppIntentClassifier] = None


def get_whatsapp_intent_classifier() -> WhatsAppIntentClassifier:
    global _instance
    if _instance is None:
        _instance = WhatsAppIntentClassifier()
    return _instance
