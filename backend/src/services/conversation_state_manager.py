"""Conversation State Manager (CSM) — single source of truth do estado.

Inspirado em CSM da ConnectaIA, adaptado pra Sofia Cuida.

Problema que resolve:
    Bug histórico da Sofia v1: Sofia pergunta "qual seu CPF?", user digita
    "51999998888" (telefone por engano), Sofia aceita como CPF porque o
    state machine só valida lexicalmente. OU pior: user manda "minha mãe
    Maria, 82, hipertensa" na fase `collect_beneficiary_name`, e o nome da
    mãe vira "minha mãe Maria, 82, hipertensa" inteiro no campo full_name.

Solução: CSM mantém **pending_question** (última pergunta feita pela Sofia) +
**expected_answer_type** (cpf, name, age, phone, plan_choice, etc). Quando
user responde, CSM valida se a resposta bate com o tipo esperado ANTES de
gravar no `collected_data`. Se não bate, força reformulação ou clarificação.

API principal:

    csm = get_csm()

    # Sofia acabou de perguntar o CPF
    csm.set_pending(
        phone="5511999",
        session_id="sess-1",
        question="Agora preciso do seu CPF",
        expected_type="cpf",
        target_field="payer.cpf",
    )

    # User respondeu
    pending = csm.get_pending(phone, session_id)
    if pending:
        result = csm.validate_response(pending, user_text)
        if result.valid:
            # salvar no target_field
        else:
            # pedir clarificação (result.reason)

    # Ao completar com sucesso
    csm.clear_pending(phone, session_id)

Persistência: em memória (single-worker) + opcionalmente snapshot em
`aia_health_onboarding_sessions.context` pra sobreviver a restart.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Tipos e estruturas
# ══════════════════════════════════════════════════════════════════

ExpectedType = Literal[
    "name",          # nome próprio (mínimo 2 palavras pra full_name)
    "first_name",    # primeiro nome (1 palavra)
    "cpf",           # CPF (11 dígitos com ou sem formatação)
    "phone",         # telefone (10-13 dígitos)
    "email",         # email formato básico
    "age",           # idade (inteiro 0-120)
    "yes_no",        # sim/não
    "plan_choice",   # essencial|familia|premium|premium_device
    "role_choice",   # self|family|caregiver
    "payment_method",# credit_card|pix
    "date",          # data no formato DD/MM/AAAA
    "address_cep",   # CEP 8 dígitos
    "free_text",     # qualquer texto (mínimo 2 chars)
    "text_with_skip",# texto ou "pular"
    "audio_or_text", # aceita áudio (transcrito) ou texto
    "image_or_skip", # aceita imagem (foto) ou "pular"
]


@dataclass
class PendingQuestion:
    """Estado de uma pergunta esperando resposta."""
    phone: str
    session_id: str
    question: str                    # texto exato que Sofia perguntou
    expected_type: ExpectedType
    target_field: str                # ex: "payer.cpf", "beneficiary.age"
    created_at: float = field(default_factory=time.time)
    attempts: int = 0                # tentativas de resposta até agora
    max_attempts: int = 3            # depois disso, escala


@dataclass
class ValidationResult:
    valid: bool = False
    parsed_value: object | None = None
    reason: str = ""                 # motivo de falha, legível pro user
    clarification: str | None = None # reformulação sugerida pela Sofia


# ══════════════════════════════════════════════════════════════════
# Validadores por tipo
# ══════════════════════════════════════════════════════════════════

NAME_RE = re.compile(r"^[A-Za-zÀ-ÿ\s'\-]+$")
EMAIL_RE = re.compile(r"^[\w\.\-]+@[\w\.\-]+\.\w+$")
CEP_RE = re.compile(r"^\d{5}-?\d{3}$")
DATE_RE = re.compile(r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$")


def _validate_cpf(raw: str) -> tuple[bool, str, str]:
    """Valida CPF com checksum. Retorna (valid, cleaned, reason)."""
    cpf = re.sub(r"\D", "", raw)
    if len(cpf) != 11:
        return False, cpf, "CPF deve ter 11 dígitos"
    if cpf == cpf[0] * 11:
        return False, cpf, "CPF inválido (todos dígitos iguais)"

    # Checksum dígito 10
    sum1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = ((sum1 * 10) % 11) % 10
    if d1 != int(cpf[9]):
        return False, cpf, "CPF inválido"

    # Checksum dígito 11
    sum2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = ((sum2 * 10) % 11) % 10
    if d2 != int(cpf[10]):
        return False, cpf, "CPF inválido"

    return True, cpf, "ok"


def _validate_phone(raw: str) -> tuple[bool, str, str]:
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 13:
        return False, digits, "Telefone deve ter entre 10 e 13 dígitos"
    return True, digits, "ok"


def _validate_email(raw: str) -> tuple[bool, str, str]:
    s = raw.strip().lower()
    if not EMAIL_RE.match(s):
        return False, s, "Email em formato inválido"
    return True, s, "ok"


def _validate_age(raw: str) -> tuple[bool, int, str]:
    # Pega primeiro número do texto
    m = re.search(r"\b(\d{1,3})\b", raw)
    if not m:
        return False, -1, "Preciso de um número da idade"
    age = int(m.group(1))
    if age < 0 or age > 120:
        return False, age, "Idade fora do intervalo válido"
    return True, age, "ok"


def _validate_name(raw: str, *, min_words: int = 2) -> tuple[bool, str, str]:
    name = raw.strip()
    if not NAME_RE.match(name):
        return False, name, "Nome tem caracteres inválidos (só letras e espaços)"
    words = [w for w in name.split() if len(w) >= 2]
    if len(words) < min_words:
        return False, name, f"Preciso de {'nome e sobrenome' if min_words >= 2 else 'pelo menos um nome'}"
    # Protege contra texto tipo "minha mãe Maria Silva" entrar como full_name
    lower = name.lower()
    # Usa startswith (não `in`), senão "maria silva" pega "a " na posição do meio
    if any(lower.startswith(starter) for starter in ["minha ", "meu ", "é ", "seu nome ", "ele ", "ela "]):
        return False, name, "Parece que veio texto extra. Me manda só o nome completo, por favor."
    return True, name.title(), "ok"


def _validate_yes_no(raw: str) -> tuple[bool, bool | None, str]:
    t = raw.strip().lower()
    # Checa "não" / "nao" / "recuso" PRIMEIRO (senão "recuso" vira True por causa do "s")
    # Word-boundary pra não dar falso positivo com substring (ex: "s" em "talvez")
    no_patterns = [
        r"\bn[ãa]o\b", r"\bnunca\b", r"\brecuso\b", r"\brecus[oa]\b",
        r"\bnegativo\b", r"\bjamais\b", r"\bno\b(?!\w)",
    ]
    yes_patterns = [
        r"\bsim\b", r"\baceito\b", r"\bconfirmo\b", r"\bpositivo\b",
        r"\byes\b", r"\bclaro\b", r"\bcom certeza\b", r"\bpode\b",
        r"\bok\b", r"\bbeleza\b",
    ]
    for p in no_patterns:
        if re.search(p, t):
            return True, False, "ok"
    for p in yes_patterns:
        if re.search(p, t):
            return True, True, "ok"
    return False, None, "Preciso de sim ou não"


def _validate_plan_choice(raw: str) -> tuple[bool, str, str]:
    t = raw.strip().lower()
    # Ordem importa: checar premium_device PRIMEIRO (contém "199"),
    # depois premium (contém "149"), depois familia ("89"), por último essencial ("49")
    # Senão "149" casa com "49" de essencial por substring.
    if "device" in t or "dispositi" in t or "pulseira" in t or t.strip() == "4" or "199" in t:
        return True, "premium_device", "ok"
    if "premium" in t or t.strip() == "3" or "149" in t:
        return True, "premium", "ok"
    if "famíl" in t or "famil" in t or t.strip() == "2" or "89" in t:
        return True, "familia", "ok"
    if "essen" in t or t.strip() == "1" or "49" in t or "básic" in t or "basic" in t:
        return True, "essencial", "ok"
    return False, "", "Não entendi qual plano. Manda 1, 2, 3 ou 4"


def _validate_role_choice(raw: str) -> tuple[bool, str, str]:
    t = raw.strip().lower()
    if "eu mesmo" in t or "pra mim" in t or "meu próprio" in t or "mim mesmo" in t:
        return True, "self", "ok"
    if "cuidador" in t or "enfermeira" in t or "profissional" in t or "trabalho como" in t:
        return True, "caregiver", "ok"
    if "mãe" in t or "pai" in t or "sogr" in t or "tio" in t or "avó" in t or "avô" in t or \
       "ente querido" in t or "parent" in t or "famil" in t:
        return True, "family", "ok"
    return False, "", "Me conta de quem você tá cuidando"


def _validate_payment_method(raw: str) -> tuple[bool, str, str]:
    t = raw.strip().lower()
    if "cart" in t or "credit" in t or "crédito" in t or "credito" in t:
        return True, "credit_card", "ok"
    if "pix" in t or "qr" in t:
        return True, "pix", "ok"
    return False, "", "Cartão ou PIX?"


def _validate_date(raw: str) -> tuple[bool, str, str]:
    m = DATE_RE.search(raw)
    if not m:
        return False, "", "Data em formato DD/MM/AAAA"
    d, mo, y = m.group(1), m.group(2), m.group(3)
    if len(y) == 2:
        y = "19" + y if int(y) > 26 else "20" + y
    try:
        from datetime import date
        iso = date(int(y), int(mo), int(d)).isoformat()
        return True, iso, "ok"
    except ValueError:
        return False, "", "Data inválida"


def _validate_cep(raw: str) -> tuple[bool, str, str]:
    m = re.search(r"\d{5}-?\d{3}", raw)
    if not m:
        return False, "", "CEP em formato XXXXX-XXX"
    clean = re.sub(r"\D", "", m.group(0))
    return True, clean, "ok"


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class ConversationStateManager:
    """Gerencia pending questions com pareamento Q/A tipado."""

    def __init__(self):
        self._pending: dict[str, PendingQuestion] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(phone: str, session_id: str) -> str:
        return f"{phone}:{session_id}"

    # ═══════════════════════════════════════════════════════════════
    # Set / Get / Clear pending
    # ═══════════════════════════════════════════════════════════════

    def set_pending(
        self,
        *,
        phone: str,
        session_id: str,
        question: str,
        expected_type: ExpectedType,
        target_field: str,
        max_attempts: int = 3,
    ) -> None:
        """Marca que Sofia está esperando uma resposta tipada."""
        with self._lock:
            self._pending[self._key(phone, session_id)] = PendingQuestion(
                phone=phone,
                session_id=session_id,
                question=question,
                expected_type=expected_type,
                target_field=target_field,
                max_attempts=max_attempts,
            )

    def get_pending(self, phone: str, session_id: str) -> PendingQuestion | None:
        with self._lock:
            return self._pending.get(self._key(phone, session_id))

    def clear_pending(self, phone: str, session_id: str) -> None:
        with self._lock:
            self._pending.pop(self._key(phone, session_id), None)

    def increment_attempts(self, phone: str, session_id: str) -> int:
        with self._lock:
            p = self._pending.get(self._key(phone, session_id))
            if p:
                p.attempts += 1
                return p.attempts
        return 0

    def exceeded_attempts(self, phone: str, session_id: str) -> bool:
        with self._lock:
            p = self._pending.get(self._key(phone, session_id))
            return bool(p and p.attempts >= p.max_attempts)

    # ═══════════════════════════════════════════════════════════════
    # Validação
    # ═══════════════════════════════════════════════════════════════

    def validate_response(
        self,
        pending: PendingQuestion,
        user_text: str,
    ) -> ValidationResult:
        """Valida resposta do user contra o tipo esperado.

        Returns:
            ValidationResult(valid, parsed_value, reason, clarification)
        """
        if not user_text or not user_text.strip():
            return ValidationResult(valid=False, reason="resposta_vazia",
                                    clarification="Não recebi mensagem. Pode mandar de novo?")

        text = user_text.strip()

        # Dispatcher por tipo
        validators: dict[str, callable] = {
            "cpf": self._validate_cpf_wrapper,
            "phone": self._validate_phone_wrapper,
            "email": self._validate_email_wrapper,
            "age": self._validate_age_wrapper,
            "name": self._validate_name_wrapper,
            "first_name": self._validate_first_name_wrapper,
            "yes_no": self._validate_yes_no_wrapper,
            "plan_choice": self._validate_plan_choice_wrapper,
            "role_choice": self._validate_role_choice_wrapper,
            "payment_method": self._validate_payment_method_wrapper,
            "date": self._validate_date_wrapper,
            "address_cep": self._validate_cep_wrapper,
            "free_text": self._validate_free_text,
            "text_with_skip": self._validate_text_with_skip,
            "audio_or_text": self._validate_audio_or_text,
            "image_or_skip": self._validate_image_or_skip,
        }

        fn = validators.get(pending.expected_type)
        if fn is None:
            logger.warning("csm_unknown_expected_type", type=pending.expected_type)
            return ValidationResult(valid=True, parsed_value=text, reason="unknown_type_passthrough")

        return fn(text, pending)

    # ─── wrappers ─────────────────────────────────────────────────
    def _validate_cpf_wrapper(self, text, pending):
        ok, cleaned, reason = _validate_cpf(text)
        return ValidationResult(
            valid=ok, parsed_value=cleaned if ok else None, reason=reason,
            clarification=None if ok else "Esse CPF não bateu. Pode conferir e mandar de novo?",
        )

    def _validate_phone_wrapper(self, text, pending):
        ok, cleaned, reason = _validate_phone(text)
        return ValidationResult(
            valid=ok, parsed_value=cleaned, reason=reason,
            clarification=None if ok else "Me manda o telefone com DDD, por favor",
        )

    def _validate_email_wrapper(self, text, pending):
        ok, cleaned, reason = _validate_email(text)
        return ValidationResult(
            valid=ok, parsed_value=cleaned, reason=reason,
            clarification=None if ok else "Email parece estar errado. Pode conferir?",
        )

    def _validate_age_wrapper(self, text, pending):
        ok, val, reason = _validate_age(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Me diz só o número da idade",
        )

    def _validate_name_wrapper(self, text, pending):
        ok, cleaned, reason = _validate_name(text, min_words=2)
        return ValidationResult(
            valid=ok, parsed_value=cleaned, reason=reason,
            clarification=None if ok else "Preciso do nome completo (nome + sobrenome)",
        )

    def _validate_first_name_wrapper(self, text, pending):
        ok, cleaned, reason = _validate_name(text, min_words=1)
        return ValidationResult(
            valid=ok, parsed_value=cleaned.split()[0] if ok else None, reason=reason,
            clarification=None if ok else "Me manda pelo menos um nome",
        )

    def _validate_yes_no_wrapper(self, text, pending):
        ok, val, reason = _validate_yes_no(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Preciso de *sim* ou *não*",
        )

    def _validate_plan_choice_wrapper(self, text, pending):
        ok, val, reason = _validate_plan_choice(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Manda 1 (Essencial), 2 (Família), 3 (Premium) ou 4 (+Device)",
        )

    def _validate_role_choice_wrapper(self, text, pending):
        ok, val, reason = _validate_role_choice(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Me conta: é pra você, pra um ente querido, ou você é cuidador?",
        )

    def _validate_payment_method_wrapper(self, text, pending):
        ok, val, reason = _validate_payment_method(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Cartão de crédito ou PIX?",
        )

    def _validate_date_wrapper(self, text, pending):
        ok, val, reason = _validate_date(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Data em formato DD/MM/AAAA, por favor",
        )

    def _validate_cep_wrapper(self, text, pending):
        ok, val, reason = _validate_cep(text)
        return ValidationResult(
            valid=ok, parsed_value=val, reason=reason,
            clarification=None if ok else "Me manda o CEP (XXXXX-XXX)",
        )

    def _validate_free_text(self, text, pending):
        if len(text.strip()) < 2:
            return ValidationResult(
                valid=False, reason="texto_muito_curto",
                clarification="Pode me contar com um pouquinho mais de detalhe?",
            )
        return ValidationResult(valid=True, parsed_value=text.strip(), reason="ok")

    def _validate_text_with_skip(self, text, pending):
        t = text.strip().lower()
        if t in ("pular", "skip", "nenhuma", "nenhum", "não tem", "nao tem", "nada"):
            return ValidationResult(valid=True, parsed_value=None, reason="skipped")
        return self._validate_free_text(text, pending)

    def _validate_audio_or_text(self, text, pending):
        # áudio já foi transcrito pelo pipeline antes de chegar aqui
        return self._validate_free_text(text, pending)

    def _validate_image_or_skip(self, text, pending):
        t = text.strip().lower()
        if t in ("pular", "skip"):
            return ValidationResult(valid=True, parsed_value=None, reason="skipped")
        return ValidationResult(valid=True, parsed_value=text, reason="ok")


# Singleton
_instance: ConversationStateManager | None = None


def get_csm() -> ConversationStateManager:
    global _instance
    if _instance is None:
        _instance = ConversationStateManager()
    return _instance
