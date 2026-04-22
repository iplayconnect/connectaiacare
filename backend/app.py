"""ConnectaIACare — Flask app entrypoint."""
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config.settings import settings
from src.handlers.routes import bp as api_bp
from src.handlers.teleconsulta_routes import bp as teleconsulta_bp
from src.utils.logger import configure_logging, get_logger


def create_app() -> Flask:
    configure_logging()
    logger = get_logger(__name__)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key

    # Limita tamanho de payload para mitigar DoS por body gigante (webhook, enrollment).
    # 20 MB é generoso para áudio WhatsApp (tipicamente < 1MB) e JSON grande.
    # Ver FINDING-005 do security audit.
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

    # ProxyFix: em produção rodamos atrás do Traefik. Sem ProxyFix, `request.remote_addr`
    # retorna o IP do proxy (não do cliente), quebrando o audit LGPD de consentimento.
    # x_for=1 assume um único proxy (Traefik). Se adicionarmos Cloudflare em frente
    # depois, subir para x_for=2.
    # Ver FINDING-003 do security audit (docs/security_best_practices_report.md).
    if settings.is_production:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )
        logger.info("proxy_fix_enabled", x_for=1)

    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    # supports_credentials desligado enquanto não implementamos cookie-based auth.
    # Auth futuro será JWT via Authorization header → credentials não aplicável.
    # Ao reativar cookies, revisitar SECURITY.md §3.1 (SameSite, Secure, HttpOnly).
    CORS(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=False,
    )

    app.register_blueprint(api_bp)
    app.register_blueprint(teleconsulta_bp)

    # Headers de segurança em todas as respostas.
    # Ver FINDING-006 do security audit.
    @app.after_request
    def add_security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        if settings.is_production:
            resp.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return resp

    # Error handler centralizado para 413 (Payload Too Large, MAX_CONTENT_LENGTH).
    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({"status": "error", "reason": "payload_too_large"}), 413

    @app.get("/")
    def root():
        return jsonify(
            {
                "service": "ConnectaIACare API",
                "version": "0.1.0-mvp",
                "env": settings.env,
            }
        )

    # Checkin Scheduler — worker background que dispara timeline de care events.
    # Concorrência: usa pg_try_advisory_lock para garantir single-writer entre workers.
    # Desabilitar em testes ou dev curto setando ENABLE_SCHEDULER=false.
    import os
    if os.getenv("ENABLE_SCHEDULER", "true").lower() == "true":
        try:
            from src.services.checkin_scheduler import get_scheduler
            get_scheduler().start()
            logger.info("checkin_scheduler_thread_started")
        except Exception as exc:
            logger.error("checkin_scheduler_failed_to_start", error=str(exc))

    logger.info("app_created", env=settings.env, debug=settings.debug)
    return app


app = create_app()


if __name__ == "__main__":
    # Dev only. Produção usa Gunicorn (ver Dockerfile).
    app.run(host="0.0.0.0", port=5055, debug=settings.debug)
