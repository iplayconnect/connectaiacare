"""Sofia availability service — janela de atendimento de operadores.

Operadores (medico, enfermeiro, admin_tenant, super_admin) podem ter
horário cadastrado em aia_health_sofia_availability_rules. Sem rules
cadastradas → sempre disponível (default-open).

Pacientes/familiares/parceiros NÃO passam por esse gate (default 24/7).

Fluxo típico:
    decision = availability_service.check(persona_ctx)
    if not decision.allowed:
        return decision.message  # Sofia responde "fora do horário..."

Timezone:
    Cada rule tem timezone próprio (default America/Sao_Paulo).
    Comparação feita com hora local do operador, não UTC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AvailabilityDecision:
    allowed: bool
    reason: str               # "ok", "outside_hours", "no_rules"
    message: str | None = None  # mensagem custom pra responder ao chamador
    next_available_at: datetime | None = None


# Default response quando fora do horário e admin não customizou
DEFAULT_OOH_MESSAGE = (
    "Estou fora do meu horário de atendimento agora. Sua mensagem foi "
    "registrada e te respondo no próximo expediente. Em caso de "
    "emergência clínica, ligue 192 (SAMU) ou procure pronto-atendimento."
)


def check(persona_ctx) -> AvailabilityDecision:
    """Verifica se o operador está dentro da janela cadastrada.

    Não-operadores: sempre allow (não usam time window).
    Operadores sem rules: allow (default-open).
    """
    if not getattr(persona_ctx, "is_operator", False):
        return AvailabilityDecision(allowed=True, reason="not_operator")

    user_id = persona_ctx.user_id
    if not user_id:
        return AvailabilityDecision(allowed=True, reason="no_user_id")

    rules = get_postgres().fetch_all(
        """
        SELECT day_of_week, time_start, time_end, timezone, out_of_hours_message
        FROM aia_health_sofia_availability_rules
        WHERE user_id = %s AND active = TRUE
        """,
        (user_id,),
    )
    if not rules:
        return AvailabilityDecision(allowed=True, reason="no_rules")

    # Avaliar contra o "agora" no timezone de cada rule. A maioria dos
    # operadores brasileiros vai ter um timezone só, mas suportamos por
    # rule pra clientes internacionais futuros.
    for rule in rules:
        tz = ZoneInfo(rule.get("timezone") or "America/Sao_Paulo")
        now_local = datetime.now(tz)
        if _dow_zero_sunday(now_local) != rule["day_of_week"]:
            continue
        cur = now_local.time()
        if rule["time_start"] <= cur <= rule["time_end"]:
            return AvailabilityDecision(allowed=True, reason="ok")

    # Não bateu nenhuma rule → fora do horário.
    custom_msg = next(
        (r.get("out_of_hours_message") for r in rules if r.get("out_of_hours_message")),
        None,
    )
    return AvailabilityDecision(
        allowed=False,
        reason="outside_hours",
        message=custom_msg or DEFAULT_OOH_MESSAGE,
    )


def _dow_zero_sunday(dt: datetime) -> int:
    """Converte weekday de Python (0=segunda) para 0=domingo (igual SQL)."""
    # Python: monday=0..sunday=6 → queremos sunday=0..saturday=6
    return (dt.weekday() + 1) % 7


def list_rules(user_id: str) -> list[dict]:
    rows = get_postgres().fetch_all(
        """
        SELECT id, day_of_week, time_start, time_end, timezone,
               out_of_hours_message, active
        FROM aia_health_sofia_availability_rules
        WHERE user_id = %s
        ORDER BY day_of_week, time_start
        """,
        (user_id,),
    )
    return [
        {
            "id": str(r["id"]),
            "dayOfWeek": int(r["day_of_week"]),
            "timeStart": r["time_start"].strftime("%H:%M"),
            "timeEnd": r["time_end"].strftime("%H:%M"),
            "timezone": r["timezone"],
            "outOfHoursMessage": r.get("out_of_hours_message"),
            "active": bool(r["active"]),
        }
        for r in rows
    ]


def upsert_rule(
    *,
    tenant_id: str,
    user_id: str,
    day_of_week: int,
    time_start: str,
    time_end: str,
    timezone: str = "America/Sao_Paulo",
    out_of_hours_message: str | None = None,
    rule_id: str | None = None,
) -> dict:
    pg = get_postgres()
    if rule_id:
        row = pg.insert_returning(
            """
            UPDATE aia_health_sofia_availability_rules
            SET day_of_week = %s, time_start = %s, time_end = %s,
                timezone = %s, out_of_hours_message = %s
            WHERE id = %s
            RETURNING id
            """,
            (day_of_week, time_start, time_end, timezone, out_of_hours_message, rule_id),
        )
    else:
        row = pg.insert_returning(
            """
            INSERT INTO aia_health_sofia_availability_rules
                (tenant_id, user_id, day_of_week, time_start, time_end,
                 timezone, out_of_hours_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (tenant_id, user_id, day_of_week, time_start, time_end,
             timezone, out_of_hours_message),
        )
    return {"id": str(row["id"]) if row else None}


def delete_rule(rule_id: str) -> None:
    get_postgres().execute(
        "DELETE FROM aia_health_sofia_availability_rules WHERE id = %s",
        (rule_id,),
    )
