"""ConnectaIACare — Flask app entrypoint."""
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config.settings import settings
from src.handlers.alerts_routes import bp as alerts_bp
from src.handlers.auth_routes import (
    authenticate_request,
    bp as auth_bp,
    is_public_path,
)
from src.handlers.caregivers_routes import bp as caregivers_bp
from src.handlers.disease_routes import bp as disease_bp
from src.handlers.medication_routes import bp as medication_bp
from src.handlers.onboarding_web_routes import bp as onboarding_web_bp
from src.handlers.patient_portal_routes import bp as patient_portal_bp
from src.handlers.profiles_routes import bp as profiles_bp
from src.handlers.routes import bp as api_bp
from src.handlers.sofia_routes import bp as sofia_bp
from src.handlers.teleconsulta_routes import bp as teleconsulta_bp
from src.handlers.users_routes import bp as users_bp
from src.handlers.voip_routes import bp as voip_bp
from src.handlers.weekly_report_routes import bp as weekly_report_bp
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(profiles_bp)
    app.register_blueprint(sofia_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(teleconsulta_bp)
    app.register_blueprint(patient_portal_bp)
    app.register_blueprint(disease_bp)
    app.register_blueprint(weekly_report_bp)
    app.register_blueprint(medication_bp)
    app.register_blueprint(onboarding_web_bp, url_prefix="/api")
    app.register_blueprint(voip_bp, url_prefix="/api")
    app.register_blueprint(caregivers_bp, url_prefix="/api")
    app.register_blueprint(alerts_bp, url_prefix="/api")

    # JWT middleware: protege /api/* exceto rotas públicas (auth, webhook,
    # portal do paciente com PIN, onboarding B2C).
    # Default DESLIGADO durante a migração de páginas SSR (que fazem fetch
    # server-side sem injetar Bearer) para client fetch. O middleware Next.js
    # do frontend já bloqueia o acesso de não-autenticados.
    # Ligar com AUTH_ENFORCE=true quando todas as páginas tiverem migrado.
    import os
    auth_enforce = (os.getenv("AUTH_ENFORCE", "false").lower() == "true")

    @app.before_request
    def _enforce_auth():
        if request.method == "OPTIONS":
            return None
        path = request.path
        if not path.startswith("/api/"):
            return None
        if is_public_path(path):
            return None
        # Sempre tenta autenticar pra popular g.user — decoradores
        # @require_role / @require_permission em endpoints específicos
        # dependem de g.user existir. Só BLOQUEIA o request quando
        # AUTH_ENFORCE=true; com false, segue sem g.user (rotas legadas
        # continuam abertas, mas /api/users etc. exigem token via decorator).
        payload, err = authenticate_request()
        if err and auth_enforce:
            return err
        if payload:
            g.user = payload
        return None

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

    # Auto-seed: cria super_admin (Alexandre) + parceiro (Murilo) se vars setadas.
    # Idempotente — skip se já existir. Roda em todo startup.
    if os.getenv("AUTH_SEED_ON_STARTUP", "true").lower() == "true":
        try:
            from src.services import user_service
            user_service.ensure_seed_users()
        except Exception as exc:
            logger.error("auth_seed_failed", error=str(exc))

    # Checkin Scheduler — worker background que dispara timeline de care events.
    # Concorrência: usa pg_try_advisory_lock para garantir single-writer entre workers.
    # Desabilitar em testes ou dev curto setando ENABLE_SCHEDULER=false.
    if os.getenv("ENABLE_SCHEDULER", "true").lower() == "true":
        try:
            from src.services.checkin_scheduler import get_scheduler
            get_scheduler().start()
            logger.info("checkin_scheduler_thread_started")
        except Exception as exc:
            logger.error("checkin_scheduler_failed_to_start", error=str(exc))

    # Proactive Scheduler — disparo de check-ins B2C, lembretes, relatórios
    # (independente de care_events). Lock advisory próprio pra não conflitar
    # com o checkin_scheduler.
    if os.getenv("ENABLE_PROACTIVE_SCHEDULER", "true").lower() == "true":
        try:
            from src.services.proactive_scheduler import get_proactive_scheduler
            get_proactive_scheduler().start()
            logger.info("proactive_scheduler_thread_started")
        except Exception as exc:
            logger.error("proactive_scheduler_failed_to_start", error=str(exc))

    logger.info("app_created", env=settings.env, debug=settings.debug)
    return app


app = create_app()


if __name__ == "__main__":
    # Dev only. Produção usa Gunicorn (ver Dockerfile).
    app.run(host="0.0.0.0", port=5055, debug=settings.debug)
