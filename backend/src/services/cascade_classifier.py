"""Cascade classifier — Tier 1 → Tier 2 → Tier 3 (Judge).

Estratégia adaptativa de classificação event_type + severity por
nível de risco:

  Tier 1: DeepSeek V4-Flash (rápido, barato, sempre executa)
    └─ severity in {routine, attention} → executa direto

  Tier 2: DeepSeek V4-Pro (raciocínio, dispara em urgent/critical)
    ├─ AGREEMENT com T1 → usa veredito de T1
    └─ DISAGREEMENT → Tier 3

  Tier 3: Claude Haiku (juiz, arquitetura diferente — reduz correlação)
    ├─ Decide veredito final
    └─ DISPARA notificação ao responsável (sempre que T3 acionado)

Tenant config decide o que fazer no final:
  - mode='no_clinical_team' (B2C/ILPI): T3 decide direto + notifica
  - mode='clinical_team' (clínica/hospital): T3 enfileira pra fila humana
  - mode='hybrid_partner' (parceiro integrador tipo): webhook pro parceiro

Audit completo persiste em aia_health_classification_cascade.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.prompts.classification_judge import SYSTEM_PROMPT as JUDGE_SYSTEM
from src.prompts.classification_judge import build_judge_input
from src.prompts.patient_extraction import SYSTEM_PROMPT as EXTRACTION_SYSTEM
from src.services.analysis_service import ALLOWED_EVENT_TYPES
from src.services.llm_router import LLMRouter
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_SEVERITIES = {"routine", "attention", "urgent", "critical"}
SEVERITY_RANK = {"routine": 0, "attention": 1, "urgent": 2, "critical": 3}


@dataclass
class TierResult:
    """Resultado de um tier do cascade."""
    tier: int
    triggered: bool = False
    trigger_reason: str | None = None
    model: str | None = None
    event_type: str | None = None
    classification: str | None = None
    rationale: str | None = None
    elapsed_ms: int = 0
    error: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class CascadeDecision:
    """Decisão final do cascade."""
    final_event_type: str
    final_classification: str
    final_decided_by: str  # tier1 | tier2_agreement | tier3_judge | human_queue | fallback_default
    tier1: TierResult
    tier2: TierResult
    tier3: TierResult
    total_elapsed_ms: int
    notify_responsible: bool = False
    notification_reason: str | None = None
    human_queue_id: str | None = None


class CascadeClassifier:
    """Pipeline de cascade pra classificar event_type + severity."""

    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter()
        self.db = get_postgres()

    def classify(
        self,
        *,
        transcript: str,
        patient_context: dict | None = None,
        report_id: str | None = None,
        care_event_id: str | None = None,
        patient_id: str | None = None,
        tenant_id: str = "connectaiacare_demo",
    ) -> CascadeDecision:
        """Executa cascade completo. Retorna decisão final + audit completo."""
        started = time.time()

        t1 = self._tier1(transcript)
        t2 = TierResult(tier=2)
        t3 = TierResult(tier=3)

        # Decisão de subir pra T2
        t1_severity = (t1.classification or "").lower()
        t1_failed = bool(t1.error) or not t1.event_type or not t1.classification

        if t1_failed:
            t2.trigger_reason = "tier1_failed"
            t2 = self._tier2(transcript, trigger=t2.trigger_reason)
        elif t1_severity in {"urgent", "critical"}:
            t2.trigger_reason = t1_severity
            t2 = self._tier2(transcript, trigger=t2.trigger_reason)

        # Resolução
        if not t2.triggered:
            # Caminho rápido: rotina/attention sem necessidade de revisão
            decision = CascadeDecision(
                final_event_type=t1.event_type or "relato_geral",
                final_classification=t1.classification or "attention",
                final_decided_by="tier1",
                tier1=t1, tier2=t2, tier3=t3,
                total_elapsed_ms=int((time.time() - started) * 1000),
            )
            self._persist(decision, transcript, report_id, care_event_id,
                          patient_id, tenant_id)
            return decision

        # T2 disparou — checa concordância
        agree_event = (t1.event_type == t2.event_type)
        agree_class = (t1.classification == t2.classification)
        t2.raw["agreement"] = agree_event and agree_class

        if t2.error or not t2.event_type:
            # T2 falhou — escala pra juiz
            t3 = self._tier3(transcript, t1, t2, "tier2_failed")
        elif agree_event and agree_class:
            # T1 e T2 concordam — usa veredito (mais conservador entre os dois)
            decision = CascadeDecision(
                final_event_type=t1.event_type,
                final_classification=self._max_severity(
                    t1.classification, t2.classification,
                ),
                final_decided_by="tier2_agreement",
                tier1=t1, tier2=t2, tier3=t3,
                total_elapsed_ms=int((time.time() - started) * 1000),
            )
            # Critical sempre notifica responsável (config tenant default)
            if decision.final_classification == "critical":
                decision.notify_responsible = True
                decision.notification_reason = "critical_agreement"
            self._persist(decision, transcript, report_id, care_event_id,
                          patient_id, tenant_id)
            return decision
        else:
            # Discordância — invoca juiz
            disagree_type = []
            if not agree_event:
                disagree_type.append("event_type")
            if not agree_class:
                disagree_type.append("severity")
            t3 = self._tier3(
                transcript, t1, t2,
                trigger="_".join(disagree_type) + "_disagreement",
            )

        # T3 decidiu (ou também falhou)
        if t3.event_type and t3.classification:
            decision = CascadeDecision(
                final_event_type=t3.event_type,
                final_classification=t3.classification,
                final_decided_by="tier3_judge",
                tier1=t1, tier2=t2, tier3=t3,
                total_elapsed_ms=int((time.time() - started) * 1000),
                notify_responsible=True,  # SEMPRE que T3 dispara
                notification_reason="judge_invoked",
            )
        else:
            # Tudo falhou — fallback conservador (escalar)
            decision = CascadeDecision(
                final_event_type=t2.event_type or t1.event_type or "relato_geral",
                final_classification=self._max_severity(
                    t1.classification, t2.classification, "attention",
                ),
                final_decided_by="fallback_default",
                tier1=t1, tier2=t2, tier3=t3,
                total_elapsed_ms=int((time.time() - started) * 1000),
                notify_responsible=True,
                notification_reason="all_tiers_failed",
            )

        self._persist(decision, transcript, report_id, care_event_id,
                      patient_id, tenant_id)
        return decision

    # ────────────────────────── Tiers ──────────────────────────

    def _tier1(self, transcript: str) -> TierResult:
        t = TierResult(tier=1, triggered=True)
        started = time.time()
        try:
            result = self.router.complete_json(
                task="intent_classifier",
                system=EXTRACTION_SYSTEM,
                user=f"Transcrição do áudio do cuidador:\n\n{transcript}",
            )
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.model = result.get("_model_used", "unknown")
            t.raw = result
            evt = result.get("event_type")
            if evt in ALLOWED_EVENT_TYPES:
                t.event_type = evt
            t.classification = self._normalize_severity(
                result.get("classification") or
                self._infer_severity_from_urgent_keywords(transcript, result)
            )
            t.rationale = result.get("classification_reasoning") or result.get("rationale")
        except Exception as exc:
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.error = str(exc)[:300]
            logger.warning("cascade_t1_failed", error=t.error)
        return t

    def _tier2(self, transcript: str, *, trigger: str) -> TierResult:
        t = TierResult(tier=2, triggered=True, trigger_reason=trigger)
        started = time.time()
        try:
            result = self.router.complete_json(
                task="intent_classifier_review",
                system=EXTRACTION_SYSTEM,
                user=f"Transcrição do áudio do cuidador:\n\n{transcript}",
            )
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.model = result.get("_model_used", "unknown")
            t.raw = result
            evt = result.get("event_type")
            if evt in ALLOWED_EVENT_TYPES:
                t.event_type = evt
            t.classification = self._normalize_severity(
                result.get("classification")
            )
            t.rationale = result.get("classification_reasoning") or result.get("rationale")
        except Exception as exc:
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.error = str(exc)[:300]
            logger.warning("cascade_t2_failed", error=t.error)
        return t

    def _tier3(
        self, transcript: str, t1: TierResult, t2: TierResult, trigger: str,
    ) -> TierResult:
        t = TierResult(tier=3, triggered=True, trigger_reason=trigger)
        started = time.time()
        try:
            judge_input = build_judge_input(
                transcript,
                {
                    "event_type": t1.event_type,
                    "classification": t1.classification,
                    "rationale": t1.rationale,
                },
                {
                    "event_type": t2.event_type,
                    "classification": t2.classification,
                    "rationale": t2.rationale,
                },
                disagreement_type=trigger,
            )
            result = self.router.complete_json(
                task="intent_classifier_judge",
                system=JUDGE_SYSTEM,
                user=judge_input,
            )
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.model = result.get("_model_used", "unknown")
            t.raw = result
            evt = result.get("final_event_type")
            if evt in ALLOWED_EVENT_TYPES:
                t.event_type = evt
            t.classification = self._normalize_severity(
                result.get("final_classification")
            )
            t.rationale = result.get("rationale")
        except Exception as exc:
            t.elapsed_ms = int((time.time() - started) * 1000)
            t.error = str(exc)[:300]
            logger.warning("cascade_t3_failed", error=t.error)
        return t

    # ────────────────────────── Helpers ──────────────────────────

    @staticmethod
    def _normalize_severity(value: str | None) -> str | None:
        if not value:
            return None
        v = value.lower().strip()
        return v if v in ALLOWED_SEVERITIES else None

    @staticmethod
    def _max_severity(*severities: str | None) -> str:
        ranks = [SEVERITY_RANK.get(s, -1) for s in severities if s]
        if not ranks:
            return "attention"
        max_rank = max(ranks)
        # Procura nome correspondente
        for name, rank in SEVERITY_RANK.items():
            if rank == max_rank:
                return name
        return "attention"

    @staticmethod
    def _infer_severity_from_urgent_keywords(transcript: str, result: dict) -> str | None:
        """Heurística mínima — se transcript tem urgent_keywords, infere
        attention no mínimo. Análise full faz isso melhor; aqui é último
        recurso quando T1 não retorna severity."""
        urgent = result.get("urgent_keywords") or []
        if urgent and isinstance(urgent, list):
            return "attention"
        return None

    # ────────────────────────── Persistência ──────────────────────────

    def _persist(
        self,
        decision: CascadeDecision,
        transcript: str,
        report_id: str | None,
        care_event_id: str | None,
        patient_id: str | None,
        tenant_id: str,
    ) -> None:
        try:
            self.db.execute(
                """INSERT INTO aia_health_classification_cascade (
                    tenant_id, report_id, care_event_id, patient_id,
                    transcript_excerpt,
                    t1_model, t1_event_type, t1_classification, t1_rationale,
                    t1_elapsed_ms, t1_error,
                    t2_triggered, t2_trigger_reason, t2_model,
                    t2_event_type, t2_classification, t2_rationale,
                    t2_elapsed_ms, t2_error, t2_agreement,
                    t3_triggered, t3_trigger_reason, t3_model,
                    t3_event_type, t3_classification, t3_rationale,
                    t3_elapsed_ms, t3_error,
                    final_event_type, final_classification, final_decided_by,
                    total_elapsed_ms
                ) VALUES (
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )""",
                (
                    tenant_id, report_id, care_event_id, patient_id,
                    transcript[:500],
                    decision.tier1.model, decision.tier1.event_type,
                    decision.tier1.classification, decision.tier1.rationale,
                    decision.tier1.elapsed_ms, decision.tier1.error,
                    decision.tier2.triggered, decision.tier2.trigger_reason,
                    decision.tier2.model, decision.tier2.event_type,
                    decision.tier2.classification, decision.tier2.rationale,
                    decision.tier2.elapsed_ms, decision.tier2.error,
                    decision.tier2.raw.get("agreement"),
                    decision.tier3.triggered, decision.tier3.trigger_reason,
                    decision.tier3.model, decision.tier3.event_type,
                    decision.tier3.classification, decision.tier3.rationale,
                    decision.tier3.elapsed_ms, decision.tier3.error,
                    decision.final_event_type, decision.final_classification,
                    decision.final_decided_by,
                    decision.total_elapsed_ms,
                ),
            )
        except Exception as exc:
            logger.exception("cascade_persist_failed: %s", exc)
