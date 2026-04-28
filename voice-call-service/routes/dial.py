"""POST /dial — origina ligação e bridgea com Grok.

Body esperado:
{
  "destination": "5551996161700",       // número E.164 sem +
  "persona": "medico"|"enfermeiro"|...,  // qual persona da Sofia
  "user_id": "uuid",                     // user que iniciou (pra memory)
  "patient_id": "uuid",                  // opcional — paciente alvo da call
  "full_name": "Dr. Alexandre",          // pra cumprimento
  "tenant_id": "connectaiacare_demo"
}

Fluxo:
1. Cria GrokCallSession + conecta WS xAI
2. Chama SipLayer.dial() — começa o INVITE
3. Cada frame inbound (PJSIP onFrameReceived) → upsample 8k→24k → grok.feed_audio_24k
4. Cada chunk outbound (grok callback) → downsample 24k→8k → SipLayer.push_audio_8k
5. Bridge fecha quando: user desliga (PJSIP DISCONNECTED) OU /hangup OU Grok cair
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

from config import Config
from services.audio_bridge import upsample_8k_to_24k, downsample_24k_to_8k
from services.grok_call_session import GrokCallSession
from services.sip_layer import SipLayer, _ensure_call_class

logger = logging.getLogger("dial_route")
bp = Blueprint("dial", __name__)

# Pool de event loops async — cada call roda num loop dedicado num thread
_executor = ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_CALLS)
# call_id → bridge state
_active_calls: dict[str, dict] = {}


@bp.post("/dial")
def dial():
    body = request.get_json(silent=True) or {}
    destination = (body.get("destination") or "").strip()
    if not destination:
        return jsonify({"status": "error", "reason": "destination_required"}), 400

    persona_ctx = {
        "persona": body.get("persona") or "anonymous",
        "user_id": body.get("user_id"),
        "patient_id": body.get("patient_id"),
        "full_name": body.get("full_name"),
        "tenant_id": body.get("tenant_id") or Config.DEFAULT_TENANT,
        "phone": destination,
        # Scenario overrides (vem do /api/communications/dial do backend)
        "scenario_code": body.get("scenario_code"),
        "scenario_system_prompt": body.get("scenario_system_prompt"),
        "scenario_voice": body.get("scenario_voice"),
        "scenario_allowed_tools": body.get("scenario_allowed_tools") or [],
        "extra_context": body.get("extra_context") or {},
    }

    sip = SipLayer.get()
    if not sip._initialized:
        return jsonify({"status": "error", "reason": "sip_not_ready"}), 503

    # Cria event loop dedicado em thread separado (PJSIP roda em outro thread,
    # vamos pingponguear áudio entre eles)
    loop = asyncio.new_event_loop()
    bridge_state = {"sip_call_id": None, "loop": loop, "grok": None}

    def _run_loop():
        asyncio.set_event_loop(loop)
        # CRÍTICO: registra esta thread no pjlib antes de processar
        # qualquer evento. Sem isso, callbacks que tocam pjlib (drain
        # quando VAD detecta interrupção, hangup quando Grok fecha)
        # disparam assertion fatal e o container morre.
        # Bug observado em produção 27/04 e 28/04: chamada cai logo
        # após o usuário começar a falar pela 1ª vez.
        try:
            sip.register_current_thread("grok-asyncio-loop")
        except Exception as exc:
            logger.warning("loop_thread_register_failed: %s", exc)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()

    async def _on_audio_out_from_grok(pcm16_24k: bytes):
        """Sofia falou — bota no telefone do paciente."""
        if not bridge_state["sip_call_id"]:
            return
        pcm_8k = downsample_24k_to_8k(pcm16_24k)
        sip.push_audio_8k(bridge_state["sip_call_id"], pcm_8k)

    def _on_user_interrupt():
        """Usuário começou a falar — dropa qualquer áudio bufferizado da
        Sofia pra ela calar a boca IMEDIATAMENTE no telefone."""
        if not bridge_state["sip_call_id"]:
            return
        n = sip.drain_outbound_audio(bridge_state["sip_call_id"])
        if n:
            logger.info(
                "interrupt_drained call_id=%s bytes=%d",
                bridge_state["sip_call_id"], n,
            )

    grok = GrokCallSession(
        persona_ctx=persona_ctx,
        on_audio_chunk_24k=_on_audio_out_from_grok,
        on_user_interrupt=_on_user_interrupt,
    )
    bridge_state["grok"] = grok

    # Inicia Grok primeiro (precisa estar pronto pra receber áudio)
    fut = asyncio.run_coroutine_threadsafe(grok.start(), loop)
    try:
        fut.result(timeout=15)
    except Exception as exc:
        logger.exception("grok_start_failed")
        loop.call_soon_threadsafe(loop.stop)
        return jsonify({"status": "error", "reason": "grok_start_failed", "detail": str(exc)}), 500

    def _on_audio_in_from_sip(pcm16_8k: bytes):
        """Paciente falou no telefone — manda pra Sofia (Grok)."""
        if not pcm16_8k:
            return
        pcm_24k = upsample_8k_to_24k(pcm16_8k)
        asyncio.run_coroutine_threadsafe(grok.feed_audio_24k(pcm_24k), loop)

    def _on_call_state(call_id: str, state: str):
        logger.info("dial_state call_id=%s state=%s", call_id, state)
        if state == "CONFIRMED":
            # Paciente atendeu — Sofia pode falar agora
            asyncio.run_coroutine_threadsafe(grok.start_kickoff(), loop)
        elif state in ("DISCONNECTED", "DISCONNCTD"):
            # Marca razão do disconnect pra UI ler depois (active-calls)
            ctx = _active_calls.get(call_id)
            if ctx:
                # Se nunca atendeu (sem CONFIRMED), provavelmente foi
                # bloqueado pelo trunk OU número não atendeu
                ctx["disconnected_at"] = call_id
            # Encerra Grok + para o loop
            asyncio.run_coroutine_threadsafe(grok.close(), loop)
            loop.call_later(2, loop.stop)
            _active_calls.pop(call_id, None)

    try:
        sip_call_id = sip.dial(
            destination=destination,
            on_audio_in=_on_audio_in_from_sip,
            on_call_state=_on_call_state,
        )
    except Exception as exc:
        logger.exception("sip_dial_failed")
        asyncio.run_coroutine_threadsafe(grok.close(), loop)
        loop.call_soon_threadsafe(loop.stop)
        return jsonify({"status": "error", "reason": "sip_dial_failed", "detail": str(exc)}), 500

    bridge_state["sip_call_id"] = sip_call_id
    _active_calls[sip_call_id] = bridge_state
    return jsonify({"status": "ok", "call_id": sip_call_id})


@bp.post("/hangup")
def hangup():
    body = request.get_json(silent=True) or {}
    call_id = (body.get("call_id") or "").strip()
    if not call_id:
        return jsonify({"status": "error", "reason": "call_id_required"}), 400
    state = _active_calls.pop(call_id, None)
    if not state:
        return jsonify({"status": "error", "reason": "call_not_found"}), 404
    SipLayer.get().hangup(call_id)
    grok = state.get("grok")
    loop = state.get("loop")
    if grok and loop:
        asyncio.run_coroutine_threadsafe(grok.close(), loop)
        loop.call_later(2, loop.stop)
    return jsonify({"status": "ok"})


@bp.get("/calls")
def list_active_calls():
    return jsonify({
        "status": "ok",
        "active_count": len(_active_calls),
        "calls": list(_active_calls.keys()),
    })
