"""SupportSofiaAgent — atende lead anônimo com intent suporte.

Ativado quando:
    - phone resolve como anônimo
    - intent_classifier diz 'suporte_cliente'

Comportamento:
    1. Acolhe a frustração (tom empático).
    2. Tenta identificar o problema com 1 pergunta clara.
    3. Pede dados pra resolver (nome cadastrado, email, ou
       descrição do problema).
    4. Em geral escala pra humano via Central 24h — suporte real
       precisa de pessoa, Sofia só faz triagem.

Sub-agente NÃO faz: dar suporte clínico, prometer SLA, fazer
reset de senha (humano faz).
"""
from __future__ import annotations

from src.services.sofia_agents.base import (
    AgentContext, AgentResponse, BaseSofiaAgent,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


PROMPT_TEMPLATE = """Você é Sofia, IA da ConnectaIACare.

Recebeu mensagem no WhatsApp de alguém que parece ser CLIENTE existente, mas o número não foi reconhecido na plataforma. Pode ser:
- Phone trocado / SIM novo
- Conta familiar e quem escreveu não é o cadastrado
- Problema técnico de conta

Seu trabalho:
1. Acolher com tom empático (UMA frase só, sem fofice)
2. Identificar o problema com UMA pergunta clara
3. Coletar dados mínimos pra humano resolver: nome (do dono da conta), email cadastrado, descrição curta do problema
4. Escalar pra humano via tool escalate_to_human_whatsapp com summary completo

REGRAS:
- Tom acolhedor, profissional. Sem "tudo bem!" automático.
- NUNCA tenta resolver senha / acesso / pagamento sozinha. Isso é pra humano.
- Curta. 1-2 frases por turno.
- Se o user já passou nome+email+problema, escala IMEDIATAMENTE.

CONTEXTO:
{context_block}

Mensagem do usuário:
{user_message}"""


class SupportSofiaAgent(BaseSofiaAgent):
    name = "support"

    def system_prompt(self, ctx: AgentContext) -> str:
        context_lines = []
        if ctx.active_context_messages:
            context_lines.append(
                f"- Conversa anterior ({len(ctx.active_context_messages)} msgs):"
            )
            for msg in ctx.active_context_messages[-4:]:
                role = msg.get("role", "?")
                content = (msg.get("content") or "")[:160]
                context_lines.append(f"  [{role}] {content}")
        if not context_lines:
            context_lines.append("- Primeira mensagem.")
        return PROMPT_TEMPLATE.format(
            context_block="\n".join(context_lines),
            user_message=ctx.inbound_text[:1500],
        )

    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        return ["escalate_to_human_whatsapp"]

    def process(self, ctx: AgentContext) -> AgentResponse:
        from src.services.llm_router import get_llm_router

        router = get_llm_router()
        try:
            decision = router.complete_json(
                task="sofia_chat_tool_decision",
                system=self.system_prompt(ctx) + (
                    "\n\nSAÍDA: JSON estrito. Escolha ENTRE:\n"
                    "  A) Texto: {\"action\": \"text\", \"text\": \"<resposta>\"}\n"
                    "  B) Escalar: {\"action\": \"tool\", \"tool_name\": \"escalate_to_human_whatsapp\", "
                    "\"args\": {\"reason\": \"...\", \"summary\": \"...\", \"urgency\": \"P2|P3\"}, "
                    "\"text_after\": \"<confirma escalation pro user>\"}"
                ),
                user=ctx.inbound_text[:1500],
            )
        except Exception as exc:
            logger.exception(
                "support_agent_llm_failed",
                trace_id=ctx.trace_id, error=str(exc)[:200],
            )
            # Failsafe: escala direto
            return AgentResponse(
                text=(
                    "Recebi sua mensagem. Vou pedir pra alguém da equipe "
                    "te atender — você receberá retorno em até 30 minutos "
                    "pelo número da Central 24h. 🙏"
                ),
                handoff_initiated=True,
                handoff_reason="support_agent_llm_failure",
                next_action="wait_human",
            )

        action = decision.get("action") or "text"
        if action == "tool":
            tool_name = decision.get("tool_name")
            tool_args = decision.get("args") or {}
            text_after = decision.get("text_after") or ""
            return AgentResponse(
                text=text_after,
                tools_called=[{
                    "name": tool_name,
                    "args": tool_args,
                    "status": "pending_phase_c4",
                }],
                handoff_initiated=(tool_name == "escalate_to_human_whatsapp"),
                handoff_reason=tool_args.get("reason"),
                next_action="wait_human",
            )
        return AgentResponse(
            text=decision.get("text") or "",
            next_action="wait_user",
        )
