"""BaseAgent — loop tool-use compartilhado.

Cada sub-agent (caregiver, family, ...) herda e define:
  PROMPT_FILE: nome do txt em prompts/
  ALLOWED_TOOL_NAMES: subset de tools (None = padrão por persona)
  TEMPERATURE / MAX_TOKENS / MODEL: tuning específico
  PERSONA: persona principal que esse agent atende
  GREETING: saudação inicial usada na FAB voz

Multi-agent dispatch (Sofia.3): orchestrator pode fan-out N agents em
paralelo e merge_responses. Hoje é 1 agent por turn.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import ClassVar

from src import persistence, tools as tools_module
from src.llm_client import GenerationResult, ToolDefinition, generate

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
DEFAULT_MODEL = os.getenv("SOFIA_LLM_MODEL", "gemini-3.1-flash")
MAX_TOOL_ROUNDS = 4


class BaseAgent:
    PERSONA: ClassVar[str] = "anonymous"
    PROMPT_FILE: ClassVar[str] = "sofia_platform.txt"
    ALLOWED_TOOL_NAMES: ClassVar[list[str] | None] = None  # None = todas da persona
    # NÃO há TEMPERATURE: Gemini 3 doc orienta usar default 1.0 (valores
    # baixos podem causar looping). Sub-agents controlam estilo via prompt.
    MAX_TOKENS: ClassVar[int] = 1024
    # thinking_level só vale na família 3 (preview). minimal|low|medium|high.
    # Saúde exige raciocínio: default medium garante respostas precisas
    # sem latência exagerada. ClinicalAgent sobe pra high; PatientAgent
    # cai pra low só pra latência soar natural ao idoso.
    THINKING_LEVEL: ClassVar[str] = "medium"
    MODEL: ClassVar[str | None] = None  # None = DEFAULT_MODEL
    GREETING: ClassVar[str] = "Oi! Sou a Sofia. Como posso te ajudar?"

    @classmethod
    def system_prompt(cls, persona_ctx: dict) -> str:
        base = (PROMPTS_DIR / "sofia_base.txt").read_text(encoding="utf-8").strip()
        persona_prompt = (PROMPTS_DIR / cls.PROMPT_FILE).read_text(encoding="utf-8").strip()
        name = persona_ctx.get("full_name") or "amigo(a)"
        ctx = f"\n\n# CONTEXTO DA SESSÃO\n- Persona: {persona_ctx.get('persona')}\n- Usuário: {name}"
        if persona_ctx.get("patient_id"):
            ctx += f"\n- Paciente vinculado: {persona_ctx['patient_id']}"
        if persona_ctx.get("partner_org"):
            ctx += f"\n- Organização parceira: {persona_ctx['partner_org']}"

        # Memória cross-session — carrega resumo + key_facts persistidos.
        # Late import pra evitar cycle import com llm_client.
        try:
            from src import memory_service
            memory = memory_service.load_user_memory(persona_ctx.get("user_id"))
            mem_block = memory_service.format_for_prompt(memory)
        except Exception:
            mem_block = ""

        # Active context cross-channel (últimos 45min de outros canais)
        try:
            from src import active_context
            ac_turns = active_context.get_recent_turns(persona_ctx=persona_ctx)
            ac_block = active_context.format_for_prompt(ac_turns)
        except Exception:
            ac_block = ""

        return f"{base}\n\n{persona_prompt}{ctx}{mem_block}{ac_block}"

    @classmethod
    def tool_definitions(cls, persona: str) -> list[ToolDefinition]:
        all_tools = tools_module.tools_for_persona(persona)
        if cls.ALLOWED_TOOL_NAMES is not None:
            allowed = set(cls.ALLOWED_TOOL_NAMES)
            all_tools = [t for t in all_tools if t["name"] in allowed]
        return [
            ToolDefinition(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
                handler=t["handler"],
            )
            for t in all_tools
        ]

    @classmethod
    def greet(cls, persona_ctx: dict) -> str:
        """Saudação personalizada. Usada pela FAB de voz no boot."""
        first_name = (persona_ctx.get("full_name") or "").split(" ")[0]
        return cls.GREETING.format(first_name=first_name or "amigo(a)")

    # ─── Loop principal ─────────────────────────────────────────

    @classmethod
    def run(
        cls,
        *,
        session_id: str,
        tenant_id: str,
        persona_ctx: dict,
        user_message: str,
    ) -> dict:
        persona = persona_ctx.get("persona") or "anonymous"
        system_prompt = cls.system_prompt(persona_ctx)
        tools = cls.tool_definitions(persona)
        model = cls.MODEL or DEFAULT_MODEL

        # Persiste a mensagem do user (1ª da turn)
        persistence.append_message(
            session_id=session_id,
            tenant_id=tenant_id,
            role="user",
            content=user_message,
        )
        # Active context cross-channel
        try:
            from src import active_context
            active_context.append_turn(
                persona_ctx=persona_ctx, role="user",
                content=user_message, channel="web",
            )
        except Exception:
            pass

        # Histórico recente (já inclui a que acabou de entrar)
        history = persistence.list_recent_messages(session_id, limit=30)
        history_serialized = cls._serialize_history(history)

        total_in = 0
        total_out = 0
        tool_calls = 0
        last_text = ""
        final_model = model

        for round_idx in range(MAX_TOOL_ROUNDS):
            result: GenerationResult = generate(
                system_prompt=system_prompt,
                messages=history_serialized,
                tools=tools,
                model=model,
                max_output_tokens=cls.MAX_TOKENS,
                thinking_level=cls.THINKING_LEVEL,
            )
            total_in += result.tokens_in
            total_out += result.tokens_out
            final_model = result.model
            last_text = result.text

            if not result.tool_calls:
                persistence.append_message(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    role="assistant",
                    content=last_text,
                    model=result.model,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                )
                # Active context cross-channel
                try:
                    from src import active_context
                    active_context.append_turn(
                        persona_ctx=persona_ctx, role="assistant",
                        content=last_text, channel="web",
                    )
                except Exception:
                    pass
                break

            # Executa cada tool e adiciona ao histórico como role=tool
            for call in result.tool_calls:
                tool_calls += 1
                name = call["name"]
                args = call.get("args") or {}
                output = tools_module.execute_tool(name, args, persona_ctx)

                persistence.append_message(
                    session_id=session_id,
                    tenant_id=tenant_id,
                    role="tool",
                    content=name,
                    tool_name=name,
                    tool_input=args,
                    tool_output=output,
                    model=result.model,
                )
                history_serialized.append({
                    "role": "tool",
                    "content": name,
                    "tool_name": name,
                    "tool_output": output,
                })
                persistence.audit(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    user_id=persona_ctx.get("user_id"),
                    persona=persona,
                    event_type="tool_call",
                    decision="allow" if output.get("ok") else "tool_error",
                    details={"tool": name, "args": args, "ok": output.get("ok")},
                )
        else:
            last_text = last_text or "Desculpa, ficou complicado aqui. Pode reformular?"
            persistence.append_message(
                session_id=session_id,
                tenant_id=tenant_id,
                role="assistant",
                content=last_text,
                model=final_model,
                metadata={"max_rounds_reached": True},
            )

        persistence.execute(
            "UPDATE aia_health_sofia_sessions SET last_active_at = NOW() WHERE id = %s",
            (session_id,),
        )

        # Atualiza memória cross-session se threshold atingido (best-effort)
        try:
            from src import memory_service
            memory_service.maybe_update_async(persona_ctx.get("user_id"))
        except Exception:
            pass

        persistence.record_usage(
            tenant_id=tenant_id,
            user_id=persona_ctx.get("user_id"),
            phone=persona_ctx.get("phone"),
            plan_sku=persona_ctx.get("plan_sku"),
            tokens_in=total_in,
            tokens_out=total_out,
            tool_calls=tool_calls,
            messages=1,
        )

        return {
            "text": last_text,
            "tokens_in": total_in,
            "tokens_out": total_out,
            "model": final_model,
            "tool_calls": tool_calls,
            "agent": cls.__name__,
        }

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _serialize_history(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            item = {"role": m.get("role"), "content": m.get("content") or ""}
            if m.get("role") == "tool":
                item["tool_name"] = m.get("tool_name")
                item["tool_output"] = m.get("tool_output")
            out.append(item)
        return out
