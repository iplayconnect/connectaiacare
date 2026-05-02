"""DataExtractor PT-BR (vertical care) — extrai dados estruturados de
mensagens livres do user pra preencher CareLeadData.

Estratégia em 2 camadas:

  1. REGEX rápido — pega padrões altíssima confiança (idades, count
     idosos, telefone, email, sim/não). Custo zero, latência <1ms.
     Cobertura típica: ~70% das respostas curtas.

  2. LLM Haiku fallback — quando regex não cobre OU quando msg longa.
     Prompt minimalista, JSON output, 1-2k tokens. Custo ~$0.0002/call.

Acionado pelo orchestrator depois de receber msg do user, ANTES de
gerar resposta. Hint do `pending_question_intent` ajuda extractor a
focar (ex: pending=COUNT_IDOSOS → priorizar regex \\d+).

API:
    extractor = get_data_extractor()
    result = extractor.extract(
        user_text="São dois idosos, 90 e 92 anos",
        pending_intent=QuestionIntent.COUNT_IDOSOS,
        current_lead_data=lead_data,  # pra evitar re-extrair o que já tem
    )
    # result = ExtractionResult(
    #     data={"count_idosos": 2, "idades_idosos": [90, 92]},
    #     confidence=0.95,
    #     method="regex",
    # )
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

from src.services.csm.care_lead_data import CareLeadData
from src.services.csm.flow_state import INTENT_TO_FIELD, QuestionIntent
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0       # 0..1
    method: str = "none"          # "regex" | "llm" | "hybrid" | "none"
    raw_matches: dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Regex extractors (PT-BR)
# ══════════════════════════════════════════════════════════════════

# Telefone: 10-13 dígitos com formatação opcional
PHONE_RE = re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?[\s\-]?)?9?\d{4}[\s\-]?\d{4}")
EMAIL_RE = re.compile(r"\b[\w\.\-]+@[\w\.\-]+\.\w+\b")

# Idades: "90 anos", "tem 92", "92 e 94 anos"
AGE_TOKEN_RE = re.compile(r"\b(\d{2,3})\s*(?:anos?|aninhos?)?\b")

# Count idosos: "dois idosos", "uma mãe", "minha mãe e meu pai" (=2)
NUMBER_WORDS_PT = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
}

# Relação com idoso
RELACAO_PATTERNS = {
    "self": [
        r"\bpra mim\b", r"\bpra eu\b", r"\bsou eu\b", r"\beu mesm[oa]\b",
        r"\bmim mesm[oa]\b", r"\bmeu próprio\b",
    ],
    "filho_a": [
        r"\bminha m[ãa]e\b", r"\bmeu pai\b", r"\bmeus pais\b",
        r"\bfilh[ao] (?:dela|dele|deles)\b", r"\bsou filh[oa]\b",
    ],
    "neto_a": [r"\bminha av[óo]\b", r"\bmeu av[óo]\b", r"\bmeus av[óo]s\b", r"\bsou net[oa]\b"],
    "conjuge": [r"\bmeu marido\b", r"\bminha esposa\b", r"\bmeu c[ôo]njuge\b", r"\bminha companheira\b"],
    "cuidador_pro": [r"\bsou cuidador[a]?\b", r"\benfermeir[ao]\b", r"\bcuidador[a]? profissional\b"],
}

# Dores principais
DOR_PATTERNS: dict[str, list[str]] = {
    "queda": [r"\bquedas?\b", r"\bca[íi]\b", r"\bcaiu\b", r"\bca[íi]ram\b"],
    "esquecimento": [r"\besquece\b", r"\besquecimento\b", r"\bmem[óo]ria\b", r"\bdem[êe]ncia\b", r"\balzheimer\b"],
    "medicacao": [r"\bremedio[s]?\b", r"\brem[ée]dio[s]?\b", r"\bmedica[çc][ãa]o\b", r"\bmedicament[oa]s?\b"],
    "isolamento": [r"\bsozinh[oa]s?\b", r"\bsolid[ãa]o\b", r"\bisolad[oa]\b", r"\bisolament[o]\b"],
    "depressao": [r"\bdepress[ãa]o\b", r"\bdepressiv[oa]\b", r"\btriste\b"],
    "incontinencia": [r"\bincontin[êe]ncia\b", r"\bfralda\b", r"\bbanheiro\b"],
    "mobilidade": [r"\bmobilidade\b", r"\bandador\b", r"\bbengala\b", r"\bcadeira de rodas\b"],
    "diabetes": [r"\bdiabetes\b", r"\bdiab[ée]tic[oa]\b", r"\baçucar\b", r"\bglicemia\b"],
    "hipertensao": [r"\bhipertens[ãa]o\b", r"\bpress[ãa]o (?:alta|arterial)\b"],
    "alimentacao": [r"\balimenta[çc][ãa]o\b", r"\bn[ãa]o (?:come|quer comer)\b"],
}

# Habitação
ILPI_PATTERNS = [r"\bilpi\b", r"\basilo\b", r"\bcasa de repouso\b", r"\binstitui[çc][ãa]o\b"]
SOZINHO_PATTERNS = [r"\bmoram? sozinh[oa]s?\b", r"\bvive[m]? sozinh[oa]s?\b", r"\bsozinh[oa] em casa\b"]


def _norm(text: str) -> str:
    """Lowercase + sem acentos. Para regex que não usa unicode."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _extract_count_idosos(text: str) -> Optional[int]:
    """Detecta quantos idosos. Heurística:
    1. Se "minha mãe E meu pai" / similar → 2
    2. Se "minha mãe" sem irmão → 1
    3. Number word "dois", "duas", "três"
    4. Dígito explícito antes de "idoso"/"pessoa"
    """
    norm = _norm(text)

    # 1. Padrão "X e Y" (mãe E pai). Permite "do meu", "da minha"
    # entre os termos (ex: "minha mãe e do meu pai").
    pair_patterns = [
        r"m[ãa]e\s+e\s+(?:d[oa]\s+)?(?:meu\s+|minha\s+)?pai",
        r"pai\s+e\s+(?:d[oa]\s+)?(?:meu\s+|minha\s+)?m[ãa]e",
        r"av[óo]\s+e\s+(?:d[oa]\s+)?(?:meu\s+|minha\s+)?av[óo]",
        r"av[óo]s\b",
        r"meus\s+pais", r"meus\s+av[óo]s",
        r"sogr[oa]\s+e", r"e\s+sogr[oa]",
        r"tio\s+e\s+tia", r"meus\s+tios",
    ]
    for p in pair_patterns:
        if re.search(p, norm):
            return 2

    # 2. "minha mãe", "meu pai" (singular) — mas só se não casar plural
    singular_relations = [
        r"minha\s+m[ãa]e\b", r"meu\s+pai\b",
        r"minha\s+av[óo]\b", r"meu\s+av[óo]\b",
        r"minha\s+sogra\b", r"meu\s+sogro\b",
        r"\bmeu\s+marido\b", r"\bminha\s+esposa\b",
    ]
    plural_relations = [r"\bmeus\s+pais\b", r"\bmeus\s+av[óo]s\b"]
    if any(re.search(p, norm) for p in plural_relations):
        return 2
    if any(re.search(p, norm) for p in singular_relations):
        return 1

    # 3. Number word seguido de idoso/pessoa/parente
    for word, n in NUMBER_WORDS_PT.items():
        if re.search(rf"\b{word}\s+(idos[oa]s?|pessoa[s]?|parent[ea]s?|familiar[ea]s?)\b", norm):
            return n

    # 4. Dígito + idoso
    m = re.search(r"\b(\d+)\s+(idos[oa]s?|pessoa[s]?|parent[ea]s?)\b", norm)
    if m:
        try:
            n = int(m.group(1))
            if 1 <= n <= 20:
                return n
        except ValueError:
            pass

    return None


def _extract_idades(text: str) -> list[int]:
    """Extrai idades. Foca em 60-110 (universo idoso). Filtra falsos
    positivos (ex: ano '92 vira idade)."""
    raw = AGE_TOKEN_RE.findall(text)
    out: list[int] = []
    for tok in raw:
        try:
            n = int(tok)
        except ValueError:
            continue
        if 60 <= n <= 110:
            if n not in out:
                out.append(n)
    return out


def _extract_dores(text: str) -> list[str]:
    norm = _norm(text)
    found: list[str] = []
    for dor, patterns in DOR_PATTERNS.items():
        for p in patterns:
            if re.search(p, norm):
                if dor not in found:
                    found.append(dor)
                break
    return found


def _extract_relacao(text: str) -> Optional[str]:
    norm = _norm(text)
    for rel, patterns in RELACAO_PATTERNS.items():
        for p in patterns:
            if re.search(p, norm):
                return rel
    return None


def _extract_email(text: str) -> Optional[str]:
    m = EMAIL_RE.search(text)
    return m.group(0).lower() if m else None


def _extract_first_name(text: str, *, pending: Optional[QuestionIntent] = None) -> Optional[str]:
    """Heurística pra primeiro nome. Confiança alta apenas quando
    pending=PRIMEIRO_NOME (resposta direta a "qual seu nome").
    Sem pending, é arriscado — deixa pro LLM."""
    if pending != QuestionIntent.PRIMEIRO_NOME:
        return None
    text = text.strip()
    # Stop-words que NUNCA podem ser nome próprio (mesmo capitalizadas)
    stop = {
        "sou", "meu", "minha", "nome", "chamo", "aqui", "eu", "olá",
        "ola", "oi", "bom", "boa", "tudo", "bem", "obrigado", "obrigada",
    }
    # Padrões "sou X", "meu nome é X", "me chamo X" — IGNORECASE
    # (user pode digitar "Sou" ou "sou")
    patterns = [
        (r"(?:sou|me chamo|meu nome [eé]|aqui [eé])\s+([A-Za-zà-ÿ]{3,})",
         re.IGNORECASE),
        (r"^([A-Za-zà-ÿ]{3,})\s+[A-Za-zà-ÿ]{3,}", 0),  # "Douglas Silva"
        (r"^([A-Za-zà-ÿ]{3,})\s*[!.,]?$", 0),         # só o nome
    ]
    for p, flags in patterns:
        m = re.search(p, text, flags) if flags else re.search(p, text)
        if m:
            name = m.group(1).strip()
            if name.lower() in stop:
                continue
            if 2 < len(name) < 25 and name.isalpha():
                return name.title()
    return None


def _extract_yes_no(text: str) -> Optional[bool]:
    norm = _norm(text)
    # Negativo primeiro pra "não" não casar com "s" de sim
    if re.search(r"\bn[ãa]o\b|\bnunca\b|\bnegativ[oa]\b|\bjamais\b", norm):
        return False
    if re.search(r"\bsim\b|\baceit[oa]\b|\bconfirm[oa]\b|\bpositiv[oa]\b|\bclaro\b|\bbeleza\b", norm):
        return True
    return None


def _extract_intent_b2c_b2b(text: str) -> Optional[str]:
    norm = _norm(text)
    # B2B markers
    b2b_patterns = [
        r"\bilpi\b", r"\basilo\b", r"\bcasa de repouso\b",
        r"\bclinica\b", r"\bhospital\b", r"\bgeriatria\b",
        r"\bnegoc[io]o\b", r"\bempresa\b", r"\bdiretor\b",
        r"\bgestor\b", r"\bcontratar pra\b", r"\bdiretora?\b",
        r"\binstitui[çc][ãa]o\b", r"\boperadora\b",
    ]
    if any(re.search(p, norm) for p in b2b_patterns):
        return "b2b"
    # B2C markers
    b2c_patterns = [
        r"\bpra minha m[ãa]e\b", r"\bpra meu pai\b",
        r"\bpra meus pais\b", r"\bpra mim\b",
        r"\bpra eu\b", r"\bpara minha\b",
    ]
    if any(re.search(p, norm) for p in b2c_patterns):
        return "b2c"
    return None


def _extract_moram_em_ilpi(text: str) -> Optional[bool]:
    norm = _norm(text)
    if any(re.search(p, norm) for p in ILPI_PATTERNS):
        return True
    return None


def _extract_moram_sozinhos(text: str) -> Optional[bool]:
    norm = _norm(text)
    if any(re.search(p, norm) for p in SOZINHO_PATTERNS):
        return True
    return None


# ══════════════════════════════════════════════════════════════════
# DataExtractor service
# ══════════════════════════════════════════════════════════════════

class DataExtractor:
    """Extrai CareLeadData fields de mensagens livres em PT-BR."""

    def __init__(self, *, llm_provider=None):
        # Lazy import — não força get_llm() em testes que não precisam
        self._llm_provider = llm_provider

    def _get_llm(self):
        if self._llm_provider is not None:
            return self._llm_provider
        from src.services.llm import get_llm
        return get_llm()

    # ─── Camada 1: Regex ────────────────────────────────────────

    def extract_regex(
        self,
        user_text: str,
        *,
        pending_intent: Optional[QuestionIntent] = None,
    ) -> ExtractionResult:
        """Extração rápida via regex. Sem custo de LLM."""
        out: dict[str, Any] = {}
        confidence = 0.0
        n_matches = 0

        # Idades sempre tenta (alta confiança quando casa)
        idades = _extract_idades(user_text)
        if idades:
            out["idades_idosos"] = idades
            n_matches += 1
            confidence = max(confidence, 0.9)

        # Count idosos
        count = _extract_count_idosos(user_text)
        if count is not None:
            out["count_idosos"] = count
            n_matches += 1
            confidence = max(confidence, 0.85)

        # Relação
        rel = _extract_relacao(user_text)
        if rel:
            out["relacao"] = rel
            n_matches += 1
            confidence = max(confidence, 0.85)

        # Dores
        dores = _extract_dores(user_text)
        if dores:
            out["dores"] = dores
            n_matches += 1
            confidence = max(confidence, 0.8)

        # Email
        email = _extract_email(user_text)
        if email:
            out["email"] = email
            n_matches += 1
            confidence = max(confidence, 0.95)

        # ILPI / sozinhos
        ilpi = _extract_moram_em_ilpi(user_text)
        if ilpi:
            out["moram_em_ilpi"] = True
            n_matches += 1
            confidence = max(confidence, 0.85)
        sozinhos = _extract_moram_sozinhos(user_text)
        if sozinhos:
            out["moram_sozinhos"] = True
            n_matches += 1
            confidence = max(confidence, 0.85)

        # B2C / B2B
        intent = _extract_intent_b2c_b2b(user_text)
        if intent:
            out["intent_b2c_b2b"] = intent
            n_matches += 1
            confidence = max(confidence, 0.7)

        # Pending-question-aware
        if pending_intent == QuestionIntent.PRIMEIRO_NOME:
            name = _extract_first_name(user_text, pending=pending_intent)
            if name:
                out["primeiro_nome"] = name
                n_matches += 1
                confidence = max(confidence, 0.9)

        if pending_intent in (
            QuestionIntent.MORAM_SOZINHOS,
            QuestionIntent.MORAM_EM_ILPI,
            QuestionIntent.QUER_DEMO,
            QuestionIntent.JA_CLIENTE_CONCORRENTE,
            QuestionIntent.DIFICULDADE_MEDICACAO,
        ):
            yn = _extract_yes_no(user_text)
            if yn is not None:
                # Mapeia field específico do intent
                fields = INTENT_TO_FIELD.get(pending_intent, [])
                for f in fields:
                    if f in (
                        "moram_sozinhos", "moram_em_ilpi", "quer_demo",
                        "ja_cliente_concorrente", "tem_dificuldade_medicacao",
                    ):
                        out[f] = yn
                        n_matches += 1
                        confidence = max(confidence, 0.9)
                        break

        return ExtractionResult(
            data=out,
            confidence=confidence if n_matches else 0.0,
            method="regex" if n_matches else "none",
        )

    # ─── Camada 2: LLM Haiku fallback ────────────────────────────

    def extract_llm(
        self,
        user_text: str,
        *,
        pending_intent: Optional[QuestionIntent] = None,
        current_lead_data: Optional[CareLeadData] = None,
    ) -> ExtractionResult:
        """Fallback Haiku quando regex insuficiente. JSON output."""
        # Hint do que ainda falta — Haiku foca melhor
        already_have: list[str] = []
        if current_lead_data:
            already_have = list(current_lead_data.dados_confirmados)

        # Hint do que perguntamos
        intent_hint = ""
        if pending_intent and pending_intent != QuestionIntent.OPEN_ENDED:
            fields = INTENT_TO_FIELD.get(pending_intent, [])
            if fields:
                intent_hint = (
                    f"\nA pergunta anterior da Sofia esperava: {', '.join(fields)}. "
                    f"Priorize extrair esse(s) campo(s)."
                )

        system = (
            "Você extrai dados estruturados de mensagens em português do Brasil "
            "sobre cuidado com idosos. Responda APENAS com JSON válido contendo "
            "os campos detectados. Omita campos que não aparecem na mensagem.\n\n"
            "Campos possíveis (Optional, omita se não detectar):\n"
            "- primeiro_nome (string)\n"
            "- nome (string, nome completo)\n"
            "- email (string)\n"
            "- cidade (string)\n"
            "- estado (string, sigla 2 letras)\n"
            "- relacao (string: 'self'|'filho_a'|'neto_a'|'conjuge'|'cuidador_pro')\n"
            "- count_idosos (int)\n"
            "- idades_idosos (list[int], só 60-110)\n"
            "- moram_sozinhos (bool)\n"
            "- moram_em_ilpi (bool)\n"
            "- dores (list[string]: 'queda','esquecimento','medicacao','isolamento',"
            "'depressao','incontinencia','mobilidade','diabetes','hipertensao','alimentacao')\n"
            "- count_medicamentos (int)\n"
            "- tem_dificuldade_medicacao (bool)\n"
            "- organizacao (string, nome empresa/ILPI)\n"
            "- cargo_b2b (string)\n"
            "- ja_cliente_concorrente (bool)\n"
            "- concorrente_nome (string)\n"
            "- quer_demo (bool)\n"
            "- intent_b2c_b2b (string: 'b2c'|'b2b')\n\n"
            "Regra: SE você não tem certeza de um campo, OMITA. Não invente."
        )
        if already_have:
            system += f"\n\nJÁ COLETADO (não preencher de novo): {', '.join(already_have)}"
        system += intent_hint

        try:
            from src.services.llm import MODEL_FAST
            llm = self._get_llm()
            raw = llm.complete_json(
                system=system,
                user=f"Mensagem do user:\n{user_text}",
                model=MODEL_FAST,
                max_tokens=512,
                temperature=0.0,
            )
        except Exception as exc:
            logger.warning(
                "data_extractor_llm_failed",
                error=str(exc)[:200], text_len=len(user_text),
            )
            return ExtractionResult()

        if not isinstance(raw, dict):
            return ExtractionResult()

        # Filtra só campos válidos do CareLeadData
        valid_fields = set(CareLeadData.__dataclass_fields__.keys())
        filtered = {k: v for k, v in raw.items() if k in valid_fields and v not in (None, "", [])}

        return ExtractionResult(
            data=filtered,
            confidence=0.7 if filtered else 0.0,
            method="llm" if filtered else "none",
        )

    # ─── API combinada ──────────────────────────────────────────

    def extract(
        self,
        user_text: str,
        *,
        pending_intent: Optional[QuestionIntent] = None,
        current_lead_data: Optional[CareLeadData] = None,
        use_llm_fallback: bool = True,
    ) -> ExtractionResult:
        """Extração 2-camadas. Tenta regex primeiro; se confidence
        baixa OU msg longa, fallback Haiku.
        """
        if not user_text or not user_text.strip():
            return ExtractionResult()

        regex_result = self.extract_regex(user_text, pending_intent=pending_intent)

        # Quando NÃO chamar Haiku:
        # - regex já cobriu com confiança alta
        # - msg curta E não há intent forçando (provavelmente nada extraível)
        msg_long = len(user_text) > 80
        regex_strong = regex_result.confidence >= 0.85 and len(regex_result.data) >= 1

        if not use_llm_fallback or regex_strong or (not msg_long and not pending_intent):
            return regex_result

        # Fallback LLM (descartado se já tem o campo)
        llm_result = self.extract_llm(
            user_text,
            pending_intent=pending_intent,
            current_lead_data=current_lead_data,
        )

        if not llm_result.data:
            return regex_result

        # Merge: regex tem prioridade (mais confiável); LLM preenche gaps
        merged = dict(llm_result.data)
        merged.update(regex_result.data)
        return ExtractionResult(
            data=merged,
            confidence=max(regex_result.confidence, llm_result.confidence),
            method="hybrid" if regex_result.data and llm_result.data else (
                regex_result.method if regex_result.data else llm_result.method
            ),
        )


# Singleton
_instance: Optional[DataExtractor] = None


def get_data_extractor() -> DataExtractor:
    global _instance
    if _instance is None:
        _instance = DataExtractor()
    return _instance
