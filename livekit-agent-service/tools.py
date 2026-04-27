"""LiveKit Agents — tools port das 10 tools que Sofia tem em ligação.

Mantém o mesmo contrato de execução do voice-call-service: tools que precisam
de revisão clínica passam pelo Safety Guardrail backend antes de executar.

Reusa lógica de persistence (postgres) e HTTP calls do sofia-service, igual
ao voice-call-service/services/persistence.py — copiado em vez de importado
porque containers separados.
"""
from __future__ import annotations

import json
import os
from typing import Annotated

import httpx
import psycopg2
import psycopg2.extras
from livekit.agents import llm

import structlog

logger = structlog.get_logger()

# ════════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL")
SOFIA_SERVICE_URL = os.getenv("SOFIA_SERVICE_URL", "http://sofia-service:5030")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://api:5055")

_TOOLS_REQUIRING_REVIEW = {
    "create_care_event",
    "schedule_teleconsulta",
    "escalate_to_attendant",
}

_TOOLS_CLINICAL_INFO = {
    "get_patient_summary",
    "list_medication_schedules",
    "get_patient_vitals",
    "query_drug_rules",
    "check_drug_interaction",
    "check_medication_safety",
}

_DISCLAIMER = (
    "Esta é informação para apoiar a sua decisão — quem decide é sempre você "
    "com o médico responsável."
)


# ════════════════════════════════════════════════════════════════
# DB helpers
# ════════════════════════════════════════════════════════════════
def _db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _fetch_one(sql: str, params: tuple) -> dict | None:
    with _db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetch_all(sql: str, params: tuple) -> list[dict]:
    with _db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ════════════════════════════════════════════════════════════════
# Safety Guardrail HTTP shim
# ════════════════════════════════════════════════════════════════
def _route_through_guardrail(
    *,
    tenant_id: str,
    action_type: str,
    severity: str,
    summary: str,
    patient_id: str | None,
    triggered_by_tool: str,
    triggered_by_persona: str | None,
    sofia_session_id: str | None,
    details: dict,
) -> dict:
    """Chama POST /api/safety/route-action — bloqueia execução se queue."""
    try:
        r = httpx.post(
            f"{BACKEND_API_URL}/api/safety/route-action",
            json={
                "tenant_id": tenant_id,
                "action_type": action_type,
                "severity": severity,
                "summary": summary,
                "patient_id": patient_id,
                "triggered_by_tool": triggered_by_tool,
                "triggered_by_persona": triggered_by_persona,
                "sofia_session_id": sofia_session_id,
                "details": details,
            },
            timeout=10.0,
        )
        if r.status_code >= 400:
            logger.warning(
                "guardrail_http_error", status=r.status_code, body=r.text[:200]
            )
            return {"decide": "execute", "reason": "guardrail_unavailable"}
        return r.json()
    except Exception as e:
        logger.warning("guardrail_http_exception", error=str(e))
        return {"decide": "execute", "reason": "guardrail_exception"}


# ════════════════════════════════════════════════════════════════
# SofiaTools — registrada no agent
# ════════════════════════════════════════════════════════════════
class SofiaTools(llm.FunctionContext):
    """Tools que Sofia pode chamar durante a ligação.

    O contexto da call (patient_id, persona, tenant_id, scenario_id, session_id)
    é injetado via construtor — vem da metadata da room LiveKit.
    """

    def __init__(self, *, call_ctx: dict):
        super().__init__()
        # ctx tem: patient_id, persona, tenant_id, sofia_session_id,
        # scenario_code, scenario_id, allowed_tools (list)
        self.ctx = call_ctx

    def _allowed(self, tool_name: str) -> bool:
        allowed = self.ctx.get("allowed_tools") or []
        if not allowed:
            return True  # sem restrição configurada → libera
        return tool_name in allowed

    # ────────────────── Patient summary ──────────────────
    @llm.ai_callable(
        description="Resume condições, medicações e alergias do paciente. "
        "Use quando precisar do panorama clínico antes de responder.",
    )
    async def get_patient_summary(
        self,
        patient_id: Annotated[
            str, llm.TypeInfo(description="UUID do paciente")
        ] = "",
    ) -> str:
        if not self._allowed("get_patient_summary"):
            return "Tool não autorizada para este cenário."
        pid = patient_id or self.ctx.get("patient_id")
        if not pid:
            return "Sem patient_id no contexto."
        row = _fetch_one(
            """SELECT full_name, nickname, birth_date, gender,
                      conditions, medications, allergies, care_level
               FROM aia_health_patients WHERE id = %s""",
            (pid,),
        )
        if not row:
            return f"Paciente {pid} não encontrado."
        return json.dumps(
            {
                "full_name": row["full_name"],
                "nickname": row.get("nickname"),
                "care_level": row.get("care_level"),
                "conditions": row.get("conditions") or [],
                "medications": row.get("medications") or [],
                "allergies": row.get("allergies") or [],
                "_disclaimer": _DISCLAIMER,
            },
            ensure_ascii=False,
            default=str,
        )

    # ────────────────── Medication schedules ──────────────────
    @llm.ai_callable(
        description="Lista esquemas de medicação ativos do paciente "
        "(princípio ativo, dose, posologia).",
    )
    async def list_medication_schedules(
        self,
        patient_id: Annotated[
            str, llm.TypeInfo(description="UUID do paciente")
        ] = "",
    ) -> str:
        if not self._allowed("list_medication_schedules"):
            return "Tool não autorizada para este cenário."
        pid = patient_id or self.ctx.get("patient_id")
        if not pid:
            return "Sem patient_id no contexto."
        rows = _fetch_all(
            """SELECT medication_name, dose, schedule_type, times_of_day,
                      special_instructions
               FROM aia_health_medication_schedules
               WHERE patient_id = %s AND active = TRUE
               ORDER BY medication_name""",
            (pid,),
        )
        return json.dumps(
            {
                "schedules": [
                    {
                        "medication": r["medication_name"],
                        "dose": r.get("dose"),
                        "schedule": r.get("schedule_type"),
                        "times": r.get("times_of_day") or [],
                        "instructions": r.get("special_instructions"),
                    }
                    for r in rows
                ],
                "_disclaimer": _DISCLAIMER,
            },
            ensure_ascii=False,
        )

    # ────────────────── Patient vitals ──────────────────
    @llm.ai_callable(
        description="Sinais vitais recentes do paciente (PA, FC, FR, SatO2, "
        "temperatura, glicemia). Pode filtrar por dias.",
    )
    async def get_patient_vitals(
        self,
        patient_id: Annotated[
            str, llm.TypeInfo(description="UUID do paciente")
        ] = "",
        days: Annotated[
            int, llm.TypeInfo(description="Janela em dias, default 7")
        ] = 7,
    ) -> str:
        if not self._allowed("get_patient_vitals"):
            return "Tool não autorizada para este cenário."
        pid = patient_id or self.ctx.get("patient_id")
        if not pid:
            return "Sem patient_id no contexto."
        rows = _fetch_all(
            """SELECT measured_at, vital_type, value, unit
               FROM aia_health_patient_vitals
               WHERE patient_id = %s
                 AND measured_at > NOW() - (%s || ' days')::INTERVAL
               ORDER BY measured_at DESC LIMIT 50""",
            (pid, str(days)),
        )
        return json.dumps(
            {
                "vitals": [
                    {
                        "at": r["measured_at"].isoformat() if r["measured_at"] else None,
                        "type": r["vital_type"],
                        "value": r["value"],
                        "unit": r.get("unit"),
                    }
                    for r in rows
                ],
                "_disclaimer": _DISCLAIMER,
            },
            ensure_ascii=False,
            default=str,
        )

    # ────────────────── Create care event (REVIEW) ──────────────────
    @llm.ai_callable(
        description="Registra um evento de cuidado/queixa relatado pelo "
        "paciente ou cuidador. Severidade routine | attention | urgent | "
        "critical. Crítico/urgente passa por revisão humana antes de notificar.",
    )
    async def create_care_event(
        self,
        summary: Annotated[
            str, llm.TypeInfo(description="Resumo do que foi reportado")
        ],
        classification: Annotated[
            str,
            llm.TypeInfo(description="routine | attention | urgent | critical"),
        ],
        patient_id: Annotated[
            str, llm.TypeInfo(description="UUID do paciente")
        ] = "",
    ) -> str:
        if not self._allowed("create_care_event"):
            return "Tool não autorizada para este cenário."
        pid = patient_id or self.ctx.get("patient_id")
        if not pid:
            return "Sem patient_id no contexto."

        # Safety Guardrail intercepta tudo
        decision = _route_through_guardrail(
            tenant_id=self.ctx.get("tenant_id", "connectaiacare_demo"),
            action_type="register_history",
            severity=classification,
            summary=summary,
            patient_id=pid,
            triggered_by_tool="create_care_event",
            triggered_by_persona=self.ctx.get("persona"),
            sofia_session_id=self.ctx.get("sofia_session_id"),
            details={"classification": classification, "summary": summary},
        )
        if decision.get("decide") == "queue":
            return json.dumps({
                "queued_for_review": True,
                "queue_id": decision.get("queue_id"),
                "_message_for_sofia": (
                    "A informação foi anotada e a equipe clínica vai revisar. "
                    "Continue a conversa naturalmente."
                ),
                "_disclaimer": _DISCLAIMER,
            })

        # Execute
        with _db() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO aia_health_care_events
                    (tenant_id, patient_id, caregiver_phone,
                     initial_classification, current_classification,
                     event_type, status, summary, opened_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'analyzing', %s, NOW())
                RETURNING id""",
                (
                    self.ctx.get("tenant_id", "connectaiacare_demo"),
                    pid,
                    self.ctx.get("destination") or "voice_call",
                    classification, classification,
                    "voice_call_report", summary,
                ),
            )
            row = cur.fetchone()
            event_id = str(row["id"]) if row else None
        return json.dumps({
            "event_id": event_id,
            "classification": classification,
            "_disclaimer": _DISCLAIMER,
        })

    # ────────────────── Escalate to attendant (REVIEW) ──────────────────
    @llm.ai_callable(
        description="Escala situação para atendente humano (enfermeira / "
        "médico de plantão / família). Use quando: emergência, reação adversa "
        "grave, paciente em pânico, ou cuidador pede pra falar com humano.",
    )
    async def escalate_to_attendant(
        self,
        reason: Annotated[
            str, llm.TypeInfo(description="Por que está escalando")
        ],
        severity: Annotated[
            str, llm.TypeInfo(description="urgent ou critical")
        ],
        summary: Annotated[
            str,
            llm.TypeInfo(description="Resumo do que aconteceu pra atendente"),
        ],
    ) -> str:
        if not self._allowed("escalate_to_attendant"):
            return "Tool não autorizada para este cenário."
        decision = _route_through_guardrail(
            tenant_id=self.ctx.get("tenant_id", "connectaiacare_demo"),
            action_type=(
                "emergency_realtime" if severity == "critical"
                else "invoke_attendant"
            ),
            severity=severity,
            summary=summary,
            patient_id=self.ctx.get("patient_id"),
            triggered_by_tool="escalate_to_attendant",
            triggered_by_persona=self.ctx.get("persona"),
            sofia_session_id=self.ctx.get("sofia_session_id"),
            details={"reason": reason, "summary": summary},
        )
        if decision.get("decide") == "queue":
            return json.dumps({
                "queued_for_review": True,
                "queue_id": decision.get("queue_id"),
                "_message_for_sofia": (
                    "Já estou avisando a equipe e vão te dar retorno em "
                    "instantes. Vou ficar com você na linha."
                ),
                "_disclaimer": _DISCLAIMER,
            })
        return json.dumps({
            "escalated": True,
            "_message_for_sofia": (
                "A equipe foi acionada e vai te ligar de volta em instantes."
            ),
        })

    # ────────────────── Schedule teleconsulta ──────────────────
    @llm.ai_callable(
        description="Agenda teleconsulta com a equipe clínica do hospital. "
        "Use quando o paciente precisa falar com um médico em vídeo.",
    )
    async def schedule_teleconsulta(
        self,
        requested_for: Annotated[
            str,
            llm.TypeInfo(
                description="ISO 8601 ou 'asap' / 'today' / 'tomorrow'"
            ),
        ],
        reason: Annotated[
            str, llm.TypeInfo(description="Motivo clínico da consulta")
        ],
        patient_id: Annotated[
            str, llm.TypeInfo(description="UUID do paciente")
        ] = "",
    ) -> str:
        if not self._allowed("schedule_teleconsulta"):
            return "Tool não autorizada para este cenário."
        pid = patient_id or self.ctx.get("patient_id")
        if not pid:
            return "Sem patient_id no contexto."

        decision = _route_through_guardrail(
            tenant_id=self.ctx.get("tenant_id", "connectaiacare_demo"),
            action_type="register_history",
            severity="attention",
            summary=f"Solicitação de teleconsulta: {reason} (slot: {requested_for})",
            patient_id=pid,
            triggered_by_tool="schedule_teleconsulta",
            triggered_by_persona=self.ctx.get("persona"),
            sofia_session_id=self.ctx.get("sofia_session_id"),
            details={"requested_for": requested_for, "reason": reason},
        )
        if decision.get("decide") == "queue":
            return json.dumps({
                "queued_for_review": True,
                "_message_for_sofia": (
                    "Vou pedir o agendamento para a equipe. Eles confirmam "
                    "o horário com você."
                ),
            })
        return json.dumps({
            "scheduled": True, "requested_for": requested_for,
            "_disclaimer": _DISCLAIMER,
        })

    # ────────────────── Drug rules (sofia-service) ──────────────────
    @llm.ai_callable(
        description="Consulta motor clínico determinístico para regras de "
        "uma medicação (dose máxima, Beers, ACB, fall risk, ajustes renal/"
        "hepático, interações).",
    )
    async def query_drug_rules(
        self,
        medication_name: Annotated[
            str,
            llm.TypeInfo(
                description="Nome do princípio ativo ou comercial"
            ),
        ],
    ) -> str:
        if not self._allowed("query_drug_rules"):
            return "Tool não autorizada para este cenário."
        try:
            r = httpx.post(
                f"{SOFIA_SERVICE_URL}/api/sofia/tools/query_drug_rules",
                json={"medication_name": medication_name},
                timeout=10.0,
            )
            if r.status_code >= 400:
                return f"Falha consultando motor: {r.status_code}"
            data = r.json()
            data["_disclaimer"] = _DISCLAIMER
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return f"Falha consultando motor: {e}"
