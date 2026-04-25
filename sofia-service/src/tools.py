"""Sofia tool registry — 12 tools acessando o DB compartilhado.

Cada tool tem:
  - schema (parâmetros JSON Schema)
  - handler (callable que recebe **args + persona_ctx e retorna dict)
  - allowed_personas (RBAC)

O orchestrator filtra as tools antes de passar pro Gemini, baseado na
persona da sessão. Qualquer tool retorna dict com `ok: bool` + payload.
Erros vão como `ok: false, error: "..."`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

import requests

from src import persistence

logger = logging.getLogger(__name__)


# ────────────────────────────── helpers ──────────────────────────────

def _patient_summary_row(patient_id: str) -> dict | None:
    return persistence.fetch_one(
        """
        SELECT id, full_name, nickname, birth_date, gender,
               photo_url, care_unit, room_number, care_level,
               conditions, medications, allergies, responsible
        FROM aia_health_patients
        WHERE id = %s AND active = TRUE
        """,
        (patient_id,),
    )


def _resolve_patient_scope(persona_ctx: dict, patient_id: str | None) -> str | None:
    """Garante que a persona pode ver esse paciente.

    cuidador_pro / familia / paciente_b2c → restrito ao próprio vínculo
    medico / enfermeiro / admin_tenant / super_admin → tenant inteiro
    parceiro → restrito a allowed_patient_ids
    """
    persona = persona_ctx.get("persona")
    if persona in ("medico", "enfermeiro", "admin_tenant", "super_admin"):
        return patient_id
    if persona == "parceiro":
        allowed = set(persona_ctx.get("allowed_patient_ids") or [])
        if not patient_id and len(allowed) == 1:
            return next(iter(allowed))
        if patient_id and patient_id in allowed:
            return patient_id
        return None
    if persona == "cuidador_pro":
        # Hoje cuidador não tem vínculo direto a um paciente — ver os ativos do tenant
        return patient_id
    if persona == "familia":
        own = persona_ctx.get("patient_id")
        if not patient_id:
            return own
        return patient_id if own == patient_id else None
    if persona == "paciente_b2c":
        return persona_ctx.get("patient_id") or patient_id
    return None


# ────────────────────────────── tool handlers ──────────────────────────────

def _tool_get_patient_summary(*, persona_ctx: dict, patient_id: str | None = None, **_: Any) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    p = _patient_summary_row(pid)
    if not p:
        return {"ok": False, "error": "patient_not_found"}

    # Última leitura de vitais
    vitals = persistence.fetch_one(
        """
        SELECT bp_systolic, bp_diastolic, heart_rate, temperature_celsius,
               oxygen_saturation, glucose_mg_dl, recorded_at
        FROM aia_health_vital_signs
        WHERE patient_id = %s
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        (pid,),
    )
    open_event = persistence.fetch_one(
        """
        SELECT id, classification, status, summary, opened_at
        FROM aia_health_care_events
        WHERE patient_id = %s AND status NOT IN ('resolved', 'expired')
        ORDER BY opened_at DESC
        LIMIT 1
        """,
        (pid,),
    )
    return {
        "ok": True,
        "patient": {
            "id": str(p["id"]),
            "full_name": p["full_name"],
            "nickname": p.get("nickname"),
            "care_unit": p.get("care_unit"),
            "room_number": p.get("room_number"),
            "care_level": p.get("care_level"),
            "conditions": p.get("conditions") or [],
            "medications": p.get("medications") or [],
            "allergies": p.get("allergies") or [],
        },
        "last_vitals": vitals,
        "open_care_event": open_event,
    }


def _tool_get_patient_vitals(*, persona_ctx: dict, patient_id: str | None = None, days: int = 7, **_: Any) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    days = max(1, min(int(days or 7), 90))
    rows = persistence.fetch_all(
        """
        SELECT bp_systolic, bp_diastolic, heart_rate, temperature_celsius,
               oxygen_saturation, glucose_mg_dl, recorded_at
        FROM aia_health_vital_signs
        WHERE patient_id = %s
          AND recorded_at >= NOW() - (%s || ' days')::interval
        ORDER BY recorded_at DESC
        LIMIT 200
        """,
        (pid, str(days)),
    )
    return {"ok": True, "days": days, "count": len(rows), "vitals": rows}


def _tool_read_care_event_history(*, persona_ctx: dict, patient_id: str | None = None, limit: int = 10, **_: Any) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    limit = max(1, min(int(limit or 10), 50))
    rows = persistence.fetch_all(
        """
        SELECT id, classification, status, summary, event_type,
               opened_at, resolved_at, closed_reason
        FROM aia_health_care_events
        WHERE patient_id = %s
        ORDER BY opened_at DESC
        LIMIT %s
        """,
        (pid, limit),
    )
    return {"ok": True, "count": len(rows), "events": rows}


def _tool_list_medication_schedules(*, persona_ctx: dict, patient_id: str | None = None, **_: Any) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    rows = persistence.fetch_all(
        """
        SELECT id, medication_name, dose, dose_form, schedule_type,
               times_of_day, days_of_week, with_food, special_instructions,
               warnings, active
        FROM aia_health_medication_schedules
        WHERE patient_id = %s AND active = TRUE
        ORDER BY medication_name
        """,
        (pid,),
    )
    return {"ok": True, "count": len(rows), "schedules": rows}


def _tool_confirm_medication_taken(
    *,
    persona_ctx: dict,
    medication_event_id: str,
    confirmed_by: str | None = None,
    notes: str | None = None,
    **_: Any,
) -> dict:
    if persona_ctx.get("persona") not in ("cuidador_pro", "enfermeiro", "paciente_b2c"):
        return {"ok": False, "error": "persona_cannot_confirm"}
    persistence.execute(
        """
        UPDATE aia_health_medication_events
        SET status = 'taken',
            confirmed_at = NOW(),
            confirmed_by = COALESCE(%s, confirmed_by),
            notes = COALESCE(%s, notes)
        WHERE id = %s
        """,
        (confirmed_by, notes, medication_event_id),
    )
    return {"ok": True, "medication_event_id": medication_event_id}


def _tool_create_care_event(
    *,
    persona_ctx: dict,
    patient_id: str,
    summary: str,
    classification: str = "routine",
    event_type: str = "report",
    **_: Any,
) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    if classification not in ("routine", "attention", "urgent", "critical"):
        return {"ok": False, "error": "invalid_classification"}
    row = persistence.insert_returning(
        """
        INSERT INTO aia_health_care_events
            (patient_id, classification, status, summary, event_type, opened_at)
        VALUES (%s, %s, 'analyzing', %s, %s, NOW())
        RETURNING id, classification, status
        """,
        (pid, classification, summary, event_type),
    )
    return {"ok": True, "event": row}


def _tool_get_alert_status(*, persona_ctx: dict, **_: Any) -> dict:
    """Lista alertas não resolvidos do tenant.

    Schema (migration 001): level low|medium|high|critical, title, description,
    acknowledged_at, resolved_at. Sem 'status' explícito; derivamos:
      open       = resolved_at IS NULL AND acknowledged_at IS NULL
      acknowledged = resolved_at IS NULL AND acknowledged_at IS NOT NULL
      resolved   = resolved_at IS NOT NULL
    """
    tenant_id = persona_ctx.get("tenant_id") or "connectaiacare_demo"
    rows = persistence.fetch_all(
        """
        SELECT a.id, a.level, a.title, a.description,
               a.acknowledged_by, a.acknowledged_at, a.resolved_at,
               a.created_at, p.full_name AS patient_name, p.nickname AS patient_nickname
        FROM aia_health_alerts a
        LEFT JOIN aia_health_patients p ON p.id = a.patient_id
        WHERE a.tenant_id = %s AND a.resolved_at IS NULL
        ORDER BY
            CASE a.level
                WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                WHEN 'medium' THEN 2 ELSE 3 END,
            a.created_at DESC
        LIMIT 25
        """,
        (tenant_id,),
    )
    # Derive status pra UI/LLM ler facilmente
    for r in rows:
        if r.get("resolved_at"):
            r["status"] = "resolved"
        elif r.get("acknowledged_at"):
            r["status"] = "acknowledged"
        else:
            r["status"] = "open"
    return {"ok": True, "count": len(rows), "alerts": rows}


def _tool_search_patients(*, persona_ctx: dict, query: str = "", limit: int = 10, **_: Any) -> dict:
    persona = persona_ctx.get("persona")
    if persona not in ("medico", "enfermeiro", "admin_tenant", "super_admin", "cuidador_pro"):
        return {"ok": False, "error": "persona_cannot_search"}
    limit = max(1, min(int(limit or 10), 25))
    rows = persistence.fetch_all(
        """
        SELECT id, full_name, nickname, room_number, care_unit, care_level
        FROM aia_health_patients
        WHERE active = TRUE
          AND (full_name ILIKE %s OR nickname ILIKE %s)
        ORDER BY similarity(full_name, %s) DESC NULLS LAST, full_name
        LIMIT %s
        """,
        (f"%{query}%", f"%{query}%", query, limit),
    )
    return {"ok": True, "count": len(rows), "patients": rows}


def _tool_schedule_teleconsulta(
    *,
    persona_ctx: dict,
    patient_id: str,
    requested_for: str,
    initiator_role: str = "family",
    **_: Any,
) -> dict:
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    row = persistence.insert_returning(
        """
        INSERT INTO aia_health_teleconsultations
            (patient_id, state, requested_for, initiator_role)
        VALUES (%s, 'scheduling', %s, %s)
        RETURNING id, state, requested_for
        """,
        (pid, requested_for, initiator_role),
    )
    return {"ok": True, "teleconsulta": row}


def _tool_query_clinical_guidelines(
    *,
    persona_ctx: dict,
    topic: str,
    **_: Any,
) -> dict:
    """Busca em aia_health_knowledge_chunks (RAG simples por ILIKE).
    Sofia.3+ vai upgrade pra pgvector quando tivermos embeddings."""
    if persona_ctx.get("persona") not in ("medico", "enfermeiro"):
        return {"ok": False, "error": "persona_cannot_query_clinical"}
    rows = persistence.fetch_all(
        """
        SELECT id, source, title, content
        FROM aia_health_knowledge_chunks
        WHERE content ILIKE %s OR title ILIKE %s
        LIMIT 5
        """,
        (f"%{topic}%", f"%{topic}%"),
    )
    return {"ok": True, "count": len(rows), "chunks": rows}


def _tool_send_check_in(
    *,
    persona_ctx: dict,
    patient_id: str,
    message: str,
    **_: Any,
) -> dict:
    """Cria um care_event de check-in proativo. Não envia WhatsApp aqui —
    o scheduler proativo do api faz isso. Esta tool apenas registra a intenção."""
    pid = _resolve_patient_scope(persona_ctx, patient_id)
    if not pid:
        return {"ok": False, "error": "patient_not_in_scope"}
    row = persistence.insert_returning(
        """
        INSERT INTO aia_health_care_events
            (patient_id, classification, status, summary, event_type, opened_at)
        VALUES (%s, 'routine', 'analyzing', %s, 'check_in', NOW())
        RETURNING id
        """,
        (pid, f"Check-in solicitado pela Sofia: {message}"),
    )
    return {"ok": True, "event": row}


def _tool_get_my_subscription(*, persona_ctx: dict, **_: Any) -> dict:
    """Retorna dados do plano do user (B2C). Pra família/paciente saberem o que têm."""
    user_id = persona_ctx.get("user_id")
    if not user_id:
        return {"ok": False, "error": "no_user"}
    row = persistence.fetch_one(
        """
        SELECT plan_sku, subscription_active, subscription_started_at
        FROM aia_health_users
        WHERE id = %s
        """,
        (user_id,),
    )
    return {"ok": True, "subscription": row}


def _tool_check_medication_safety(
    *,
    persona_ctx: dict,
    medication_name: str,
    dose: str,
    patient_id: str | None = None,
    times_of_day: list[str] | None = None,
    route: str = "oral",
    schedule_type: str | None = None,
    **_: Any,
) -> dict:
    """Roda o motor de cruzamentos da prescrição candidata. Não persiste —
    apenas retorna risco/issues pra que o profissional decida."""
    if not medication_name or not dose:
        return {"ok": False, "error": "medication_name_and_dose_required"}
    pid = patient_id or persona_ctx.get("patient_id")
    api_base = os.getenv("BACKEND_API_URL", "http://api:5055")
    payload = {
        "medication_name": medication_name,
        "dose": dose,
        "route": route,
    }
    if times_of_day:
        payload["times_of_day"] = times_of_day
    if schedule_type:
        payload["schedule_type"] = schedule_type
    if pid:
        payload["patient_id"] = pid
    try:
        r = requests.post(
            f"{api_base}/api/clinical-rules/validate-prescription",
            json=payload,
            timeout=12,
        )
    except Exception as exc:
        logger.exception("check_medication_safety_http_failed")
        return {"ok": False, "error": f"backend_unreachable:{exc}"}
    if r.status_code != 200:
        return {
            "ok": False,
            "error": "validator_http_error",
            "status": r.status_code,
            "body": r.text[:500],
        }
    data = r.json() or {}
    validation = data.get("validation") or {}
    issues = validation.get("issues") or []
    summary = {
        "severity": validation.get("severity"),
        "blocked": validation.get("severity") == "block",
        "issue_count": len(issues),
        "by_code": sorted({i.get("code") for i in issues if i.get("code")}),
    }
    return {
        "ok": True,
        "patient_id": pid,
        "medication_name": medication_name,
        "dose": dose,
        "summary": summary,
        "validation": validation,
    }


# ────────────────────────────── registry ──────────────────────────────

TOOLS: dict[str, dict[str, Any]] = {
    "get_patient_summary": {
        "description": "Resumo do paciente: condições, medicações, alergias, último relato/evento aberto e últimos vitais. Use quando alguém pede 'como tá o(a) Fulano(a)?' ou precisa de contexto.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "UUID do paciente. Pode ser omitido se a persona já está vinculada a um paciente."},
            },
        },
        "handler": _tool_get_patient_summary,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin", "familia", "cuidador_pro", "paciente_b2c", "parceiro"],
    },
    "get_patient_vitals": {
        "description": "Sinais vitais (PA, FC, temperatura, SatO2, glicemia) dos últimos N dias.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "days": {"type": "integer", "minimum": 1, "maximum": 90, "description": "Dias pra trás (1-90). Default 7."},
            },
        },
        "handler": _tool_get_patient_vitals,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin", "familia", "cuidador_pro", "paciente_b2c", "parceiro"],
    },
    "read_care_event_history": {
        "description": "Histórico dos últimos N care_events (relatos + eventos clínicos) do paciente.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
        "handler": _tool_read_care_event_history,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin", "familia", "cuidador_pro", "parceiro"],
    },
    "list_medication_schedules": {
        "description": "Lista de medicações ativas do paciente (nome, dose, horários, instruções, warnings).",
        "parameters": {
            "type": "object",
            "properties": {"patient_id": {"type": "string"}},
        },
        "handler": _tool_list_medication_schedules,
        "allowed_personas": ["medico", "enfermeiro", "cuidador_pro", "familia", "paciente_b2c"],
    },
    "confirm_medication_taken": {
        "description": "Registra que o paciente tomou uma dose. Recebe ID do medication_event do calendário.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication_event_id": {"type": "string"},
                "confirmed_by": {"type": "string", "description": "Nome de quem confirmou (cuidador, paciente)"},
                "notes": {"type": "string"},
            },
            "required": ["medication_event_id"],
        },
        "handler": _tool_confirm_medication_taken,
        "allowed_personas": ["cuidador_pro", "enfermeiro", "paciente_b2c"],
    },
    "create_care_event": {
        "description": "Cria um care_event (relato, queixa, evento clínico). Sofia usa ao receber relato do cuidador/paciente. Classification: routine/attention/urgent/critical.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "summary": {"type": "string", "description": "Resumo factual do que aconteceu"},
                "classification": {"type": "string", "enum": ["routine", "attention", "urgent", "critical"]},
                "event_type": {"type": "string", "description": "Ex: report, fall, fever, symptom_complaint, check_in"},
            },
            "required": ["patient_id", "summary"],
        },
        "handler": _tool_create_care_event,
        "allowed_personas": ["cuidador_pro", "enfermeiro", "medico", "paciente_b2c", "familia"],
    },
    "get_alert_status": {
        "description": "Lista alertas abertos do tenant (não resolvidos / não expirados).",
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_get_alert_status,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin"],
    },
    "search_patients": {
        "description": "Busca paciente por nome (fuzzy). Use quando o usuário não disse o ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
        "handler": _tool_search_patients,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin", "cuidador_pro"],
    },
    "schedule_teleconsulta": {
        "description": "Cria solicitação de teleconsulta no estado 'scheduling'. Equipe médica do tenant aprova depois.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "requested_for": {"type": "string", "description": "Data/hora ISO 8601 desejada"},
                "initiator_role": {"type": "string", "enum": ["family", "patient", "caregiver", "doctor"]},
            },
            "required": ["patient_id", "requested_for"],
        },
        "handler": _tool_schedule_teleconsulta,
        "allowed_personas": ["familia", "paciente_b2c", "cuidador_pro", "medico"],
    },
    "query_clinical_guidelines": {
        "description": "Busca diretrizes clínicas (Beers, drug-drug interactions, doses geriátricas) na base de conhecimento.",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
        "handler": _tool_query_clinical_guidelines,
        "allowed_personas": ["medico", "enfermeiro"],
    },
    "send_check_in": {
        "description": "Cria um care_event de check-in proativo da Sofia (não dispara WhatsApp aqui — apenas registra).",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["patient_id", "message"],
        },
        "handler": _tool_send_check_in,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant"],
    },
    "check_medication_safety": {
        "description": "Valida uma prescrição candidata contra o motor de cruzamentos clínicos: dose máxima diária, alergias, interações medicamentosas (incluindo separação por horário), contraindicações por condição, ajuste renal/hepático, ACB score, risco de queda, NTI e constraints de sinais vitais. NÃO persiste a prescrição — apenas retorna a análise de risco. Use ANTES de criar/atualizar uma medication_schedule, ou quando o médico pergunta 'é seguro prescrever X mg de Y para o paciente Z?'.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication_name": {"type": "string", "description": "Nome do medicamento (princípio ativo ou nome comercial — o validador resolve aliases)."},
                "dose": {"type": "string", "description": "Dose por administração, ex: '10 mg', '0,5 mg', '1 g'."},
                "patient_id": {"type": "string", "description": "UUID do paciente (opcional se a persona já tem patient_id no contexto)."},
                "times_of_day": {"type": "array", "items": {"type": "string"}, "description": "Horários do dia em HH:MM, ex: ['08:00','20:00']. Necessário pra checar interações por separação de horário."},
                "route": {"type": "string", "description": "Via de administração. Default 'oral'."},
                "schedule_type": {"type": "string", "description": "Ex: 'fixed_daily', 'prn', 'weekly'."},
            },
            "required": ["medication_name", "dose"],
        },
        "handler": _tool_check_medication_safety,
        "allowed_personas": ["medico", "enfermeiro", "admin_tenant", "super_admin"],
    },
    "get_my_subscription": {
        "description": "Retorna o plano contratado do próprio user (B2C).",
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_get_my_subscription,
        "allowed_personas": ["paciente_b2c", "familia"],
    },
}


def tools_for_persona(persona: str) -> list[dict]:
    """Retorna lista de tools acessíveis pela persona, no formato ToolDefinition."""
    out = []
    for name, spec in TOOLS.items():
        if persona in spec["allowed_personas"]:
            out.append({
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
                "handler": spec["handler"],
            })
    return out


def execute_tool(name: str, args: dict, persona_ctx: dict) -> dict:
    spec = TOOLS.get(name)
    if not spec:
        return {"ok": False, "error": f"tool_not_found:{name}"}
    if persona_ctx.get("persona") not in spec["allowed_personas"]:
        return {"ok": False, "error": "persona_not_allowed"}
    try:
        return spec["handler"](persona_ctx=persona_ctx, **(args or {}))
    except Exception as exc:
        logger.exception("tool_exec_failed name=%s", name)
        return {"ok": False, "error": str(exc)}
