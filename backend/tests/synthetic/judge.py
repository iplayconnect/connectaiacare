"""LLM-as-judge usando DeepSeek V4-Flash.

Quando o classificador erra, queremos saber se foi:
  - erro real (predição claramente errada)
  - ambiguidade legítima (predição alternativa plausível)
  - rótulo ground-truth duvidoso (corpus precisa revisão)

O judge classifica cada erro em 3 buckets via DeepSeek (barato + rápido).

Uso programático:
    from tests.synthetic.judge import judge_error
    verdict = judge_error(transcript, expected, predicted)
    # verdict.bucket: 'real_error' | 'ambiguous' | 'corpus_issue'
    # verdict.rationale: justificativa em 1 frase

Custo: ~$0.0001 por chamada (V4-Flash). 240 itens com 20% errors = $0.005/run.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import requests


DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"  # alias = V4-Flash atual

EVENT_TYPE_DESCRIPTIONS = {
    "relato_geral": "relato amplo cobrindo múltiplos tipos sem dominância clara, ou resumo de plantão",
    "cuidado_higiene": "banho, fralda, curativos, mobilização — cuidado físico de rotina",
    "alimentacao_hidratacao": "refeição (comeu/recusou), aceitação de líquidos, hidratação",
    "medicacao": "administração, recusa, efeito ou ajuste de medicamento",
    "sinal_vital": "aferição numérica de PA, FC, glicemia, SpO₂, temperatura, peso",
    "intercorrencia": "queda, agitação súbita, episódio agudo — evento adverso pontual",
    "sintoma_novo": "dor, tontura, dispneia, confusão, fraqueza nova reportada",
    "apoio_emocional": "cuidador desabafa, expressa cansaço, dúvida não-clínica",
}


JUDGE_PROMPT = """Você é um avaliador imparcial de classificação clínica.

Há uma TAXONOMIA de 8 classes pra rotular relatos de cuidadores de idosos:

{taxonomy}

Vou te dar:
1. TRANSCRIPT do áudio do cuidador
2. RÓTULO ESPERADO (ground truth definido por humano clínico)
3. RÓTULO PREDITO pelo modelo

Sua tarefa: classificar a discordância em 1 dos 3 buckets:

- "real_error": predição claramente errada. Há evidência forte no transcript pro rótulo esperado e o predito não faz sentido.
- "ambiguous": ambos os rótulos têm justificativa razoável. Caso fronteiriço onde dois clínicos poderiam discordar.
- "corpus_issue": o rótulo esperado parece duvidoso. O predito pode ser melhor que o esperado.

Responda APENAS JSON:
{{"bucket": "real_error|ambiguous|corpus_issue", "rationale": "1 frase curta justificando"}}"""


@dataclass
class Verdict:
    bucket: str  # 'real_error' | 'ambiguous' | 'corpus_issue'
    rationale: str
    raw: dict


def _build_taxonomy() -> str:
    return "\n".join(f"- {k}: {v}" for k, v in EVENT_TYPE_DESCRIPTIONS.items())


def judge_error(
    transcript: str,
    expected: str,
    predicted: str | None,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    timeout: float = 15.0,
) -> Verdict:
    """Avalia 1 erro de classificação. Retorna veredito + rationale."""
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY não configurada")

    user_msg = (
        f"TRANSCRIPT: {transcript}\n\n"
        f"RÓTULO ESPERADO: {expected}\n"
        f"RÓTULO PREDITO: {predicted or '(nenhum)'}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_PROMPT.format(taxonomy=_build_taxonomy())},
            {"role": "user", "content": user_msg},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 200,
        "temperature": 0.0,  # determinístico — judge deve ser repetível
    }
    r = requests.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload, timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    bucket = parsed.get("bucket", "ambiguous")
    if bucket not in ("real_error", "ambiguous", "corpus_issue"):
        bucket = "ambiguous"
    return Verdict(
        bucket=bucket,
        rationale=parsed.get("rationale", ""),
        raw=body,
    )


def judge_all_errors(predictions: list[dict], corpus_index: dict[str, dict]) -> list[dict]:
    """Aplica judge a todos os predictions errados. Retorna lista enriquecida."""
    out = []
    for p in predictions:
        if p["expected"] == p["predicted"]:
            continue
        item = corpus_index[p["id"]]
        try:
            v = judge_error(item["transcript"], p["expected"], p["predicted"])
            out.append({
                **p,
                "judge_bucket": v.bucket,
                "judge_rationale": v.rationale,
            })
        except Exception as exc:
            out.append({
                **p,
                "judge_bucket": "judge_error",
                "judge_rationale": str(exc)[:200],
            })
    return out
