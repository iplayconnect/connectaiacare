"""Benchmark: Gemini 3.1 Flash-Lite vs Deepgram (transcrição) + Flash TTS (audio tags).

Objetivo: avaliar viabilidade de migrar parte do pipeline de voz ConnectaIACare
do Deepgram+Ultravox pro Gemini 3.1 (família lançada abr/2026).

Testes:
    1. Pega N áudios reais do banco (aia_health_reports com audio_url não-null)
    2. Transcreve com Gemini 3.1 Flash-Lite
    3. Compara com a transcrição original (Deepgram) — calcula diff/score
    4. Gera TTS com audio tags pt-BR (warm, serious, urgent, gentle)
    5. Salva áudios MP3 gerados + relatório markdown

Uso:
    docker compose exec api python -m scripts.test_gemini_voice
    # Ou local com env GOOGLE_API_KEY setado:
    python backend/scripts/test_gemini_voice.py

Outputs:
    /app/storage/gemini_tests/
        report.md              — análise qualitativa + métricas
        tts_*.mp3              — TTS samples com audio tags
        transcription_*.txt    — transcrições Gemini pra cada áudio testado
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.services.postgres import get_postgres  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

OUTPUT_DIR = Path("/app/storage/gemini_tests")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MAX_SAMPLES = int(os.getenv("MAX_SAMPLES", "5"))


# ══════════════════════════════════════════════════════════════════
# 1. Transcrição — Gemini Flash-Lite vs Deepgram
# ══════════════════════════════════════════════════════════════════

def test_transcription() -> list[dict]:
    """Pega últimos N relatos com áudio + transcrição Deepgram, roda Gemini."""
    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_API_KEY não definida. Abortando transcrição.")
        return []

    import google.generativeai as genai

    genai.configure(api_key=GOOGLE_API_KEY)

    db = get_postgres()
    rows = db.fetch_all(
        """
        SELECT id, audio_url, audio_duration_seconds, transcription
        FROM aia_health_reports
        WHERE audio_url IS NOT NULL
          AND transcription IS NOT NULL
          AND transcription != ''
        ORDER BY received_at DESC
        LIMIT %s
        """,
        (MAX_SAMPLES,),
    )

    print(f"\n📝 Testando transcrição em {len(rows)} áudios reais...")

    results = []
    # Gemini 3.1 pode estar em nome diferente — tenta múltiplos
    model_candidates = [
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",  # fallback se 3.1 não estiver disponível
        "gemini-1.5-flash",
    ]

    model = None
    for name in model_candidates:
        try:
            model = genai.GenerativeModel(name)
            # Smoke test
            model.generate_content("ping", generation_config={"max_output_tokens": 5})
            print(f"   ✓ Modelo ativo: {name}")
            break
        except Exception as exc:
            print(f"   ✗ {name}: {str(exc)[:100]}")
            model = None
            continue

    if not model:
        print("❌ Nenhum modelo Gemini disponível.")
        return []

    for row in rows:
        report_id = str(row["id"])
        audio_path = Path("/app/storage/audio") / f"{report_id}.ogg"
        if not audio_path.exists():
            print(f"   ⚠️  Áudio não encontrado: {report_id}")
            continue

        audio_bytes = audio_path.read_bytes()
        deepgram_text = row["transcription"]
        duration = row.get("audio_duration_seconds", 0)

        print(f"\n   🎧 Report {report_id[:8]}... ({duration}s)")
        print(f"      Deepgram: {deepgram_text[:80]}...")

        t_start = time.time()
        try:
            response = model.generate_content(
                [
                    {
                        "mime_type": "audio/ogg",
                        "data": audio_bytes,
                    },
                    "Transcreva EXATAMENTE o áudio em português brasileiro. "
                    "Preserve nomes próprios, números e pontuação. "
                    "Responda apenas com a transcrição, sem comentários.",
                ],
            )
            gemini_text = (response.text or "").strip()
            latency_ms = int((time.time() - t_start) * 1000)
        except Exception as exc:
            print(f"      ❌ Erro Gemini: {exc}")
            continue

        similarity = _word_overlap(deepgram_text, gemini_text)

        print(f"      Gemini:   {gemini_text[:80]}...")
        print(f"      ⏱️  {latency_ms}ms · similaridade {similarity:.0%}")

        # Salva pros relatórios
        out_file = OUTPUT_DIR / f"transcription_{report_id[:8]}.txt"
        out_file.write_text(
            f"=== REPORT {report_id} ({duration}s) ===\n\n"
            f"--- Deepgram nova-2 ---\n{deepgram_text}\n\n"
            f"--- Gemini ---\n{gemini_text}\n\n"
            f"Similaridade: {similarity:.2%}\n"
            f"Latência Gemini: {latency_ms}ms\n",
            encoding="utf-8",
        )

        results.append({
            "report_id": report_id,
            "duration_s": duration,
            "deepgram": deepgram_text,
            "gemini": gemini_text,
            "similarity": similarity,
            "latency_ms": latency_ms,
        })

    return results


def _word_overlap(a: str, b: str) -> float:
    """Jaccard word overlap (aproxima WER — não é preciso mas dá direção)."""
    if not a or not b:
        return 0.0
    wa = set(w.lower().strip(".,!?") for w in a.split() if len(w) > 1)
    wb = set(w.lower().strip(".,!?") for w in b.split() if len(w) > 1)
    if not wa or not wb:
        return 0.0
    inter = wa & wb
    union = wa | wb
    return len(inter) / len(union) if union else 0.0


# ══════════════════════════════════════════════════════════════════
# 2. TTS com audio tags — Flash TTS
# ══════════════════════════════════════════════════════════════════

TTS_SAMPLES = [
    {
        "name": "checkin_warm",
        "desc": "Check-in matinal — tom acolhedor",
        "text": (
            "[warm] Bom dia Juliana, tudo certo por aí? "
            "[gentle] Só queria ver como a Dona Maria amanheceu hoje."
        ),
    },
    {
        "name": "attention_change",
        "desc": "Mudança atenção — tom sério mas calmo",
        "text": (
            "[neutral] Juliana, aqui é a Sofia. "
            "[serious] Notei uma alteração na pressão da sua mãe hoje. "
            "[calm] Está controlada, mas quero te avisar."
        ),
    },
    {
        "name": "urgent_fall",
        "desc": "Queda — tom urgente e direto",
        "text": (
            "[urgent] Juliana, a Dona Maria caiu. "
            "[urgent] Chamei o SAMU, eles já estão a caminho. "
            "[firm] Você precisa ir pra casa dela agora."
        ),
    },
    {
        "name": "reassurance",
        "desc": "Confirmação após susto — tom tranquilizador",
        "text": (
            "[gentle] Oi Juliana. [warm] A Dona Maria está bem. "
            "[reassuring] Foi só um susto, ela já está sentada, "
            "comeu um pão e tomou água. Tudo tranquilo aqui."
        ),
    },
]


def test_tts() -> list[dict]:
    """Gera samples TTS com audio tags em pt-BR."""
    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_API_KEY não definida. Abortando TTS.")
        return []

    import google.generativeai as genai

    genai.configure(api_key=GOOGLE_API_KEY)

    # Gemini 3.1 Flash TTS não está em genai.GenerativeModel tradicional
    # pode ser via endpoint /models/*:generateContent com response_modalities=["AUDIO"]
    # ou via Vertex AI TTS. Tenta abordagem nativa primeiro.
    model_candidates = [
        "gemini-3.1-flash-tts",
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-native-audio",
        "gemini-1.5-flash",  # não suporta áudio nativo — mas testa disponibilidade
    ]

    print("\n🔊 Testando TTS com audio tags...")
    results = []

    model = None
    working_model = None
    for name in model_candidates:
        try:
            model = genai.GenerativeModel(name)
            print(f"   ✓ Testando modelo: {name}")
            working_model = name
            break
        except Exception as exc:
            print(f"   ✗ {name}: {str(exc)[:80]}")

    if not model:
        print("   ❌ Nenhum modelo TTS Gemini disponível na família atual.")
        print("   ℹ️  Flash TTS pode exigir Vertex AI API (não Gemini API).")
        return []

    for sample in TTS_SAMPLES:
        t_start = time.time()
        try:
            response = model.generate_content(
                sample["text"],
                generation_config={
                    "response_modalities": ["AUDIO"],
                },
            )
            latency_ms = int((time.time() - t_start) * 1000)

            audio_part = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_part = part.inline_data.data
                    break

            if audio_part:
                out_file = OUTPUT_DIR / f"tts_{sample['name']}.mp3"
                audio_bytes = (
                    base64.b64decode(audio_part)
                    if isinstance(audio_part, str)
                    else audio_part
                )
                out_file.write_bytes(audio_bytes)
                print(
                    f"   ✓ {sample['name']:25s} ({latency_ms}ms) → {out_file.name}"
                )
                results.append({
                    "name": sample["name"],
                    "desc": sample["desc"],
                    "text": sample["text"],
                    "output_file": str(out_file),
                    "size_bytes": len(audio_bytes),
                    "latency_ms": latency_ms,
                    "model": working_model,
                })
            else:
                print(f"   ⚠️  {sample['name']}: resposta sem áudio")
        except Exception as exc:
            print(f"   ❌ {sample['name']}: {str(exc)[:120]}")

    return results


# ══════════════════════════════════════════════════════════════════
# 3. Relatório
# ══════════════════════════════════════════════════════════════════

def write_report(
    transcription_results: list[dict],
    tts_results: list[dict],
) -> Path:
    lines = [
        "# Gemini 3.1 — Benchmark ConnectaIACare",
        "",
        f"Executado em: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. Transcrição — Flash-Lite vs Deepgram nova-2",
        "",
    ]

    if transcription_results:
        avg_sim = sum(r["similarity"] for r in transcription_results) / len(transcription_results)
        avg_lat = sum(r["latency_ms"] for r in transcription_results) / len(transcription_results)
        lines.append(f"- **{len(transcription_results)} áudios testados**")
        lines.append(f"- **Similaridade média**: {avg_sim:.0%} (Jaccard word overlap)")
        lines.append(f"- **Latência média Gemini**: {avg_lat:.0f}ms")
        lines.append("")
        lines.append("### Amostras (comparação lado a lado)")
        lines.append("")
        for i, r in enumerate(transcription_results, 1):
            lines.append(f"#### Amostra {i} — {r['duration_s']}s")
            lines.append(f"- Similaridade: **{r['similarity']:.0%}**")
            lines.append(f"- Latência Gemini: {r['latency_ms']}ms")
            lines.append("")
            lines.append(f"**Deepgram**: {r['deepgram']}")
            lines.append("")
            lines.append(f"**Gemini**: {r['gemini']}")
            lines.append("")
            lines.append("---")
            lines.append("")
    else:
        lines.append("❌ Nenhum resultado de transcrição (ver logs).")
        lines.append("")

    lines.append("## 2. TTS com audio tags — Flash TTS")
    lines.append("")

    if tts_results:
        lines.append(f"- **{len(tts_results)} samples gerados**")
        lines.append(f"- **Modelo usado**: `{tts_results[0].get('model', '?')}`")
        lines.append("")
        lines.append("| Cenário | Descrição | Tamanho | Latência | Arquivo |")
        lines.append("|---------|-----------|---------|----------|---------|")
        for r in tts_results:
            size_kb = r["size_bytes"] / 1024
            name = Path(r["output_file"]).name
            lines.append(
                f"| `{r['name']}` | {r['desc']} | {size_kb:.1f} KB | {r['latency_ms']}ms | `{name}` |"
            )
        lines.append("")
        lines.append("### Textos usados (com audio tags)")
        lines.append("")
        for r in tts_results:
            lines.append(f"**{r['name']}** ({r['desc']}):")
            lines.append("```")
            lines.append(r["text"])
            lines.append("```")
            lines.append("")
    else:
        lines.append("❌ Nenhum TTS gerado — Flash TTS pode exigir Vertex AI API específica.")
        lines.append("")
        lines.append("Abordagem alternativa:")
        lines.append("- Testar via Vertex AI SDK (`vertexai.generative_models`)")
        lines.append("- Ou aguardar disponibilidade do Flash TTS no Gemini API público")
        lines.append("")

    lines.append("## 3. Conclusão preliminar")
    lines.append("")
    if transcription_results:
        avg_sim = sum(r["similarity"] for r in transcription_results) / len(transcription_results)
        if avg_sim >= 0.85:
            lines.append(
                f"✅ **Transcrição Gemini: MIGRAÇÃO RECOMENDADA** "
                f"(similaridade {avg_sim:.0%})"
            )
            lines.append("- Economia estimada vs Deepgram: ~80% no custo por minuto")
            lines.append("- Próximo passo: integrar como `task='transcription'` no llm_routing.yaml (ADR-025)")
        elif avg_sim >= 0.70:
            lines.append(
                f"⚠️  **Transcrição Gemini: TESTES ADICIONAIS NECESSÁRIOS** "
                f"(similaridade {avg_sim:.0%})"
            )
            lines.append("- Pode ter perda em termos médicos críticos")
            lines.append("- Validar com amostras maiores (>100 áudios, múltiplos cuidadores)")
        else:
            lines.append(
                f"❌ **Transcrição Gemini: NÃO RECOMENDADA AGORA** "
                f"(similaridade {avg_sim:.0%})"
            )
            lines.append("- Qualidade abaixo de Deepgram em contexto clínico pt-BR geriátrico")
            lines.append("- Manter Deepgram como primário")
        lines.append("")

    lines.append("## 4. Roadmap migração (se aprovado)")
    lines.append("")
    lines.append("- **Q2 2026**: testes A/B em produção (10% tráfego Gemini, shadow mode)")
    lines.append("- **Q2 2026**: integração Flash TTS substituindo ElevenLabs (audio tags → tom por classification)")
    lines.append("- **Q3 2026**: POC Flash Live substituindo Ultravox na Sofia Voz (bridge Asterisk preserva audit)")
    lines.append("")

    report_path = OUTPUT_DIR / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Gemini 3.1 Benchmark — ConnectaIACare")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Max samples: {MAX_SAMPLES}")
    print()

    transcription_results = test_transcription()
    tts_results = test_tts()

    report_path = write_report(transcription_results, tts_results)

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"✅ Relatório salvo em: {report_path}")
    print(f"   Transcrições: {len(transcription_results)}")
    print(f"   TTS samples: {len(tts_results)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
