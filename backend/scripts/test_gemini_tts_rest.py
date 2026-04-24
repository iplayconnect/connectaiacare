"""Teste Gemini 3.1 Flash TTS via REST direto (contorna limitação do SDK Python).

O SDK `google-generativeai` não expõe `response_modalities` na versão atual.
A API REST v1beta aceita esse campo. Contornamos chamando direto via httpx.

Docs: https://ai.google.dev/gemini-api/docs/speech-generation
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

OUTPUT_DIR = Path("/app/storage/gemini_tests")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Modelos TTS disponíveis (Gemini 3.1 Flash TTS)
TTS_MODEL_CANDIDATES = [
    "gemini-3.1-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",  # TTS oficial disponível hoje
    "gemini-2.5-pro-preview-tts",
]

TTS_SAMPLES = [
    {
        "name": "checkin_warm",
        "desc": "Check-in matinal — tom acolhedor",
        "text": (
            "Say warmly: Bom dia Juliana, tudo certo por aí? "
            "Só queria ver como a Dona Maria amanheceu hoje."
        ),
        "voice": "Kore",  # voz feminina Gemini TTS
    },
    {
        "name": "attention_change",
        "desc": "Mudança atenção — tom sério mas calmo",
        "text": (
            "Say in a serious but calm tone: Juliana, aqui é a Sofia. "
            "Notei uma alteração na pressão da sua mãe hoje. "
            "Está controlada, mas quero te avisar."
        ),
        "voice": "Kore",
    },
    {
        "name": "urgent_fall",
        "desc": "Queda — tom urgente e direto",
        "text": (
            "Say urgently and firmly: Juliana, a Dona Maria caiu. "
            "Chamei o SAMU, eles já estão a caminho. "
            "Você precisa ir pra casa dela agora."
        ),
        "voice": "Kore",
    },
    {
        "name": "reassurance",
        "desc": "Confirmação após susto — tom tranquilizador",
        "text": (
            "Say gently and warmly: Oi Juliana, a Dona Maria está bem. "
            "Foi só um susto, ela já está sentada, comeu um pão e tomou água. "
            "Tudo tranquilo aqui."
        ),
        "voice": "Kore",
    },
]


def tts_generate(model: str, text: str, voice: str) -> tuple[bytes | None, str, int]:
    """Chama Gemini TTS via REST. Retorna (audio_bytes, error, latency_ms)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GOOGLE_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                },
            },
        },
    }

    t_start = time.time()
    try:
        resp = httpx.post(url, json=payload, timeout=60.0)
        latency_ms = int((time.time() - t_start) * 1000)
    except httpx.RequestError as exc:
        return None, f"network: {exc}", 0

    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}", latency_ms

    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        for part in parts:
            if "inlineData" in part and part["inlineData"].get("mimeType", "").startswith("audio/"):
                b64 = part["inlineData"]["data"]
                return base64.b64decode(b64), "", latency_ms
        return None, "sem audio na resposta", latency_ms
    except (KeyError, IndexError) as exc:
        return None, f"shape inesperado: {exc}", latency_ms


def main():
    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_API_KEY não definida.")
        return

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Gemini TTS via REST — ConnectaIACare")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    # Descobre qual modelo TTS está disponível
    working_model = None
    print("🔎 Procurando modelo TTS disponível...")
    for candidate in TTS_MODEL_CANDIDATES:
        audio, err, _ = tts_generate(
            candidate, "Olá. Teste de um dois três.", "Kore",
        )
        if audio:
            working_model = candidate
            print(f"   ✓ {candidate} ATIVO")
            break
        else:
            print(f"   ✗ {candidate}: {err[:100]}")

    if not working_model:
        print("\n❌ Nenhum modelo TTS Gemini disponível na API pública.")
        print("   Provavelmente requer Vertex AI com projeto GCP.")
        return

    print(f"\n🔊 Gerando {len(TTS_SAMPLES)} samples com {working_model}...")
    results = []

    for sample in TTS_SAMPLES:
        audio, err, latency_ms = tts_generate(
            working_model, sample["text"], sample["voice"],
        )
        if audio:
            out_path = OUTPUT_DIR / f"tts_{sample['name']}.wav"
            out_path.write_bytes(audio)
            print(
                f"   ✓ {sample['name']:25s} ({latency_ms}ms, {len(audio)} bytes) "
                f"→ {out_path.name}"
            )
            results.append({**sample, "file": out_path.name, "latency": latency_ms, "size": len(audio)})
        else:
            print(f"   ❌ {sample['name']}: {err[:120]}")

    # Atualiza report.md com seção TTS
    if results:
        report_path = OUTPUT_DIR / "report.md"
        if report_path.exists():
            content = report_path.read_text(encoding="utf-8")
            tts_section = "\n\n## 2b. TTS via REST (retry) — SUCESSO\n\n"
            tts_section += f"- **Modelo**: `{working_model}`\n"
            tts_section += f"- **Samples gerados**: {len(results)}\n"
            tts_section += f"- **Voz**: Kore (feminina)\n\n"
            tts_section += "| Cenário | Tamanho | Latência | Arquivo |\n"
            tts_section += "|---------|---------|----------|---------|\n"
            for r in results:
                tts_section += f"| {r['desc']} | {r['size']/1024:.1f} KB | {r['latency']}ms | `{r['file']}` |\n"
            report_path.write_text(content + tts_section, encoding="utf-8")
            print(f"\n✅ Report atualizado: {report_path}")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"   TTS samples: {len(results)}/{len(TTS_SAMPLES)}")
    print(f"   Output: {OUTPUT_DIR}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
