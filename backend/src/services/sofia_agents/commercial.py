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

Acabou de receber mensagem no WhatsApp de alguém NÃO cadastrado — provavelmente um lead. Sua missão:

1. Cumprimentar com calor (UMA frase)
2. Apresentar a ConnectaIACare em 1-2 frases CURTAS
3. Coletar progressivamente: nome, papel/empresa, dor que querem resolver
4. **REGRA OBRIGATÓRIA**: ASSIM QUE souber o NOME do lead, chame a tool `capture_lead` IMEDIATAMENTE — mesmo se ainda houver perguntas pendentes. A tool é idempotente: você pode chamar de novo depois com mais dados (organization, role, etc.). NUNCA termine um turno SEM chamar capture_lead se já tiver o nome.
5. Se intent=agendar_demo OU lead pediu demo explicitamente, chame `schedule_demo` (após capture_lead).
6. Após 5 turnos sem evolução OU se lead pedir humano, chame `escalate_to_human_whatsapp`.

REGRAS DE TOM:
- Brasileiro coloquial, profissional. Sem firulas.
- CURTO. Máximo 3 frases por turno.
- Empática sem ser pegajosa.
- Honesta: NUNCA inventa preço, prazo, integração específica. Diz "vou passar pro time comercial te detalhar" quando perguntarem.
- UMA pergunta por turno (nunca 3 juntas).

QUANDO USAR TOOL VS TEXTO:
- Lead disse só "oi" / sem dados → text (cumprimenta + pergunta nome)
- Lead deu apenas nome → tool capture_lead com {{phone, intent, full_name}} + text_after pedindo organização/papel
- Lead deu nome + empresa + papel → tool capture_lead completo + text_after pedindo dor específica
- Lead pediu demo claramente → tool schedule_demo
- Lead pediu humano → tool escalate_to_human_whatsapp com summary completo

EXEMPLO de tool call (saída JSON):
{{
  "action": "tool",
  "tool_name": "capture_lead",
  "args": {{
    "phone": "5511987654321",
    "intent": "interesse_servico_b2b",
    "full_name": "João Silva",
    "organization": "Casa Bem Cuidada",
    "role_self_declared": "gestor_ilpi",
    "confidence": 0.9,
    "notes": "ILPI 30 idosos, dor de quedas no turno da noite"
  }},
  "text_after": "Anotei aqui, João. Sobre quedas na madrugada — quantos colaboradores atuam nesse turno?"
}}

CONTEXTO DESTE TURNO:
- Phone do lead: {phone}
- Intent classificado: {intent_label}
{context_block}

Mensagem do usuário:
{user_message}"""


class CommercialSofiaAgent(BaseSofiaAgent):
    name = "commercial"

    def system_prompt(self, ctx: AgentContext) -> str:
        ci = ctx.metadata.get("classified_intent") or {}
        intent_label = (
            f"{ci.get('intent', 'unclear')} "
            f"(confiança {ci.get('confidence', 0):.2f})"
        )

        context_lines = []
        if ctx.active_context_messages:
            context_lines.append(
                f"- Conversa anterior ({len(ctx.active_context_messages)} msgs nos últimos 45min):"
            )
            for msg in ctx.active_context_messages[-6:]:
                role = msg.get("role", "?")
                content = (msg.get("content") or "")[:160]
                context_lines.append(f"  [{role}] {content}")
        else:
            context_lines.append("- Primeira mensagem do lead nesta sessão.")

        return PROMPT_TEMPLATE.format(
            phone=ctx.phone,
            intent_label=intent_label,
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
