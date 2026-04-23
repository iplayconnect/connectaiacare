"""Correction Handler — detecta intenção de correção/cancelamento/retorno.

Sofia precisa parecer humana: o usuário deve poder dizer "espera, não"
ou "deixa eu corrigir" ou "na verdade é outro nome" e ela entender
que ele quer refazer a última informação passada.

Três intents detectados aqui (sem LLM — matching lexical, zero custo):

    - RETRY_LAST: "espera, não", "errei", "me enganei", "deixa eu corrigir"
       → Reverter último campo coletado / reabrir última pergunta
    - GO_BACK: "voltar", "anterior", "passo anterior"
       → Ir pro estado anterior (diferença sutil: GO_BACK é navegação,
         RETRY_LAST é correção do conteúdo)
    - CANCEL: "cancelar", "parar", "desistir", "esquece"
       → Abortar sessão / retornar à saudação
    - HUMAN: "humano", "atendente", "falar com pessoa"
       → Escalar para Atente

O pipeline/onboarding consulta primeiro com detect() e só se retornar None
segue processamento normal do estado.

Design deliberado:
    - Matching por frases em pt-BR comuns (ConnectaIA prompt style)
    - Tolerante a typos simples ("nao" == "não")
    - Palavras-chave isoladas NÃO disparam (precisam estar em contexto)
      — ex: "não quero esse plano" não dispara CANCEL, só "cancelar"
"""
from __future__ import annotations

import re
from enum import Enum


class CorrectionIntent(str, Enum):
    RETRY_LAST = "retry_last"
    GO_BACK = "go_back"
    CANCEL = "cancel"
    HUMAN = "human"


# ══════════════════════════════════════════════════════════════════
# Padrões
# ══════════════════════════════════════════════════════════════════

# Correção do conteúdo recém-informado (mais comum)
RETRY_PATTERNS = [
    r"\bespera,?\s*n[aã]o\b",
    r"\bpera[i]?,?\s*n[aã]o\b",
    r"\bhum,?\s*errei\b",
    r"\berrei\b",
    r"\bme enganei\b",
    r"\bequivoquei\b",
    r"\bdeixa eu (corrigir|refazer|trocar|mudar)\b",
    r"\bna verdade\s+(e|é|eh|s[aã]o)\b",
    r"\bquero corrigir\b",
    r"\bt[oô] errado\b",
    r"\besse n[aã]o [eé]\b",
    r"\bdigitei errado\b",
    r"\bmandei errado\b",
    r"\btroca (a|o)\b",
]

# Navegação: voltar ao estado anterior
GO_BACK_PATTERNS = [
    r"\bvoltar\b",
    r"\bvolta\b",
    r"\bpasso anterior\b",
    r"\betapa anterior\b",
    r"\banterior\b",
]

# Abortar sessão
CANCEL_PATTERNS = [
    r"\bcancelar\b",
    r"\bdesistir\b",
    r"\besquece\b",
    r"\bparar\b",
    r"\bdeixa pra l[aá]\b",
    r"\bn[aã]o quero mais\b",
    r"\bdesisto\b",
]

# Escalar pra humano
HUMAN_PATTERNS = [
    r"\bhumano\b",
    r"\batendente\b",
    r"\bfalar com (algu[eé]m|pessoa|ger[eê]nte)\b",
    r"\bquero uma pessoa\b",
    r"\bn[aã]o s[oô] rob[oô]\b",
    r"\bconsultor\b",
]


# Compila para performance (chamado por msg)
_RETRY_RE = re.compile("|".join(RETRY_PATTERNS), flags=re.IGNORECASE)
_GO_BACK_RE = re.compile("|".join(GO_BACK_PATTERNS), flags=re.IGNORECASE)
_CANCEL_RE = re.compile("|".join(CANCEL_PATTERNS), flags=re.IGNORECASE)
_HUMAN_RE = re.compile("|".join(HUMAN_PATTERNS), flags=re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════

def detect(text: str) -> CorrectionIntent | None:
    """Detecta intent de correção em texto livre.

    Returns:
        CorrectionIntent ou None se texto não é uma correção.

    Ordem de prioridade:
        1. HUMAN (escalação imediata, nunca ambíguo)
        2. CANCEL (abortar > retry)
        3. RETRY_LAST (correção > voltar)
        4. GO_BACK
    """
    if not text:
        return None
    t = text.strip()
    # Se msg é muito longa, provavelmente contém info real, não só correção
    if len(t) > 120:
        return None

    if _HUMAN_RE.search(t):
        return CorrectionIntent.HUMAN
    if _CANCEL_RE.search(t):
        return CorrectionIntent.CANCEL
    if _RETRY_RE.search(t):
        return CorrectionIntent.RETRY_LAST
    if _GO_BACK_RE.search(t):
        return CorrectionIntent.GO_BACK
    return None


def friendly_response(intent: CorrectionIntent) -> str:
    """Resposta padrão humanizada para cada intent (reutilizada por onboarding)."""
    if intent == CorrectionIntent.HUMAN:
        return (
            "Claro! Vou avisar uma pessoa do nosso time pra te atender. "
            "Enquanto isso, pode ir me contando o que precisa — assim agilizo. 🤝"
        )
    if intent == CorrectionIntent.CANCEL:
        return (
            "Tudo bem 💙 Encerrei essa conversa aqui. "
            "Quando quiser voltar, é só me mandar um *oi*."
        )
    if intent == CorrectionIntent.RETRY_LAST:
        return "Sem problema, me manda de novo do jeito certo que eu atualizo aqui."
    if intent == CorrectionIntent.GO_BACK:
        return "Ok, voltei um passo. Vamos refazer."
    return ""
