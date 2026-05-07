"""Validação fisiológica de vital signs.

Decisão arquitetural (2026-05-07): a validação de plausibilidade dos
valores é responsabilidade NOSSA, não do TotalCare/Tecnosenior. Eles
armazenam o que mandarmos. A gente decide o que vai.

Por quê:
    1. Cuidadores reportam via voz/foto/texto natural — cabem erros de
       transcrição (Sofia ouvir "cento e trinta" como "1300"), erros de
       leitura de equipamento (cuidador trocando systolic/diastolic),
       erros de tipo (peso de pulseira em libras vendo como kg).
    2. Valores reais críticos (PA 220x120) precisam disparar care_event
       com classificação clínica adequada.
    3. Valores impossíveis fisiologicamente devem trigger Sofia pedir
       reconfirmação ao cuidador ("tem certeza? 50x300 parece estranho,
       pode conferir o aparelho?") antes de persistir local OU mandar
       pro TotalCare.

Faixas baseadas em referências clínicas (adulto/idoso). Valores fora
da PHYSIOLOGIC range são tratados como prováveis erros de extração e
NÃO devem ser persistidos sem confirmação humana.

Output do validate():
    ValidationResult com:
    - is_physiologic: bool — tá dentro do range que humano vivo pode ter
    - clinical_status: 'routine' | 'attention' | 'urgent' | 'critical'
    - confidence_concern: bool — borderline plausible, vale reconfirmar
    - reason_text: explicação curta do veredito (pra Sofia usar no diálogo)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _Range:
    """Faixa de valores pra um vital sign type.

    Layered:
        physiologic: total range que humano vivo pode apresentar.
            Fora disso = erro de extração quase certo. NÃO persistir
            sem reconfirmação.
        plausible: range típico em prática (±2σ da população idosa).
            Fora dele mas dentro do physiologic = vale reconfirmar
            (confidence_concern=True) mas pode persistir.
        normal: range normal-saudável.
        critical_low / critical_high: bordas que disparam care_event
            com classification='critical' (precisa ação imediata).
        urgent_low / urgent_high: bordas que disparam 'urgent'.
        attention_low / attention_high: bordas pra 'attention'.
    """
    physiologic_min: float
    physiologic_max: float
    plausible_min: float
    plausible_max: float
    normal_min: float
    normal_max: float
    attention_low: float
    attention_high: float
    urgent_low: float
    urgent_high: float
    critical_low: float
    critical_high: float
    unit: str


# Referências: AHA, MS Brasil, Beers (idoso), faixas clínicas comuns.
# physiologic = limite biológico (fora = quase certo erro de extração).
# plausible = faixa que aparece na prática mesmo em casos extremos.
_RANGES: dict[str, _Range] = {
    "heart_rate": _Range(
        physiologic_min=20, physiologic_max=300,
        plausible_min=30, plausible_max=220,
        normal_min=60, normal_max=100,
        attention_low=50, attention_high=110,
        urgent_low=40, urgent_high=130,
        critical_low=35, critical_high=160,
        unit="bpm",
    ),
    "blood_pressure_systolic": _Range(
        physiologic_min=40, physiologic_max=280,
        plausible_min=70, plausible_max=240,
        normal_min=90, normal_max=130,
        attention_low=85, attention_high=140,
        urgent_low=80, urgent_high=170,
        critical_low=70, critical_high=200,
        unit="mmHg",
    ),
    "blood_pressure_diastolic": _Range(
        physiologic_min=20, physiologic_max=160,
        plausible_min=40, plausible_max=140,
        normal_min=60, normal_max=85,
        attention_low=55, attention_high=90,
        urgent_low=50, urgent_high=110,
        critical_low=40, critical_high=130,
        unit="mmHg",
    ),
    "blood_glucose": _Range(
        # mg/dL — diabéticos descompensados podem chegar a 600+
        physiologic_min=10, physiologic_max=900,
        plausible_min=30, plausible_max=700,
        normal_min=70, normal_max=140,  # pós-prandial
        attention_low=65, attention_high=180,
        urgent_low=55, urgent_high=300,
        critical_low=40, critical_high=400,
        unit="mg/dL",
    ),
    "temperature": _Range(
        # °C — life-incompatible <30 ou >43
        physiologic_min=28, physiologic_max=44,
        plausible_min=33, plausible_max=42,
        normal_min=36.0, normal_max=37.5,
        attention_low=35.5, attention_high=37.8,
        urgent_low=35.0, urgent_high=38.5,
        critical_low=34.5, critical_high=40.0,
        unit="°C",
    ),
    "weight": _Range(
        # kg — adulto. Idoso: tipicamente 40-120
        physiologic_min=15, physiologic_max=350,
        plausible_min=30, plausible_max=200,
        # "normal" é mais útil como referência da pessoa,
        # mas pra validation: range que não dispara nada
        normal_min=40, normal_max=120,
        attention_low=35, attention_high=130,
        urgent_low=30, urgent_high=180,
        critical_low=25, critical_high=250,
        unit="kg",
    ),
    "oxygen_saturation": _Range(
        # % — fora 70-100 muito raro fora de UTI
        physiologic_min=40, physiologic_max=100,
        plausible_min=70, plausible_max=100,
        normal_min=95, normal_max=100,
        attention_low=92, attention_high=100,
        urgent_low=88, urgent_high=100,
        critical_low=85, critical_high=100,
        unit="%",
    ),
}


@dataclass(frozen=True)
class ValidationResult:
    is_physiologic: bool
    """False = valor impossível biologicamente. Quase certo erro de
    extração/transcrição/typo. NÃO persistir sem reconfirmação."""

    clinical_status: str
    """'routine' | 'attention' | 'urgent' | 'critical' | 'invalid'.
    Quando is_physiologic=False, status='invalid'."""

    confidence_concern: bool
    """True = dentro do physiologic mas fora do plausible. Sofia deve
    perguntar ao cuidador antes de persistir, pra não enviar dado
    suspeito que pode disparar alerta clínico desnecessário."""

    reason_text: str
    """Frase curta explicando o veredito. Sofia usa no diálogo:
    "Confirmou que a pressão da Dona Maria foi 50 por 300 mesmo? Esse
    valor não bate com nenhuma medida possível, deve ter algum erro
    de leitura."
    """

    suggested_unit: str
    """Unidade canônica esperada pra esse type. Útil quando cuidador
    relatou em unidade errada (ex: peso em libras → kg)."""


def validate(measure_type: str, value: float | None) -> ValidationResult | None:
    """Valida (type, value) contra faixa fisiológica + classifica.

    Retorna None se measure_type desconhecido (caller decide skip).
    """
    if measure_type not in _RANGES:
        return None
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None

    r = _RANGES[measure_type]

    # Camada 1: physiologic check (life-incompatible = erro de extração)
    if v < r.physiologic_min or v > r.physiologic_max:
        return ValidationResult(
            is_physiologic=False,
            clinical_status="invalid",
            confidence_concern=True,
            reason_text=(
                f"Valor {v}{r.unit} fora da faixa biologicamente "
                f"possível pra {measure_type} ({r.physiologic_min}–"
                f"{r.physiologic_max}{r.unit}). Provável erro de "
                f"leitura/transcrição."
            ),
            suggested_unit=r.unit,
        )

    # Camada 2: plausibility check (raro mas possível, pede reconfirmação)
    confidence_concern = (v < r.plausible_min or v > r.plausible_max)

    # Camada 3: clinical classification
    if v <= r.critical_low or v >= r.critical_high:
        status = "critical"
    elif v <= r.urgent_low or v >= r.urgent_high:
        status = "urgent"
    elif v <= r.attention_low or v >= r.attention_high:
        status = "attention"
    elif r.normal_min <= v <= r.normal_max:
        status = "routine"
    else:
        # Entre normal e attention thresholds (zona cinza)
        status = "routine"

    if confidence_concern:
        reason = (
            f"Valor {v}{r.unit} é raro mas biologicamente possível. "
            f"Vale conferir com o cuidador antes de persistir."
        )
    elif status == "critical":
        reason = (
            f"Valor {v}{r.unit} em faixa CRÍTICA — requer ação imediata."
        )
    elif status == "urgent":
        reason = f"Valor {v}{r.unit} fora do normal — atenção urgente."
    elif status == "attention":
        reason = f"Valor {v}{r.unit} levemente alterado — monitorar."
    else:
        reason = f"Valor {v}{r.unit} dentro do normal."

    return ValidationResult(
        is_physiologic=True,
        clinical_status=status,
        confidence_concern=confidence_concern,
        reason_text=reason,
        suggested_unit=r.unit,
    )


def filter_valid_for_persistence(
    measures: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Separa medidas em (válidas pra persistir, suspeitas pra reconfirmar).

    Útil pro pipeline: o que vai pro INSERT direto vs o que vai pra
    fila de "Sofia pergunta novamente".

    Cada measure deve ter 'type' e 'value'. Adiciona campos:
        - clinical_status (do validator)
        - validation_reason
    """
    valid: list[dict] = []
    suspicious: list[dict] = []

    for m in measures:
        if not isinstance(m, dict):
            suspicious.append(m if isinstance(m, dict) else {"raw": m})
            continue
        result = validate(m.get("type"), m.get("value"))
        if result is None:
            # Type desconhecido — skip, mas mantém na suspicious pra log
            suspicious.append({**m, "validation_reason": "unknown_type"})
            continue

        annotated = {
            **m,
            "clinical_status": result.clinical_status,
            "validation_reason": result.reason_text,
        }

        if not result.is_physiologic:
            # Erro biológico — NÃO persistir, vai pra reconfirmação
            suspicious.append(annotated)
        elif result.confidence_concern:
            # Plausível mas raro — pede reconfirmação antes
            suspicious.append(annotated)
        else:
            valid.append(annotated)

    return valid, suspicious


__all__ = [
    "ValidationResult",
    "validate",
    "filter_valid_for_persistence",
]
