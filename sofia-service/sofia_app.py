"""Sofia Care service — Flask app porta 5031.

Endpoints (chamados internamente pelo connectaiacare-api via rede Docker):

  GET  /health                    health check
  POST /sofia/chat                executa um turno (persona já injetada pelo proxy)
  POST /sofia/greeting            retorna saudação (sem chamar LLM)
  GET  /sofia/sessions/<id>       histórico
  GET  /sofia/usage               consumo do mês corrente
  POST /sofia/tts                 gera áudio do texto (Gemini TTS)

Auth: o sofia-service confia na rede Docker interna. Persona vem no body
do request, validada pelo proxy api antes (que aplicou JWT). Service-to-
service token simples via SOFIA_INTERNAL_KEY como segunda camada.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request

from src import orchestrator, persistence, tts_client

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sofia-service")

app = Flask(__name__)

INTERNAL_KEY = os.getenv("SOFIA_INTERNAL_KEY", "")


# ──── Collective Insights Scheduler ────
# Roda extração diária de padrões anonimizados das interações Sofia↔
# Profissional, gera knowledge_chunks com domain='collective_insight'.
# Lock advisory garante single-writer entre workers Gunicorn.
if os.getenv("ENABLE_COLLECTIVE_MEMORY", "true").lower() == "true":
    try:
        from src.collective_insights_scheduler import get_scheduler
        get_scheduler().start()
    except Exception as _exc:
        logger.warning("collective_insights_scheduler_failed_to_start: %s", _exc)


def _check_internal_auth() -> tuple | None:
    """Valida X-Internal-Key se configurado. Retorna (response, status) se falhar."""
    if not INTERNAL_KEY:
        return None  # Sem key configurada = sem check (dev)
    received = request.headers.get("X-Internal-Key", "")
    if received != INTERNAL_KEY:
        return jsonify({"status": "error", "reason": "internal_auth_failed"}), 401
    return None


def _persona_from_body() -> dict:
    body = request.get_json(silent=True) or {}
    ctx = body.get("persona") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    return ctx


# ════════════════════════════════════════════════════
# Health
# ════════════════════════════════════════════════════

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "sofia-care", "version": "0.2.0"})


# ════════════════════════════════════════════════════
# Chat — turno completo
# ════════════════════════════════════════════════════

@app.post("/sofia/chat")
def chat():
    err = _check_internal_auth()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"status": "error", "reason": "empty_message"}), 400
    if len(message) > 4000:
        return jsonify({"status": "error", "reason": "message_too_long"}), 400

    persona_ctx = _persona_from_body()
    if not persona_ctx.get("persona"):
        return jsonify({"status": "error", "reason": "missing_persona"}), 400

    channel = body.get("channel") or "web"
    try:
        result = orchestrator.handle_turn(
            persona_ctx=persona_ctx,
            user_message=message,
            channel=channel,
        )
    except Exception as exc:
        logger.exception("chat_failed")
        return jsonify({"status": "error", "reason": "internal_error", "detail": str(exc)}), 500

    return jsonify({
        "status": "ok",
        "sessionId": result["session_id"],
        "agent": result["agent"],
        "model": result["model"],
        "text": result["text"],
        "tokensIn": result["tokens_in"],
        "tokensOut": result["tokens_out"],
        "toolCalls": result["tool_calls"],
    })


# ════════════════════════════════════════════════════
# Greeting — sem LLM, só template
# ════════════════════════════════════════════════════

@app.post("/sofia/greeting")
def greeting():
    err = _check_internal_auth()
    if err:
        return err
    persona_ctx = _persona_from_body()
    text = orchestrator.initial_greeting(persona_ctx)
    return jsonify({"status": "ok", "text": text})


# ════════════════════════════════════════════════════
# Histórico
# ════════════════════════════════════════════════════

@app.get("/sofia/sessions/<session_id>")
def session_history(session_id: str):
    err = _check_internal_auth()
    if err:
        return err
    rows = persistence.list_recent_messages(session_id, limit=100)
    return jsonify({
        "status": "ok",
        "sessionId": session_id,
        "messages": [
            {
                "role": r["role"],
                "content": r.get("content"),
                "toolName": r.get("tool_name"),
                "toolOutput": r.get("tool_output"),
                "model": r.get("model"),
                "tokensIn": r.get("tokens_in"),
                "tokensOut": r.get("tokens_out"),
                "audioUrl": r.get("audio_url"),
                "createdAt": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    })


# ════════════════════════════════════════════════════
# Consumo
# ════════════════════════════════════════════════════

@app.post("/sofia/usage")
def usage():
    """POST porque persona vem no body (proxy injeta após validar JWT)."""
    err = _check_internal_auth()
    if err:
        return err
    persona_ctx = _persona_from_body()
    data = persistence.usage_for_user(
        tenant_id=persona_ctx.get("tenant_id") or "connectaiacare_demo",
        user_id=persona_ctx.get("user_id"),
        phone=persona_ctx.get("phone"),
    )
    return jsonify({"status": "ok", "usage": data})


# ════════════════════════════════════════════════════
# TTS — gera áudio
# ════════════════════════════════════════════════════

@app.post("/sofia/tts")
def tts():
    err = _check_internal_auth()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"status": "error", "reason": "empty_text"}), 400
    if len(text) > 1500:
        return jsonify({"status": "error", "reason": "text_too_long"}), 400
    voice = body.get("voice")

    try:
        out = tts_client.synthesize(text, voice=voice)
    except Exception as exc:
        logger.exception("tts_failed")
        return jsonify({"status": "error", "reason": "tts_failed", "detail": str(exc)}), 500

    return jsonify({
        "status": "ok",
        "audioBase64": out["audio_base64"],
        "mimeType": out["mime_type"],
        "durationSeconds": out["duration_seconds"],
        "model": out["model"],
        "voice": out["voice"],
    })


@app.post("/sofia/collective/trigger")
def collective_trigger():
    """Roda 1 ciclo de extração de insights coletivos sob demanda.
    Protegido por X-Internal-Key. Útil pra forçar fora do cron diário."""
    auth_err = _check_internal_auth()
    if auth_err:
        return auth_err
    from src import collective_memory_service
    try:
        stats = collective_memory_service.run_one_cycle()
    except Exception as exc:
        logger.exception("collective_trigger_failed")
        return jsonify({"status": "error", "reason": str(exc)}), 500
    return jsonify({"status": "ok", "stats": stats})


@app.get("/sofia/collective/status")
def collective_status():
    """Retorna métricas do último ciclo + contagens atuais."""
    auth_err = _check_internal_auth()
    if auth_err:
        return auth_err
    cursor = persistence.fetch_one(
        "SELECT * FROM aia_health_sofia_collective_cursor WHERE id = 1"
    )
    raw_stats = persistence.fetch_one(
        """SELECT COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE promoted) AS promoted,
                  COUNT(*) FILTER (WHERE NOT promoted AND frequency >= 3) AS pending_promote,
                  AVG(frequency)::float AS avg_freq,
                  MAX(frequency) AS max_freq
           FROM aia_health_sofia_collective_insights_raw"""
    )
    chunks_published = persistence.fetch_one(
        """SELECT COUNT(*) AS n FROM aia_health_knowledge_chunks
           WHERE domain = 'collective_insight' AND active = TRUE"""
    )
    return jsonify({
        "status": "ok",
        "cursor": cursor,
        "raw_insights": raw_stats,
        "chunks_published": (chunks_published or {}).get("n") or 0,
    })


@app.post("/sofia/tool/execute")
def sofia_tool_execute():
    """Executa uma tool do registry. Usado pelo voice-call-service pra
    delegar tools clínicas pesadas (motor de cruzamentos) sem duplicar
    código. Persona vem no body (não usa JWT — chamada interna)."""
    body = request.get_json(silent=True) or {}
    name = body.get("name") or ""
    args = body.get("args") or {}
    persona_ctx = body.get("persona") or {}
    if not name:
        return jsonify({"status": "error", "reason": "name_required"}), 400
    from src import tools as tools_module
    output = tools_module.execute_tool(name, args, persona_ctx)
    return jsonify({"status": "ok", "output": output})


@app.post("/sofia/memory/update")
def sofia_memory_update():
    """Força extração de memória cross-session pra um user_id.
    Chamado pelo voice-call-service no fim da chamada."""
    body = request.get_json(silent=True) or {}
    user_id = body.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "reason": "user_id_required"}), 400
    from src import memory_service
    try:
        result = memory_service.update_user_memory(user_id, force=True)
    except Exception as exc:
        logger.exception("memory_update_failed")
        return jsonify({"status": "error", "reason": str(exc)}), 500
    return jsonify({
        "status": "ok",
        "updated": bool(result),
        "summary_chars": len((result or {}).get("summary") or ""),
        "facts_keys": list(((result or {}).get("key_facts") or {}).keys()),
    })


@app.errorhandler(404)
def not_found(_):
    return jsonify({"status": "error", "reason": "not_found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5031, debug=False)
