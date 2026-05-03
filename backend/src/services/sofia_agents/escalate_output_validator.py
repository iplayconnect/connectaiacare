"""Output validator: pega Sofia "mentindo" sobre escalate.

Bug raiz observado em prod 2026-05-03: LLM (commercial agent) recebe
"quero falar com humano agora, é uma emergência" e decide `action="text"`
com texto narrativo ("Vou avisar uma pessoa do nosso time pra te atender")
em vez de `action="tool"` chamando `escalate_to_human_whatsapp`.

Resultado pro lead: vê uma resposta acolhedora MAS handoff_queue continua
vazio — operador humano nunca é acionado. Comportamento típico de "lying"
de LLM (promete fazer ação X enquanto retorna apenas texto que descreve X).

Por que NÃO usamos heurística de keywords no INPUT:
  - "ambulância" pode aparecer em conversa não-emergência ("vi uma
     ambulância passando")
  - "gerente" pode ser pedido legítimo de qualificação comercial
  - "queda" pode ser metafórica ("queda do mercado")
  - Em escala (1000+ leads/dia) gera falso positivo demais

Por que validamos o OUTPUT:
  - Zero falso positivo: só dispara quando LLM já decidiu escalar
    semanticamente (prometeu) mas esqueceu/falhou em chamar a tool
  - Cobre o bug exato observado
  - Não interfere com qualificação/comercial normal

Padrões detectados são frases de promessa de handoff em pt-BR. Lista
ordenada por especificidade — frases compostas primeiro pra evitar
shadow de keywords genéricas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


# Frases que CARACTERIZAM promessa de escalate sem ambiguidade.
# Match em texto NORMALIZADO (lowercase + sem acentos).
# Compilado uma vez no import (regex eficiente).
_PROMISE_PATTERNS = (
    # Verbos de transferência/notificação clara (1ª pessoa singular)
    r"vou (?:avisar|chamar|acionar|escalar|pedir pra|passar pra|conectar com|transferir pra)",
    r"vou (?:te |)(?:transferir|conectar|passar|encaminhar|escalar)",
    r"estou (?:avisando|chamando|acionando|pedindo|conectando|transferindo|escalando|encaminhando)",
    r"(?:ja |)(?:estou|to|estamos|estao|vamos) (?:avisando|chamando|acionando|pedindo|conectando|escalando|encaminhando)",
    r"acabei de (?:avisar|chamar|acionar|pedir pra|conectar|escalar|transferir|encaminhar)",
    r"to (?:te |)(?:passando|conectando|transferindo|encaminhando|escalando)",
    r"vou (?:te |)(?:colocar|encaminhar|direcionar) (?:em contato|pra)",
    # 1ª plural ("nossa equipe vai", "vamos te atender")
    r"(?:ja |)vamos (?:avisar|chamar|acionar|escalar|transferir|encaminhar|conectar)",

    # "alguém da equipe vai..."
    r"(?:alguem|uma pessoa|nosso time|a equipe|um humano|uma humana|o time) (?:vai|esta|esta indo|esta a caminho|chega) (?:te |)(?:atender|chamar|ligar|entrar em contato|responder|falar)",
    r"(?:vai|esta|estara) (?:a caminho|em contato|te ligando|chegando)",
    r"em (?:instantes|breve|alguns minutos|minutos) (?:alguem|um humano|uma pessoa|o time)",
    r"em (?:instantes|breve) (?:te |)(?:chamamos|atendemos|ligamos|respondemos)",

    # "passar pra equipe humana"
    r"passar pra (?:equipe|nosso time|humano|um humano|nossa central|atendente)",
    r"transferir (?:te |o caso |a conversa |)(?:pra|para) (?:equipe|humano|atendente|central)",

    # Promessa de retorno por outro canal
    r"vamos (?:te |)(?:ligar|chamar|retornar|atender|responder)",
    r"a (?:central|equipe|nossa equipe) (?:vai|ja vai|vai te) (?:ligar|chamar|atender|responder|entrar em contato)",
)

_PROMISE_RE = re.compile("|".join(_PROMISE_PATTERNS), re.IGNORECASE)


@dataclass
class ValidationResult:
    """Resultado da validação semantica.

    Atributos:
        promised_escalate: True se a resposta tem promessa de escalate
        matched_pattern: Snippet do match exato (pra audit/log)
    """
    promised_escalate: bool
    matched_pattern: Optional[str] = None


def _normalize(text: str) -> str:
    """Lowercase + remove acentos pra match resiliente em pt-BR."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower()


def detect_escalate_promise(text: Optional[str]) -> ValidationResult:
    """Detecta se o texto contém promessa de escalate sem chamar tool.

    Chamado APENAS quando agent retornou action="text" (LLM não chamou
    tool). Se detectar promessa, agent deve auto-disparar
    escalate_to_human_whatsapp pra cumprir o que prometeu.

    Returns:
        ValidationResult(promised_escalate=True, matched_pattern=<snippet>)
        OR
        ValidationResult(promised_escalate=False)
    """
    if not text or len(text.strip()) < 5:
        return ValidationResult(promised_escalate=False)

    norm = _normalize(text)
    m = _PROMISE_RE.search(norm)
    if m:
        # Pega contexto local pro log (até 60 chars centrados na match)
        start = max(0, m.start() - 10)
        end = min(len(norm), m.end() + 30)
        snippet = norm[start:end].strip()
        return ValidationResult(
            promised_escalate=True,
            matched_pattern=snippet,
        )
    return ValidationResult(promised_escalate=False)


def build_recovery_summary(
    inbound_text: str,
    response_text: str,
    matched_pattern: str,
    max_chars: int = 600,
) -> str:
    """Resumo pra preencher `summary` da tool quando auto-disparamos.

    Operador humano recebe contexto suficiente pra entender:
      - O que o lead disse
      - O que a Sofia prometeu (e que esta tool foi auto-disparada
        em consequência)
    """
    inbound = (inbound_text or "").strip()[:max_chars // 2]
    response = (response_text or "").strip()[:max_chars // 2]
    return (
        f"[AUTO-RECOVERY] Sofia narrou escalate sem chamar tool — "
        f"validador semântico detectou promessa: '{matched_pattern}'.\n\n"
        f'Lead disse: "{inbound}"\n\n'
        f'Sofia respondeu: "{response}"'
    )
