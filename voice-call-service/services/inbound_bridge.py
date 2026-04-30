"""Inbound bridge — quando alguém liga PRA o nosso DID, criamos
GrokCallSession + bridge igual ao outbound.

Reusa pattern do routes/dial.py mas é registrado uma vez no boot
(em voice_call_app) ao invés de spawn por request HTTP.
"""
from __future__ import annotations

import asyncio
import logging
import threading

from config import Config
from services.audio_bridge import upsample_8k_to_24k, downsample_24k_to_8k
from services.grok_call_session import GrokCallSession
from services.sip_layer import SipLayer

logger = logging.getLogger("inbound_bridge")

# call_id → bridge state (igual _active_calls do dial.py — mas separado
# porque inbound não passa pelo /dial endpoint)
_active_inbound: dict[str, dict] = {}


def install_inbound_handler() -> None:
    """Registra o handler de chamada inbound no SipLayer.

    Chamado uma vez pelo voice_call_app no boot. Quando alguém ligar
    pro nosso DID, SipLayer._handle_incoming_call → este handler.
    """
    sip = SipLayer.get()

    def _handler(caller_phone: str, call_id: str, pj_call):
        """Sofia atendendo. Cria Grok session e retorna callbacks de
        áudio que SipLayer vai disparar conforme o pjsua entrega frames.
        """
        logger.info(
            "inbound_handler_started caller=%s call_id=%s",
            caller_phone, call_id,
        )

        # Resolve quem está ligando — busca em caregivers, users e
        # patients pelo phone. Sem isso a Sofia atende em branco
        # (sem memória/contexto), o que mata o valor da plataforma.
        from services.caller_resolver import resolve_caller
        try:
            resolved = resolve_caller(caller_phone, Config.DEFAULT_TENANT)
        except Exception as exc:
            logger.warning("caller_resolve_failed: %s", exc)
            resolved = {
                "patient_id": None, "caregiver_id": None,
                "user_id": None, "full_name": "",
                "persona": "anonymous", "phone_type": "unknown",
                "extra_context": {},
            }

        first_name = (resolved["full_name"] or "").split(" ")[0]

        # System prompt enriquecido: a base é injection-friendly,
        # GrokCallSession.start() vai automaticamente acrescentar
        # _load_memory_block(user_id) + _load_active_context_block
        # + patient context quando scenario_system_prompt está setado.
        if resolved["persona"] == "cuidador_pro":
            base_prompt = (
                "Você é a Sofia, assistente de IA da ConnectaIACare. "
                "Está atendendo uma ligação de um CUIDADOR PROFISSIONAL "
                f"({resolved['full_name'] or 'cuidador(a)'}). Seja "
                "técnica, direta e ágil — cuidador costuma ter pressa. "
                "Aceite termos médicos. Pergunte sobre qual paciente é "
                "o relato se necessário. Use as ferramentas disponíveis "
                "(get_patient_summary, query_drug_rules, create_care_event, "
                "escalate_to_attendant) quando apropriado."
            )
        elif resolved["persona"] == "familia":
            base_prompt = (
                "Você é a Sofia, assistente de IA da ConnectaIACare. "
                "Está atendendo uma ligação de um FAMILIAR "
                f"({resolved['full_name'] or 'familiar'}) "
                "do paciente. Seja acolhedora, empática, mais "
                "explicativa. Foco em passar tranquilidade e atualizar "
                "sobre o estado geral. Quando apropriado, consulte "
                "get_patient_summary pra dar contexto preciso."
            )
        elif resolved["persona"] == "paciente_b2c":
            base_prompt = (
                "Você é a Sofia, assistente de IA da ConnectaIACare. "
                f"Está atendendo o paciente {resolved['full_name']} "
                "diretamente (B2C, idoso solo). Use linguagem MUITO "
                "simples, fale devagar, frases curtas. Se mencionar "
                "dor ou sintoma grave, pergunte se quer falar com humano "
                "(escalate_to_attendant). Tom acolhedor e calmo."
            )
        elif resolved["persona"] in ("medico", "enfermeiro", "admin_tenant"):
            base_prompt = (
                "Você é a Sofia. Está atendendo um profissional clínico "
                f"({resolved['persona']}: {resolved['full_name']}). "
                "Aceite linguagem técnica, seja objetiva. Tools clínicas "
                "completas disponíveis."
            )
        elif resolved["persona"] == "comercial":
            # Phone NÃO cadastrado — é um lead em potencial. Sofia
            # precisa apresentar a plataforma e qualificar.
            base_prompt = (
                "Você é a Sofia, assistente de IA comercial da "
                "ConnectaIACare. Você acabou de receber uma ligação de "
                "alguém que NÃO é cliente cadastrado — provavelmente é "
                "um lead querendo conhecer a plataforma.\n\n"
                "## SEU OBJETIVO NESTA LIGAÇÃO\n"
                "Em UMA ligação curta (3-5 minutos):\n"
                "1. Cumprimente, identifique-se como Sofia da "
                "ConnectaIACare.\n"
                "2. Pergunte com quem está falando (nome) e o motivo do "
                "contato.\n"
                "3. Identifique o PERFIL do lead — é dono(a)/gestor(a) de "
                "lar de idosos? Médico(a)? Familiar de idoso? Cuidador "
                "particular? Empresa parceira?\n"
                "4. Apresente a ConnectaIACare em 2-3 frases adaptadas "
                "ao perfil dele(a).\n"
                "5. Capte: nome completo, telefone (já tem mas confirme), "
                "e-mail, papel/empresa, e qual problema específico ele(a) "
                "está tentando resolver.\n"
                "6. NUNCA prometa preço fechado. Diga que vai passar pro "
                "time comercial entrar em contato em até 24 horas com "
                "proposta personalizada.\n"
                "7. Use a tool 'escalate_to_attendant' no FIM passando "
                "como reason='lead_comercial_qualificado' e summary "
                "contendo TUDO que captou (nome, contato, perfil, dor). "
                "Isso registra o lead no CRM e dispara aviso pro time.\n\n"
                "## SOBRE A CONNECTAIACARE (use apenas o que for "
                "relevante pro perfil do lead)\n"
                "Plataforma de IA + atendimento humano 24x7 pra cuidados "
                "de idosos. Sofia (você) é a IA que conversa com cuidadores "
                "via WhatsApp e voz, classifica relatos clínicos, valida "
                "doses de medicamentos contra Beers/RENAME 2024, detecta "
                "interações, dispara alertas críticos pra equipe humana, "
                "integra com plataformas de prontuário (Tecnosenior/TotalCare). "
                "Hoje serve ~900 usuários ativos.\n\n"
                "## REGRAS DE TOM\n"
                "- Você é COMERCIAL, mas NÃO insistente. Se a pessoa "
                "quiser desligar, agradeça.\n"
                "- Não entre em detalhes técnicos profundos — passe a "
                "humano se ele insistir em técnica.\n"
                "- NUNCA invente preço, prazo de implantação ou feature.\n"
                "- Se a pessoa pedir pra falar com humano agora, escalate "
                "imediatamente.\n"
                "- Tom: profissional, acolhedor, brasileiro coloquial."
            )
        else:
            base_prompt = (
                "Você é a Sofia, assistente de IA da ConnectaIACare. "
                "Está atendendo uma ligação. Cumprimente brevemente, "
                "pergunte com quem está falando e como pode ajudar. "
                "Tom acolhedor."
            )

        persona_ctx = {
            "persona": resolved["persona"],
            "user_id": resolved["user_id"],
            "patient_id": resolved["patient_id"],
            "caregiver_id": resolved["caregiver_id"],
            "full_name": resolved["full_name"] or first_name or "amigo(a)",
            "tenant_id": Config.DEFAULT_TENANT,
            "phone": caller_phone,
            "scenario_code": "inbound_resolved",
            "scenario_system_prompt": base_prompt,
            "scenario_voice": None,
            "scenario_allowed_tools": None,  # None = todas permitidas pra persona
            "extra_context": {
                "inbound": True,
                "caller_phone": caller_phone,
                "phone_type": resolved.get("phone_type"),
                **resolved.get("extra_context", {}),
            },
        }
        logger.info(
            "inbound_persona_ctx persona=%s user_id=%s patient_id=%s "
            "caregiver_id=%s name=%s",
            persona_ctx["persona"], persona_ctx["user_id"],
            persona_ctx["patient_id"], persona_ctx.get("caregiver_id"),
            persona_ctx["full_name"],
        )

        # Loop asyncio dedicado pra essa chamada.
        # IMPORTANTE: NÃO registrar essa thread no pjlib via
        # libRegisterThread. Histórico (29/04): SIGABRT em
        # grp_lock_set_owner_thread durante call.answer() — registrar
        # thread externa cria descriptor que sobrescreve o owner do
        # group lock; quando a thread INTERNA do pjsua (que processou
        # onIncomingCall) tenta operar o lock, owner mismatch → assert.
        # As operações que o asyncio loop faz (push_audio_8k,
        # drain_outbound_audio) NÃO tocam pjlib — só manipulam buffers
        # bytearray thread-safe. libRegisterThread era desnecessário.
        loop = asyncio.new_event_loop()
        bridge_state = {
            "sip_call_id": call_id, "loop": loop,
            "grok": None, "caller_phone": caller_phone,
        }
        _active_inbound[call_id] = bridge_state

        def _run_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        threading.Thread(
            target=_run_loop, daemon=True, name=f"inbound-loop-{call_id}",
        ).start()

        async def _on_audio_out_from_grok(pcm16_24k: bytes):
            if not bridge_state["sip_call_id"]:
                return
            pcm_8k = downsample_24k_to_8k(pcm16_24k)
            sip.push_audio_8k(bridge_state["sip_call_id"], pcm_8k)

        def _on_user_interrupt():
            if not bridge_state["sip_call_id"]:
                return
            n = sip.drain_outbound_audio(bridge_state["sip_call_id"])
            if n:
                logger.info(
                    "inbound_interrupt_drained call_id=%s bytes=%d",
                    bridge_state["sip_call_id"], n,
                )

        grok = GrokCallSession(
            persona_ctx=persona_ctx,
            on_audio_chunk_24k=_on_audio_out_from_grok,
            on_user_interrupt=_on_user_interrupt,
        )
        bridge_state["grok"] = grok

        # IMPORTANTE: NÃO bloquear esta thread esperando grok.start().
        # Esta thread É a worker interna do pjsua que processou
        # onIncomingCall. Bloquear aqui (fut.result(timeout=15)) trava
        # ela enquanto pjsua precisa dela pra outros callbacks da
        # mesma chamada (ex: onCallMediaState após SDP) — quando
        # pjsua tenta operar group lock dessa chamada de outra
        # worker, owner mismatch → SIGABRT em
        # grp_lock_set_owner_thread (lock.c:270).
        # Fix: schedular start+kickoff async sem aguardar. Erros
        # vão ser logados mas a thread retorna imediatamente.
        async def _start_then_kickoff():
            try:
                await grok.start()
                await grok.start_kickoff()
            except Exception as exc:
                logger.exception("inbound_grok_start_failed: %s", exc)

        asyncio.run_coroutine_threadsafe(_start_then_kickoff(), loop)

        def _on_audio_in_from_sip(pcm16_8k: bytes):
            if not pcm16_8k:
                return
            pcm_24k = upsample_8k_to_24k(pcm16_8k)
            asyncio.run_coroutine_threadsafe(grok.feed_audio_24k(pcm_24k), loop)

        def _on_call_state(local_id: str, state: str):
            logger.info(
                "inbound_state call_id=%s state=%s", local_id, state,
            )
            if state in ("DISCONNECTED", "DISCONNCTD"):
                # Memory writeback — extrai aprendizado da conversa
                # pra o user continuar sendo "lembrado" no chat/whatsapp
                # depois (cross-channel context da Sofia).
                user_id = persona_ctx.get("user_id")
                if user_id:
                    try:
                        from services.persistence import update_user_memory_force
                        update_user_memory_force(user_id)
                    except Exception as exc:
                        logger.warning("memory_writeback_failed: %s", exc)
                asyncio.run_coroutine_threadsafe(grok.close(), loop)
                loop.call_later(2, loop.stop)
                _active_inbound.pop(local_id, None)

        return _on_audio_in_from_sip, _on_call_state

    sip.register_on_incoming_call(_handler)
    logger.info("inbound_handler_registered")


def list_active_inbound() -> dict:
    return {
        "active_count": len(_active_inbound),
        "calls": [
            {"call_id": cid, "caller_phone": st.get("caller_phone")}
            for cid, st in _active_inbound.items()
        ],
    }
