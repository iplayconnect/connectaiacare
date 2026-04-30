"""Gerador de corpus sintético via DeepSeek V4-Pro.

Recebe o seed (24 itens, 3 por classe) e expande pra ~30 por classe
(240 total). DeepSeek gera variações estilísticas/contextuais que
cobrem distribuições realistas de severity.

Uso:
    cd backend && python -m tests.synthetic.corpus_generator \\
        --seed tests/synthetic/corpus/event_type_seed.yaml \\
        --output tests/synthetic/corpus/event_type_full.yaml \\
        --per-class 30

Custo: ~$0.20 pra gerar 240 itens com V4-Pro (output longo).
Após gerar: REVISÃO HUMANA OBRIGATÓRIA antes de aceitar como
ground truth — LLM pode errar e contaminar o benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
import yaml


DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-reasoner"  # V4-Pro alias

GENERATION_PROMPT = """Você é um especialista em geração de dados sintéticos pra avaliar classificadores
de relatos de cuidadores de idosos brasileiros.

TAXONOMIA das 8 classes funcionais (event_type):

- relato_geral: relato amplo cobrindo múltiplos tipos sem dominância clara, ou resumo de plantão
- cuidado_higiene: banho, fralda, curativos, mobilização — cuidado físico de rotina
- alimentacao_hidratacao: refeição (comeu/recusou), aceitação de líquidos, hidratação
- medicacao: administração, recusa, efeito ou ajuste de medicamento
- sinal_vital: aferição numérica de PA, FC, glicemia, SpO₂, temperatura, peso
- intercorrencia: queda, agitação súbita, episódio agudo — evento adverso pontual
- sintoma_novo: dor, tontura, dispneia, confusão, fraqueza nova reportada
- apoio_emocional: cuidador desabafa, expressa cansaço, dúvida não-clínica

CLASSIFICATION (severity, ortogonal a event_type):
- routine: rotineiro, sem alarme
- attention: merece atenção da enfermagem, não emergência
- urgent: avaliação médica nas próximas horas
- critical: emergência médica iminente

Vou te dar EXEMPLOS pra uma classe e quero que você gere {n} VARIAÇÕES NOVAS
pra mesma classe (event_type={cls}). REQUISITOS:

1. Cada relato é como saiu do Whisper/Deepgram (linguagem oral, possíveis pequenos erros gramaticais)
2. Diversifique:
   - Estilo: formal, informal, com pausas, com hesitação, contagem de história
   - Contexto clínico: paciente diabético, hipertenso, IC, Parkinson, sem comorbidades
   - Severidades: distribua entre routine/attention/urgent/critical de forma realista pra esta classe
   - Pacientes: varie nomes (M/F), idades implícitas, ambientes (casa, ILPI, hospital)
3. NÃO copie os exemplos. Use eles como inspiração de STYLE, não de conteúdo.
4. Cada item deve ser ROTULADO corretamente — você é o ground-truth gerador.

EXEMPLOS desta classe:
{examples}

Responda APENAS JSON com schema:
{{"items": [
  {{
    "id": "{cls}_NNN",
    "transcript": "...",
    "expected_event_type": "{cls}",
    "expected_classification": "routine|attention|urgent|critical",
    "rationale": "1 frase auditável",
    "difficulty": "easy|medium|hard"
  }},
  ...
]}}"""


def load_seed(path: str) -> list[dict]:
    with open(path) as f:
        return yaml.safe_load(f)


def group_by_class(items: list[dict]) -> dict[str, list[dict]]:
    by_class: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_class[it["expected_event_type"]].append(it)
    return by_class


def generate_for_class(
    cls: str,
    seed_examples: list[dict],
    n_target: int,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> list[dict]:
    """Gera n_target items pra classe cls via DeepSeek."""
    examples_text = "\n\n".join(
        f"  - id: {e['id']}\n    transcript: {e['transcript']!r}\n"
        f"    expected_classification: {e['expected_classification']}\n"
        f"    rationale: {e['rationale']}"
        for e in seed_examples
    )
    prompt = GENERATION_PROMPT.format(
        cls=cls, n=n_target, examples=examples_text,
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
        "temperature": 0.7,  # variabilidade estilística
    }
    print(f"  → DeepSeek call (cls={cls}, target={n_target})...", file=sys.stderr)
    r = requests.post(
        DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload, timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    items = parsed.get("items", [])
    # validação: classe correta?
    valid = [it for it in items if it.get("expected_event_type") == cls]
    if len(valid) < len(items):
        print(
            f"    [warn] {len(items) - len(valid)} items com classe errada, descartados",
            file=sys.stderr,
        )
    print(f"    ✓ {len(valid)} items válidos", file=sys.stderr)
    return valid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-class", type=int, default=30)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY não setada no env", file=sys.stderr)
        sys.exit(1)

    seed = load_seed(args.seed)
    by_class = group_by_class(seed)
    print(f"Seed: {len(seed)} items em {len(by_class)} classes", file=sys.stderr)

    all_items = list(seed)  # mantém os seeds (ground truth humano)
    for cls, examples in by_class.items():
        n_seed = len(examples)
        n_to_gen = max(0, args.per_class - n_seed)
        if n_to_gen == 0:
            continue
        try:
            new_items = generate_for_class(
                cls, examples, n_to_gen,
                api_key=api_key, model=args.model,
            )
            all_items.extend(new_items)
        except Exception as exc:
            print(f"  ✗ Falha em {cls}: {exc}", file=sys.stderr)
        time.sleep(1)  # rate limit politeness

    # Renumera ids garantindo unicidade
    out_items = []
    counters: dict[str, int] = defaultdict(int)
    for it in all_items:
        cls = it["expected_event_type"]
        counters[cls] += 1
        it = {**it, "id": f"{cls}_{counters[cls]:03d}"}
        out_items.append(it)

    with open(args.output, "w") as f:
        yaml.safe_dump(out_items, f, allow_unicode=True, sort_keys=False, width=200)

    print(f"\n✓ {len(out_items)} items salvos em {args.output}", file=sys.stderr)
    print(
        "⚠️  REVISÃO HUMANA OBRIGATÓRIA — itens gerados podem ter rótulos incorretos",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
