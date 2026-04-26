"""Persistência mínima da voice-call-service. Reusa o mesmo PG do
sofia-service (`aia_health_sofia_*` tables) — Sofia tem visão unificada
do que aconteceu, seja chat texto, voz browser ou ligação telefônica.

Pra evitar acoplar imports do sofia-service container, replicamos
helpers core aqui (mesmas queries, mesmas tabelas).
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config import Config

logger = logging.getLogger("voice_persistence")
_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 4, Config.DATABASE_URL)
        psycopg2.extras.register_uuid()
    return _pool


@contextmanager
def _cursor(commit: bool = True):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        yield cur
        if commit:
            conn.commit()
        cur.close()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _fetch_one(sql: str, params=()) -> dict | None:
    with _cursor(commit=False) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _execute(sql: str, params=()) -> None:
    with _cursor() as cur:
        cur.execute(sql, params)


def _insert_returning(sql: str, params=()) -> dict | None:
    with _cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


# ─── Sessions ───

def get_or_create_session(
    *, tenant_id: str, persona: str, user_id: str | None = None,
    phone: str | None = None, patient_id: str | None = None,
    channel: str = "voice_call",
) -> dict:
    """Mesma lógica do sofia-service.persistence.get_or_create_session
    mas channel='voice_call' por default."""
    if user_id:
        row = _fetch_one(
            """SELECT id, persona, channel FROM aia_health_sofia_sessions
               WHERE tenant_id = %s AND user_id = %s AND closed_at IS NULL
                 AND last_active_at > NOW() - INTERVAL '1 hour'
               ORDER BY last_active_at DESC LIMIT 1""",
            (tenant_id, user_id),
        )
        if row:
            _execute(
                "UPDATE aia_health_sofia_sessions SET last_active_at = NOW() WHERE id = %s",
                (row["id"],),
            )
            return row
    return _insert_returning(
        """INSERT INTO aia_health_sofia_sessions
            (tenant_id, persona, user_id, phone, patient_id, channel)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, persona, channel""",
        (tenant_id, persona, user_id, phone, patient_id, channel),
    )


def append_message_voice_call(
    *, session_id: str, tenant_id: str, role: str, content: str | None = None,
    tool_name: str | None = None, tool_input: dict | None = None,
    tool_output: dict | None = None, model: str | None = None,
) -> None:
    _execute(
        """INSERT INTO aia_health_sofia_messages
            (session_id, tenant_id, role, content, tool_name, tool_input,
             tool_output, model, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            session_id, tenant_id, role, content, tool_name,
            psycopg2.extras.Json(tool_input) if tool_input else None,
            psycopg2.extras.Json(tool_output) if tool_output else None,
            model,
            psycopg2.extras.Json({"channel": "voice_call", "provider": "grok"}),
        ),
    )


# ─── Persona prompt + memory injection ───

def build_persona_prompt(persona_ctx: dict) -> str:
    """Carrega o prompt da persona + injeta memória cross-session.
    Replica o que sofia-service base_agent.system_prompt faz, mas usando
    leitura direta do PG (não temos acesso aos arquivos .txt aqui)."""
    persona = persona_ctx.get("persona") or "anonymous"
    name = persona_ctx.get("full_name") or "amigo(a)"

    # Fallback: prompt sintético baseado em persona quando não há acesso
    # ao filesystem do sofia-service. NA FASE 1 fica simples; podemos
    # depois montar volume compartilhado pra ler os .txt direto.
    base = (
        "Você é a Sofia, assistente da ConnectaIACare. Tom natural, caloroso, "
        "frases curtas. Não diagnostica nem prescreve — apoia profissionais "
        "e cuidadores."
    )

    role_line = {
        "medico": "Está falando com um(a) médico(a) — pode usar termos clínicos.",
        "enfermeiro": "Está falando com enfermagem.",
        "cuidador_pro": "Está falando com cuidador profissional.",
        "familia": "Está falando com familiar do paciente — tom acolhedor.",
        "paciente_b2c": "Está falando com paciente B2C — tom acolhedor.",
        "admin_tenant": "Está falando com admin da plataforma.",
        "super_admin": "Está falando com super admin.",
    }.get(persona, "")

    parts = [base, role_line, f"Usuário na ligação: {name}."]

    # Memória cross-session
    mem_block = _load_memory_block(persona_ctx.get("user_id"))
    if mem_block:
        parts.append(mem_block)

    return "\n".join(p for p in parts if p)


def _load_memory_block(user_id: str | None) -> str:
    """Lê aia_health_sofia_user_memory + formata em markdown."""
    if not user_id:
        return ""
    enabled = _fetch_one(
        "SELECT sofia_memory_enabled FROM aia_health_users WHERE id = %s",
        (user_id,),
    )
    if not enabled or not enabled.get("sofia_memory_enabled"):
        return ""
    row = _fetch_one(
        "SELECT summary, key_facts FROM aia_health_sofia_user_memory WHERE user_id = %s",
        (user_id,),
    )
    if not row:
        return ""
    parts = ["\n# MEMÓRIA SOBRE O USUÁRIO (de conversas anteriores)"]
    if row.get("summary"):
        parts.append(row["summary"])
    facts = row.get("key_facts") or {}
    if isinstance(facts, dict) and facts:
        parts.append("\n## Fatos importantes:")
        for k_label, k_field in [
            ("Contexto", "role_context"),
            ("Preferências", "preferences"),
            ("Tópicos em curso", "ongoing_topics"),
            ("Preocupações", "concerns"),
        ]:
            v = facts.get(k_field)
            if isinstance(v, list) and v:
                parts.append(f"- {k_label}: " + "; ".join(str(x) for x in v[:5]))
            elif isinstance(v, str) and v:
                parts.append(f"- {k_label}: {v}")
    return "\n".join(parts)


def update_user_memory_force(user_id: str | None) -> None:
    """No fim da ligação dispara extração de memória user no sofia-service.
    Chamada não-bloqueante: se falhar, próxima sessão da Sofia faz."""
    if not user_id:
        return
    try:
        import httpx
        url = f"{Config.SOFIA_SERVICE_URL}/sofia/memory/update"
        r = httpx.post(url, json={"user_id": user_id}, timeout=20.0)
        if r.status_code == 200:
            data = r.json()
            logger.info(
                "memory_writeback_done user_id=%s updated=%s summary_chars=%d facts=%s",
                user_id,
                data.get("updated"),
                data.get("summary_chars") or 0,
                data.get("facts_keys") or [],
            )
        else:
            logger.warning(
                "memory_writeback_http_%d body=%s",
                r.status_code, r.text[:200],
            )
    except Exception as exc:
        logger.warning("memory_writeback_failed user_id=%s: %s", user_id, exc)


# ─── Tools (replica enxuta do execute_tool sofia-service) ───

# Tools com handler local (DB direto)
_LOCAL_TOOLS = {
    "get_patient_summary": "_tool_get_patient_summary",
    "create_care_event": "_tool_create_care_event",
    "schedule_teleconsulta": "_tool_schedule_teleconsulta",
    "list_medication_schedules": "_tool_list_medication_schedules",
    "get_patient_vitals": "_tool_get_patient_vitals",
}

# Tools que delegamos via HTTP pro sofia-service (motor de cruzamentos
# pesado — evita duplicar ~700 linhas de lógica)
_REMOTE_TOOLS = {
    "query_drug_rules",
    "check_drug_interaction",
    "list_beers_avoid_in_condition",
    "check_medication_safety",
    "query_clinical_guidelines",
}


def execute_voice_tool(name: str, args: dict, persona_ctx: dict) -> dict:
    """Roteia tool: handler local ou HTTP pro sofia-service."""
    if name in _LOCAL_TOOLS:
        handler = globals().get(_LOCAL_TOOLS[name])
        if not handler:
            return {"ok": False, "error": "handler_missing"}
        try:
            return handler(persona_ctx=persona_ctx, **args)
        except Exception as exc:
            logger.exception("voice_tool_local_failed name=%s", name)
            return {"ok": False, "error": str(exc)}

    if name in _REMOTE_TOOLS:
        return _execute_remote_tool(name, args, persona_ctx)

    return {"ok": False, "error": f"tool_not_available_in_voice:{name}"}


def _execute_remote_tool(name: str, args: dict, persona_ctx: dict) -> dict:
    """HTTP POST pro sofia-service /sofia/tool/execute. Evita duplicar
    código pesado (dose_validator, queries do motor)."""
    try:
        import httpx
        url = f"{Config.SOFIA_SERVICE_URL}/sofia/tool/execute"
        payload = {"name": name, "args": args, "persona": persona_ctx}
        r = httpx.post(url, json=payload, timeout=10.0)
        if r.status_code != 200:
            return {
                "ok": False, "error": f"sofia_tool_http_{r.status_code}",
                "body": r.text[:300],
            }
        data = r.json()
        return data.get("output") or data
    except Exception as exc:
        logger.exception("voice_tool_remote_failed name=%s", name)
        return {"ok": False, "error": str(exc)}


def _tool_get_patient_summary(*, persona_ctx: dict, patient_id: str | None = None, **_: Any) -> dict:
    pid = patient_id or persona_ctx.get("patient_id")
    if not pid:
        return {"ok": False, "error": "no_patient"}
    row = _fetch_one(
        """SELECT id, full_name, nickname, conditions, allergies,
                  care_unit, room_number
           FROM aia_health_patients WHERE id = %s""",
        (pid,),
    )
    if not row:
        return {"ok": False, "error": "patient_not_found"}
    # Conta meds ativas
    meds = _fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_medication_schedules
           WHERE patient_id = %s AND active = TRUE""",
        (pid,),
    )
    return {
        "ok": True,
        "patient": {**row, "active_meds_count": (meds or {}).get("n") or 0},
    }


def _tool_create_care_event(
    *, persona_ctx: dict, patient_id: str, summary: str,
    classification: str = "routine", **_: Any,
) -> dict:
    row = _insert_returning(
        """INSERT INTO aia_health_care_events
            (tenant_id, patient_id, classification, status,
             initiator_role, source)
        VALUES (%s, %s, %s, 'open', 'sofia_voice_call', 'voice_call')
        RETURNING id""",
        (persona_ctx.get("tenant_id") or Config.DEFAULT_TENANT,
         patient_id, classification),
    )
    if not row:
        return {"ok": False, "error": "create_failed"}
    # Adiciona o report inicial
    _execute(
        """INSERT INTO aia_health_reports
            (care_event_id, tenant_id, patient_id, transcription,
             classification, source)
        VALUES (%s, %s, %s, %s, %s, 'voice_call')""",
        (row["id"], persona_ctx.get("tenant_id") or Config.DEFAULT_TENANT,
         patient_id, summary, classification),
    )
    return {"ok": True, "care_event_id": str(row["id"])}


def _tool_list_medication_schedules(
    *, persona_ctx: dict, patient_id: str | None = None, **_: Any,
) -> dict:
    pid = patient_id or persona_ctx.get("patient_id")
    if not pid:
        return {"ok": False, "error": "no_patient"}
    rows = _fetch_one  # placeholder, vamos usar fetch_all
    with _cursor(commit=False) as cur:
        cur.execute(
            """SELECT medication_name, dose, dose_form, route,
                      schedule_type, times_of_day, with_food,
                      special_instructions, warnings
               FROM aia_health_medication_schedules
               WHERE patient_id = %s AND active = TRUE
               ORDER BY medication_name""",
            (pid,),
        )
        meds = [dict(r) for r in cur.fetchall()]
    # Sanitize times_of_day (pg time array → strings)
    for m in meds:
        tods = m.get("times_of_day") or []
        m["times_of_day"] = [
            t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)
            for t in tods
        ]
    return {"ok": True, "patient_id": str(pid), "count": len(meds), "medications": meds}


def _tool_get_patient_vitals(
    *, persona_ctx: dict, patient_id: str | None = None, days: int = 7, **_: Any,
) -> dict:
    pid = patient_id or persona_ctx.get("patient_id")
    if not pid:
        return {"ok": False, "error": "no_patient"}
    days = max(1, min(int(days or 7), 90))
    with _cursor(commit=False) as cur:
        cur.execute(
            """SELECT measured_at, bp_systolic, bp_diastolic, heart_rate,
                      respiratory_rate, oxygen_saturation, temperature_c,
                      blood_glucose, notes
               FROM aia_health_vital_measurements
               WHERE patient_id = %s
                 AND measured_at > NOW() - INTERVAL '%s days'
               ORDER BY measured_at DESC LIMIT 30""",
            (pid, days),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if r.get("measured_at"):
            r["measured_at"] = r["measured_at"].isoformat()
    return {"ok": True, "patient_id": str(pid), "days": days, "count": len(rows), "vitals": rows}


def _tool_schedule_teleconsulta(
    *, persona_ctx: dict, patient_id: str, requested_for: str, **_: Any,
) -> dict:
    row = _insert_returning(
        """INSERT INTO aia_health_teleconsultas
            (tenant_id, patient_id, requested_for, status,
             initiator_role, source)
        VALUES (%s, %s, %s, 'scheduling',
                COALESCE(%s, 'caregiver'), 'voice_call')
        RETURNING id""",
        (persona_ctx.get("tenant_id") or Config.DEFAULT_TENANT,
         patient_id, requested_for, persona_ctx.get("persona")),
    )
    if not row:
        return {"ok": False, "error": "create_failed"}
    return {"ok": True, "teleconsulta_id": str(row["id"])}
