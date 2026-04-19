"""ConnectaIACare — Flask app entrypoint."""
from flask import Flask, jsonify
from flask_cors import CORS

from config.settings import settings
from src.handlers.routes import bp as api_bp
from src.utils.logger import configure_logging, get_logger


def create_app() -> Flask:
    configure_logging()
    logger = get_logger(__name__)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key

    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)

    app.register_blueprint(api_bp)

    @app.get("/")
    def root():
        return jsonify(
            {
                "service": "ConnectaIACare API",
                "version": "0.1.0-mvp",
                "env": settings.env,
            }
        )

    logger.info("app_created", env=settings.env, debug=settings.debug)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5055, debug=settings.debug)
