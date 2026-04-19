"""Voice Biometrics Service — identificação de cuidadores por voz.

Adaptado do serviço em produção na ConnectaIA (Resemblyzer + pgvector).

Fluxo no contexto ConnectaIACare:
  1. **Enrollment** — cuidador grava 3 amostras de ~5s (onboarding). Cada
     amostra vira um embedding de 256-dim armazenado em pgvector.
  2. **Identification (1:N)** — a cada relato, extraímos embedding dos
     primeiros 5s do áudio e comparamos contra todos os cuidadores ATIVOS
     do tenant (busca por similaridade cosseno via pgvector).
  3. **Verification (1:1)** — opcional, quando já sabemos o número do
     cuidador (match inicial por phone) e queremos confirmar.
  4. **Fallback** — se nenhum caregiver reconhecido, o relato segue mas
     fica marcado como "caregiver não identificado". Phone é usado como
     identidade alternativa.

Thresholds conservadores (plantão = operação crítica):
  - 1:1 ≥ 0.75: reconhecido com alta confiança
  - 1:N ≥ 0.65: reconhecido em varredura do tenant
  - Abaixo: não reconhecido, flaggar para revisão manual
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("connectaiacare.voice_biometrics")

VERIFY_1TO1_THRESHOLD = 0.75
IDENTIFY_1TON_THRESHOLD = 0.65
MAX_ENROLLMENT_SAMPLES = 5
MIN_SAMPLES_FOR_COMPLETE = 3
MIN_AUDIO_DURATION_MS = 2000  # 2s mínimo


class VoiceBiometricsService:
    """Speaker identification usando Resemblyzer (256-dim embeddings)."""

    def __init__(self, postgres_service=None):
        self.postgres = postgres_service
        self._encoder = None
        self._encoder_lock = None
        logger.info("VoiceBiometricsService inicializado (lazy-load Resemblyzer)")

    # ══════════════════════════════════════════════════════════════════
    # Lazy-load do modelo Resemblyzer (~50MB, carrega na primeira chamada)
    # ══════════════════════════════════════════════════════════════════

    def _ensure_encoder(self):
        if self._encoder is not None:
            return self._encoder

        if self._encoder_lock is None:
            import threading
            self._encoder_lock = threading.Lock()

        with self._encoder_lock:
            if self._encoder is not None:
                return self._encoder
            logger.info("carregando Resemblyzer VoiceEncoder (~50MB)...")
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder()
            logger.info("Resemblyzer carregado")
            return self._encoder

    # ══════════════════════════════════════════════════════════════════
    # Processamento de áudio
    # ══════════════════════════════════════════════════════════════════

    def _bytes_to_wav_array(self, audio_bytes: bytes, sample_rate: int) -> np.ndarray | None:
        """Converte bytes (OGG/OPUS/PCM) para array float32 16kHz mono.

        Para áudio WhatsApp (OGG/OPUS), usamos ffmpeg via subprocess.
        Para PCM16, conversão direta.
        """
        try:
            if sample_rate == 0:  # auto-detect via ffmpeg
                return self._decode_via_ffmpeg(audio_bytes)
            # PCM16 raw
            int16_array = np.frombuffer(audio_bytes, dtype=np.int16)
            float32_array = int16_array.astype(np.float32) / 32768.0
            if sample_rate == 16000:
                return float32_array
            # Resample
            try:
                from scipy.signal import resample
                target_samples = int(len(float32_array) * 16000 / sample_rate)
                return resample(float32_array, target_samples).astype(np.float32)
            except ImportError:
                return float32_array
        except Exception as exc:
            logger.error("audio_decode_failed error=%s", exc)
            return None

    def _decode_via_ffmpeg(self, audio_bytes: bytes) -> np.ndarray | None:
        """Decodifica qualquer formato via ffmpeg → WAV 16kHz mono float32."""
        import subprocess
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix=".input", delete=True) as fin:
                fin.write(audio_bytes)
                fin.flush()
                proc = subprocess.run(
                    [
                        "ffmpeg", "-v", "error", "-i", fin.name,
                        "-f", "s16le", "-ar", "16000", "-ac", "1", "-",
                    ],
                    capture_output=True,
                    timeout=30,
                )
            if proc.returncode != 0:
                logger.error("ffmpeg_failed stderr=%s", proc.stderr.decode()[:200])
                return None
            int16_array = np.frombuffer(proc.stdout, dtype=np.int16)
            return (int16_array.astype(np.float32) / 32768.0)
        except Exception as exc:
            logger.error("ffmpeg_decode_failed error=%s", exc)
            return None

    def _extract_embedding(self, audio_bytes: bytes, sample_rate: int = 0) -> np.ndarray | None:
        """Extrai embedding 256-dim do áudio. `sample_rate=0` = auto-detect via ffmpeg."""
        wav = self._bytes_to_wav_array(audio_bytes, sample_rate)
        if wav is None or len(wav) < 32000:
            logger.warning(
                "audio_too_short_or_invalid samples=%s", len(wav) if wav is not None else None
            )
            return None

        encoder = self._ensure_encoder()
        from resemblyzer import preprocess_wav
        processed = preprocess_wav(wav)
        return encoder.embed_utterance(processed)

    # ══════════════════════════════════════════════════════════════════
    # Enrollment
    # ══════════════════════════════════════════════════════════════════

    def enroll(
        self,
        caregiver_id: str,
        tenant_id: str,
        audio_bytes: bytes,
        sample_label: str = "enrollment",
        consent_ip: str = "",
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        """Cadastra uma amostra de voz para um cuidador."""
        if not self.postgres:
            return {"success": False, "message": "Serviço de banco indisponível"}

        current = self._count_samples(caregiver_id, tenant_id)
        if current >= MAX_ENROLLMENT_SAMPLES:
            return {
                "success": False,
                "message": f"Limite de {MAX_ENROLLMENT_SAMPLES} amostras atingido.",
            }

        embedding = self._extract_embedding(audio_bytes, sample_rate)
        if embedding is None:
            return {"success": False, "message": "Falha ao extrair embedding (áudio curto ou ruim)."}

        quality = self._quality_score(audio_bytes)
        embedding_str = "[" + ",".join(str(float(v)) for v in embedding) + "]"

        try:
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_embeddings
                    (caregiver_id, tenant_id, embedding, sample_label, quality_score, consent_ip)
                VALUES (%s, %s, %s::vector, %s, %s, %s)
                """,
                (caregiver_id, tenant_id, embedding_str, sample_label, quality, consent_ip),
            )
            new_count = current + 1
            logger.info(
                "voice_enrollment_saved caregiver=%s samples=%d/%d quality=%.3f",
                caregiver_id, new_count, MAX_ENROLLMENT_SAMPLES, quality,
            )
            return {
                "success": True,
                "samples_count": new_count,
                "samples_needed": max(0, MIN_SAMPLES_FOR_COMPLETE - new_count),
                "quality_score": round(quality, 3),
                "enrollment_complete": new_count >= MIN_SAMPLES_FOR_COMPLETE,
            }
        except Exception as exc:
            logger.error("voice_enrollment_db_failed error=%s", exc)
            return {"success": False, "message": str(exc)}

    # ══════════════════════════════════════════════════════════════════
    # Verification 1:1 (cuidador conhecido via phone)
    # ══════════════════════════════════════════════════════════════════

    def verify_1to1(
        self,
        caregiver_id: str,
        tenant_id: str,
        audio_bytes: bytes,
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        embedding = self._extract_embedding(audio_bytes, sample_rate)
        if embedding is None:
            return {"verified": False, "score": 0.0, "method": "1:1", "reason": "embedding_failed"}

        embedding_str = "[" + ",".join(str(float(v)) for v in embedding) + "]"
        rows = self.postgres.fetch_all(
            """
            SELECT 1 - (embedding <=> %s::vector) AS similarity, quality_score
            FROM aia_health_voice_embeddings
            WHERE caregiver_id = %s AND tenant_id = %s
            ORDER BY similarity DESC
            LIMIT 3
            """,
            (embedding_str, caregiver_id, tenant_id),
        )
        if not rows:
            return {"verified": False, "score": 0.0, "method": "1:1", "reason": "not_enrolled"}

        # Média ponderada por qualidade
        total_w, weighted_sum = 0.0, 0.0
        for r in rows:
            w = max(0.1, float(r.get("quality_score") or 0.5))
            s = float(r["similarity"])
            weighted_sum += s * w
            total_w += w
        avg = weighted_sum / total_w if total_w > 0 else 0.0

        verified = avg >= VERIFY_1TO1_THRESHOLD
        logger.info(
            "voice_verify_1to1 caregiver=%s score=%.3f verified=%s",
            caregiver_id, avg, verified,
        )
        return {
            "verified": verified,
            "score": round(avg, 4),
            "method": "1:1",
            "caregiver_id": caregiver_id,
        }

    # ══════════════════════════════════════════════════════════════════
    # Identification 1:N (varre todos os cuidadores do tenant)
    # ══════════════════════════════════════════════════════════════════

    def identify_1toN(
        self, tenant_id: str, audio_bytes: bytes, sample_rate: int = 0
    ) -> dict[str, Any]:
        embedding = self._extract_embedding(audio_bytes, sample_rate)
        if embedding is None:
            return {"identified": False, "score": 0.0, "method": "1:N", "reason": "embedding_failed"}

        embedding_str = "[" + ",".join(str(float(v)) for v in embedding) + "]"
        rows = self.postgres.fetch_all(
            """
            SELECT ve.caregiver_id, c.full_name,
                   1 - (ve.embedding <=> %s::vector) AS similarity,
                   ve.quality_score
            FROM aia_health_voice_embeddings ve
            JOIN aia_health_caregivers c ON c.id = ve.caregiver_id
            WHERE ve.tenant_id = %s AND c.active = TRUE
            ORDER BY similarity DESC
            LIMIT 10
            """,
            (embedding_str, tenant_id),
        )
        if not rows:
            return {"identified": False, "score": 0.0, "method": "1:N", "reason": "no_enrollments"}

        # Agrupa por caregiver_id e calcula média ponderada
        by_caregiver: dict[str, list[tuple[float, float]]] = {}
        names: dict[str, str] = {}
        for r in rows:
            cid = str(r["caregiver_id"])
            by_caregiver.setdefault(cid, []).append(
                (float(r["similarity"]), float(r.get("quality_score") or 0.5))
            )
            names[cid] = r.get("full_name", "")

        candidates = []
        for cid, scores in by_caregiver.items():
            total_w = sum(max(0.1, w) for _, w in scores)
            weighted = sum(s * max(0.1, w) for s, w in scores)
            avg = weighted / total_w if total_w > 0 else 0.0
            candidates.append({
                "caregiver_id": cid,
                "caregiver_name": names.get(cid, ""),
                "score": round(avg, 4),
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        identified = best["score"] >= IDENTIFY_1TON_THRESHOLD
        logger.info(
            "voice_identify_1toN tenant=%s best=%s(%.3f) identified=%s",
            tenant_id, best["caregiver_name"], best["score"], identified,
        )
        return {
            "identified": identified,
            "score": best["score"],
            "method": "1:N",
            "matched_caregiver_id": best["caregiver_id"] if identified else None,
            "matched_caregiver_name": best["caregiver_name"] if identified else None,
            "candidates": candidates[:3],
        }

    # ══════════════════════════════════════════════════════════════════
    # LGPD
    # ══════════════════════════════════════════════════════════════════

    def delete_enrollment(self, caregiver_id: str, tenant_id: str, ip: str = "") -> dict[str, Any]:
        try:
            row = self.postgres.fetch_one(
                "SELECT COUNT(*) AS cnt FROM aia_health_voice_embeddings WHERE caregiver_id = %s AND tenant_id = %s",
                (caregiver_id, tenant_id),
            )
            count = row["cnt"] if row else 0
            self.postgres.execute(
                "DELETE FROM aia_health_voice_embeddings WHERE caregiver_id = %s AND tenant_id = %s",
                (caregiver_id, tenant_id),
            )
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_consent_log (caregiver_id, tenant_id, action, ip_address)
                VALUES (%s, %s, 'data_deleted', %s)
                """,
                (caregiver_id, tenant_id, ip),
            )
            logger.info("voice_enrollment_deleted caregiver=%s count=%d", caregiver_id, count)
            return {"success": True, "deleted_count": count}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def get_enrollment_status(self, caregiver_id: str, tenant_id: str) -> dict[str, Any]:
        row = self.postgres.fetch_one(
            """
            SELECT COUNT(*) AS cnt,
                   MAX(created_at) AS last_updated,
                   AVG(quality_score) AS avg_quality
            FROM aia_health_voice_embeddings
            WHERE caregiver_id = %s AND tenant_id = %s
            """,
            (caregiver_id, tenant_id),
        )
        if not row or row["cnt"] == 0:
            return {"enrolled": False, "sample_count": 0, "enrollment_complete": False}
        return {
            "enrolled": True,
            "sample_count": int(row["cnt"]),
            "enrollment_complete": int(row["cnt"]) >= MIN_SAMPLES_FOR_COMPLETE,
            "last_updated": str(row["last_updated"]) if row["last_updated"] else None,
            "avg_quality": round(float(row["avg_quality"]), 3) if row["avg_quality"] else None,
        }

    # ══════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════

    def _count_samples(self, caregiver_id: str, tenant_id: str) -> int:
        row = self.postgres.fetch_one(
            "SELECT COUNT(*) AS cnt FROM aia_health_voice_embeddings WHERE caregiver_id = %s AND tenant_id = %s",
            (caregiver_id, tenant_id),
        )
        return int(row["cnt"]) if row else 0

    def _quality_score(self, audio_bytes: bytes) -> float:
        try:
            int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            if len(int16) == 0:
                return 0.0
            rms = float(np.sqrt(np.mean(int16.astype(np.float64) ** 2)))
            return round(min(1.0, rms / 3000.0), 3)
        except Exception:
            return 0.5


_voice_bio_instance: VoiceBiometricsService | None = None


def get_voice_biometrics():
    global _voice_bio_instance
    if _voice_bio_instance is None:
        from src.services.postgres import get_postgres
        _voice_bio_instance = VoiceBiometricsService(postgres_service=get_postgres())
    return _voice_bio_instance
