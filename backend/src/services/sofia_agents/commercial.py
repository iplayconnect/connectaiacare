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

╔══════════════════════════════════════════════════════════════════╗
║ REGRA DE OURO — NÃO REPETIR PERGUNTAS                            ║
║ • Antes de perguntar QUALQUER coisa, consulte DADOS_JÁ_COLETADOS.║
║ • Se o campo está em DADOS_JÁ_COLETADOS, NÃO pergunte de novo.   ║
║ • Use SHOULD_ASK pra escolher próxima pergunta.                  ║
║ • Se PENDING_QUESTION existe, é continuação direta da conversa.  ║
║   Trate a mensagem do user como resposta a essa pergunta.         ║
╚══════════════════════════════════════════════════════════════════╝

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
  "text_after": "Anotei aqui, João. Sobre quedas na madrugada — quantos colaboradores atuam nesse turno?",
  "next_question_intent": "open_ended"
}}

{capabilities_block}

CONTEXTO DESTE TURNO:
- Phone do lead: {phone}
- Intent classificado: {intent_label}
- Stage do funil: {stage}
{csm_block}
{context_block}

Mensagem do usuário:
{user_message}"""


def _format_csm_block(csm_ctx: dict) -> str:
    """Formata snapshot do CSM (lead_data + flow_state) pra injetar
    no system prompt. Inclui: dados já coletados, próximas perguntas,
    pending question.
    """
    if not csm_ctx:
        return "- CSM: sem state ainda (1ª msg desta sessão)."
    lines: list[str] = []

    # 1. Dados já coletados — REGRA DE OURO
    confirmados = csm_ctx.get("dados_confirmados") or []
    if confirmados:
        kv = []
        for f in confirmados:
            v = csm_ctx.get(f)
            if v is None:
                continue
            kv.append(f"  • {f}: {v}")
        lines.append("DADOS_JÁ_COLETADOS (NÃO pergunte de novo):")
        if kv:
            lines.extend(kv)
    else:
        lines.append("DADOS_JÁ_COLETADOS: (nada ainda)")

    # 2. Should-ask flags — próximas perguntas válidas
    should_ask = [
        k.replace("should_ask_", "")
        for k in csm_ctx.keys() if k.startswith("should_ask_")
    ]
    if should_ask:
        lines.append(
            "SHOULD_ASK (campos esperados pelo stage atual, ainda "
            "não coletados): " + ", ".join(should_ask)
        )

    # 3. Pending question (continuação direta da conversa)
    pending = csm_ctx.get("pending_question")
    pending_intent = csm_ctx.get("pending_question_intent")
    if pending:
        lines.append(
            f"PENDING_QUESTION: você fez essa pergunta no turno "
            f"anterior — '{pending[:200]}' "
            f"(intent={pending_intent or 'open_ended'}). A mensagem "
            f"do user PROVAVELMENTE é resposta a ela."
        )

    # 4. Última interação (continuidade narrativa)
    last = csm_ctx.get("last_interaction")
    if last and last.get("bot_message"):
        lines.append(
            f"ÚLTIMA_INTERAÇÃO: bot disse '{(last.get('bot_message') or '')[:120]}', "
            f"user respondeu '{(last.get('lead_message') or '(ainda não respondeu)')[:120]}'."
        )

    return "\n".join(lines)


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

        # CSM v2 snapshot — chave pra Sofia não repetir perguntas.
        csm_block = _format_csm_block(ctx.csm_context or {})
        stage = (ctx.csm_context or {}).get("stage", "warmup")

        # Whitelist de capabilities (anti-invenção) — Phase C v2.5.
        # Best-effort: se DB não responde, format_for_prompt retorna
        # mensagem de fallback informando Sofia a checar com time.
        try:
            from src.services.csm import get_capabilities_service
            capabilities_block = get_capabilities_service().format_for_prompt(
                persona="anonymous",
            )
        except Exception:
            capabilities_block = (
                "REGRA: se o lead perguntar de feature específica, "
                "diga que vai checar com o time e passar o detalhe — "
                "nunca invente capability."
            )

        return PROMPT_TEMPLATE.format(
            phone=ctx.phone,
            intent_label=intent_label,
            stage=stage,
            csm_block=csm_block,
            capabilities_block=capabilities_block,
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
        # Lista de intents válidos pra próximo turno (CSM v2).
        # LLM declara o que está perguntando — orchestrator marca
        # como pending_question pra próximo turno saber a qual
        # pergunta o user respondeu.
        intents_hint = (
            "primeiro_nome, nome_completo, email, cidade, relacao_idoso, "
            "count_idosos, idades_idosos, moram_sozinhos, moram_em_ilpi, "
            "dor_principal, count_medicamentos, dificuldade_medicacao, "
            "organizacao, cargo_b2b, ja_cliente_concorrente, quer_demo, "
            "intent_b2c_b2b, open_ended"
        )
        try:
            # Decision: texto direto OU tool call
            decision = router.complete_json(
                task="sofia_chat_tool_decision",
                system=self.system_prompt(ctx) + (
                    "\n\nSAÍDA OBRIGATÓRIA: JSON estrito. Escolha ENTRE:\n"
                    "  A) Resposta de texto (sem tool):\n"
                    '     {"action": "text", '
                    '"text": "<sua resposta brasileira coloquial>", '
                    '"next_question_intent": "<um destes: ' + intents_hint + '>"}\n\n'
                    "  B) Chamar tool (uma das permitidas: " +
                    ", ".join(self.allowed_tools(ctx)) + "):\n"
                    '     {"action": "tool", "tool_name": "<nome>", "args": {...}, '
                    '"text_after": "<resposta confirmando ao user>", '
                    '"next_question_intent": "<um destes ou null>"}'
                    "\n\nO campo `next_question_intent` é OBRIGATÓRIO quando "
                    "o text/text_after contém uma pergunta. Se for só "
                    "afirmação/confirmação sem pergunta, use null."
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
        next_q = decision.get("next_question_intent")
        # Normaliza valor inválido / None
        if next_q in ("", "null", "none", "None"):
            next_q = None
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
                next_question_intent=next_q,
                metadata={"phase_c_version": "v1_dry_run"},
            )
        # action == 'text'
        text = decision.get("text") or ""
        return AgentResponse(
            text=text,
            next_action="wait_user",
            next_question_intent=next_q,
        )
