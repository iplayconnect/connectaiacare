"""Caller resolver — quem é a pessoa do outro lado da ligação?

Resolve `caller_phone` (vem do INVITE) em:
- patient_id (se quem ligou é o próprio paciente reportando)
- caregiver_id (se é cuidador profissional/familiar)
- user_id (pra carregar memória per-user da Sofia)

Usado pelo `inbound_bridge.py` antes de spawn da GrokCallSession,
pra que o `persona_ctx` carregue memory + active_context da Sofia
em vez de iniciar conversa em branco (que era o estado padrão).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from services.persistence import _fetch_one

logger = logging.getLogger("caller_resolver")


def _normalize_phone(phone: str) -> str:
    """Mantém só dígitos. Aceita +5551..., 5551..., 51..., etc."""
    return re.sub(r"\D", "", phone or "")


def _phone_variants(phone: str) -> list[str]:
    """Gera variantes do número pra match em diferentes cadastros.

    Ex: '5551996161700' → ['5551996161700', '551996161700',
                            '51996161700', '+5551996161700']
    """
    n = _normalize_phone(phone)
    if not n:
        return []
    variants = {n, "+" + n}
    if n.startswith("55") and len(n) >= 12:
        without_55 = n[2:]
        variants.add(without_55)
        variants.add("+" + without_55)
    if not n.startswith("55") and len(n) in (10, 11):
        with_55 = "55" + n
        variants.add(with_55)
        variants.add("+" + with_55)
    return list(variants)


def resolve_caller(
    caller_phone: str, tenant_id: str,
) -> dict[str, Any]:
    """Resolve caller_phone em ids da Sofia.

    Retorna dict:
        {
          patient_id: UUID|None,
          caregiver_id: UUID|None,
          user_id: UUID|None,
          full_name: str,
          persona: 'cuidador_pro'|'paciente_b2c'|'familia'|'anonymous',
          phone_type: 'personal'|'shared'|'unknown',
          extra_context: {patient: dict|None, ...}
        }

    Cascata (em ordem):
    1. caregivers.phone match → cuidador profissional
    2. users.phone match → user direto (médico/enfermeiro/admin)
    3. patients.responsible.phone match → familiar de paciente
    4. Nenhum → anonymous
    """
    out: dict[str, Any] = {
        "patient_id": None,
        "caregiver_id": None,
        "user_id": None,
        "full_name": "",
        "persona": "anonymous",
        "phone_type": "unknown",
        "extra_context": {},
    }

    variants = _phone_variants(caller_phone)
    if not variants:
        return out

    # ─── 1) Cuidador? ────────────────────────────────────────────
    for v in variants:
        cg = _fetch_one(
            """
            SELECT id::text AS caregiver_id, full_name, phone_type, role,
                   tenant_id
            FROM aia_health_caregivers
            WHERE tenant_id = %s AND phone = %s AND active = TRUE
            LIMIT 1
            """,
            (tenant_id, v),
        )
        if cg:
            out["caregiver_id"] = cg["caregiver_id"]
            out["full_name"] = cg["full_name"]
            out["phone_type"] = cg.get("phone_type") or "unknown"
            out["persona"] = "cuidador_pro"
            # User vinculado ao cuidador (pra memory) — se tiver
            user_link = _fetch_one(
                "SELECT id::text AS user_id FROM aia_health_users "
                "WHERE caregiver_id = %s LIMIT 1",
                (cg["caregiver_id"],),
            )
            if user_link:
                out["user_id"] = user_link["user_id"]
            logger.info(
                "caller_resolved_as_caregiver caregiver_id=%s name=%s",
                out["caregiver_id"], out["full_name"],
            )
            return out

    # ─── 2) User direto (médico/enfermeiro/admin)? ──────────────
    for v in variants:
        user = _fetch_one(
            """
            SELECT id::text AS user_id, full_name, role
            FROM aia_health_users
            WHERE tenant_id = %s AND phone = %s AND active = TRUE
            LIMIT 1
            """,
            (tenant_id, v),
        )
        if user:
            out["user_id"] = user["user_id"]
            out["full_name"] = user["full_name"]
            role = user.get("role") or "anonymous"
            persona_map = {
                "medico": "medico",
                "enfermeiro": "enfermeiro",
                "admin_tenant": "admin_tenant",
                "super_admin": "super_admin",
            }
            out["persona"] = persona_map.get(role, "anonymous")
            logger.info(
                "caller_resolved_as_user user_id=%s name=%s role=%s",
                out["user_id"], out["full_name"], role,
            )
            return out

    # ─── 3) Familiar de paciente (responsible.phone)? ──────────
    for v in variants:
        # responsible JSONB pode ter formato legado ({phone, name}) ou
        # novo ({family: [{phone}], nurse_override: {phone}})
        pat = _fetch_one(
            """
            SELECT id::text AS patient_id, full_name, nickname,
                   conditions, allergies, care_unit, room_number,
                   responsible
            FROM aia_health_patients
            WHERE tenant_id = %s
              AND active = TRUE
              AND (
                responsible->>'phone' = %s
                OR responsible::text LIKE %s
              )
            LIMIT 1
            """,
            (tenant_id, v, f"%{v}%"),
        )
        if pat:
            out["patient_id"] = pat["patient_id"]
            # Tenta achar nome do familiar no responsible JSONB
            resp = pat.get("responsible") or {}
            family_name = ""
            if isinstance(resp, dict):
                if resp.get("phone") in variants:
                    family_name = resp.get("name") or ""
                elif isinstance(resp.get("family"), list):
                    for f in resp["family"]:
                        if isinstance(f, dict) and f.get("phone") in variants:
                            family_name = f.get("name") or ""
                            break
            out["full_name"] = family_name or "Familiar"
            out["persona"] = "familia"
            out["extra_context"]["patient"] = _enrich_patient_context(pat)
            logger.info(
                "caller_resolved_as_family patient_id=%s family_name=%s",
                out["patient_id"], family_name,
            )
            return out

    # ─── 4) Paciente self-reporting (B2C com is_self_reporting)? ──
    for v in variants:
        pat = _fetch_one(
            """
            SELECT id::text AS patient_id, full_name, nickname,
                   conditions, allergies, care_unit, room_number
            FROM aia_health_patients
            WHERE tenant_id = %s AND active = TRUE
              AND is_self_reporting = TRUE
              AND (
                responsible->>'phone' = %s
                OR responsible::text LIKE %s
              )
            LIMIT 1
            """,
            (tenant_id, v, f"%{v}%"),
        )
        if pat:
            out["patient_id"] = pat["patient_id"]
            out["full_name"] = pat["full_name"]
            out["persona"] = "paciente_b2c"
            out["extra_context"]["patient"] = _enrich_patient_context(pat)
            logger.info(
                "caller_resolved_as_patient_self patient_id=%s",
                out["patient_id"],
            )
            return out

    # ─── 5) Phone não cadastrado em lugar nenhum = LEAD COMERCIAL ──
    # Não é anonymous (que era um buraco) — é alguém potencial que liga
    # querendo conhecer a plataforma. Sofia entra em modo comercial.
    out["persona"] = "comercial"
    out["full_name"] = ""
    logger.info(
        "caller_unrecognized_lead phone=%s tenant=%s — modo comercial",
        caller_phone, tenant_id,
    )
    return out


def _enrich_patient_context(pat: dict) -> dict:
    """Adiciona contexto clínico recente do paciente.

    Carrega:
    - Medicações ativas (top 5 mais recentes)
    - Último care_event resumo (data + summary + classification)
    - Alertas abertos count + tipos
    - Voltado pra Sofia ter contexto rico já no primeiro turno.
    """
    from services.persistence import _fetch_one, _fetch_all

    base = {
        "id": pat["patient_id"],
        "full_name": pat["full_name"],
        "nickname": pat.get("nickname"),
        "conditions": pat.get("conditions") or [],
        "allergies": pat.get("allergies") or [],
        "care_unit": pat.get("care_unit"),
        "room_number": pat.get("room_number"),
    }

    try:
        # Medicações ativas (top 5)
        meds = _fetch_all(
            """
            SELECT medication_name, dose, route,
                   times_of_day::text AS times_of_day
            FROM aia_health_medication_schedules
            WHERE patient_id = %s AND active = TRUE
            ORDER BY created_at DESC LIMIT 5
            """,
            (pat["patient_id"],),
        )
        if meds:
            base["active_medications"] = [
                {
                    "name": m.get("medication_name"),
                    "dose": m.get("dose"),
                    "route": m.get("route"),
                    "times": m.get("times_of_day"),
                }
                for m in meds
            ]
    except Exception:
        pass

    try:
        last_event = _fetch_one(
            """
            SELECT human_id, event_type, current_classification, summary,
                   opened_at::text AS opened_at, status
            FROM aia_health_care_events
            WHERE patient_id = %s
            ORDER BY opened_at DESC LIMIT 1
            """,
            (pat["patient_id"],),
        )
        if last_event:
            base["last_event"] = {
                "human_id": last_event.get("human_id"),
                "type": last_event.get("event_type"),
                "classification": last_event.get("current_classification"),
                "summary": last_event.get("summary"),
                "opened_at": last_event.get("opened_at"),
                "status": last_event.get("status"),
            }
    except Exception:
        pass

    try:
        open_alerts = _fetch_all(
            """
            SELECT severity, COUNT(*) AS cnt
            FROM aia_health_alerts
            WHERE patient_id = %s AND status IN ('open', 'acknowledged')
            GROUP BY severity
            """,
            (pat["patient_id"],),
        )
        if open_alerts:
            base["open_alerts"] = [
                {"severity": a.get("severity"), "count": a.get("cnt")}
                for a in open_alerts
            ]
    except Exception:
        pass

    return base
