"""voice-call-service — entry point.

Inicializa PJSIP + Flask. Endpoints em /api/voice-call/* (atrás de
proxy do connectaiacare-api se exposto externamente).
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify

from config import Config
from services.sip_layer import SipLayer, _ensure_call_class

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("voice_call_app")

app = Flask(__name__)


@app.get("/health")
def health():
    sip = SipLayer.get()
    missing = Config.validate()
    return jsonify({
        "status": "ok" if not missing and sip._initialized else "degraded",
        "service": "voice-call-service",
        "sip_initialized": sip._initialized,
        "missing_config": missing,
    })


def _init_sip():
    """Inicializa PJSIP no boot. Requer SIP creds + PJSIP nativo instalado."""
    missing = Config.validate()
    if missing:
        logger.warning("config_missing_skipping_sip_init: %s", missing)
        return
    try:
        sip = SipLayer.get()
        if sip.initialize():
            _ensure_call_class()
            sip.install_gc_thread_guard()
            # Registra handler de chamada INBOUND. Sem isso, INVITEs
            # entrantes (alguém liga pro DID) caem em "no media handler"
            # e o trunk recebe 503/408 — Sofia não atende.
            from services.inbound_bridge import install_inbound_handler
            install_inbound_handler()
            logger.info("sip_layer_ready")
        else:
            logger.error("sip_layer_init_failed")
    except Exception:
        logger.exception("sip_init_error")


# Registra blueprints
from routes.dial import bp as dial_bp
app.register_blueprint(dial_bp, url_prefix="/api/voice-call")

# Boot SIP em background pra não bloquear health-check inicial
import threading
threading.Thread(target=_init_sip, daemon=True, name="sip-init").start()


# ─── Graceful shutdown ────────────────────────────────────────────
# Docker para o container com SIGTERM. Sem handler explícito, o
# gunicorn morre sem chamar sip.shutdown() → un-register não é
# enviado → Flux acumula "ghost registrations" (4+ contatos ativos
# da mesma linha, INVITE bate em ghosts mortos = "linha não atende").
import atexit
import signal


def _graceful_shutdown(*_args):
    try:
        SipLayer.get().shutdown()
        logger.info("sip_layer_shutdown_complete")
    except Exception:
        logger.exception("graceful_shutdown_error")


atexit.register(_graceful_shutdown)
signal.signal(signal.SIGTERM, lambda *_: (_graceful_shutdown(), sys.exit(0)))
signal.signal(signal.SIGINT, lambda *_: (_graceful_shutdown(), sys.exit(0)))


if __name__ == "__main__":
    # Em produção: gunicorn -w 1 voice_call_app:app
    # (1 worker pq PJSIP é singleton — múltiplos workers conflitariam no UDP)
    app.run(host="0.0.0.0", port=Config.HTTP_PORT, debug=False, threaded=True)
