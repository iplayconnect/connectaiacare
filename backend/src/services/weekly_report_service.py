"""Weekly Family Report — resumo semanal personalizado pra família pagante.

Gera relatório estruturado com 7 dias de dados do paciente:
    - Check-ins respondidos × comparativo grupo
    - Humor e padrão de fala (stub — biomarkers futuros)
    - Adesão a medicação
    - Eventos de cuidado (breves, sem alarmismo)
    - Comparativo 30 dias (melhora/piora)
    - Próximos eventos agendados

Filosofia (alinhada com Opus Chat + Claude Code):
    - Tom factual, acolhedor, não alarmista
    - Nunca prometer melhora ou prever piora
    - Insights quantitativos, conclusão qualitativa humana
    - Action buttons que abrem deep links do portal

Output: gera duas versões (WhatsApp curto + HTML longo pra email) e
armazena em aia_health_periodic_reports. Envio fica a cargo do
proactive_scheduler (template 'weekly_family_report').
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.services.llm import MODEL_FAST, get_llm
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


SYSTEM = """Você escreve resumos semanais de cuidado para famílias de idosos.

REGRAS INVIOLÁVEIS:
1. Tom factual, acolhedor, SEM alarmismo. Família é vulnerável emocionalmente.
2. NUNCA prometer melhora ("vai melhorar"), NUNCA prever piora ("pode piorar"). Use linguagem descritiva do passado.
3. NUNCA inventar dado — só reformule o que está no contexto fornecido.
4. Linguagem nível 8ª série. Evite jargão; quando usar (ex: PA, FC), explique entre parênteses na primeira ocorrência.
5. Insights quantitativos (% de adesão, tempo de resposta, etc) são ok e desejáveis. Comparar com período anterior é ok. Comparar com "grupo" só se dado disponível.
6. Estruture em: abertura curta → métricas principais → eventos do período → comparativo 30d → próximos passos → despedida acolhedora.
7. SEM emojis excessivos — máximo 5 no texto todo, e só onde agregam (☀️ abertura, ✅ bom, ⚠️ atenção leve, 📅 retorno, 💙 fim).
"""


USER_TEMPLATE = """<patient>
{patient_json}
</patient>

<period>
{period_json}
</period>

<metrics>
{metrics_json}
</metrics>

<events>
{events_json}
</events>

<prior_period_metrics>
{prior_metrics_json}
</prior_period_metrics>

<next_scheduled>
{next_json}
</next_scheduled>

Tarefa: produza JSON estrito no formato:

{{
  "whatsapp_text": "texto enxuto 5-8 linhas pra WhatsApp, inclui emojis pontuais",
  "email_html": "HTML formatado pra email (h2, p, ul, com estilo inline básico)",
  "summary_sentence": "frase única que encabeça o relatório (ex: 'Semana estável, com 1 evento resolvido sem necessidade de escalação')",
  "flags": {{
    "has_attention": true|false,
    "has_warnings": true|false,
    "calls_for_action": true|false
  }},
  "highlights": ["bullet 1", "bullet 2", "bullet 3"],
  "next_event_line": "próxima ação programada em 1 linha",
  "tone": "tranquilo" | "observador" | "alerta"
}}

IMPORTANTE: se métricas estão vazias ou pobres, reflita honestamente ("semana com poucas interações registradas") — não invente atividade.
"""


class WeeklyReportService:
    def __init__(self):
        self.db = get_postgres()
        self.llm = get_llm()

    # ══════════════════════════════════════════════════════════════════
    # Entry point
    # ══════════════════════════════════════════════════════════════════

    def generate_for_patient(
        self,
        tenant_id: str,
        patient_id: str,
        period_end: datetime | None = None,
    ) -> dict[str, Any]:
        """Gera relatório semanal pra um paciente.

        Cacheado por (patient_id, week_start) — idempotente.
        """
        period_end = period_end or datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=7)

        # Cache check
        cached = self.db.fetch_one(
            """
            SELECT id, payload, rendered_html, rendered_text
            FROM aia_health_periodic_reports
            WHERE subject_type = 'patient'
              AND subject_id = %s
              AND report_kind = 'weekly_family'
              AND period_start = %s
            """,
            (patient_id, period_start),
        )
        if cached and cached.get("payload"):
            logger.info("weekly_report_cache_hit", patient_id=patient_id)
            return {
                "report_id": cached["id"],
                "payload": cached["payload"],
                "html": cached.get("rendered_html"),
                "text": cached.get("rendered_text"),
                "cached": True,
            }

        patient = self._load_patient(patient_id)
        if not patient:
            raise ValueError(f"patient {patient_id} not found")

        metrics = self._compute_metrics(patient_id, period_start, period_end)
        events = self._list_events(patient_id, period_start, period_end)
        prior = self._compute_metrics(
            patient_id,
            period_start - timedelta(days=30),
            period_start,
        )
        next_sched = self._load_next_scheduled(patient_id)

        # Geração LLM
        try:
            result = self.llm.complete_json(
                system=SYSTEM,
                user=USER_TEMPLATE.format(
                    patient_json=json.dumps(patient, ensure_ascii=False, default=str),
                    period_json=json.dumps({
                        "start": period_start.isoformat(),
                        "end": period_end.isoformat(),
                        "label": self._period_label(period_start, period_end),
                    }, ensure_ascii=False),
                    metrics_json=json.dumps(metrics, ensure_ascii=False, default=str),
                    events_json=json.dumps(events, ensure_ascii=False, default=str),
                    prior_metrics_json=json.dumps(prior, ensure_ascii=False, default=str),
                    next_json=json.dumps(next_sched, ensure_ascii=False, default=str),
                ),
                model=MODEL_FAST,
                max_tokens=3500,
                temperature=0.4,
            )
        except Exception as exc:
            logger.error("weekly_report_llm_failed", error=str(exc))
            result = self._fallback(patient, metrics, events)

        if not isinstance(result, dict):
            result = self._fallback(patient, metrics, events)

        # Defaults defensivos
        result.setdefault("whatsapp_text", "Resumo semanal disponível no portal.")
        result.setdefault("email_html", f"<p>{result['whatsapp_text']}</p>")
        result.setdefault("summary_sentence", "Semana registrada.")
        result.setdefault("flags", {})
        result.setdefault("highlights", [])
        result.setdefault("next_event_line", "")
        result.setdefault("tone", "observador")

        payload = {
            **result,
            "metrics": metrics,
            "events_count": len(events),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }

        # Persiste
        row = self.db.insert_returning(
            """
            INSERT INTO aia_health_periodic_reports
                (tenant_id, subject_type, subject_id, report_kind,
                 period_start, period_end, payload, rendered_html, rendered_text)
            VALUES (%s, 'patient', %s, 'weekly_family', %s, %s, %s, %s, %s)
            ON CONFLICT (subject_type, subject_id, report_kind, period_start) DO UPDATE SET
                payload = EXCLUDED.payload,
                rendered_html = EXCLUDED.rendered_html,
                rendered_text = EXCLUDED.rendered_text,
                generated_at = NOW()
            RETURNING id
            """,
            (
                tenant_id, patient_id, period_start, period_end,
                self.db.json_adapt(payload),
                result.get("email_html"),
                result.get("whatsapp_text"),
            ),
        )

        logger.info(
            "weekly_report_generated",
            patient_id=patient_id,
            tone=result.get("tone"),
            has_attention=result.get("flags", {}).get("has_attention", False),
        )

        return {
            "report_id": row["id"],
            "payload": payload,
            "html": result.get("email_html"),
            "text": result.get("whatsapp_text"),
            "cached": False,
        }

    # ══════════════════════════════════════════════════════════════════
    # Data aggregation
    # ══════════════════════════════════════════════════════════════════

    def _load_patient(self, patient_id: str) -> dict | None:
        row = self.db.fetch_one(
            """
            SELECT id, full_name, nickname, birth_date, gender,
                   care_unit, conditions, medications, allergies
            FROM aia_health_patients
            WHERE id = %s
            """,
            (patient_id,),
        )
        if not row:
            return None
        return {
            "full_name": row["full_name"],
            "first_name": self._first_name(row.get("nickname") or row["full_name"]),
            "age": self._calc_age(row.get("birth_date")),
            "care_unit": row.get("care_unit"),
            "conditions_count": len(row.get("conditions") or []),
            "medications_count": len(row.get("medications") or []),
        }

    def _compute_metrics(
        self, patient_id: str, start: datetime, end: datetime,
    ) -> dict:
        # Check-ins respondidos (via scheduled_fires)
        fires = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'responded' OR responded_at IS NOT NULL) AS responded,
                AVG(response_duration_seconds)::INT AS avg_response_sec
            FROM aia_health_scheduled_fires sf
            JOIN aia_health_proactive_schedules ps ON ps.id = sf.schedule_id
            WHERE ps.subject_type = 'patient'
              AND ps.subject_id = %s
              AND sf.fired_at >= %s
              AND sf.fired_at < %s
            """,
            (patient_id, start, end),
        )

        # Eventos de cuidado no período
        events = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE current_classification IN ('urgent','critical')) AS critical,
                COUNT(*) FILTER (WHERE status = 'resolved') AS resolved,
                COUNT(*) FILTER (WHERE closed_reason = 'sem_intercorrencia') AS without_issue
            FROM aia_health_care_events
            WHERE patient_id = %s
              AND opened_at >= %s AND opened_at < %s
            """,
            (patient_id, start, end),
        )

        # Vitais agregados
        vitals = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS readings,
                AVG(value_numeric) FILTER (WHERE code = 'bp_systolic') AS avg_sys,
                AVG(value_numeric) FILTER (WHERE code = 'bp_diastolic') AS avg_dia,
                AVG(value_numeric) FILTER (WHERE code = 'heart_rate') AS avg_hr
            FROM aia_health_vital_signs
            WHERE patient_id = %s
              AND measured_at >= %s AND measured_at < %s
            """,
            (patient_id, start, end),
        )

        return {
            "checkins_total": (fires or {}).get("total") or 0,
            "checkins_responded": (fires or {}).get("responded") or 0,
            "avg_response_seconds": (fires or {}).get("avg_response_sec"),
            "events_total": (events or {}).get("total") or 0,
            "events_critical": (events or {}).get("critical") or 0,
            "events_resolved_ok": (events or {}).get("without_issue") or 0,
            "vital_readings": (vitals or {}).get("readings") or 0,
            "avg_bp": self._format_bp(
                (vitals or {}).get("avg_sys"),
                (vitals or {}).get("avg_dia"),
            ),
            "avg_hr": self._format_numeric((vitals or {}).get("avg_hr")),
        }

    def _list_events(
        self, patient_id: str, start: datetime, end: datetime,
    ) -> list[dict]:
        rows = self.db.fetch_all(
            """
            SELECT human_id, current_classification, summary,
                   opened_at, resolved_at, closed_reason
            FROM aia_health_care_events
            WHERE patient_id = %s
              AND opened_at >= %s AND opened_at < %s
            ORDER BY opened_at ASC
            LIMIT 12
            """,
            (patient_id, start, end),
        )
        return [
            {
                "id": f"#{r.get('human_id', 0):04d}",
                "classification": r.get("current_classification"),
                "summary": (r.get("summary") or "")[:160],
                "opened_at": r.get("opened_at"),
                "resolved": bool(r.get("resolved_at")),
                "closed_reason": r.get("closed_reason"),
            }
            for r in rows
        ]

    def _load_next_scheduled(self, patient_id: str) -> dict | None:
        # Futura teleconsulta / evento agendado
        # Por enquanto retorna None (teleconsultations não tem schedule_at ainda)
        return None

    # ══════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _first_name(full: str | None) -> str:
        if not full:
            return "paciente"
        return full.strip().split()[0]

    @staticmethod
    def _calc_age(bd) -> int | None:
        if not bd:
            return None
        try:
            if isinstance(bd, str):
                bd_d = datetime.strptime(bd.split("T")[0], "%Y-%m-%d").date()
            else:
                bd_d = bd
            today = datetime.now().date()
            return today.year - bd_d.year - ((today.month, today.day) < (bd_d.month, bd_d.day))
        except Exception:
            return None

    @staticmethod
    def _format_bp(sys: float | None, dia: float | None) -> str | None:
        if sys is None or dia is None:
            return None
        try:
            return f"{int(float(sys))}/{int(float(dia))} mmHg"
        except Exception:
            return None

    @staticmethod
    def _format_numeric(val) -> str | None:
        if val is None:
            return None
        try:
            return f"{int(float(val))} bpm"
        except Exception:
            return None

    @staticmethod
    def _period_label(start: datetime, end: datetime) -> str:
        meses = ["jan", "fev", "mar", "abr", "mai", "jun",
                 "jul", "ago", "set", "out", "nov", "dez"]
        s = start.astimezone(timezone.utc)
        e = end.astimezone(timezone.utc)
        return f"{s.day:02d}/{meses[s.month-1]} a {e.day:02d}/{meses[e.month-1]}"

    def _fallback(self, patient: dict, metrics: dict, events: list) -> dict:
        first = patient.get("first_name", "paciente")
        total = metrics.get("checkins_total") or 0
        resp = metrics.get("checkins_responded") or 0
        evs = len(events)
        text = (
            f"☀️ Resumo semanal — {first}\n\n"
            f"✅ {resp}/{total} check-ins respondidos\n"
            f"📋 {evs} evento{'s' if evs != 1 else ''} registrado{'s' if evs != 1 else ''} na semana\n\n"
            "Para detalhes completos acesse o portal da família.\n\n"
            "Com carinho, Equipe ConnectaIACare 💙"
        )
        return {
            "whatsapp_text": text,
            "email_html": f"<p>{text.replace(chr(10), '<br>')}</p>",
            "summary_sentence": "Resumo semanal disponível.",
            "flags": {"has_attention": False, "has_warnings": False, "calls_for_action": False},
            "highlights": [],
            "next_event_line": "",
            "tone": "observador",
            "_fallback": True,
        }


_instance: WeeklyReportService | None = None


def get_weekly_report_service() -> WeeklyReportService:
    global _instance
    if _instance is None:
        _instance = WeeklyReportService()
    return _instance
