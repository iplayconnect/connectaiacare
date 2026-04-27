"""Dispatcher HTTP — mesma contract de voice-call-service.

POST /api/voice-call/dial { destination, scenario_*, patient_id, ... }
  1. Cria room LiveKit com metadata (system_prompt, contexto, etc)
  2. Dispatch explícito do agent worker pra essa room (agent_name=sofia-voice)
  3. Cria SIP participant outbound (LiveKit liga via trunk Flux)
  4. Retorna call_id = room.name

Permite o backend continuar chamando o mesmo endpoint — basta trocar a env
VOICE_BACKEND_URL pra apontar pra livekit-agent-service:5042 em vez de
voice-call-service:5040.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import structlog
from flask import Flask, jsonify, request
from livekit import api

logger = structlog.get_logger()

app = Flask(__name__)


# ════════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════════
LIVEKIT_URL = os.getenv("LIVEKIT_URL")  # ex https://...livekit.cloud
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# SIP trunk ID (criado uma vez na LiveKit Cloud, configurado pra falar com
# revendapbx.flux.net.br) — vem como env var.
LIVEKIT_OUTBOUND_TRUNK_ID = os.getenv("LIVEKIT_OUTBOUND_TRUNK_ID")

# Nome do agent worker que vai ser despachado pra room
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "sofia-voice")

# Prefixo do número (Flux pode exigir, ex 0 ou +55) — sem prefixo por default
SIP_DESTINATION_PREFIX = os.getenv("SIP_DESTINATION_PREFIX", "")


# ════════════════════════════════════════════════════════════════
# Health
# ════════════════════════════════════════════════════════════════
@app.get("/health")
def health():
    issues = []
    if not LIVEKIT_URL:
        issues.append("missing_LIVEKIT_URL")
    if not LIVEKIT_API_KEY:
        issues.append("missing_LIVEKIT_API_KEY")
    if not LIVEKIT_API_SECRET:
        issues.append("missing_LIVEKIT_API_SECRET")
    if not LIVEKIT_OUTBOUND_TRUNK_ID:
        issues.append("missing_LIVEKIT_OUTBOUND_TRUNK_ID")
    return jsonify({
        "status": "ok" if not issues else "degraded",
        "service": "livekit-agent-dispatcher",
        "config_issues": issues,
        "agent_name": AGENT_NAME,
    })


# ════════════════════════════════════════════════════════════════
# Dial endpoint — mesmo contract do voice-call-service
# ════════════════════════════════════════════════════════════════
@app.post("/api/voice-call/dial")
def dial():
    body = request.get_json(silent=True) or {}

    destination = body.get("destination")
    if not destination:
        return jsonify({"status": "error", "reason": "missing_destination"}), 400

    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET,
                LIVEKIT_OUTBOUND_TRUNK_ID]):
        return jsonify({
            "status": "error", "reason": "livekit_not_configured",
            "needs": ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
                      "LIVEKIT_OUTBOUND_TRUNK_ID"],
        }), 503

    full_name = body.get("full_name") or "amigo(a)"
    sofia_session_id = body.get("sofia_session_id") or str(uuid.uuid4())
    room_name = f"sofia-call-{sofia_session_id[:8]}-{int(datetime.now(timezone.utc).timestamp())}"

    metadata = {
        "destination": destination,
        "full_name": full_name,
        "patient_id": body.get("patient_id"),
        "user_id": body.get("user_id"),
        "tenant_id": body.get("tenant_id") or "connectaiacare_demo",
        "persona": body.get("persona"),
        "sofia_session_id": sofia_session_id,
        "scenario_id": body.get("scenario_id"),
        "scenario_code": body.get("scenario_code"),
        "system_prompt": body.get("scenario_system_prompt"),
        "voice": body.get("scenario_voice"),
        "allowed_tools": body.get("scenario_allowed_tools") or [],
        "extra_context": body.get("extra_context") or {},
    }

    sip_destination = f"{SIP_DESTINATION_PREFIX}{destination}"

    # asyncio.run pra rodar SDK async dentro de handler Flask sync
    try:
        result = asyncio.run(
            _create_room_and_dial(
                room_name=room_name,
                metadata=metadata,
                sip_destination=sip_destination,
                full_name=full_name,
            )
        )
    except Exception as e:
        logger.exception("dial_failed")
        return jsonify({
            "status": "error", "reason": "dial_exception",
            "error": str(e),
        }), 500

    return jsonify({
        "status": "ok",
        "call_id": room_name,
        "room_name": room_name,
        "sip_participant_identity": result["sip_participant_identity"],
        "scenario_code": body.get("scenario_code"),
    })


async def _create_room_and_dial(
    *,
    room_name: str,
    metadata: dict,
    sip_destination: str,
    full_name: str,
) -> dict:
    """Cria room + dispatch + SIP outbound via LiveKit API."""
    lkapi = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    try:
        # 1. Cria a room — Sofia entra antes do callee
        await lkapi.room.create_room(api.CreateRoomRequest(
            name=room_name,
            metadata=json.dumps(metadata, ensure_ascii=False),
            empty_timeout=300,        # 5min sem ninguém → kill
            max_participants=4,        # SIP + agent + (futuro: humano transfer)
            departure_timeout=20,
        ))

        # 2. Dispatch explícito do agent pra esta room
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=json.dumps(metadata, ensure_ascii=False),
            )
        )

        # 3. Cria SIP participant outbound — LiveKit disca via trunk
        sip_participant_identity = f"caller-{room_name[-8:]}"
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=LIVEKIT_OUTBOUND_TRUNK_ID,
                sip_call_to=sip_destination,
                room_name=room_name,
                participant_identity=sip_participant_identity,
                participant_name=full_name,
                # Opcional: timeout pra atender. Default 30s.
                # ringing_timeout, max_call_duration podem ser ajustados aqui
            )
        )
        logger.info(
            "livekit_dial_dispatched",
            room=room_name, sip_to=sip_destination,
        )
        return {"sip_participant_identity": sip_participant_identity}
    finally:
        await lkapi.aclose()


# ════════════════════════════════════════════════════════════════
# Hangup
# ════════════════════════════════════════════════════════════════
@app.post("/api/voice-call/hangup")
def hangup():
    body = request.get_json(silent=True) or {}
    call_id = body.get("call_id")
    if not call_id:
        return jsonify({"status": "error", "reason": "missing_call_id"}), 400

    try:
        asyncio.run(_delete_room(call_id))
    except Exception as e:
        return jsonify({"status": "error", "reason": "hangup_failed",
                        "error": str(e)}), 500
    return jsonify({"status": "ok", "call_id": call_id})


async def _delete_room(room_name: str) -> None:
    lkapi = api.LiveKitAPI(
        url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )
    try:
        await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
    finally:
        await lkapi.aclose()


@app.get("/api/voice-call/calls")
def list_active_calls():
    try:
        rooms = asyncio.run(_list_rooms())
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    return jsonify({
        "status": "ok",
        "calls": [
            {
                "room_name": r.name,
                "num_participants": r.num_participants,
                "created_at": r.creation_time,
                "metadata": json.loads(r.metadata) if r.metadata else {},
            }
            for r in rooms if r.name.startswith("sofia-call-")
        ],
    })


async def _list_rooms() -> list:
    lkapi = api.LiveKitAPI(
        url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )
    try:
        resp = await lkapi.room.list_rooms(api.ListRoomsRequest())
        return list(resp.rooms)
    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5042)
