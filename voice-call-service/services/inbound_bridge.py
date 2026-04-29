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

        # Persona default: cuidador profissional. Sprint 2 vai resolver
        # via voice biometrics + plantão (já temos schema).
        persona_ctx = {
            "persona": "cuidador_pro",
            "user_id": None,
            "patient_id": None,
            "full_name": None,
            "tenant_id": Config.DEFAULT_TENANT,
            "phone": caller_phone,
            "scenario_code": "inbound_default",
            "scenario_system_prompt": (
                "Você atende ligações de cuidadores e pacientes da "
                "ConnectaIACare. Cumprimente brevemente, identifique-se "
                "como Sofia e pergunte em que pode ajudar. Seja calma, "
                "acolhedora e fale devagar."
            ),
            "scenario_voice": None,
            "scenario_allowed_tools": [],
            "extra_context": {"inbound": True, "caller_phone": caller_phone},
        }

        # Loop asyncio dedicado pra essa chamada
        loop = asyncio.new_event_loop()
        bridge_state = {
            "sip_call_id": call_id, "loop": loop,
            "grok": None, "caller_phone": caller_phone,
        }
        _active_inbound[call_id] = bridge_state

        def _run_loop():
            asyncio.set_event_loop(loop)
            try:
                sip.register_current_thread(f"grok-inbound-{call_id}")
            except Exception as exc:
                logger.warning("inbound_loop_register_failed: %s", exc)
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

        # Inicia Grok + dispara saudação (não esperamos CONFIRMED como
        # outbound — a chamada já está atendida quando o handler roda)
        fut_start = asyncio.run_coroutine_threadsafe(grok.start(), loop)
        try:
            fut_start.result(timeout=15)
            asyncio.run_coroutine_threadsafe(grok.start_kickoff(), loop)
        except Exception:
            logger.exception("inbound_grok_start_failed")
            return None, None

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
