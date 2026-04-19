#!/usr/bin/env python3
"""Testa o pipeline de biometria de voz com áudios reais.

Uso:
    # Testar preprocessing e extração (sem DB):
    python scripts/test_voice_biometrics.py --audio demo-assets/audio_samples/audio_01.ogg

    # Comparar dois áudios (mesma pessoa? diferente?):
    python scripts/test_voice_biometrics.py --compare demo-assets/audio_samples/a.ogg demo-assets/audio_samples/b.ogg

    # Enrollment + identify completo (exige DB rodando + caregiver criado):
    python scripts/test_voice_biometrics.py --enroll <caregiver_id> demo-assets/audio_samples/a.ogg
    python scripts/test_voice_biometrics.py --identify demo-assets/audio_samples/x.ogg
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("DEEPGRAM_API_KEY", "x")


def test_preprocessing(path: str) -> None:
    from src.services.audio_preprocessing import preprocess

    with open(path, "rb") as f:
        audio_bytes = f.read()

    print(f"\n=== Preprocessing: {path} ({len(audio_bytes)} bytes) ===")
    result = preprocess(audio_bytes)
    if result is None:
        print("❌ Decode falhou (ffmpeg ausente?)")
        return
    q = result.quality
    print(f"  Duração:         {q.duration_ms}ms")
    print(f"  Speech detectado: {q.speech_duration_ms}ms")
    print(f"  RMS:             {q.rms:.4f}")
    print(f"  SNR estimado:    {q.snr_estimate} dB")
    print(f"  Clipping:        {q.clipping_ratio:.2%}")
    print(f"  Overall quality: {q.overall:.2f}")
    if q.rejection_reason:
        print(f"  ⚠️  REJEITADO: {q.rejection_reason}")
    else:
        print("  ✅ Áudio aprovado para embedding")


def test_compare(path_a: str, path_b: str) -> None:
    import numpy as np
    from resemblyzer import VoiceEncoder, preprocess_wav
    from src.services.audio_preprocessing import preprocess

    print(f"\n=== Comparando: {path_a}  vs  {path_b} ===")
    encoder = VoiceEncoder()
    embeddings = []
    for p in [path_a, path_b]:
        with open(p, "rb") as f:
            audio_bytes = f.read()
        result = preprocess(audio_bytes)
        if result is None or result.quality.rejection_reason:
            print(f"  ❌ {p}: {result.quality.rejection_reason if result else 'decode_failed'}")
            return
        wav_p = preprocess_wav(result.pcm_float32_16k)
        emb = encoder.embed_utterance(wav_p)
        embeddings.append(emb)
        print(f"  ✅ {p}: quality={result.quality.overall:.2f} speech={result.quality.speech_duration_ms}ms")

    e1, e2 = embeddings
    cosine = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))
    print(f"\n  Similaridade cosseno: {cosine:.4f}")
    if cosine >= 0.75:
        print("  🔵 MESMA pessoa (alta confiança)")
    elif cosine >= 0.65:
        print("  🟡 Provavelmente mesma pessoa (confiança moderada)")
    elif cosine >= 0.50:
        print("  🟠 Ambíguo")
    else:
        print("  🔴 Pessoas DIFERENTES")


def test_enroll(caregiver_id: str, path: str) -> None:
    from config.settings import settings
    from src.services.voice_biometrics_service import get_voice_biometrics

    with open(path, "rb") as f:
        audio_bytes = f.read()
    svc = get_voice_biometrics()
    result = svc.enroll(
        caregiver_id=caregiver_id, tenant_id=settings.tenant_id,
        audio_bytes=audio_bytes, sample_label=f"cli_enroll_{Path(path).stem}",
    )
    print(f"\n=== Enroll caregiver={caregiver_id} ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


def test_identify(path: str) -> None:
    from config.settings import settings
    from src.services.voice_biometrics_service import get_voice_biometrics

    with open(path, "rb") as f:
        audio_bytes = f.read()
    svc = get_voice_biometrics()
    result = svc.identify_1toN(settings.tenant_id, audio_bytes)
    print(f"\n=== Identify: {path} ===")
    for k, v in result.items():
        if k == "candidates":
            print(f"  {k}:")
            for c in v:
                print(f"    - {c}")
        else:
            print(f"  {k}: {v}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", help="Testa preprocessing de um áudio")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="Compara dois áudios")
    ap.add_argument("--enroll", nargs=2, metavar=("CID", "AUDIO"), help="Enrolla amostra para caregiver_id (requer DB)")
    ap.add_argument("--identify", metavar="AUDIO", help="Identifica cuidador a partir de áudio (requer DB)")
    args = ap.parse_args()

    if args.audio:
        test_preprocessing(args.audio)
    elif args.compare:
        test_compare(args.compare[0], args.compare[1])
    elif args.enroll:
        test_enroll(args.enroll[0], args.enroll[1])
    elif args.identify:
        test_identify(args.identify)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
