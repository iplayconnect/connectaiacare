"""Serviço de configuração por tenant — timings, escalação, feature flags.

Lê `aia_health_tenant_config` e aplica overrides por classificação.
Cache em memória com TTL curto (60s) — configs mudam raramente.

Uso típico:
    cfg = get_tenant_config_service()
    timings = cfg.get_timings('connectaiacare_demo', classification='urgent')
    # {'pattern_analysis_after_min': 5, 'check_in_after_min': 8, ...}

    policy = cfg.get_escalation_policy('connectaiacare_demo', classification='critical')
    # ['central', 'nurse', 'doctor', 'family_1', 'family_2', 'family_3']

    contacts = cfg.get_contacts('connectaiacare_demo')
    # {'central': {'name': '...', 'phone': '...'}, 'nurse': {...}, ...}

Feature flags:
    if cfg.is_feature_enabled('connectaiacare_demo', 'sofia_voice_calls'): ...
"""
from __future__ import annotations

import time
from typing import Any

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 60

# Defaults robustos caso tenant_config não exista ou falhe query
_DEFAULT_CONFIG: dict[str, Any] = {
    "central_phone": None,
    "central_name": "Central",
    "nurse_phone": None,
    "nurse_name": "Enfermagem",
    "doctor_phone": None,
    "doctor_name": "Médico de plantão",
    "pattern_analysis_after_min": 5,
    "check_in_after_min": 10,
    "closure_decision_after_min": 30,
    "escalation_level1_wait_min": 5,
    "escalation_level2_wait_min": 10,
    "escalation_level3_wait_min": 10,
    "timings": {},
    "escalation_policy": {
        "critical": ["central", "nurse", "doctor", "family_1", "family_2", "family_3"],
        "urgent": ["central", "nurse", "family_1"],
        "attention": ["central"],
        "routine": [],
    },
    "features": {
        "proactive_checkin": True,
        "pattern_detection": True,
        "sofia_voice_calls": True,
        "medmonitor_integration": False,
    },
}


class TenantConfigService:
    def __init__(self):
        self.db = get_postgres()
        self._cache: dict[str, tuple[dict[str, Any], float]] = {}

    # ---------- core ----------
    def get_config(self, tenant_id: str) -> dict[str, Any]:
        now = time.time()
        cached = self._cache.get(tenant_id)
        if cached and (now - cached[1]) < CACHE_TTL_SECONDS:
            return cached[0]

        row = self.db.fetch_one(
            """
            SELECT central_phone, central_name, nurse_phone, nurse_name,
                   doctor_phone, doctor_name,
                   pattern_analysis_after_min, check_in_after_min, closure_decision_after_min,
                   escalation_level1_wait_min, escalation_level2_wait_min, escalation_level3_wait_min,
                   timings, escalation_policy, features
            FROM aia_health_tenant_config
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        if not row:
            logger.warning("tenant_config_not_found_using_defaults", tenant_id=tenant_id)
            return dict(_DEFAULT_CONFIG)

        config = dict(row)
        # Normalização: jsonb fields podem vir como dict ou str dependendo do driver
        for k in ("timings", "escalation_policy", "features"):
            v = config.get(k)
            if isinstance(v, str):
                import json
                try:
                    config[k] = json.loads(v)
                except Exception:
                    config[k] = _DEFAULT_CONFIG[k]
            elif v is None:
                config[k] = _DEFAULT_CONFIG[k]

        self._cache[tenant_id] = (config, now)
        return config

    def invalidate_cache(self, tenant_id: str | None = None) -> None:
        if tenant_id:
            self._cache.pop(tenant_id, None)
        else:
            self._cache.clear()

    # ---------- getters convenientes ----------
    def get_timings(self, tenant_id: str, classification: str | None = None) -> dict[str, int]:
        cfg = self.get_config(tenant_id)
        base = {
            "pattern_analysis_after_min": cfg["pattern_analysis_after_min"],
            "check_in_after_min": cfg["check_in_after_min"],
            "closure_decision_after_min": cfg["closure_decision_after_min"],
            "escalation_level1_wait_min": cfg["escalation_level1_wait_min"],
            "escalation_level2_wait_min": cfg["escalation_level2_wait_min"],
            "escalation_level3_wait_min": cfg["escalation_level3_wait_min"],
        }
        # Override por classificação se presente
        if classification:
            overrides = (cfg.get("timings") or {}).get(classification) or {}
            base.update({k: v for k, v in overrides.items() if isinstance(v, int) and v >= 0})
        return base

    def get_escalation_policy(self, tenant_id: str, classification: str) -> list[str]:
        cfg = self.get_config(tenant_id)
        policy = cfg.get("escalation_policy") or {}
        return list(policy.get(classification) or [])

    def get_contacts(self, tenant_id: str) -> dict[str, dict[str, str | None]]:
        """Retorna os contatos da "casa" (aplicam a todos pacientes do tenant).
        Contatos de família vêm do paciente (patients.responsible.family[]).
        """
        cfg = self.get_config(tenant_id)
        return {
            "central": {"name": cfg.get("central_name"), "phone": cfg.get("central_phone")},
            "nurse": {"name": cfg.get("nurse_name"), "phone": cfg.get("nurse_phone")},
            "doctor": {"name": cfg.get("doctor_name"), "phone": cfg.get("doctor_phone")},
        }

    def is_feature_enabled(self, tenant_id: str, feature: str) -> bool:
        cfg = self.get_config(tenant_id)
        features = cfg.get("features") or {}
        return bool(features.get(feature, False))


_tenant_config_instance: TenantConfigService | None = None


def get_tenant_config_service() -> TenantConfigService:
    global _tenant_config_instance
    if _tenant_config_instance is None:
        _tenant_config_instance = TenantConfigService()
    return _tenant_config_instance
