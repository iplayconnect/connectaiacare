"""Voice Biometrics Service — identificação de cuidadores por voz.

Versão robusta: usa `audio_preprocessing` para VAD + normalização + quality gate,
faz cache em memória dos embeddings por tenant, loga todos os scores para
calibração, e rejeita áudios ruins ao invés de contaminar o perfil do cuidador.

Arquitetura:
  [audio bytes]
        ↓
  audio_preprocessing.preprocess() → ProcessedAudio com quality + speech segment
        ↓
  Resemblyzer.embed_utterance() → embedding 256-dim
        ↓
  Cache em memória + pgvector query → identificação

Thresholds (conservadores para cenário médico):
  - 1:1 ≥ 0.75 → verificado
  - 1:N ≥ 0.65 → identificado
  - Diferença top1-top2 < 0.05 → rejeita (ambíguo)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.services.audio_preprocessing import (
    MAX_EMBED_MS,
    MIN_SPEECH_MS,
    ProcessedAudio,
    preprocess,
)

logger = logging.getLogger("connectaiacare.voice_biometrics")

VERIFY_1TO1_THRESHOLD = 0.75
IDENTIFY_1TON_THRESHOLD = 0.65
IDENTIFY_AMBIGUITY_MARGIN = 0.05  # top1 deve ser pelo menos 5p.p. melhor que top2
MAX_ENROLLMENT_SAMPLES = 5
MIN_SAMPLES_FOR_COMPLETE = 3
MIN_ENROLL_QUALITY = 0.55         # enrollment exige qualidade >= 55%
MIN_IDENTIFY_QUALITY = 0.30       # identificação tolera qualidade >= 30%
EMBEDDING_TIMEOUT_SEC = 15
CACHE_TTL_SEC = 300               # 5 min


@dataclass
class EmbeddingResult:
    embedding: np.ndarray | None
    quality_score: float
    processed: ProcessedAudio | None
    error: str | None = None


@dataclass
class _CacheEntry:
    by_caregiver: dict[str, np.ndarray]  # caregiver_id → mean embedding
    names: dict[str, str]                # caregiver_id → full_name
    loaded_at: float
    by_patient: dict[str, np.ndarray] | None = None  # patient_id → mean embedding
    patient_names: dict[str, str] | None = None      # patient_id → full_name


class VoiceBiometricsService:
    """Speaker identification via Resemblyzer (256-dim) + pgvector + cache."""

    def __init__(self, postgres_service=None):
        self.postgres = postgres_service
        self._encoder = None
        self._encoder_lock = threading.Lock()
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = threading.Lock()
        logger.info("voice_biometrics_initialized")

    # ══════════════════════════════════════════════════════════════════
    # Resemblyzer lazy-load (~50MB, heavy)
    # ══════════════════════════════════════════════════════════════════

    def _ensure_encoder(self):
        if self._encoder is not None:
            return self._encoder
        with self._encoder_lock:
            if self._encoder is not None:
                return self._encoder
            logger.info("resemblyzer_loading")
            from resemblyzer import VoiceEncoder
            self._encoder = VoiceEncoder()
            logger.info("resemblyzer_loaded")
            return self._encoder

    # ══════════════════════════════════════════════════════════════════
    # Pipeline de extração de embedding (com quality gate)
    # ══════════════════════════════════════════════════════════════════

    def _extract(
        self,
        audio_bytes: bytes,
        sample_rate: int = 0,
        min_quality: float = MIN_IDENTIFY_QUALITY,
    ) -> EmbeddingResult:
        """Processa áudio e extrai embedding.

        Se quality < min_quality, retorna `EmbeddingResult` com error preenchido
        (embedding pode estar presente mesmo assim para caller decidir).
        """
        start = time.time()
        try:
            processed = preprocess(
                audio_bytes, hinted_sr=sample_rate, trim_to_speech=True, normalize=True,
                max_ms=MAX_EMBED_MS,
            )
        except Exception as exc:
            logger.exception("preprocess_failed error=%s", exc)
            return EmbeddingResult(None, 0.0, None, error=f"preprocess_failed: {exc}")

        if processed is None:
            return EmbeddingResult(None, 0.0, None, error="decode_failed")

        q = processed.quality
        logger.info(
            "audio_preprocessed duration_ms=%d speech_ms=%d rms=%.3f snr=%s quality=%.2f reject=%s",
            q.duration_ms, q.speech_duration_ms, q.rms, q.snr_estimate, q.overall, q.rejection_reason,
        )

        if q.rejection_reason:
            return EmbeddingResult(None, q.overall, processed, error=f"quality_rejected:{q.rejection_reason}")

        if q.overall < min_quality:
            return EmbeddingResult(None, q.overall, processed, error=f"quality_low:{q.overall:.2f}")

        # Extrai embedding
        try:
            encoder = self._ensure_encoder()
            from resemblyzer import preprocess_wav
            processed_wav = preprocess_wav(processed.pcm_float32_16k)
            embedding = encoder.embed_utterance(processed_wav)
        except Exception as exc:
            logger.exception("embedding_extraction_failed error=%s", exc)
            return EmbeddingResult(None, q.overall, processed, error=f"embedding_failed: {exc}")

        elapsed = time.time() - start
        logger.info("embedding_extracted dim=%d elapsed_ms=%d quality=%.2f",
                    len(embedding), int(elapsed * 1000), q.overall)

        if elapsed > EMBEDDING_TIMEOUT_SEC:
            logger.warning("embedding_slow elapsed_s=%.1f", elapsed)

        return EmbeddingResult(embedding, q.overall, processed, error=None)

    # ══════════════════════════════════════════════════════════════════
    # Cache
    # ══════════════════════════════════════════════════════════════════

    def _get_cached_tenant(self, tenant_id: str) -> _CacheEntry | None:
        with self._cache_lock:
            entry = self._cache.get(tenant_id)
            if entry and (time.time() - entry.loaded_at) < CACHE_TTL_SEC:
                return entry
            return None

    def _load_tenant_embeddings(self, tenant_id: str) -> _CacheEntry:
        """Carrega média de embeddings por cuidador E paciente ativo do tenant.

        Após migration 050, a mesma tabela armazena ambos via person_type +
        XOR de caregiver_id/patient_id. Carrega tudo em uma passada.
        """
        cached = self._get_cached_tenant(tenant_id)
        if cached:
            return cached

        # Cuidadores
        rows_c = self.postgres.fetch_all(
            """
            SELECT ve.caregiver_id, c.full_name,
                   ve.embedding, ve.quality_score
            FROM aia_health_voice_embeddings ve
            JOIN aia_health_caregivers c ON c.id = ve.caregiver_id
            WHERE ve.tenant_id = %s AND c.active = TRUE
              AND ve.person_type = 'caregiver'
            """,
            (tenant_id,),
        )

        # Pacientes (best-effort: column person_type pode não existir
        # antes da migration 050. Fallback gracioso pra zero pacientes.)
        try:
            rows_p = self.postgres.fetch_all(
                """
                SELECT ve.patient_id, p.full_name,
                       ve.embedding, ve.quality_score
                FROM aia_health_voice_embeddings ve
                JOIN aia_health_patients p ON p.id = ve.patient_id
                WHERE ve.tenant_id = %s AND p.active = TRUE
                  AND ve.person_type = 'patient'
                """,
                (tenant_id,),
            )
        except Exception as exc:
            logger.warning("patient_embeddings_load_skipped reason=%s", exc)
            rows_p = []

        means_c, names_c = self._aggregate_embeddings(rows_c, "caregiver_id")
        means_p, names_p = self._aggregate_embeddings(rows_p, "patient_id")

        entry = _CacheEntry(
            by_caregiver=means_c,
            names=names_c,
            by_patient=means_p,
            patient_names=names_p,
            loaded_at=time.time(),
        )
        with self._cache_lock:
            self._cache[tenant_id] = entry
        logger.info(
            "tenant_embeddings_cached tenant=%s caregivers=%d patients=%d",
            tenant_id, len(means_c), len(means_p),
        )
        return entry

    @staticmethod
    def _aggregate_embeddings(
        rows: list[dict],
        key_field: str,
    ) -> tuple[dict[str, np.ndarray], dict[str, str]]:
        """Agrupa embeddings por pessoa e retorna média ponderada por qualidade."""
        grouped: dict[str, list[tuple[np.ndarray, float]]] = {}
        names: dict[str, str] = {}
        for r in rows:
            pid = str(r[key_field])
            emb_raw = r["embedding"]
            emb = np.array(VoiceBiometricsService._parse_vector(emb_raw), dtype=np.float32)
            q = float(r.get("quality_score") or 0.5)
            grouped.setdefault(pid, []).append((emb, q))
            names[pid] = r.get("full_name", "")

        means: dict[str, np.ndarray] = {}
        for pid, items in grouped.items():
            embs = np.stack([e for e, _ in items])
            weights = np.array([max(0.1, w) for _, w in items])
            weights = weights / weights.sum()
            mean_emb = (embs * weights[:, None]).sum(axis=0)
            norm = np.linalg.norm(mean_emb)
            if norm > 0:
                mean_emb = mean_emb / norm
            means[pid] = mean_emb.astype(np.float32)
        return means, names

    def invalidate_cache(self, tenant_id: str | None = None):
        with self._cache_lock:
            if tenant_id:
                self._cache.pop(tenant_id, None)
            else:
                self._cache.clear()

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    @staticmethod
    def _parse_vector(vec) -> list[float]:
        if isinstance(vec, (list, np.ndarray)):
            return list(vec)
        s = str(vec).strip("[]() ")
        return [float(x) for x in s.split(",") if x.strip()]

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
        if not self.postgres:
            return {"success": False, "message": "DB indisponível"}

        current = self._count_samples(caregiver_id, tenant_id)
        if current >= MAX_ENROLLMENT_SAMPLES:
            return {"success": False, "message": f"Limite de {MAX_ENROLLMENT_SAMPLES} amostras atingido"}

        result = self._extract(audio_bytes, sample_rate=sample_rate, min_quality=MIN_ENROLL_QUALITY)
        if result.error or result.embedding is None:
            return {
                "success": False,
                "message": f"Áudio rejeitado: {result.error}",
                "quality_detail": result.processed.quality.__dict__ if result.processed else None,
            }

        duration_ms = result.processed.quality.duration_ms if result.processed else 0
        embedding_str = "[" + ",".join(str(float(v)) for v in result.embedding) + "]"

        try:
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_embeddings
                    (caregiver_id, tenant_id, embedding, sample_label,
                     audio_duration_ms, quality_score, consent_ip)
                VALUES (%s, %s, %s::vector, %s, %s, %s, %s)
                """,
                (
                    caregiver_id, tenant_id, embedding_str, sample_label,
                    duration_ms, result.quality_score, consent_ip,
                ),
            )
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_consent_log (caregiver_id, tenant_id, action, ip_address)
                VALUES (%s, %s, 'enrollment_added', %s)
                """,
                (caregiver_id, tenant_id, consent_ip),
            )
            self.invalidate_cache(tenant_id)

            new_count = current + 1
            logger.info(
                "voice_enrolled caregiver=%s samples=%d/%d quality=%.2f",
                caregiver_id, new_count, MAX_ENROLLMENT_SAMPLES, result.quality_score,
            )
            return {
                "success": True,
                "samples_count": new_count,
                "samples_needed": max(0, MIN_SAMPLES_FOR_COMPLETE - new_count),
                "quality_score": result.quality_score,
                "enrollment_complete": new_count >= MIN_SAMPLES_FOR_COMPLETE,
                "quality_detail": result.processed.quality.__dict__ if result.processed else None,
            }
        except Exception as exc:
            logger.exception("enroll_db_failed error=%s", exc)
            return {"success": False, "message": f"DB: {exc}"}

    # ══════════════════════════════════════════════════════════════════
    # Verification 1:1
    # ══════════════════════════════════════════════════════════════════

    def verify_1to1(
        self,
        caregiver_id: str,
        tenant_id: str,
        audio_bytes: bytes,
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        result = self._extract(audio_bytes, sample_rate=sample_rate, min_quality=MIN_IDENTIFY_QUALITY)
        if result.embedding is None:
            return {"verified": False, "score": 0.0, "method": "1:1", "reason": result.error or "unknown"}

        entry = self._load_tenant_embeddings(tenant_id)
        stored = entry.by_caregiver.get(str(caregiver_id))
        if stored is None:
            return {"verified": False, "score": 0.0, "method": "1:1", "reason": "not_enrolled"}

        score = self._cosine(result.embedding, stored)
        verified = score >= VERIFY_1TO1_THRESHOLD

        self._log_calibration(
            tenant_id=tenant_id, method="1:1", score=score,
            caregiver_id=str(caregiver_id),
            audio_quality=result.quality_score,
            accepted=verified,
        )

        logger.info(
            "voice_verify_1to1 caregiver=%s score=%.3f verified=%s quality=%.2f",
            caregiver_id, score, verified, result.quality_score,
        )
        return {
            "verified": verified,
            "score": round(score, 4),
            "method": "1:1",
            "caregiver_id": str(caregiver_id),
            "audio_quality": round(result.quality_score, 3),
        }

    # ══════════════════════════════════════════════════════════════════
    # Identification 1:N
    # ══════════════════════════════════════════════════════════════════

    def identify_1toN(
        self, tenant_id: str, audio_bytes: bytes, sample_rate: int = 0
    ) -> dict[str, Any]:
        result = self._extract(audio_bytes, sample_rate=sample_rate, min_quality=MIN_IDENTIFY_QUALITY)
        if result.embedding is None:
            return {"identified": False, "score": 0.0, "method": "1:N", "reason": result.error or "unknown"}

        entry = self._load_tenant_embeddings(tenant_id)
        if not entry.by_caregiver:
            return {"identified": False, "score": 0.0, "method": "1:N", "reason": "no_enrollments"}

        # Cosine contra cada cuidador do tenant
        scores: list[tuple[str, float]] = []
        for cid, mean_emb in entry.by_caregiver.items():
            scores.append((cid, self._cosine(result.embedding, mean_emb)))
        scores.sort(key=lambda x: x[1], reverse=True)

        top_cid, top_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0.0
        margin = top_score - second_score

        identified = (
            top_score >= IDENTIFY_1TON_THRESHOLD
            and margin >= IDENTIFY_AMBIGUITY_MARGIN
        )

        candidates = [
            {
                "caregiver_id": cid,
                "caregiver_name": entry.names.get(cid, ""),
                "score": round(s, 4),
            }
            for cid, s in scores[:3]
        ]

        self._log_calibration(
            tenant_id=tenant_id, method="1:N", score=top_score,
            caregiver_id=top_cid if identified else None,
            audio_quality=result.quality_score,
            accepted=identified,
            extra={"margin": margin, "top3": candidates},
        )

        logger.info(
            "voice_identify_1toN tenant=%s best=%s(%.3f) margin=%.3f identified=%s quality=%.2f",
            tenant_id, entry.names.get(top_cid, top_cid), top_score, margin, identified, result.quality_score,
        )

        return {
            "identified": identified,
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "method": "1:N",
            "matched_caregiver_id": top_cid if identified else None,
            "matched_caregiver_name": entry.names.get(top_cid, "") if identified else None,
            "candidates": candidates,
            "audio_quality": round(result.quality_score, 3),
        }

    # ══════════════════════════════════════════════════════════════════
    # Calibration log (tunable thresholds com dados reais)
    # ══════════════════════════════════════════════════════════════════

    def _log_calibration(
        self,
        tenant_id: str,
        method: str,
        score: float,
        audio_quality: float,
        accepted: bool,
        caregiver_id: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """Loga cada decisão em `aia_health_voice_consent_log` para calibração posterior."""
        try:
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_consent_log
                    (caregiver_id, tenant_id, action, metadata)
                VALUES (%s, %s, 'data_accessed', %s)
                """,
                (
                    caregiver_id,
                    tenant_id,
                    self.postgres.json_adapt({
                        "calibration": True,
                        "method": method,
                        "score": round(score, 4),
                        "quality": round(audio_quality, 3),
                        "accepted": accepted,
                        **(extra or {}),
                    }),
                ),
            )
        except Exception as exc:
            # Não propaga — log é best-effort
            logger.warning("calibration_log_failed error=%s", exc)

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
            self.invalidate_cache(tenant_id)
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

    def _count_samples(self, caregiver_id: str, tenant_id: str) -> int:
        row = self.postgres.fetch_one(
            "SELECT COUNT(*) AS cnt FROM aia_health_voice_embeddings WHERE caregiver_id = %s AND tenant_id = %s",
            (caregiver_id, tenant_id),
        )
        return int(row["cnt"]) if row else 0

    # ══════════════════════════════════════════════════════════════════
    # Paciente — enroll / verify / identify / status / delete
    # ══════════════════════════════════════════════════════════════════
    #
    # Migration 050 estende aia_health_voice_embeddings com person_type +
    # patient_id (XOR com caregiver_id). Os métodos abaixo são análogos
    # aos de cuidador mas operam sobre patient_id.

    def enroll_patient(
        self,
        patient_id: str,
        tenant_id: str,
        audio_bytes: bytes,
        sample_label: str = "enrollment",
        consent_ip: str = "",
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        if not self.postgres:
            return {"success": False, "message": "DB indisponível"}

        current = self._count_patient_samples(patient_id, tenant_id)
        if current >= MAX_ENROLLMENT_SAMPLES:
            return {
                "success": False,
                "message": f"Limite de {MAX_ENROLLMENT_SAMPLES} amostras atingido",
            }

        result = self._extract(
            audio_bytes, sample_rate=sample_rate, min_quality=MIN_ENROLL_QUALITY,
        )
        if result.error or result.embedding is None:
            return {
                "success": False,
                "message": f"Áudio rejeitado: {result.error}",
                "quality_detail": result.processed.quality.__dict__ if result.processed else None,
            }

        duration_ms = result.processed.quality.duration_ms if result.processed else 0
        embedding_str = "[" + ",".join(str(float(v)) for v in result.embedding) + "]"

        try:
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_embeddings
                    (patient_id, person_type, tenant_id, embedding, sample_label,
                     audio_duration_ms, quality_score, consent_ip)
                VALUES (%s, 'patient', %s, %s::vector, %s, %s, %s, %s)
                """,
                (
                    patient_id, tenant_id, embedding_str, sample_label,
                    duration_ms, result.quality_score, consent_ip,
                ),
            )
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_consent_log
                    (patient_id, person_type, tenant_id, action, ip_address)
                VALUES (%s, 'patient', %s, 'enrollment_added', %s)
                """,
                (patient_id, tenant_id, consent_ip),
            )
            self.invalidate_cache(tenant_id)

            new_count = current + 1
            logger.info(
                "voice_enrolled_patient patient=%s samples=%d/%d quality=%.2f",
                patient_id, new_count, MAX_ENROLLMENT_SAMPLES, result.quality_score,
            )
            return {
                "success": True,
                "person_type": "patient",
                "samples_count": new_count,
                "samples_needed": max(0, MIN_SAMPLES_FOR_COMPLETE - new_count),
                "quality_score": result.quality_score,
                "enrollment_complete": new_count >= MIN_SAMPLES_FOR_COMPLETE,
                "quality_detail": result.processed.quality.__dict__ if result.processed else None,
            }
        except Exception as exc:
            logger.exception("enroll_patient_db_failed error=%s", exc)
            return {"success": False, "message": f"DB: {exc}"}

    def verify_patient_1to1(
        self,
        patient_id: str,
        tenant_id: str,
        audio_bytes: bytes,
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        result = self._extract(
            audio_bytes, sample_rate=sample_rate, min_quality=MIN_IDENTIFY_QUALITY,
        )
        if result.embedding is None:
            return {
                "verified": False, "score": 0.0, "method": "1:1",
                "person_type": "patient", "reason": result.error or "unknown",
            }

        entry = self._load_tenant_embeddings(tenant_id)
        stored = (entry.by_patient or {}).get(str(patient_id))
        if stored is None:
            return {
                "verified": False, "score": 0.0, "method": "1:1",
                "person_type": "patient", "reason": "not_enrolled",
            }

        score = self._cosine(result.embedding, stored)
        verified = score >= VERIFY_1TO1_THRESHOLD

        self._log_calibration(
            tenant_id=tenant_id, method="1:1_patient", score=score,
            audio_quality=result.quality_score, accepted=verified,
            extra={"patient_id": str(patient_id)},
        )
        logger.info(
            "voice_verify_patient_1to1 patient=%s score=%.3f verified=%s",
            patient_id, score, verified,
        )
        return {
            "verified": verified,
            "score": round(score, 4),
            "method": "1:1",
            "person_type": "patient",
            "patient_id": str(patient_id),
            "audio_quality": round(result.quality_score, 3),
        }

    def identify_patient_1toN(
        self, tenant_id: str, audio_bytes: bytes, sample_rate: int = 0,
    ) -> dict[str, Any]:
        """Identifica paciente entre os pacientes ativos do tenant."""
        result = self._extract(
            audio_bytes, sample_rate=sample_rate, min_quality=MIN_IDENTIFY_QUALITY,
        )
        if result.embedding is None:
            return {
                "identified": False, "score": 0.0, "method": "1:N",
                "person_type": "patient", "reason": result.error or "unknown",
            }

        entry = self._load_tenant_embeddings(tenant_id)
        candidates_pool = entry.by_patient or {}
        patient_names = entry.patient_names or {}
        if not candidates_pool:
            return {
                "identified": False, "score": 0.0, "method": "1:N",
                "person_type": "patient", "reason": "no_enrollments",
            }

        scores: list[tuple[str, float]] = [
            (pid, self._cosine(result.embedding, mean_emb))
            for pid, mean_emb in candidates_pool.items()
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        top_pid, top_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0.0
        margin = top_score - second_score
        identified = (
            top_score >= IDENTIFY_1TON_THRESHOLD
            and margin >= IDENTIFY_AMBIGUITY_MARGIN
        )

        candidates = [
            {
                "patient_id": pid,
                "patient_name": patient_names.get(pid, ""),
                "score": round(s, 4),
            }
            for pid, s in scores[:3]
        ]
        self._log_calibration(
            tenant_id=tenant_id, method="1:N_patient", score=top_score,
            audio_quality=result.quality_score, accepted=identified,
            extra={"margin": margin, "top3": candidates},
        )
        logger.info(
            "voice_identify_patient_1toN tenant=%s best=%s(%.3f) margin=%.3f identified=%s",
            tenant_id, patient_names.get(top_pid, top_pid), top_score, margin, identified,
        )
        return {
            "identified": identified,
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "method": "1:N",
            "person_type": "patient",
            "matched_patient_id": top_pid if identified else None,
            "matched_patient_name": patient_names.get(top_pid, "") if identified else None,
            "candidates": candidates,
            "audio_quality": round(result.quality_score, 3),
        }

    def identify_any_1toN(
        self, tenant_id: str, audio_bytes: bytes, sample_rate: int = 0,
    ) -> dict[str, Any]:
        """Identifica em pool unificado (cuidadores + pacientes).

        Útil para áudios em domicílio onde paciente e cuidador podem
        responder pela mesma linha. Retorna tipo + id do match.
        """
        result = self._extract(
            audio_bytes, sample_rate=sample_rate, min_quality=MIN_IDENTIFY_QUALITY,
        )
        if result.embedding is None:
            return {
                "identified": False, "score": 0.0, "method": "1:N_any",
                "reason": result.error or "unknown",
            }

        entry = self._load_tenant_embeddings(tenant_id)
        scores: list[tuple[str, str, str, float]] = []
        for cid, mean in entry.by_caregiver.items():
            scores.append((
                "caregiver", cid, entry.names.get(cid, ""),
                self._cosine(result.embedding, mean),
            ))
        for pid, mean in (entry.by_patient or {}).items():
            scores.append((
                "patient", pid, (entry.patient_names or {}).get(pid, ""),
                self._cosine(result.embedding, mean),
            ))
        if not scores:
            return {
                "identified": False, "score": 0.0, "method": "1:N_any",
                "reason": "no_enrollments",
            }
        scores.sort(key=lambda x: x[3], reverse=True)

        top_type, top_id, top_name, top_score = scores[0]
        second_score = scores[1][3] if len(scores) > 1 else 0.0
        margin = top_score - second_score
        identified = (
            top_score >= IDENTIFY_1TON_THRESHOLD
            and margin >= IDENTIFY_AMBIGUITY_MARGIN
        )
        candidates = [
            {
                "person_type": t, "person_id": i, "person_name": n,
                "score": round(s, 4),
            }
            for t, i, n, s in scores[:3]
        ]
        return {
            "identified": identified,
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "method": "1:N_any",
            "matched_person_type": top_type if identified else None,
            "matched_person_id": top_id if identified else None,
            "matched_person_name": top_name if identified else None,
            "candidates": candidates,
            "audio_quality": round(result.quality_score, 3),
        }

    def get_patient_enrollment_status(
        self, patient_id: str, tenant_id: str,
    ) -> dict[str, Any]:
        row = self.postgres.fetch_one(
            """
            SELECT COUNT(*) AS cnt,
                   MAX(created_at) AS last_updated,
                   AVG(quality_score) AS avg_quality
            FROM aia_health_voice_embeddings
            WHERE patient_id = %s AND tenant_id = %s
              AND person_type = 'patient'
            """,
            (patient_id, tenant_id),
        )
        if not row or row["cnt"] == 0:
            return {
                "enrolled": False, "sample_count": 0, "enrollment_complete": False,
                "person_type": "patient",
            }
        return {
            "enrolled": True,
            "person_type": "patient",
            "sample_count": int(row["cnt"]),
            "enrollment_complete": int(row["cnt"]) >= MIN_SAMPLES_FOR_COMPLETE,
            "last_updated": str(row["last_updated"]) if row["last_updated"] else None,
            "avg_quality": round(float(row["avg_quality"]), 3) if row["avg_quality"] else None,
        }

    def delete_patient_enrollment(
        self, patient_id: str, tenant_id: str, ip: str = "",
    ) -> dict[str, Any]:
        try:
            row = self.postgres.fetch_one(
                """
                SELECT COUNT(*) AS cnt FROM aia_health_voice_embeddings
                WHERE patient_id = %s AND tenant_id = %s AND person_type = 'patient'
                """,
                (patient_id, tenant_id),
            )
            count = row["cnt"] if row else 0
            self.postgres.execute(
                """
                DELETE FROM aia_health_voice_embeddings
                WHERE patient_id = %s AND tenant_id = %s AND person_type = 'patient'
                """,
                (patient_id, tenant_id),
            )
            self.postgres.execute(
                """
                INSERT INTO aia_health_voice_consent_log
                    (patient_id, person_type, tenant_id, action, ip_address)
                VALUES (%s, 'patient', %s, 'data_deleted', %s)
                """,
                (patient_id, tenant_id, ip),
            )
            self.invalidate_cache(tenant_id)
            logger.info(
                "voice_enrollment_deleted_patient patient=%s count=%d",
                patient_id, count,
            )
            return {"success": True, "deleted_count": count}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def _count_patient_samples(self, patient_id: str, tenant_id: str) -> int:
        row = self.postgres.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM aia_health_voice_embeddings
            WHERE patient_id = %s AND tenant_id = %s AND person_type = 'patient'
            """,
            (patient_id, tenant_id),
        )
        return int(row["cnt"]) if row else 0

    # ══════════════════════════════════════════════════════════════════
    # Identificação restrita ao pool do plantão atual (insight Grok)
    # ══════════════════════════════════════════════════════════════════
    #
    # Em vez de comparar contra todos os cuidadores do tenant
    # (1:N grande, impreciso), restringe ao pool de cuidadores
    # ativos no plantão atual (3-4 vozes). Acerto sobe muito.
    # Resolve também troca de plantão: se voz não bate no pool,
    # caller faz fallback de pergunta explícita.

    def identify_caregiver_in_shift(
        self,
        tenant_id: str,
        audio_bytes: bytes,
        shift_caregiver_ids: list[str] | None = None,
        sample_rate: int = 0,
    ) -> dict[str, Any]:
        """Variante de identify_1toN que restringe o pool a uma lista
        explícita de caregiver_ids (vinda do shift_resolver).

        Se shift_caregiver_ids vazio ou None → falha graciosa com
        reason='no_active_shift' (caller deve perguntar identidade).
        """
        if not shift_caregiver_ids:
            return {
                "identified": False, "score": 0.0, "method": "1:N_shift",
                "reason": "no_active_shift",
            }

        result = self._extract(
            audio_bytes, sample_rate=sample_rate,
            min_quality=MIN_IDENTIFY_QUALITY,
        )
        if result.embedding is None:
            return {
                "identified": False, "score": 0.0, "method": "1:N_shift",
                "reason": result.error or "unknown",
            }

        entry = self._load_tenant_embeddings(tenant_id)
        # Filtra só os IDs do plantão
        pool = {
            cid: emb for cid, emb in entry.by_caregiver.items()
            if cid in set(shift_caregiver_ids)
        }
        if not pool:
            return {
                "identified": False, "score": 0.0, "method": "1:N_shift",
                "reason": "no_enrollments_in_shift",
                "shift_pool_size": len(shift_caregiver_ids),
            }

        scores: list[tuple[str, float]] = [
            (cid, self._cosine(result.embedding, mean_emb))
            for cid, mean_emb in pool.items()
        ]
        scores.sort(key=lambda x: x[1], reverse=True)

        top_cid, top_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0.0
        margin = top_score - second_score
        identified = (
            top_score >= IDENTIFY_1TON_THRESHOLD
            and margin >= IDENTIFY_AMBIGUITY_MARGIN
        )
        candidates = [
            {
                "caregiver_id": cid,
                "caregiver_name": entry.names.get(cid, ""),
                "score": round(s, 4),
            }
            for cid, s in scores[:3]
        ]
        self._log_calibration(
            tenant_id=tenant_id, method="1:N_shift", score=top_score,
            caregiver_id=top_cid if identified else None,
            audio_quality=result.quality_score, accepted=identified,
            extra={
                "margin": margin, "top3": candidates,
                "shift_pool_size": len(pool),
            },
        )
        logger.info(
            "voice_identify_in_shift tenant=%s pool=%d best=%s(%.3f) "
            "margin=%.3f identified=%s",
            tenant_id, len(pool), entry.names.get(top_cid, top_cid),
            top_score, margin, identified,
        )
        return {
            "identified": identified,
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "method": "1:N_shift",
            "shift_pool_size": len(pool),
            "matched_caregiver_id": top_cid if identified else None,
            "matched_caregiver_name": (
                entry.names.get(top_cid, "") if identified else None
            ),
            "candidates": candidates,
            "audio_quality": round(result.quality_score, 3),
            # Caller pode usar isso para montar pergunta de fallback
            # tipo "você é Carla, Joana ou Maria?"
            "fallback_options": (
                [{"id": cid, "name": entry.names.get(cid, "")}
                 for cid in shift_caregiver_ids
                 if cid in entry.names]
                if not identified else None
            ),
        }

    def list_coverage_summary(self, tenant_id: str) -> dict[str, Any]:
        """Retorna resumo de cobertura para a página admin."""
        try:
            rows = self.postgres.fetch_all(
                """
                SELECT person_type, people_enrolled, samples_total,
                       avg_quality, last_enrollment
                FROM aia_health_voice_coverage_summary
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
        except Exception:
            rows = []
        out = {
            "caregiver": {"people_enrolled": 0, "samples_total": 0},
            "patient": {"people_enrolled": 0, "samples_total": 0},
        }
        for r in rows or []:
            pt = r.get("person_type", "caregiver")
            out[pt] = {
                "people_enrolled": int(r.get("people_enrolled") or 0),
                "samples_total": int(r.get("samples_total") or 0),
                "avg_quality": float(r["avg_quality"]) if r.get("avg_quality") else None,
                "last_enrollment": str(r["last_enrollment"]) if r.get("last_enrollment") else None,
            }
        return out


_instance: VoiceBiometricsService | None = None


def get_voice_biometrics() -> VoiceBiometricsService:
    global _instance
    if _instance is None:
        from src.services.postgres import get_postgres
        _instance = VoiceBiometricsService(postgres_service=get_postgres())
    return _instance
