"""CommercialSofiaAgent — atende leads B2B/B2C anônimos.

Ativado quando:
    - phone resolve como anônimo
    - intent_classifier diz 'interesse_servico_b2c|b2b' OU 'agendar_demo'

Comportamento:
    1. Cumprimenta calorosamente, identifica como Sofia da
       ConnectaIACare.
    2. Faz 1-2 perguntas pra qualificar (nome, papel, dor).
    3. Captura dados via tool capture_lead.
    4. Se intent = agendar_demo → schedule_demo.
    5. Se >5 turnos sem evolução → escalate_to_human_whatsapp.

Sub-agente NÃO faz: prometer preço, fechar venda, falar de
contrato. Tudo isso é responsabilidade do humano via Central 24h.
"""
from __future__ import annotations

from src.services.sofia_agents.base import (
    AgentContext, AgentResponse, BaseSofiaAgent,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


PROMPT_TEMPLATE = """Você é Sofia, IA da ConnectaIACare (cuidados de idosos com IA + atendimento humano 24/7).

Acabou de receber uma mensagem no WhatsApp de alguém NÃO cadastrado na plataforma — provavelmente um lead. Seu trabalho é:

1. Cumprimentar com calor (uma frase só)
2. Apresentar a ConnectaIACare em 1-2 frases CURTAS adaptadas ao perfil que você acabou de identificar
3. Fazer UMA pergunta de qualificação por vez (nunca 3 perguntas juntas)
4. Coletar progressivamente: nome, papel/empresa, dor que querem resolver
5. Quando tiver dados básicos suficientes, usar a tool `capture_lead` pra registrar

REGRAS DE TOM:
- Brasileiro coloquial, mas profissional. Sem firulas.
- Curto. Idoso/familiar não tem paciência pra parágrafo.
- Empático sem ser pegajoso.
- Honesto: NUNCA inventa preço, prazo, integração. Diz "vou passar pro time comercial te falar" quando não souber.
- NUNCA promete o que a plataforma não faz.

QUANDO ESCALAR PRO HUMANO (tool escalate_to_human_whatsapp):
- Pessoa pede preço fechado / proposta detalhada
- Pessoa pede demo (use tool schedule_demo PRIMEIRO; só escala se ela
  insistir em humano agora)
- Pessoa parece insatisfeita ou desconfiada
- Conversa passou de 5 turnos sem evolução clara

CONTEXTO DESTE TURNO:
{context_block}

Mensagem do usuário:
{user_message}

Responda com naturalidade. Se precisar coletar info, faz UMA pergunta. Se for o momento de salvar lead ou agendar demo, use a tool apropriada."""


class CommercialSofiaAgent(BaseSofiaAgent):
    name = "commercial"

    def system_prompt(self, ctx: AgentContext) -> str:
        # Contexto enxuto: histórico curto + intent detectado
        context_lines = []
        if ctx.metadata.get("classified_intent"):
            ci = ctx.metadata["classified_intent"]
            context_lines.append(
                f"- Intent classificado: {ci.get('intent')} "
                f"(confiança {ci.get('confidence', 0):.2f})"
            )
        if ctx.active_context_messages:
            context_lines.append(
                f"- Conversa anterior ({len(ctx.active_context_messages)} msgs nos últimos 45min):"
            )
            for msg in ctx.active_context_messages[-6:]:
                role = msg.get("role", "?")
                content = (msg.get("content") or "")[:160]
                context_lines.append(f"  [{role}] {content}")

        if not context_lines:
            context_lines.append("- Primeira mensagem do lead.")

        return PROMPT_TEMPLATE.format(
            context_block="\n".join(context_lines),
            user_message=ctx.inbound_text[:1500],
        )

    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        return [
            "capture_lead",
            "schedule_demo",
            "escalate_to_human_whatsapp",
        ]

    def process(self, ctx: AgentContext) -> AgentResponse:
        """Phase C v1: implementação básica via LLM single-shot.

        Phase C v2 (futura): tool-use loop completo (LLM decide
        chamar tool → exec tool → LLM continua com resultado).
        Por enquanto fazemos uma decisão por turno: ou texto, ou
        1 tool call, definido por uma chamada `sofia_chat_tool_decision`.
        """
        from src.services.llm_router import get_llm_router

        router = get_llm_router()
        try:
            # Decision: texto direto OU tool call
            decision = router.complete_json(
                task="sofia_chat_tool_decision",
                system=self.system_prompt(ctx) + (
                    "\n\nSAÍDA OBRIGATÓRIA: JSON estrito. Escolha ENTRE:\n"
                    "  A) Resposta de texto (sem tool):\n"
                    "     {\"action\": \"text\", \"text\": \"<sua resposta brasileira coloquial>\"}\n\n"
                    "  B) Chamar tool (uma das permitidas: " +
                    ", ".join(self.allowed_tools(ctx)) + "):\n"
                    "     {\"action\": \"tool\", \"tool_name\": \"<nome>\", \"args\": {...}, "
                    "\"text_after\": \"<resposta confirmando ao user>\"}"
                ),
                user=ctx.inbound_text[:1500],
            )
        except Exception as exc:
            logger.exception(
                "commercial_agent_llm_failed",
                trace_id=ctx.trace_id, error=str(exc)[:200],
            )
            return AgentResponse(
                text=(
                    "Olá! Aqui é a Sofia da ConnectaIACare. Recebi sua mensagem. "
                    "Estou tendo um pequeno problema técnico aqui — em instantes "
                    "um humano da nossa equipe te chama. Pode me contar enquanto "
                    "isso o seu nome e em qual contexto você quer conhecer a "
                    "plataforma? 🙏"
                ),
                next_action="wait_user",
                metadata={"llm_failure": str(exc)[:200]},
            )

        action = decision.get("action") or "text"
        if action == "tool":
            # Phase C v1: registramos a INTENT da tool mas a execução
            # da tool fica pra Phase C.4 (tool registry). Por enquanto,
            # respondemos com text_after como se a tool tivesse rodado
            # em modo dry-run (audit log marca pendente).
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
                next_action="wait_user",
                metadata={"phase_c_version": "v1_dry_run"},
            )
        # action == 'text'
        text = decision.get("text") or ""
        return AgentResponse(
            text=text,
            next_action="wait_user",
        )
