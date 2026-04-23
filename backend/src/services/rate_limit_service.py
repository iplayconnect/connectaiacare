"""Rate Limit Service — sustentabilidade financeira por plano.

Gap identificado em revisão do ADR-027 (§8.5): safety cobre jailbreak mas
não uso normal. Um idoso solitário facilmente manda 150-200 msgs/dia pra
Sofia no modo companion — cada msg é uma chamada LLM. Sem limite, 10k
usuários B2C estouram custo.

Limites por plano (mensagens user→Sofia por janela 24h rolling):

    essencial        →  30 msgs/dia
    familia          →  60 msgs/dia
    premium          → 100 msgs/dia
    premium_device   → 150 msgs/dia
    atente (B2B)     → sem limite (cobrança por uso)

Exceções (sempre passam, independente de cota):
    - Triggers safety emergency (suicidal_ideation, elder_abuse, medical)
    - Msgs começando com "ajuda", "socorro", "emergência"
    - Primeiras 3 msgs do dia (não quebra no "bom dia")
    - Respostas a check-ins ativos de care events

Mensagem de limite: acolhedora, nunca rejeitante. Sofia agenda wake-up
pra 6h da manhã seguinte.

Uso:

    rl = get_rate_limiter()
    check = rl.check(phone)
    if not check.allowed:
        return {"reply": check.response, "rate_limited": True}
    # ... processa normalmente ...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.services.conversation_history_service import get_conversation_history
from src.services.postgres import get_postgres
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════
# Config — limites iniciais HIPÓTESE (precisam ser calibrados com dados reais)
# ══════════════════════════════════════════════════════════════════
#
# Estes números são uma HIPÓTESE INICIAL. O valor certo só aparece observando
# comportamento real dos primeiros 50-100 usuários B2C ao longo de 2-4 semanas.
#
# Metodologia de calibração (a executar pós-primeiros 50 assinantes):
#
#   1. Observar distribuição real de msgs/dia por plano (P50, P90, P95, P99)
#      via query: SELECT plan_sku, percentile_cont(0.9) WITHIN GROUP
#                 (ORDER BY daily_count) FROM ... GROUP BY plan_sku
#
#   2. Definir limite como P95 + margem (cobrindo 95% dos usuários sem bloquear)
#
#   3. Cross-checar com custo: limite × custo_msg ≤ (receita_plano − margem_alvo)
#      Ex: Essencial R$ 49,90/mês → 50 msgs/mês × R$ 0,015 = R$ 0,75 (1.5%),
#      sobra margem confortável. Mas se média for 200/mês, 200 × 0,015 = R$ 3
#      (6% do plano) — ainda viável se LTV for bom.
#
#   4. A/B test: um grupo com limite atual, outro 20% maior. Medir:
#      - Churn rate (quem saiu por limite apertado demais?)
#      - NPS (insatisfação latente antes de churn?)
#      - Custo de infra (limite folgado estoura margem?)
#      - Engajamento (usuários que batem limite tem mais retenção?)
#
#   5. Ajustar via `llm_routing.yaml` ou nova tabela `rate_limit_config`
#      SEM redeploy de código (config-as-data).
#
# Enquanto não temos dados: valores conservadores que cobrem "uso saudável"
# segundo benchmark de chatbots de companhia + dieta "saúde idoso típico".

PLAN_LIMITS: dict[str, int] = {
    "essencial": 30,          # ~1 check-in + 2-3 conversas leves/dia
    "familia": 60,            # + conversa com família + lembretes
    "premium": 100,           # + companion ativo + teleconsultas
    "premium_device": 150,    # + interação com dispositivo IoT
    "atente": 10_000,         # efetivamente sem limite (B2B, cobrança por uso)
}

# Usuários sem plano (onboarding em andamento ou trial) usam limite generoso
# — onboarding típico usa ~15-25 msgs e deve SEMPRE caber
DEFAULT_LIMIT_NO_PLAN = 50

# Grace window: primeiras N mensagens do dia nunca são bloqueadas
# (não quebra no "bom dia" matinal mesmo se o user bateu limite ontem)
GRACE_MSGS_PER_DAY = 3

# Threshold de alerta: quando usuário usa ≥ X% do limite, loga pra observação
# (útil pra calibração + detectar upgrade orgânico de plano)
USAGE_ALERT_THRESHOLD = 0.8

# Keywords que bypass limit (urgência do próprio usuário)
EMERGENCY_KEYWORDS_REGEX = re.compile(
    r"\b(ajuda|socorro|emerg[êe]ncia|urgente|me ajuda|preciso de ajuda)\b",
    flags=re.IGNORECASE,
)


@dataclass
class RateLimitCheck:
    allowed: bool = True
    used: int = 0
    limit: int = 0
    plan: str = "unknown"
    reason: str = "ok"               # ok | over_limit | emergency_bypass | grace_period
    response: str | None = None       # msg acolhedora se blocked


# ══════════════════════════════════════════════════════════════════
# Service
# ══════════════════════════════════════════════════════════════════

class RateLimitService:
    def __init__(self):
        self.db = get_postgres()
        self.history = get_conversation_history()

    def check(
        self,
        phone: str,
        *,
        text: str = "",
        safety_triggers: list[str] | None = None,
        has_active_care_event: bool = False,
        tenant_id: str = "sofiacuida_b2c",
    ) -> RateLimitCheck:
        """Decide se usuário pode mandar essa mensagem.

        Args:
            phone: número do usuário
            text: conteúdo da msg (pra detectar emergência por keyword)
            safety_triggers: se já foi moderado antes, passa os triggers detectados
            has_active_care_event: se tem evento de cuidado ativo, libera
            tenant_id: escopo

        Returns:
            RateLimitCheck com allowed=True se pode processar.
        """
        # 1. Safety emergency → sempre passa
        triggers = safety_triggers or []
        emergency_triggers = {
            "suicidal_ideation", "elder_abuse", "medical_emergency", "csam",
        }
        if any(t in emergency_triggers for t in triggers):
            return RateLimitCheck(
                allowed=True, plan=self._get_plan(phone, tenant_id),
                reason="emergency_bypass",
            )

        # 2. Keyword de emergência no texto
        if text and EMERGENCY_KEYWORDS_REGEX.search(text):
            return RateLimitCheck(
                allowed=True, plan=self._get_plan(phone, tenant_id),
                reason="emergency_bypass",
            )

        # 3. Care event ativo → sempre passa (paciente em risco)
        if has_active_care_event:
            return RateLimitCheck(
                allowed=True, plan=self._get_plan(phone, tenant_id),
                reason="active_care_event",
            )

        # 4. Resolve plano e limite
        plan = self._get_plan(phone, tenant_id)
        limit = PLAN_LIMITS.get(plan, DEFAULT_LIMIT_NO_PLAN)

        # 5. Conta mensagens inbound nas últimas 24h
        used = self.history.count_recent(
            phone, tenant_id=tenant_id, minutes=1440, direction="inbound",
        )

        # 6. Grace window — primeiras N do dia sempre passam
        if used < GRACE_MSGS_PER_DAY:
            return RateLimitCheck(
                allowed=True, used=used, limit=limit, plan=plan,
                reason="grace_period",
            )

        # 7. Limit check
        if used < limit:
            # Telemetria pra calibração — loga quando usuário passa 80% do limite
            # (sinal de que o limite pode estar apertado OU que ele tá querendo upgrade)
            if limit > 0 and used / limit >= USAGE_ALERT_THRESHOLD:
                logger.info(
                    "rate_limit_usage_alert",
                    phone=phone, plan=plan, used=used, limit=limit,
                    pct=round(used / limit, 2),
                )
            return RateLimitCheck(
                allowed=True, used=used, limit=limit, plan=plan, reason="ok",
            )

        # 8. Over limit — resposta acolhedora + telemetria
        # Este log é OURO pra calibração: ver quantos usuários por plano batem
        # limite, em que horários, com que padrão de conteúdo.
        logger.warning(
            "rate_limit_exceeded",
            phone=phone, plan=plan, used=used, limit=limit,
            tenant_id=tenant_id,
        )
        return RateLimitCheck(
            allowed=False,
            used=used,
            limit=limit,
            plan=plan,
            reason="over_limit",
            response=self._build_over_limit_message(),
        )

    # ───────────────────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────────────────

    def _get_plan(self, phone: str, tenant_id: str) -> str:
        """Busca plano ativo do usuário. Retorna 'unknown' se não achar."""
        try:
            row = self.db.fetch_one(
                """
                SELECT plan_sku
                FROM aia_health_subscriptions
                WHERE payer_phone = %s
                  AND tenant_id = %s
                  AND status IN ('active', 'trialing')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (phone, tenant_id),
            )
            if row and row.get("plan_sku"):
                return row["plan_sku"]
        except Exception as exc:
            logger.debug("rate_limit_plan_lookup_failed", phone=phone, error=str(exc))
        return "unknown"

    @staticmethod
    def _build_over_limit_message() -> str:
        return (
            "Que bom conversar contigo 💙\n\n"
            "Vou descansar um pouquinho pra conseguir atender todo mundo — "
            "a gente continua amanhã cedo, tá?\n\n"
            "Se for *urgência*, manda _\"ajuda\"_ agora mesmo que eu "
            "respondo — emergência nunca fica de fora."
        )


# Singleton
_instance: RateLimitService | None = None


def get_rate_limiter() -> RateLimitService:
    global _instance
    if _instance is None:
        _instance = RateLimitService()
    return _instance
