"""Audio bridge — converte entre PCM 8kHz (SIP/PCMU decodado) e PCM 24kHz
(Grok Realtime). Mono 16-bit signed little-endian em ambos os lados.

PJSIP entrega PCM 16-bit nativo após decodar PCMU/PCMA, taxa do clock RTP
(8kHz). Não preciso decodar µ-law manualmente.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("audio_bridge")

SIP_RATE = 8000
GROK_RATE = 24000


def upsample_8k_to_24k(pcm16_8k: bytes) -> bytes:
    """Upsample PCM 16-bit mono de 8kHz pra 24kHz. Razão 1:3."""
    if not pcm16_8k:
        return pcm16_8k
    try:
        import audioop
        out, _ = audioop.ratecv(pcm16_8k, 2, 1, SIP_RATE, GROK_RATE, None)
        return out
    except Exception:
        return _numpy_resample(pcm16_8k, SIP_RATE, GROK_RATE)


def downsample_24k_to_8k(pcm16_24k: bytes) -> bytes:
    """Downsample PCM 16-bit mono de 24kHz pra 8kHz. Razão 3:1."""
    if not pcm16_24k:
        return pcm16_24k
    try:
        import audioop
        out, _ = audioop.ratecv(pcm16_24k, 2, 1, GROK_RATE, SIP_RATE, None)
        return out
    except Exception:
        return _numpy_resample(pcm16_24k, GROK_RATE, SIP_RATE)


def _numpy_resample(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Fallback se audioop não estiver disponível (Python 3.13+)."""
    try:
        import numpy as np
        src = np.frombuffer(pcm, dtype="<i2")
        if len(src) == 0:
            return pcm
        n_out = int(round(len(src) * dst_rate / src_rate))
        x_old = np.arange(len(src))
        x_new = np.linspace(0, len(src) - 1, n_out)
        interp = np.interp(x_new, x_old, src).astype("<i2")
        return interp.tobytes()
    except Exception as exc:
        logger.error("numpy_resample_failed: %s", exc)
        return pcm
