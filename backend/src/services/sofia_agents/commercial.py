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


# ──────────────────────────────────────────────────────────────────
# Prompt commercial em DUAS partes (Phase D escala — Anthropic cache)
#
# Parte estática (STATIC_PROMPT_BASE + capabilities) → cacheable_system
#   - Não muda entre turnos da mesma persona
#   - ~3000 tokens (acima do mínimo 1024 do Anthropic cache)
#   - Hit do cache em <5min reduz custo desse bloco em ~90% e
#     latência ~30%
#
# Parte dinâmica (DYNAMIC_PROMPT_TEMPLATE) → system normal
#   - Muda a cada turno (CSM ctx, intent, contexto recente)
#   - ~500-1500 tokens
#
# user_message NÃO entra mais no system prompt — vai como user message
# da chamada (era duplicado antes).
# ──────────────────────────────────────────────────────────────────

STATIC_PROMPT_BASE = """Você é Sofia, IA da ConnectaIACare (cuidados de idosos com IA + atendimento humano 24/7).

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

╔══════════════════════════════════════════════════════════════════╗
║ REGRA DE OURO — NUNCA DEIXE O USER NO LIMBO APÓS TOOL CALL       ║
║ • SEMPRE que chamar UMA TOOL, gere TAMBÉM um bloco de TEXTO       ║
║   curto (1 frase) confirmando o que vai acontecer pro user.       ║
║ • capture_lead → "Anotei aqui, [nome]. <próxima pergunta>"        ║
║ • schedule_demo → "Vou agendar a demo, te chamo já com horários"  ║
║ • escalate_to_human_whatsapp → "Já avisei nossa equipe humana,    ║
║   alguém vai te chamar em instantes. Estou aqui se precisar."     ║
║ NUNCA chame tool sem dar feedback ao user — ele fica esperando    ║
║ resposta no WhatsApp e a ausência parece falha.                   ║
╚══════════════════════════════════════════════════════════════════╝

QUANDO USAR TOOL VS TEXTO:
- Lead disse só "oi" / sem dados → text (cumprimenta + pergunta nome)
- Lead deu apenas nome → tool capture_lead com {phone, intent, full_name} + text_after pedindo organização/papel
- Lead deu nome + empresa + papel → tool capture_lead completo + text_after pedindo dor específica
- Lead pediu demo claramente → tool schedule_demo
- Lead pediu humano → tool escalate_to_human_whatsapp com summary completo

EXEMPLO de tool call (saída JSON):
{
  "action": "tool",
  "tool_name": "capture_lead",
  "args": {
    "phone": "5511987654321",
    "intent": "interesse_servico_b2b",
    "full_name": "João Silva",
    "organization": "Casa Bem Cuidada",
    "role_self_declared": "gestor_ilpi",
    "confidence": 0.9,
    "notes": "ILPI 30 idosos, dor de quedas no turno da noite"
  },
  "text_after": "Anotei aqui, João. Sobre quedas na madrugada — quantos colaboradores atuam nesse turno?",
  "next_question_intent": "open_ended"
}"""


# Schema de saída + lista de intents — também estático, cacheable junto.
ALLOWED_TOOLS_TEXT = "capture_lead, schedule_demo, escalate_to_human_whatsapp"
INTENTS_HINT = (
    "primeiro_nome, nome_completo, email, cidade, relacao_idoso, "
    "count_idosos, idades_idosos, moram_sozinhos, moram_em_ilpi, "
    "dor_principal, count_medicamentos, dificuldade_medicacao, "
    "organizacao, cargo_b2b, ja_cliente_concorrente, quer_demo, "
    "intent_b2c_b2b, open_ended"
)
JSON_SCHEMA_TEXT = (
    "\n\nSAÍDA OBRIGATÓRIA: JSON estrito. Escolha ENTRE:\n"
    "  A) Resposta de texto (sem tool):\n"
    '     {"action": "text", '
    '"text": "<sua resposta brasileira coloquial>", '
    f'"next_question_intent": "<um destes: {INTENTS_HINT}>"}}\n\n'
    "  B) Chamar tool (uma das permitidas: " + ALLOWED_TOOLS_TEXT + "):\n"
    '     {"action": "tool", "tool_name": "<nome>", "args": {...}, '
    '"text_after": "<resposta confirmando ao user>", '
    '"next_question_intent": "<um destes ou null>"}'
    "\n\nO campo `next_question_intent` é OBRIGATÓRIO quando "
    "o text/text_after contém uma pergunta. Se for só "
    "afirmação/confirmação sem pergunta, use null."
)


# Parte dinâmica — varia por turno, NÃO entra no cache.
DYNAMIC_PROMPT_TEMPLATE = """CONTEXTO DESTE TURNO:
- Phone do lead: {phone}
- Intent classificado: {intent_label}
- Stage do funil: {stage}
{csm_block}
{context_block}"""


# ──────────────────────────────────────────────────────────────────
# Tool schemas (Anthropic tool-use nativo, Phase D 2026-05-02)
#
# Formato segue spec da Anthropic: name + description + input_schema
# (JSON Schema). Modelo recebe esses schemas via param `tools=[...]`
# do messages.create — diferente do pattern legado JSON-em-string,
# aqui Anthropic FORÇA o output a seguir o schema. Solução robusta
# pro bug de 2026-05-02 onde DeepSeek e Haiku NÃO chamavam
# escalate_to_human_whatsapp mesmo com pedido explícito do user.
# ──────────────────────────────────────────────────────────────────

COMMERCIAL_TOOLS_SCHEMA: list[dict] = [
    {
        "name": "capture_lead",
        "description": (
            "Captura/atualiza dados do lead em aia_health_leads. "
            "É IDEMPOTENTE — chame ASSIM QUE souber o nome do lead, "
            "mesmo que faltem dados. Pode chamar de novo nos turnos "
            "seguintes pra adicionar organization, role, etc. NUNCA "
            "termine um turno SEM chamar capture_lead se já souber o "
            "nome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Phone do lead em formato E.164 (vem em CONTEXTO DESTE TURNO).",
                },
                "intent": {
                    "type": "string",
                    "enum": [
                        "interesse_servico_b2c",
                        "interesse_servico_b2b",
                        "agendar_demo",
                        "duvida_geral",
                        "outro",
                    ],
                },
                "full_name": {
                    "type": "string",
                    "description": "Nome completo do lead (ou só primeiro nome se for tudo que tiver).",
                },
                "email": {"type": "string"},
                "organization": {
                    "type": "string",
                    "description": "Nome da empresa/ILPI/clínica do lead (B2B).",
                },
                "role_self_declared": {
                    "type": "string",
                    "description": "Cargo/papel declarado: 'gestor_ilpi','enfermeira_chefe','medico','familiar','cuidador_pro', etc.",
                },
                "confidence": {
                    "type": "number",
                    "description": "0.0–1.0. Quão confiante você está dos dados acima.",
                },
                "notes": {
                    "type": "string",
                    "description": "Resumo da dor / contexto / detalhes relevantes (ex: 'ILPI 30 leitos, dor quedas turno noite').",
                },
            },
            "required": ["phone", "intent", "full_name"],
        },
    },
    {
        "name": "schedule_demo",
        "description": (
            "Agenda demo com time comercial. Use quando lead pediu "
            "demo explicitamente OU intent=agendar_demo. Chame APÓS "
            "capture_lead (ou junto se já tiver dados). NÃO chame se "
            "lead ainda não confirmou interesse claro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "lead_full_name": {"type": "string"},
                "preferred_window": {
                    "type": "string",
                    "description": "Janela preferida do lead se mencionou (ex: 'amanhã de manhã', 'esta semana à tarde'). Se não, omita.",
                },
            },
            "required": ["phone", "lead_full_name"],
        },
    },
    {
        "name": "escalate_to_human_whatsapp",
        "description": (
            "Escala lead pra time humano da Central 24h. CHAME SEMPRE "
            "que o user: (a) pedir explicitamente humano/atendente/"
            "pessoa real ('quero falar com humano', 'preciso de "
            "alguém da equipe'), (b) demonstrar emergência clínica "
            "ou urgência ('minha mãe caiu', 'é emergência'), (c) "
            "expressar frustração com a IA, (d) você tiver feito 5+ "
            "turnos sem evolução. NÃO qualifique antes — escale "
            "primeiro, dados ficam no summary. Após escalate, "
            "responda ao user dizendo que humano vai contatar "
            "(curto, sem prometer prazo)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "reason": {
                    "type": "string",
                    "description": "Motivo da escalação em 1 frase. Ex: 'lead pediu humano agora, emergência clínica reportada (mãe caiu)'.",
                },
                "summary": {
                    "type": "string",
                    "description": "Resumo da conversa pra humano (ate 1000 chars). Inclua: nome, dor, urgência, dados qualificados até o momento.",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3"],
                    "description": "P1 (5min SLA, emergência clínica/risco), P2 (30min SLA, urgência), P3 (2h SLA, rotina).",
                },
            },
            "required": ["phone", "reason", "summary", "urgency"],
        },
    },
    # ─── Phase D Comercial — funil completo (migration 068) ────────
    {
        "name": "query_plans",
        "description": (
            "Consulta o catálogo de planos vendáveis. USE quando lead "
            "pergunta 'quanto custa', 'quais planos têm', 'tem opção mais "
            "barata'. Retorna sku/name/preço/features/pitch_short. Filtra "
            "por target_persona se passado (individual/familia/ilpi/"
            "clinica/hospital)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_persona": {
                    "type": "string",
                    "enum": ["individual", "familia", "ilpi", "clinica",
                             "hospital", "parceiro"],
                },
            },
        },
    },
    {
        "name": "schedule_demo_with_calendar",
        "description": (
            "Agenda demo COM data/hora explícita. Use quando lead aceita "
            "demo e dá horário específico. Cria row em lead_demos. "
            "Idempotente por (lead, dia). PREFIRA esta sobre schedule_demo "
            "(que é placeholder antigo)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "scheduled_at": {
                    "type": "string",
                    "description": "ISO 8601 com timezone, ex: '2026-05-09T14:00:00-03:00'",
                },
                "duration_minutes": {"type": "integer"},
                "full_name": {"type": "string"},
                "organization": {"type": "string"},
                "plan_focus_sku": {
                    "type": "string",
                    "description": "SKU do plano focal (de query_plans)",
                },
                "notes": {"type": "string"},
            },
            "required": ["phone", "scheduled_at"],
        },
    },
    {
        "name": "schedule_callback_call",
        "description": (
            "Agenda ligação de retorno. Use quando lead diz 'me liga depois', "
            "'amanhã às 14h tô livre'. Cria row em lead_calls. "
            "Time comercial vê em /comercial/agenda."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "scheduled_at": {"type": "string"},
                "call_type": {
                    "type": "string",
                    "enum": ["discovery", "follow_up", "callback", "proposal",
                             "closing", "qualification"],
                },
                "full_name": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["phone", "scheduled_at"],
        },
    },
    {
        "name": "register_lead_activity",
        "description": (
            "Anota observação no timeline do lead. Use pra capturar sinais "
            "que NÃO disparam outras tools: objeção levantada, sentimento, "
            "preferência de canal, indicação de orçamento/decisor. "
            "Aparece na UI /comercial/leads/<id>."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "activity_type": {
                    "type": "string",
                    "enum": ["note_added", "qualification_signal",
                             "objection_raised", "positive_feedback",
                             "concern_raised"],
                },
                "summary": {"type": "string"},
                "importance": {
                    "type": "string",
                    "enum": ["minor", "normal", "important", "critical"],
                },
            },
            "required": ["phone", "activity_type", "summary"],
        },
    },
    {
        "name": "send_proposal",
        "description": (
            "Registra envio de proposta com plano + valor + validade. "
            "Use APÓS lead confirmar interesse. Cria row em lead_proposals "
            "+ atualiza lead.status='proposal_sent'. Idempotente por "
            "(lead, plano)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "plan_sku": {
                    "type": "string",
                    "description": "SKU do plano (obtenha via query_plans)",
                },
                "custom_price_monthly_cents": {"type": "integer"},
                "discount_percent": {"type": "number"},
                "valid_until": {
                    "type": "string",
                    "description": "Data ISO YYYY-MM-DD",
                },
                "sent_via": {
                    "type": "string",
                    "enum": ["email", "whatsapp", "in_demo", "voice_call"],
                },
                "notes": {"type": "string"},
            },
            "required": ["phone", "plan_sku"],
        },
    },
    {
        "name": "get_lead_status",
        "description": (
            "Consulta status atual do lead pelo phone. USE NO INÍCIO da "
            "sessão se quiser saber se ele já é lead conhecido (com demo "
            "agendada, proposta ativa, etc.) — você continua de onde "
            "parou em vez de começar do zero."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "update_lead_qualification",
        "description": (
            "Atualiza score de qualificação (0-100). Heurística: "
            "0-30 frio (curiosidade); 30-60 morno (interesse); "
            "60-80 quente (orçamento+urgência+decisor); 80+ pronto pra "
            "fechar. Pode também avançar status (qualified/lost/etc)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "qualification_score": {"type": "integer"},
                "new_status": {
                    "type": "string",
                    "enum": ["new", "qualified", "demo_scheduled", "in_demo",
                             "proposal_sent", "converted", "lost"],
                },
                "reason": {"type": "string"},
            },
            "required": ["phone", "qualification_score"],
        },
    },
]


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

    # ─── System prompt em duas partes (Phase D escala) ──────────────

    def _cacheable_system(self, ctx: AgentContext) -> str:
        """Parte ESTÁTICA do prompt — não muda entre turnos.

        Esta é a parte que vai com cache_control no Anthropic. Inclui:
        - Persona + missão + regras de tom + REGRA DE OURO
        - Whitelist de capabilities (varia por persona, mas mesma persona
          em sessão consecutiva é o MESMO bloco)
        - Schema de saída JSON + lista de intents

        Tem ~3000 tokens (acima do mínimo 1024 do Anthropic).
        """
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
        return (
            STATIC_PROMPT_BASE
            + "\n\n" + capabilities_block
            + JSON_SCHEMA_TEXT
        )

    def _dynamic_system(self, ctx: AgentContext) -> str:
        """Parte DINÂMICA — muda a cada turno. Não entra no cache."""
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

        csm_block = _format_csm_block(ctx.csm_context or {})
        stage = (ctx.csm_context or {}).get("stage", "warmup")

        return DYNAMIC_PROMPT_TEMPLATE.format(
            phone=ctx.phone,
            intent_label=intent_label,
            stage=stage,
            csm_block=csm_block,
            context_block="\n".join(context_lines),
        )

    def system_prompt(self, ctx: AgentContext) -> str:
        """Backward-compat: retorna prompt completo (estático + dinâmico).

        Usado pra audit log + tests. Em produção, .process() usa as duas
        partes separadas pra aproveitar cache do Anthropic.
        """
        return self._cacheable_system(ctx) + "\n\n" + self._dynamic_system(ctx)

    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        return [
            # Legado (Phase C v1) — capture_lead aqui é o original em
            # sofia_tools.py que cria/atualiza row em aia_health_leads.
            # Continua funcionando pra Sofia gravar nome/intent/etc.
            "capture_lead",
            "schedule_demo",                # placeholder genérico, mantido pra compat
            "escalate_to_human_whatsapp",
            # Phase D Comercial (migration 068) — funil completo
            "query_plans",
            "schedule_demo_with_calendar",
            "schedule_callback_call",
            "register_lead_activity",
            "send_proposal",
            "get_lead_status",
            "update_lead_qualification",
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
            # Decision: texto direto OU tool call (NATIVO Anthropic).
            #
            # Phase D 2026-05-02: passa tools=COMMERCIAL_TOOLS_SCHEMA
            # pra ativar tool-use NATIVO. Modelo (Haiku 4.5) recebe
            # schema estruturado, output garantido vem como tool_use
            # block (não JSON-em-string que o modelo podia ignorar).
            #
            # Anthropic prompt caching: parte estática (regras +
            # capabilities) vai como cacheable_system; parte dinâmica
            # (CSM ctx, intent, contexto recente) vai como system
            # normal. Cache TTL ~5min — turnos consecutivos do mesmo
            # lead pagam ~10% do custo desse bloco.
            decision = router.complete_json(
                task="sofia_chat_tool_decision",
                cacheable_system=self._cacheable_system(ctx),
                system=self._dynamic_system(ctx),
                user=ctx.inbound_text[:1500],
                tools=COMMERCIAL_TOOLS_SCHEMA,
                tool_choice="auto",
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
            # Executa de fato via TOOL_REGISTRY (sofia_tools.execute_tool).
            # Antes ficava como dry-run "pending_phase_c4" e nada acontecia
            # — tool decisão era registrada mas nunca rodava (handoff
            # nunca era criado, capture_lead nunca persistia, etc.).
            # Bug observado em prod 2026-05-03: lead pediu humano em
            # emergência, Sofia decidiu chamar escalate_to_human_whatsapp,
            # texto narrativizado foi enviado mas handoff_queue ficou vazio.
            from src.services.sofia_tools import execute_tool

            tool_name = decision.get("tool_name") or ""
            llm_args = decision.get("args") or {}
            text_after = decision.get("text_after") or ""

            # Sanitiza args do LLM: phone e tenant_id sempre vêm do ctx
            # (anti-hijack — LLM não pode escalar handoff de outro lead
            # ou pra outro tenant). Demais args (reason/summary/urgency)
            # ficam por conta do LLM.
            safe_args = dict(llm_args)
            safe_args["phone"] = ctx.phone
            if tool_name == "escalate_to_human_whatsapp":
                # conversation_log: deriva do active_context_messages do
                # ctx pra dar contexto pro operador humano.
                safe_args.setdefault(
                    "conversation_log",
                    list(ctx.active_context_messages or []),
                )

            tool_result = execute_tool(
                tool_name,
                safe_args,
                tenant_id=ctx.tenant.id,
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
            )

            tool_call_record = {
                "name": tool_name,
                "args": safe_args,
                "ok": tool_result.ok,
                "idempotent_skip": tool_result.idempotent_skip,
                "output": tool_result.data,
            }
            if tool_result.error:
                tool_call_record["error"] = tool_result.error

            # Se a tool falhou (não idempotent_skip), evita prometer ao
            # lead algo que não aconteceu. Devolve fallback honesto.
            if not tool_result.ok and not tool_result.idempotent_skip:
                logger.warning(
                    "commercial_tool_failed",
                    trace_id=ctx.trace_id,
                    tool=tool_name,
                    error=tool_result.error,
                )
                return AgentResponse(
                    text=(
                        "Recebi sua mensagem mas tive um problema técnico aqui "
                        "do meu lado. Em instantes alguém da equipe humana entra "
                        "em contato com você. 🙏"
                    ),
                    tools_called=[tool_call_record],
                    next_action="wait_user",
                    next_question_intent=next_q,
                    metadata={"tool_exec_failed": True},
                )

            return AgentResponse(
                text=text_after,
                tools_called=[tool_call_record],
                handoff_initiated=(
                    tool_name == "escalate_to_human_whatsapp"
                    and tool_result.ok
                    and not tool_result.idempotent_skip
                ),
                handoff_reason=(
                    safe_args.get("reason")
                    if tool_name == "escalate_to_human_whatsapp"
                    else None
                ),
                next_action=(
                    "wait_human"
                    if tool_name == "escalate_to_human_whatsapp" and tool_result.ok
                    else "wait_user"
                ),
                next_question_intent=next_q,
                metadata={
                    "tool_executed": True,
                    "tool_idempotent_skip": tool_result.idempotent_skip,
                },
            )
        # action == 'text' — mas validator semântico pega o caso em que
        # o LLM "mente": narra promessa de escalate ("vou avisar a equipe…")
        # sem ter chamado a tool. Auto-recovery: dispara
        # escalate_to_human_whatsapp com defaults seguros pra cumprir o
        # que foi prometido. Zero falso positivo (só dispara quando o
        # próprio LLM produziu texto de promessa).
        text = decision.get("text") or ""
        from src.services.sofia_agents.escalate_output_validator import (
            detect_escalate_promise, build_recovery_summary,
        )

        validation = detect_escalate_promise(text)
        if validation.promised_escalate:
            from src.services.sofia_tools import execute_tool

            recovery_args = {
                "phone": ctx.phone,
                "reason": (
                    "[AUTO-RECOVERY] Sofia narrou escalate sem chamar tool — "
                    f"validador detectou promessa: '{validation.matched_pattern}'"
                ),
                "summary": build_recovery_summary(
                    ctx.inbound_text or "",
                    text,
                    validation.matched_pattern or "",
                ),
                # P2 default — não inflar P1 sem confirmação semântica clínica.
                # Operador pode reclassificar no chat se contexto exigir.
                "urgency": "P2",
                "conversation_log": list(ctx.active_context_messages or []),
            }
            tool_result = execute_tool(
                "escalate_to_human_whatsapp",
                recovery_args,
                tenant_id=ctx.tenant.id,
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
            )
            logger.warning(
                "commercial_escalate_auto_recovered",
                trace_id=ctx.trace_id,
                matched_pattern=validation.matched_pattern,
                tool_ok=tool_result.ok,
                idempotent_skip=tool_result.idempotent_skip,
                tool_error=tool_result.error,
            )
            tool_call_record = {
                "name": "escalate_to_human_whatsapp",
                "args": recovery_args,
                "ok": tool_result.ok,
                "idempotent_skip": tool_result.idempotent_skip,
                "output": tool_result.data,
                "auto_recovery": True,
                "matched_pattern": validation.matched_pattern,
            }
            if tool_result.error:
                tool_call_record["error"] = tool_result.error
            return AgentResponse(
                text=text,
                tools_called=[tool_call_record],
                handoff_initiated=(
                    tool_result.ok and not tool_result.idempotent_skip
                ),
                handoff_reason=recovery_args["reason"],
                next_action="wait_human",
                next_question_intent=next_q,
                metadata={
                    "auto_escalate_recovery": True,
                    "tool_executed": True,
                    "tool_idempotent_skip": tool_result.idempotent_skip,
                },
            )

        return AgentResponse(
            text=text,
            next_action="wait_user",
            next_question_intent=next_q,
        )
