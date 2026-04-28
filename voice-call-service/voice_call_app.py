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
            # Instala guard anti-crash: registra thread atual no pjlib
            # antes de cada GC sweep, prevenindo SIGABRT quando Python
            # libera objetos pjsua2 em threads Werkzeug aleatórias.
            sip.install_gc_thread_guard()
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


if __name__ == "__main__":
    # Em produção: gunicorn -w 1 voice_call_app:app
    # (1 worker pq PJSIP é singleton — múltiplos workers conflitariam no UDP)
    app.run(host="0.0.0.0", port=Config.HTTP_PORT, debug=False, threaded=True)
