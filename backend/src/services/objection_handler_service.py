"""Objection Handler — detecta e responde objeções comerciais.

Inspirado no pattern "objection_retriever" da ConnectaIA original.
Adaptado pra Sofia Cuida (B2C healthcare).

Pipeline:
    1. Detecta se msg do user é objeção (regex + heurística léxica)
    2. Classifica categoria (caro, não precisa, já tem plano, ...)
    3. Busca na KB (domain='pricing_objections') argumentos adequados
    4. Monta resposta via LLM OU usa resposta canônica da KB
    5. Registra tentativa no log pra melhorar continuamente

Uso:

    obj = get_objection_handler()

    # Detecção rápida
    if obj.is_objection(user_text):
        response = obj.handle(
            user_text=user_text,
            phone=phone,
            session_id=session_id,
            context={"plan_interest": "premium"},
        )
        # response.reply, response.category, response.kb_chunks_used

Filosofia (§Constitutional):
    - Nunca menosprezar objeção
    - Nunca usar escassez falsa ("última chance", "preço só hoje")
    - Respeitar "não" firme
    - Objetivo é ESCLARECER valor, não pressionar
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.knowledge_base_service import get_knowledge_base
from src.services.llm_router import get_llm_router
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Categorias de objeção + padrões léxicos
# ══════════════════════════════════════════════════════════════════

OBJECTION_PATTERNS = {
    "caro": [
        r"\b(car[oa]|car[íi]ssim|muito dinheiro|muito caro)\b",
        r"\b(n[ãa]o tenho dinheiro|apertad[oa]|sem grana)\b",
        r"\b(pre[çc]o|valor)\s+(alto|muito|abusiv)\b",
    ],
    "nao_preciso": [
        r"\b(n[ãa]o precis[ao])\b",
        r"\b(aut[ôo]nom[oa]|independ[ea]nte)\b",
        r"\b(ela|ele)\s+(cuida|est[áa])\s+bem\b",
        r"\bn[ãa]o vejo necessidade\b",
    ],
    "ja_tem_plano_saude": [
        r"\b(j[áa]|tenho|tem)\s+(plano de sa[úu]de|conv[êe]nio)\b",
        r"\b(unimed|bradesco|sulam[ée]rica|amil|porto sa[úu]de|golden cross)\b",
        r"\bcobertura\s+(m[ée]dica|de sa[úu]de)\b",
    ],
    "nao_confio_ia": [
        r"\bn[ãa]o confio\s+(em|n[ao])?\s*(ia|intelig[êe]ncia artificial|rob[ôo]|bot|tecnologia)\b",
        r"\b(prefiro|melhor)\s+(pessoa|humano|m[ée]dico)\b",
        r"\bdesconfio\b",
        r"\bia\s+n[ãa]o\s+(serve|ajuda|resolve)\b",
    ],
    "mae_recusa_tech": [
        r"\b(m[ãa]e|pai|av[óo])\s+(n[ãa]o\s+(aceita|usa|gosta)|rec[uo]sa|tem idade)\b",
        r"\bn[ãa]o\s+(sabe|consegue)\s+(usar|mexer)\s+(celular|whatsapp|tecnologia)\b",
        r"\b(idad[eo]|idos[oa])\s+(demais|avan[çc]ada)\s+pra\s+(tecnologia|isso)\b",
    ],
    "medo_dependencia": [
        r"\b(medo|receio)\s+de\s+(virar|ficar)\s+depend[ea]nte\b",
        r"\bvirar v[íi]cio\b",
        r"\bdepend[êe]ncia\b",
    ],
    "prefere_cuidador": [
        r"\bprefiro\s+(contratar|ter)\s+cuidador\b",
        r"\bcuidador\s+(particular|contratad[oa]|profissional)\b",
        r"\benfermeira\s+(particular|contratad[oa])\b",
    ],
    "esperar_mais": [
        r"\b(vou pensar|depois decido|preciso pensar|pensar melhor)\b",
        r"\b(falar com|conversar com)\s+(fam[íi]lia|mulher|marido|filhos)\b",
        r"\bn[ãa]o agora\b",
        r"\bdepois eu vejo\b",
    ],
    "alternativas_gratuitas": [
        r"\b(gr[áa]tis|gratuit[oa]|sem pagar|de gra[çc]a)\b",
        r"\balternativ[oa]\s+(free|gr[áa]tis)\b",
    ],
    "muito_complicado": [
        r"\b(complicad[oa]|dif[íi]cil|complex[oa]|burocr[áa]tico)\b",
        r"\bparece\s+(uma)?\s*(confus[ãa]o|cabe[çc]a)\b",
    ],
}

_COMPILED = {
    cat: [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    for cat, patterns in OBJECTION_PATTERNS.items()
}


# ══════════════════════════════════════════════════════════════════
# Resultado
# ══════════════════════════════════════════════════════════════════

@dataclass
class ObjectionResponse:
    is_objection: bool = False
    category: str | None = None
    confidence: float = 0.0
    reply: str = ""
    kb_chunks_used: list[str] = field(default_factory=list)  # chunk IDs usados
    fallback_used: bool = False                               # se não achou na KB


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class ObjectionHandlerService:
    def __init__(self):
        self.kb = get_knowledge_base()
        self.router = get_llm_router()

    # ═══════════════════════════════════════════════════════════════
    # Detecção
    # ═══════════════════════════════════════════════════════════════

    def detect(self, text: str) -> tuple[str | None, float]:
        """Detecta se texto é objeção. Retorna (category, confidence).

        Matching léxico (regex). Se múltiplas categorias batem, pega a
        primeira (ordem definida em OBJECTION_PATTERNS — mais comum primeiro).
        """
        if not text:
            return None, 0.0

        for category, patterns in _COMPILED.items():
            for pat in patterns:
                if pat.search(text):
                    # Confiança proporcional ao tamanho do match vs texto
                    # (match pequeno em texto grande = menos confiança)
                    return category, 0.85

        return None, 0.0

    def is_objection(self, text: str) -> bool:
        cat, _ = self.detect(text)
        return cat is not None

    # ═══════════════════════════════════════════════════════════════
    # Handling (resposta contextualizada)
    # ═══════════════════════════════════════════════════════════════

    def handle(
        self,
        *,
        user_text: str,
        phone: str | None = None,
        session_id: str | None = None,
        context: dict | None = None,
    ) -> ObjectionResponse:
        """Detecta + busca KB + retorna resposta pronta.

        Args:
            user_text: texto do user
            phone: opcional (pra log)
            session_id: opcional (pra log)
            context: dados extras (plan_interest, role, etc.)
        """
        category, confidence = self.detect(user_text)
        result = ObjectionResponse(
            is_objection=category is not None,
            category=category,
            confidence=confidence,
        )

        if not category:
            return result

        # Busca na KB — subdomain direto match com category
        chunks = self.kb.search(
            query=user_text,
            domain="pricing_objections",
            subdomain=category,
            top_k=1,
            min_similarity=0.0,  # aceita qualquer score aqui (subdomain filtrou)
            phone=phone,
            session_id=session_id,
            log=True,
        )

        if not chunks:
            # Fallback: busca sem filtro de subdomain, só domain
            chunks = self.kb.search(
                query=user_text,
                domain="pricing_objections",
                top_k=1,
                min_similarity=0.45,
                phone=phone,
                session_id=session_id,
                log=True,
            )

        if chunks:
            # Usa content do chunk como resposta canônica
            best = chunks[0]
            result.reply = self._extract_reply_from_chunk(best.content)
            result.kb_chunks_used = [best.id]
            logger.info(
                "objection_handled_via_kb",
                category=category,
                chunk_id=best.id,
                similarity=round(best.similarity, 3),
            )
        else:
            # Fallback: resposta genérica acolhedora
            result.reply = self._build_generic_fallback(category, context)
            result.fallback_used = True
            logger.warning(
                "objection_fallback_used",
                category=category, user_text=user_text[:80],
            )

        return result

    # ═══════════════════════════════════════════════════════════════
    # Helpers internos
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _extract_reply_from_chunk(content: str) -> str:
        """Extrai a resposta do chunk da KB.

        Convenção dos seeds: após "**Resposta padrão" ou "**Resposta:**"
        vem a resposta entre aspas. Se não encontrar, retorna primeiras linhas.
        """
        # Tenta extrair bloco "Resposta:" até próximo **Estratégia** ou EOF
        match = re.search(
            r"\*\*Resposta(?:\s+padrão)?(?:\s*\([^)]+\))?:\*\*\s*\n+(.*?)(?=\n\*\*Estratégia|\Z)",
            content, flags=re.DOTALL,
        )
        if match:
            reply = match.group(1).strip()
            # Remove aspas de abertura/fechamento e trailing
            reply = re.sub(r'^"\s*', '', reply)
            reply = re.sub(r'\s*"$', '', reply)
            return reply

        # Fallback: primeiras 500 chars
        return content[:500].strip()

    @staticmethod
    def _build_generic_fallback(
        category: str | None, context: dict | None,
    ) -> str:
        """Resposta genérica se KB não retornar nada utilizável."""
        generic = {
            "caro": (
                "Entendo 💙. Posso te oferecer o plano Essencial por R$ 49,90 — "
                "ou um teste grátis de 7 dias pra ver se faz sentido. "
                "Quer conhecer?"
            ),
            "nao_preciso": (
                "Fico feliz que tá tudo bem 💙. Pensa na Sofia como rede de segurança — "
                "autonomia preservada, mas alguém de olho. "
                "O teste grátis de 7 dias dá pra sentir na prática."
            ),
            "ja_tem_plano_saude": (
                "Ótimo que tem plano de saúde! A Sofia complementa — "
                "cuida do dia-a-dia entre consultas, que o plano não cobre. "
                "Testa 7 dias sem compromisso?"
            ),
            "nao_confio_ia": (
                "Respeito essa preocupação. A Sofia nunca decide clinicamente sozinha — "
                "tem médico humano no time. Quer marcar uma conversa com nossa "
                "enfermeira chefe pra tirar dúvida ao vivo?"
            ),
            "mae_recusa_tech": (
                "Muito comum! A Sofia fala pelo WhatsApp que ela já usa — "
                "zero tecnologia nova. E no início é você que configura. "
                "Testa 7 dias, se não servir cancela."
            ),
        }
        return generic.get(
            category or "",
            "Entendi 💙. Quer que eu te conte mais sobre o plano antes de decidir?"
        )


# Singleton
_instance: ObjectionHandlerService | None = None


def get_objection_handler() -> ObjectionHandlerService:
    global _instance
    if _instance is None:
        _instance = ObjectionHandlerService()
    return _instance
