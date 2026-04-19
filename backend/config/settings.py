"""Configuração central do ConnectaIACare backend."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    env: str = os.getenv("ENV", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/connectaiacare"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/5")

    evolution_api_url: str = os.getenv("EVOLUTION_API_URL", "")
    evolution_api_key: str = os.getenv("EVOLUTION_API_KEY", "")
    evolution_instance: str = os.getenv("EVOLUTION_INSTANCE", "v6")

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")

    sofia_voice_url: str = os.getenv("SOFIA_VOICE_API_URL", "")
    sofia_voice_key: str = os.getenv("SOFIA_VOICE_API_KEY", "")

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:5055")
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "*")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    tenant_id: str = os.getenv("TENANT_ID", "connectaiacare_demo")


settings = Settings()
