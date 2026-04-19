"""Audio preprocessing para biometria de voz.

Pipeline padrão:
    bytes (qualquer formato) → PCM 16kHz mono float32 → normalized → VAD-trimmed → quality-checked

Pensado para ser robusto com áudios do WhatsApp (OGG/Opus, 16kHz/48kHz, ruído, silêncio).
Funciona sem webrtcvad (usa VAD energético em numpy como fallback).
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger("connectaiacare.audio")

TARGET_SR = 16_000
MIN_SPEECH_MS = 2_000       # mínimo de fala útil
MAX_EMBED_MS = 8_000        # usamos no máximo 8s de fala para embedding (sobra é ruído)
VAD_FRAME_MS = 30           # frames de 30ms para VAD
VAD_MIN_ACTIVE_FRAMES = 8   # mínimo 240ms de fala agrupados
SILENCE_RMS_THRESHOLD = 0.005    # RMS normalizado (fala mínima)
NOISE_RMS_THRESHOLD_LOW = 0.001  # abaixo: áudio essencialmente silêncio → rejeita
CLIP_THRESHOLD = 0.95            # acima: áudio clipado → qualidade ruim
FFMPEG_TIMEOUT_SEC = 20


@dataclass
class AudioQuality:
    """Indicadores de qualidade do áudio processado."""
    duration_ms: int
    speech_duration_ms: int
    rms: float                  # amplitude média normalizada (0-1)
    snr_estimate: float | None  # estimativa de signal-to-noise ratio (dB), pode ser None
    clipping_ratio: float       # fração de samples saturados
    overall: float              # score 0-1 (0=ruim, 1=ótimo)
    rejection_reason: str | None  # None se passou; string curta se rejeitado


@dataclass
class ProcessedAudio:
    pcm_float32_16k: np.ndarray  # mono, float32, 16kHz, normalizado
    quality: AudioQuality

    @property
    def ok(self) -> bool:
        return self.quality.rejection_reason is None


# ──────────────────────────────────────────────────────────────────
# Decoding (qualquer formato → PCM 16kHz mono float32)
# ──────────────────────────────────────────────────────────────────

def decode_any_to_pcm_16k(audio_bytes: bytes, hinted_sr: int = 0) -> np.ndarray | None:
    """Decodifica bytes de qualquer formato comum para PCM float32 16kHz mono.

    Estratégia:
    1. Se `hinted_sr` > 0, assume PCM16 raw e faz resample direto (rápido).
    2. Senão, chama ffmpeg via subprocess (robusto para OGG/OPUS/M4A/MP3/WAV).
    """
    if hinted_sr > 0:
        try:
            int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            f32 = int16.astype(np.float32) / 32768.0
            if hinted_sr == TARGET_SR:
                return f32
            return _resample(f32, hinted_sr, TARGET_SR)
        except Exception as exc:
            logger.warning("pcm_raw_decode_failed error=%s fallback=ffmpeg", exc)

    return _decode_via_ffmpeg(audio_bytes)


def _decode_via_ffmpeg(audio_bytes: bytes) -> np.ndarray | None:
    if not _has_ffmpeg():
        logger.error("ffmpeg_not_available — installing ffmpeg is required for non-PCM audio")
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as fin:
            fin.write(audio_bytes)
            fin.flush()
            proc = subprocess.run(
                [
                    "ffmpeg", "-v", "error",
                    "-i", fin.name,
                    "-f", "s16le",
                    "-ar", str(TARGET_SR),
                    "-ac", "1",
                    "-",
                ],
                capture_output=True,
                timeout=FFMPEG_TIMEOUT_SEC,
                check=False,
            )
        if proc.returncode != 0:
            logger.error("ffmpeg_decode_nonzero rc=%s stderr=%s", proc.returncode, proc.stderr.decode("utf-8", "ignore")[:200])
            return None
        int16 = np.frombuffer(proc.stdout, dtype=np.int16)
        return (int16.astype(np.float32) / 32768.0)
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg_timeout after=%ss", FFMPEG_TIMEOUT_SEC)
        return None
    except Exception as exc:
        logger.error("ffmpeg_exception error=%s", exc)
        return None


def _has_ffmpeg() -> bool:
    if os.environ.get("_FFMPEG_UNAVAILABLE"):
        return False
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3, check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _resample(wav: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return wav
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(src_sr, dst_sr)
        return resample_poly(wav, dst_sr // g, src_sr // g).astype(np.float32)
    except ImportError:
        # fallback linear (menos preciso mas funcional)
        target_len = int(len(wav) * dst_sr / src_sr)
        indices = np.linspace(0, len(wav) - 1, target_len)
        return np.interp(indices, np.arange(len(wav)), wav).astype(np.float32)


# ──────────────────────────────────────────────────────────────────
# Normalização
# ──────────────────────────────────────────────────────────────────

def normalize_peak(wav: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    """Normaliza para pico alvo. Evita divisão por zero."""
    peak = float(np.max(np.abs(wav)))
    if peak < 1e-6:
        return wav
    return (wav * (target_peak / peak)).astype(np.float32)


# ──────────────────────────────────────────────────────────────────
# VAD (Voice Activity Detection) — energético, sem deps pesadas
# ──────────────────────────────────────────────────────────────────

def energy_vad(wav: np.ndarray, sr: int = TARGET_SR) -> np.ndarray:
    """Retorna array bool de mesmo tamanho que wav: True onde há fala.

    Abordagem: RMS em janelas de 30ms; frame é "fala" se RMS > threshold adaptativo.
    Adaptativo = base_noise + delta, medido pelo percentil 20 do sinal.
    """
    frame_len = int(sr * VAD_FRAME_MS / 1000)
    if frame_len <= 0 or len(wav) < frame_len:
        return np.zeros(len(wav), dtype=bool)

    n_frames = len(wav) // frame_len
    rms_per_frame = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = wav[i * frame_len: (i + 1) * frame_len]
        rms_per_frame[i] = float(np.sqrt(np.mean(chunk ** 2)))

    # Threshold adaptativo: percentil 20 + margem
    noise_floor = float(np.percentile(rms_per_frame, 20))
    threshold = max(noise_floor * 2.5, SILENCE_RMS_THRESHOLD)

    frame_is_speech = rms_per_frame > threshold

    # Suaviza: grupos muito curtos viram silêncio
    frame_is_speech = _smooth_frames(frame_is_speech, min_run=VAD_MIN_ACTIVE_FRAMES // 3)

    # Expande para per-sample
    per_sample = np.repeat(frame_is_speech, frame_len)
    if len(per_sample) < len(wav):
        per_sample = np.concatenate([per_sample, np.zeros(len(wav) - len(per_sample), dtype=bool)])
    return per_sample[: len(wav)]


def _smooth_frames(mask: np.ndarray, min_run: int = 3) -> np.ndarray:
    """Remove 'ilhas' curtas de fala/silêncio (< min_run frames)."""
    if len(mask) == 0:
        return mask
    out = mask.copy()
    # Fechar buracos curtos de silêncio entre fala
    i = 0
    while i < len(out):
        if not out[i]:
            j = i
            while j < len(out) and not out[j]:
                j += 1
            # Buraco curto entre duas regiões de fala → preencher
            if 0 < i and j < len(out) and (j - i) < min_run:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def extract_speech_segment(
    wav: np.ndarray, sr: int = TARGET_SR, max_ms: int = MAX_EMBED_MS
) -> np.ndarray:
    """Extrai o melhor segmento contínuo de fala, até `max_ms`.

    Útil para mandar só áudio com fala pro encoder (reduz contaminação).
    """
    vad_mask = energy_vad(wav, sr)
    if not vad_mask.any():
        return wav[: int(sr * max_ms / 1000)]  # fallback: primeiros N segundos

    # Acha o maior run contínuo
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for i, is_speech in enumerate(vad_mask):
        if is_speech and not in_run:
            start, in_run = i, True
        elif not is_speech and in_run:
            runs.append((start, i))
            in_run = False
    if in_run:
        runs.append((start, len(vad_mask)))

    if not runs:
        return wav[: int(sr * max_ms / 1000)]

    # Pega o maior run
    best = max(runs, key=lambda r: r[1] - r[0])
    s, e = best
    max_samples = int(sr * max_ms / 1000)
    return wav[s: min(s + max_samples, e)]


# ──────────────────────────────────────────────────────────────────
# Quality scoring + rejeição
# ──────────────────────────────────────────────────────────────────

def compute_quality(wav: np.ndarray, vad_mask: np.ndarray | None = None, sr: int = TARGET_SR) -> AudioQuality:
    duration_ms = int(len(wav) * 1000 / sr)
    rms = float(np.sqrt(np.mean(wav ** 2))) if len(wav) else 0.0

    if vad_mask is None:
        vad_mask = energy_vad(wav, sr)
    speech_samples = int(vad_mask.sum()) if len(vad_mask) else 0
    speech_ms = int(speech_samples * 1000 / sr)

    # Clipping
    clipping_ratio = float(np.mean(np.abs(wav) > CLIP_THRESHOLD)) if len(wav) else 0.0

    # SNR estimado: RMS(fala) vs RMS(silêncio)
    snr_db: float | None = None
    if vad_mask.any() and (~vad_mask).any():
        speech_rms = float(np.sqrt(np.mean(wav[vad_mask] ** 2))) if vad_mask.sum() else 0.0
        noise_rms = float(np.sqrt(np.mean(wav[~vad_mask] ** 2))) if (~vad_mask).sum() else 1e-9
        if speech_rms > 0 and noise_rms > 0:
            snr_db = 20.0 * np.log10(speech_rms / max(noise_rms, 1e-9))

    # Score global (heurística)
    score = 1.0
    if rms < NOISE_RMS_THRESHOLD_LOW:
        score = 0.0
    else:
        # penaliza áudio curto
        if speech_ms < MIN_SPEECH_MS:
            score *= max(0.2, speech_ms / MIN_SPEECH_MS)
        # penaliza clipping
        if clipping_ratio > 0.05:
            score *= max(0.3, 1 - clipping_ratio * 2)
        # bonifica SNR bom (> 15 dB é bom)
        if snr_db is not None:
            if snr_db < 5:
                score *= 0.5
            elif snr_db < 10:
                score *= 0.75

    # Rejeições explícitas
    rejection: str | None = None
    if rms < NOISE_RMS_THRESHOLD_LOW:
        rejection = "audio_silencioso"
    elif speech_ms < MIN_SPEECH_MS:
        rejection = f"fala_insuficiente_{speech_ms}ms"
    elif clipping_ratio > 0.20:
        rejection = f"audio_clipado_{clipping_ratio:.0%}"
    elif snr_db is not None and snr_db < 3:
        rejection = f"snr_baixo_{snr_db:.1f}dB"

    return AudioQuality(
        duration_ms=duration_ms,
        speech_duration_ms=speech_ms,
        rms=round(rms, 4),
        snr_estimate=round(snr_db, 1) if snr_db is not None else None,
        clipping_ratio=round(clipping_ratio, 4),
        overall=round(score, 3),
        rejection_reason=rejection,
    )


# ──────────────────────────────────────────────────────────────────
# Pipeline completo
# ──────────────────────────────────────────────────────────────────

def preprocess(
    audio_bytes: bytes,
    hinted_sr: int = 0,
    trim_to_speech: bool = True,
    normalize: bool = True,
    max_ms: int = MAX_EMBED_MS,
) -> Optional[ProcessedAudio]:
    """Faz decode + normalize + (opcional) trim → retorna ProcessedAudio com quality.

    Retorna None apenas se o decode falhar completamente. Para casos de baixa qualidade,
    retorna ProcessedAudio com `quality.rejection_reason` populado; caller decide o que fazer.
    """
    wav = decode_any_to_pcm_16k(audio_bytes, hinted_sr=hinted_sr)
    if wav is None or len(wav) < TARGET_SR:  # menos de 1s
        return None

    if normalize:
        wav = normalize_peak(wav)

    vad_mask = energy_vad(wav, TARGET_SR)
    quality = compute_quality(wav, vad_mask=vad_mask, sr=TARGET_SR)

    if trim_to_speech and vad_mask.any():
        wav = extract_speech_segment(wav, TARGET_SR, max_ms=max_ms)

    return ProcessedAudio(pcm_float32_16k=wav, quality=quality)
