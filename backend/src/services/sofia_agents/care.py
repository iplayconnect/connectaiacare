"""CareSofiaAgent — atende cuidador (profissional ou autônomo) com
contexto clínico e pharmacovigilância ativa.

Ativado quando:
    - phone resolve como `cuidador` ou `cuidador_pro`
    - feature flag CARE_AGENT_ENABLED=true (rollout gradual)

Comportamento:
    1. Cumprimenta com tom acolhedor (UMA frase, sem firulas).
    2. Lê o relato do cuidador. Se relato menciona MEDICAÇÃO ou
       PRESCRIÇÃO NOVA, chama `safety_review_prescriptions` ANTES
       de responder.
    3. Se review retorna max_severity ∈ ('block', 'warning_strong'),
       NÃO responde com voz própria — chama `escalate_to_human_clinical`
       passando drug_safety_findings pra Henrique/médico decidir.
    4. Se review retorna 'warning' ou 'info', alerta cuidador no texto
       e registra no relato (`register_caregiver_report` com severity).
    5. Pra relatos rotineiros (sem med), registra report 'rotina_diaria'
       e responde com pergunta de follow-up apropriada.
    6. Cuidador pediu humano explicitamente OU 5 turnos sem evolução
       OU sintoma agudo (dor súbita, queda, alteração consciência) →
       `escalate_to_human_clinical` urgency=P2.

REGRAS QUE CAREsOFIAAGENT NÃO PODE QUEBRAR:
    - NUNCA prescreve medicação ("dê tal med") nem confirma posologia
      sem o pipeline drug_safety ter aprovado
    - NUNCA inventa dose/horário; quando incerta, cita o que está
      cadastrado (medications) e pede confirmação
    - NUNCA simula raciocínio clínico próprio — sempre delega via tool
      ou escala humano
    - SEMPRE chama safety_review_prescriptions quando texto menciona
      med, mesmo que não tenha certeza (fail-open pra alerta)

Phase C v2 PR 2: implementação inicial. Phase C v2.x posterior pode:
    - Tool `register_vital_sign` (PA, glicemia, peso) parser regex
    - Tool `register_medication_administered` (confirmar med dada)
    - Cross-reference com baselines do paciente (alerta de desvio)
    - Tool `query_patient_history` pra cuidador consultar plano de cuidado
"""
from __future__ import annotations

from typing import Optional

from src.services.sofia_agents.base import (
    AgentContext, AgentResponse, BaseSofiaAgent,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────
# Heurística leve pra detecção de menção a med/prescrição
# ──────────────────────────────────────────────────────────────────

import re as _re

_MED_MENTION_PATTERNS = [
    _re.compile(r"\b\d+\s*mg\b", _re.IGNORECASE),
    _re.compile(r"\b\d+\s*mcg\b", _re.IGNORECASE),
    _re.compile(r"\b\d+\s*ml\b", _re.IGNORECASE),
    _re.compile(r"\b\d+\s*ui\b", _re.IGNORECASE),
    _re.compile(r"\bcomprimid|c[áa]psul|gota|inje|amp[óo]ula\b", _re.IGNORECASE),
    _re.compile(
        r"\b(losartan|metform|sinvas|atorv|enalapr|captopr|amlodip|"
        r"atenol|hidroclor|aspirin|paracetamol|dipiron|ibuprof|"
        r"diazep|alpraz|clonaz|lorazepa|zolpidem|"
        r"omeprazol|pantopr|esomepr|"
        r"varfarin|cumadin|rivaroxa|apixab|dabigat|"
        r"insulin|gliclaz|glibenc|"
        r"sertralin|fluoxet|escitalopr|venlafax|"
        r"tramadol|codein|morfin|fentan|"
        r"prednis|dexamet)",
        _re.IGNORECASE,
    ),
    _re.compile(
        r"\b(receit|prescri[çc][ãa]o|come[çc]ar|iniciar|tomar|administr)\w*\s+\w*",
        _re.IGNORECASE,
    ),
]

_ACUTE_SYMPTOM_PATTERNS = [
    _re.compile(r"\bcaiu|caiu\s+do|tombou|despencou\b", _re.IGNORECASE),
    _re.compile(r"\bdor\s+(forte|aguda|s[úu]bita|no\s+peito|de\s+cabe[çc]a)\b", _re.IGNORECASE),
    _re.compile(r"\bn[ãa]o\s+(responde|reage|acorda|fala)\b", _re.IGNORECASE),
    _re.compile(r"\bconvuls|crise|desmaiou|desfaleceu\b", _re.IGNORECASE),
    _re.compile(r"\bsangra|hemorra|v[ôo]mit\w*\s+sangue|fezes\s+pretas\b", _re.IGNORECASE),
    _re.compile(r"\bfalta\s+de\s+ar|sufoca|n[ãa]o\s+consegue\s+respirar\b", _re.IGNORECASE),
    _re.compile(r"\bfebre\s+(\d{2,3}|alta|persistente)\b", _re.IGNORECASE),
]


def _mentions_medication(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _MED_MENTION_PATTERNS)


def _mentions_acute_symptom(text: str) -> Optional[str]:
    """Retorna padrão matched (descrição) ou None."""
    if not text:
        return None
    for p in _ACUTE_SYMPTOM_PATTERNS:
        m = p.search(text)
        if m:
            return m.group(0)[:60]
    return None


# ──────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────

STATIC_PROMPT_BASE = """Você é Sofia, IA de cuidado da ConnectaIACare. Está no WhatsApp conversando com um CUIDADOR (profissional ou familiar) que cuida de um idoso.

Seu papel:
1. Receber relatos do dia (rotina, sinais vitais, comportamento, intercorrências)
2. Validar QUALQUER menção a medicação contra nosso pipeline farmacológico ANTES de responder
3. Registrar relatos importantes pra equipe clínica revisar
4. Escalar pra humano clinical quando: alta severidade farmacológica, sintoma agudo, ou cuidador pedir explicitamente

REGRAS INVIOLÁVEIS:
- NUNCA prescreva medicação. Você NÃO é médica.
- NUNCA confirme posologia sem ter rodado safety_review_prescriptions.
- NUNCA invente dose/horário. Se incerta, cite o que está cadastrado pro paciente.
- NUNCA simule raciocínio clínico próprio — delega via tool ou escala.
- SEMPRE chame safety_review_prescriptions se texto menciona med, mesmo se não tem certeza (fail-open).

REGRAS DE TOM:
- Brasileiro coloquial, calorosa-profissional. Cuidador tá cansado, não quer formalidade vazia.
- CURTO. Máximo 3 frases por turno.
- UMA pergunta por turno. Nunca empilhar.
- Honesta sobre limites: "vou pedir pra equipe clínica olhar" é resposta válida e desejável.
- Empática mas não pegajosa. Sem "que bom que você tá cuidando" todo turno.

╔══════════════════════════════════════════════════════════════════╗
║ FLUXO DE DECISÃO POR TURNO                                       ║
╠══════════════════════════════════════════════════════════════════╣
║ 1. Texto menciona SINTOMA AGUDO (caiu, dor forte, não responde,  ║
║    convulsão, sangramento, falta de ar, febre alta)?             ║
║    → escalate_to_human_clinical urgency=P1, NÃO espera review.   ║
║                                                                   ║
║ 2. Texto menciona MEDICAÇÃO (dose mg, nome med, "receitou",      ║
║    "tomar")?                                                      ║
║    → SEMPRE chama safety_review_prescriptions PRIMEIRO.          ║
║    → Se max_severity in (block, warning_strong):                 ║
║        chama escalate_to_human_clinical urgency=P2 com           ║
║        drug_safety_findings preenchido. Resposta ao cuidador     ║
║        deve dizer "vou pedir o time clínico revisar antes de     ║
║        confirmar — me chamam em breve".                          ║
║    → Se max_severity in (warning, info):                         ║
║        responde alertando cuidador com clareza E chama           ║
║        register_caregiver_report severity=attention/info.        ║
║    → Se max_severity is None (med não cadastrada/desconhecida):  ║
║        responde "preciso confirmar com o time clínico antes de   ║
║        opinar" e chama escalate_to_human_clinical urgency=P3.    ║
║                                                                   ║
║ 3. Texto é relato ROTINEIRO (sem med, sem sintoma agudo)?        ║
║    → register_caregiver_report report_type='rotina_diaria'       ║
║      severity=info. Responde com follow-up útil (1 pergunta).    ║
║                                                                   ║
║ 4. Cuidador pediu humano OU 5 turnos sem evolução?               ║
║    → escalate_to_human_clinical urgency=P3.                      ║
╚══════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════╗
║ NUNCA DEIXE O CUIDADOR NO LIMBO APÓS TOOL CALL                   ║
║ • SEMPRE que chamar UMA TOOL, gere TAMBÉM um TEXTO curto         ║
║   (1 frase) confirmando o que vai acontecer.                     ║
║ • safety_review_prescriptions → "Deixa eu checar essa medicação  ║
║   no nosso sistema clínico…" (depois processa o resultado)        ║
║ • register_caregiver_report → "Anotei aqui no prontuário."       ║
║ • escalate_to_human_clinical → "Vou pedir o time clínico olhar.  ║
║   Te chamam pelo WhatsApp em breve."                             ║
╚══════════════════════════════════════════════════════════════════╝
"""

JSON_SCHEMA_TEXT = """
Output JSON:
{"action": "tool" OR "text",
 "tool_name": "<um dos abaixo>" (se action=tool),
 "args": {...} (se action=tool, args específicos da tool),
 "text_after": "1 frase curta pro cuidador" (se action=tool — confirma o que vai rolar),
 "text": "resposta completa" (se action=text — só quando NENHUMA tool é necessária),
 "next_question_intent": "<intent>" (opcional)}

Tools disponíveis:
- safety_review_prescriptions(prescriptions, patient_id)
- register_caregiver_report(caregiver_id, caregiver_phone, patient_id, report_type, summary, severity, details)
- escalate_to_human_clinical(phone, reason, summary, patient_id, caregiver_id, drug_safety_findings, urgency)
"""


CARE_TOOLS_SCHEMA: list[dict] = [
    {
        "name": "safety_review_prescriptions",
        "description": (
            "Consulta o knowledge graph farmacológico (142 drugs, 93 "
            "interações, dose limits, ACB, fall risk, renal/hepatic, "
            "cascatas) pra avaliar uma ou mais prescrições. SEMPRE "
            "chame quando o texto do cuidador mencionar medicação, "
            "dose, ou prescrição nova. Retorna max_severity e "
            "requires_human_review pra decidir próximo passo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prescriptions": {
                    "type": "array",
                    "description": (
                        "Lista de prescrições candidatas extraídas do "
                        "texto do cuidador. Mesmo se cuidador relatou med "
                        "que já está cadastrada, inclua aqui pra revalidar."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "medication_name": {"type": "string"},
                            "dose": {"type": "string"},
                            "times_of_day": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["medication_name", "dose"],
                    },
                },
                "patient_id": {
                    "type": "string",
                    "description": "UUID do paciente (vem em CONTEXTO).",
                },
            },
            "required": ["prescriptions"],
        },
    },
    {
        "name": "register_caregiver_report",
        "description": (
            "Registra relato do cuidador em aia_health_reports. Use "
            "pra documentar rotina diária, sinais vitais, mudanças de "
            "comportamento, eventos relevantes. Severity controla "
            "priorização (info=normal; attention=time clínico revisa "
            "no plantão; urgent=alerta imediato)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caregiver_id": {"type": "string"},
                "caregiver_phone": {"type": "string"},
                "patient_id": {"type": "string"},
                "report_type": {
                    "type": "string",
                    "enum": [
                        "rotina_diaria", "mudanca_comportamento",
                        "queda", "sinal_vital", "recusa_medicacao",
                        "agitacao", "medicacao_administrada",
                        "alerta_farmacologico", "outro",
                    ],
                },
                "summary": {
                    "type": "string",
                    "description": "Resumo do relato em até 2-3 frases.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "attention", "urgent"],
                },
                "details": {
                    "type": "object",
                    "description": "Dados estruturados extraídos (ex: {pa_sistolica, pa_diastolica}).",
                },
            },
            "required": [
                "caregiver_id", "caregiver_phone", "patient_id",
                "report_type", "summary", "severity",
            ],
        },
    },
    {
        "name": "escalate_to_human_clinical",
        "description": (
            "Escala pra equipe CLÍNICA (não comercial). Use quando: "
            "(1) sintoma agudo no relato; (2) drug_safety retornou "
            "max_severity in (block, warning_strong); (3) med não "
            "cadastrada/reconhecida; (4) cuidador pediu humano clínico "
            "explicitamente; (5) 5 turnos sem evolução. Inclua "
            "drug_safety_findings se já rodou safety_review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "patient_id": {"type": "string"},
                "caregiver_id": {"type": "string"},
                "reason": {"type": "string"},
                "summary": {
                    "type": "string",
                    "description": (
                        "Resumo pra quem reivindicar entender o caso "
                        "sem precisar ler todo o histórico."
                    ),
                },
                "drug_safety_findings": {
                    "type": "object",
                    "description": (
                        "Output completo de safety_review_prescriptions "
                        "se já rodou no turno. Omita se não rodou."
                    ),
                },
                "urgency": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3"],
                },
            },
            "required": ["phone", "reason", "summary", "urgency"],
        },
    },
]


# ──────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────


class CareSofiaAgent(BaseSofiaAgent):
    """Sub-agent clínico pra cuidador identificado.

    Substitui PassthroughSofiaAgent pra perfis 'cuidador' e 'cuidador_pro'
    quando feature flag `CARE_AGENT_ENABLED` está ativa.

    Identificado pelo orchestrator via classe `CLINICAL_AGENTS` em
    super_sofia_orchestrator — sofre guardrail anti-hallucination
    automaticamente.
    """

    name = "care"

    def system_prompt(self, ctx: AgentContext) -> str:
        return self._cacheable_system(ctx) + "\n\n" + self._dynamic_system(ctx)

    def _cacheable_system(self, ctx: AgentContext) -> str:
        return STATIC_PROMPT_BASE + "\n\n" + JSON_SCHEMA_TEXT

    def _dynamic_system(self, ctx: AgentContext) -> str:
        # Contexto do paciente associado ao cuidador (carregado on-demand)
        patient_block = self._load_patient_block(ctx)

        context_lines: list[str] = []
        if ctx.active_context_messages:
            context_lines.append(
                f"- Conversa anterior ({len(ctx.active_context_messages)} msgs nos últimos 45min):"
            )
            for msg in ctx.active_context_messages[-6:]:
                role = msg.get("role", "?")
                content = (msg.get("content") or "")[:160]
                context_lines.append(f"  [{role}] {content}")
        else:
            context_lines.append("- Primeira mensagem do cuidador nesta sessão.")

        caregiver_id = (
            ctx.identity_match.caregiver_id if ctx.identity_match else None
        )
        full_name = ctx.full_name or "(nome não cadastrado)"

        return f"""CONTEXTO DESTE TURNO:

- Cuidador: {full_name}
- Caregiver ID: {caregiver_id or 'NÃO CADASTRADO'}
- Phone: {ctx.phone}
- Tenant: {ctx.tenant.id}
- Trace: {ctx.trace_id}

{patient_block}

CONVERSA RECENTE:
{chr(10).join(context_lines)}

REGRAS DESTE TURNO:
- Use SEMPRE o caregiver_id e caregiver_phone do CONTEXTO acima ao chamar tools.
- Se mensagem menciona med, chame safety_review_prescriptions ANTES de qualquer texto.
- Se mensagem tem sintoma agudo, escale CLINICAL urgency=P1 IMEDIATAMENTE.
- Se relato é rotineiro, register_caregiver_report e responda com follow-up.
"""

    def _load_patient_block(self, ctx: AgentContext) -> str:
        """Carrega ficha resumida do paciente atribuído ao cuidador.

        Best-effort. Se cuidador atende N pacientes, escolhe o primário
        (is_primary=TRUE). Se nenhum, retorna "sem paciente atribuído".
        """
        caregiver_id = (
            ctx.identity_match.caregiver_id if ctx.identity_match else None
        )
        if not caregiver_id:
            return "PACIENTE: cuidador sem caregiver_id resolvido. NÃO chame tools que exijam patient_id."

        try:
            from src.services.postgres import get_postgres
            row = get_postgres().fetch_one(
                """SELECT p.id::text AS id, p.full_name, p.nickname,
                          p.birth_date, p.gender, p.care_level,
                          p.conditions, p.medications, p.allergies,
                          p.serum_creatinine_mg_dl,
                          a.is_primary, a.relationship
                   FROM aia_health_caregiver_patient_assignments a
                   JOIN aia_health_patients p ON p.id = a.patient_id
                   WHERE a.caregiver_id = %s AND a.active = TRUE
                     AND p.active = TRUE
                   ORDER BY a.is_primary DESC, a.created_at ASC
                   LIMIT 1""",
                (caregiver_id,),
            )
            if not row:
                return "PACIENTE: cuidador sem assignment ativo no momento."

            from datetime import date
            age = "?"
            if row.get("birth_date"):
                bd = row["birth_date"]
                today = date.today()
                age = today.year - bd.year - (
                    (today.month, today.day) < (bd.month, bd.day)
                )

            conditions = row.get("conditions") or []
            cond_str = ", ".join(
                c.get("description") or c.get("code", "?")
                for c in conditions
            ) if isinstance(conditions, list) else "?"

            medications = row.get("medications") or []
            meds_str = ", ".join(
                m.get("name", "?") for m in medications
            ) if isinstance(medications, list) else "?"

            allergies = row.get("allergies") or []
            alg_str = ", ".join(
                a if isinstance(a, str) else a.get("name", "?")
                for a in allergies
            ) if isinstance(allergies, list) else "?"

            return f"""PACIENTE ATRIBUÍDO:
- ID: {row['id']}
- Nome: {row['full_name']} ({row.get('nickname') or '-'})
- Idade: {age} anos · {row.get('gender') or '?'}
- Care level: {row.get('care_level') or '?'}
- Condições: {cond_str or 'nenhuma cadastrada'}
- Medicações em uso: {meds_str or 'nenhuma cadastrada'}
- Alergias: {alg_str or 'nenhuma cadastrada'}
- Creatinina sérica: {row.get('serum_creatinine_mg_dl') or 'não medida'} mg/dL"""
        except Exception as exc:
            logger.warning(
                "care_agent_patient_load_failed",
                caregiver_id=caregiver_id,
                trace_id=ctx.trace_id,
                error=str(exc)[:200],
            )
            return "PACIENTE: erro carregando ficha. Use só tools que NÃO exijam patient_id."

    def allowed_tools(self, ctx: AgentContext) -> list[str]:
        return [
            "safety_review_prescriptions",
            "register_caregiver_report",
            "escalate_to_human_clinical",
        ]

    def process(self, ctx: AgentContext) -> AgentResponse:
        """Phase C v2 PR 2: implementação básica via LLM tool-use.

        Estratégia (compatível com commercial/support):
            1. Pre-check heurístico de sintoma agudo → escalate direto
               sem LLM (latência baixa em emergência)
            2. LLM decide: tool OR text. Se tool, executa via execute_tool.
            3. Tools clínicas (drug_safety) podem ser chamadas em CADEIA
               futuramente — Phase C v2.x. Por enquanto 1 tool por turno.
        """
        # ─── Pre-check: sintoma agudo bypassa LLM ────────────────────
        acute = _mentions_acute_symptom(ctx.inbound_text or "")
        if acute:
            return self._handle_acute_symptom(ctx, acute_pattern=acute)

        # ─── LLM decision ────────────────────────────────────────────
        from src.services.llm_router import get_llm_router

        router = get_llm_router()
        try:
            decision = router.complete_json(
                task="sofia_chat_tool_decision",
                cacheable_system=self._cacheable_system(ctx),
                system=self._dynamic_system(ctx),
                user=ctx.inbound_text[:1500],
                tools=CARE_TOOLS_SCHEMA,
                tool_choice="auto",
            )
        except Exception as exc:
            logger.exception(
                "care_agent_llm_failed",
                trace_id=ctx.trace_id, error=str(exc)[:200],
            )
            # Failsafe: se LLM crashou, escalar conservadoramente
            return self._failsafe_escalate(
                ctx,
                reason="care_agent_llm_failure",
                summary=(
                    "LLM falhou no caregiver agent. Cuidador tinha mandado: "
                    f"'{(ctx.inbound_text or '')[:200]}'"
                ),
            )

        action = decision.get("action") or "text"
        next_q = decision.get("next_question_intent")
        if next_q in ("", "null", "none", "None"):
            next_q = None

        if action == "tool":
            return self._execute_tool_action(ctx, decision, next_q)

        # ─── action == 'text' ────────────────────────────────────────
        text = decision.get("text") or ""
        if _mentions_medication(ctx.inbound_text or "") and not text:
            # Defesa: se mensagem menciona med mas LLM não chamou
            # safety_review, cair pra escalate clinical (P3) pra revisão
            # humana — política conservadora.
            logger.warning(
                "care_agent_med_mentioned_no_review",
                trace_id=ctx.trace_id,
                inbound_preview=(ctx.inbound_text or "")[:120],
            )
            return self._failsafe_escalate(
                ctx,
                reason="med_mentioned_no_review",
                summary=(
                    "Cuidador mencionou medicação mas LLM não rodou "
                    "safety_review. Escalando pra revisão humana. "
                    f"Texto original: '{(ctx.inbound_text or '')[:300]}'"
                ),
                urgency="P3",
            )

        return AgentResponse(
            text=text or (
                "Recebi seu relato. Deixa eu olhar com atenção e "
                "te respondo já."
            ),
            next_action="wait_user",
            next_question_intent=next_q,
        )

    # ── Handlers internos ──────────────────────────────────────────

    def _handle_acute_symptom(
        self, ctx: AgentContext, *, acute_pattern: str,
    ) -> AgentResponse:
        """Sintoma agudo → escalate IMEDIATO P1 sem esperar LLM."""
        from src.services.sofia_tools import execute_tool

        caregiver_id = (
            ctx.identity_match.caregiver_id if ctx.identity_match else None
        )
        patient_id = self._get_patient_id_for_caregiver(caregiver_id)

        result = execute_tool(
            "escalate_to_human_clinical",
            {
                "phone": ctx.phone,
                "caregiver_id": caregiver_id,
                "patient_id": patient_id,
                "reason": f"acute_symptom_detected:{acute_pattern}",
                "summary": (
                    f"[PRE-LLM EMERGENCY] Cuidador relatou: "
                    f"'{(ctx.inbound_text or '')[:300]}'. "
                    f"Padrão detectado: '{acute_pattern}'."
                ),
                "urgency": "P1",
            },
            tenant_id=ctx.tenant.id,
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )

        tool_call_record = {
            "name": "escalate_to_human_clinical",
            "args": {"urgency": "P1", "pattern": acute_pattern},
            "ok": result.ok,
            "idempotent_skip": result.idempotent_skip,
            "output": result.data,
        }
        if result.error:
            tool_call_record["error"] = result.error

        return AgentResponse(
            text=(
                "Recebi. Vou acionar a equipe clínica AGORA — alguém "
                "vai te chamar em instantes. Se for emergência grave, "
                "ligue 192 (SAMU) também. 🚨"
            ),
            tools_called=[tool_call_record],
            handoff_initiated=True,
            handoff_reason=f"acute_symptom:{acute_pattern}",
            next_action="wait_human",
            metadata={"acute_symptom_bypass": True, "pattern": acute_pattern},
        )

    def _execute_tool_action(
        self, ctx: AgentContext, decision: dict, next_q: Optional[str],
    ) -> AgentResponse:
        from src.services.sofia_tools import execute_tool

        tool_name = decision.get("tool_name") or ""
        llm_args = decision.get("args") or {}
        text_after = decision.get("text_after") or ""

        # Sanitiza args: usa caregiver_id/phone/patient_id do CTX
        # (anti-hijack — LLM não pode injetar IDs arbitrários).
        safe_args = dict(llm_args)
        safe_args["phone"] = ctx.phone

        caregiver_id = (
            ctx.identity_match.caregiver_id if ctx.identity_match else None
        )
        if caregiver_id and tool_name in (
            "register_caregiver_report", "escalate_to_human_clinical",
        ):
            safe_args["caregiver_id"] = caregiver_id

        if tool_name == "register_caregiver_report":
            safe_args["caregiver_phone"] = ctx.phone

        # patient_id: se LLM não preencheu, usa primary do caregiver
        if "patient_id" not in safe_args or not safe_args.get("patient_id"):
            patient_id = self._get_patient_id_for_caregiver(caregiver_id)
            if patient_id:
                safe_args["patient_id"] = patient_id

        if tool_name == "escalate_to_human_clinical":
            safe_args.setdefault(
                "conversation_log", list(ctx.active_context_messages or []),
            )

        result = execute_tool(
            tool_name, safe_args,
            tenant_id=ctx.tenant.id,
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )

        tool_call_record = {
            "name": tool_name,
            "args": safe_args,
            "ok": result.ok,
            "idempotent_skip": result.idempotent_skip,
            "output": result.data,
        }
        if result.error:
            tool_call_record["error"] = result.error

        # Tool failed (não idempotente, erro de fato) → escalate failsafe
        if not result.ok and not result.idempotent_skip:
            logger.warning(
                "care_tool_failed",
                trace_id=ctx.trace_id, tool=tool_name, error=result.error,
            )
            return AgentResponse(
                text=(
                    "Recebi seu relato mas tive um problema técnico aqui. "
                    "Vou pedir o time clínico humano olhar — te chamam "
                    "em breve. 🙏"
                ),
                tools_called=[tool_call_record],
                handoff_initiated=False,
                next_action="wait_human",
                metadata={"tool_exec_failed": True, "tool": tool_name},
            )

        # safety_review retornou + max_severity alto → cadeia: chama
        # escalate em sequência (não no mesmo turno — registra na
        # response que próximo turno deve escalar). Phase C v2.x melhora
        # isso com tool-use loop nativo.
        # Por ora, se review pediu human review, retornamos texto neutro
        # e LLM no próximo turno (mesmo se for retry) decide o escalate.
        if tool_name == "safety_review_prescriptions" and result.ok:
            review = result.data or {}
            if review.get("requires_human_review"):
                # Auto-escala no MESMO turno pra não deixar cuidador
                # esperando se severidade for alta
                escalate_args = {
                    "phone": ctx.phone,
                    "caregiver_id": caregiver_id,
                    "patient_id": safe_args.get("patient_id"),
                    "reason": f"drug_safety_high_severity:{review.get('max_severity')}",
                    "summary": (
                        f"safety_review identificou max_severity="
                        f"{review.get('max_severity')}. "
                        f"Texto original: '{(ctx.inbound_text or '')[:300]}'"
                    ),
                    "drug_safety_findings": review,
                    "urgency": (
                        "P1" if review.get("max_severity") == "block"
                        else "P2"
                    ),
                    "conversation_log": list(ctx.active_context_messages or []),
                }
                escalate_result = execute_tool(
                    "escalate_to_human_clinical", escalate_args,
                    tenant_id=ctx.tenant.id,
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                )
                escalate_record = {
                    "name": "escalate_to_human_clinical",
                    "args": escalate_args,
                    "ok": escalate_result.ok,
                    "idempotent_skip": escalate_result.idempotent_skip,
                    "output": escalate_result.data,
                }
                if escalate_result.error:
                    escalate_record["error"] = escalate_result.error

                return AgentResponse(
                    text=(
                        text_after or
                        "Verifiquei aqui no nosso sistema farmacológico "
                        "e identifiquei pontos importantes. Vou pedir "
                        "o time clínico revisar antes de qualquer ação. "
                        "Te chamam em breve. 🙏"
                    ),
                    tools_called=[tool_call_record, escalate_record],
                    handoff_initiated=True,
                    handoff_reason="drug_safety_requires_review",
                    next_action="wait_human",
                    metadata={
                        "drug_safety_max_severity": review.get("max_severity"),
                        "auto_escalated": True,
                    },
                )

        # Caso normal: tool ok + sem escalate em cadeia
        return AgentResponse(
            text=text_after or "Anotei. Como o(a) idoso(a) está agora?",
            tools_called=[tool_call_record],
            handoff_initiated=(
                tool_name == "escalate_to_human_clinical"
                and result.ok and not result.idempotent_skip
            ),
            handoff_reason=safe_args.get("reason") if tool_name == "escalate_to_human_clinical" else None,
            next_action=(
                "wait_human" if tool_name == "escalate_to_human_clinical"
                and result.ok and not result.idempotent_skip
                else "wait_user"
            ),
            next_question_intent=next_q,
            metadata={
                "tool_executed": True,
                "tool_idempotent_skip": result.idempotent_skip,
            },
        )

    def _failsafe_escalate(
        self,
        ctx: AgentContext,
        *,
        reason: str,
        summary: str,
        urgency: str = "P2",
    ) -> AgentResponse:
        from src.services.sofia_tools import execute_tool
        caregiver_id = (
            ctx.identity_match.caregiver_id if ctx.identity_match else None
        )
        patient_id = self._get_patient_id_for_caregiver(caregiver_id)
        result = execute_tool(
            "escalate_to_human_clinical",
            {
                "phone": ctx.phone,
                "caregiver_id": caregiver_id,
                "patient_id": patient_id,
                "reason": reason,
                "summary": summary,
                "urgency": urgency,
                "conversation_log": list(ctx.active_context_messages or []),
            },
            tenant_id=ctx.tenant.id,
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )
        tool_call_record = {
            "name": "escalate_to_human_clinical",
            "args": {"reason": reason, "urgency": urgency},
            "ok": result.ok,
            "idempotent_skip": result.idempotent_skip,
            "output": result.data,
        }
        return AgentResponse(
            text=(
                "Recebi seu relato. Vou pedir o time clínico humano olhar "
                "com calma e te chamar em breve. 🙏"
            ),
            tools_called=[tool_call_record],
            handoff_initiated=result.ok and not result.idempotent_skip,
            handoff_reason=reason,
            next_action="wait_human",
            metadata={"failsafe_escalate": True, "reason": reason},
        )

    @staticmethod
    def _get_patient_id_for_caregiver(caregiver_id: Optional[str]) -> Optional[str]:
        """Resolve patient_id primary do caregiver. Best-effort."""
        if not caregiver_id:
            return None
        try:
            from src.services.postgres import get_postgres
            row = get_postgres().fetch_one(
                """SELECT patient_id::text AS patient_id
                   FROM aia_health_caregiver_patient_assignments
                   WHERE caregiver_id = %s AND active = TRUE
                   ORDER BY is_primary DESC, created_at ASC LIMIT 1""",
                (caregiver_id,),
            )
            return (row or {}).get("patient_id")
        except Exception:
            return None
