"""Configuração central do ConnectaIACare backend.

Fail-closed em produção: se variáveis de segurança críticas não estiverem
configuradas corretamente, o processo não inicia. Ver SECURITY.md §7 e
docs/security_best_practices_report.md (FINDING-001, 002, 008).
"""
import os
import secrets
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


PRODUCTION_ENVS = {"production", "prod", "staging"}
MIN_SECRET_KEY_LENGTH = 32


@dataclass
class Settings:
    env: str = os.getenv("ENV", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    # Sem default de string fraca — dev autogenera em __post_init__, prod falha se vazio.
    secret_key: str = os.getenv("SECRET_KEY", "")

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/connectaiacare"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/5")

    evolution_api_url: str = os.getenv("EVOLUTION_API_URL", "")
    evolution_api_key: str = os.getenv("EVOLUTION_API_KEY", "")
    evolution_instance: str = os.getenv("EVOLUTION_INSTANCE", "v6")
    evolution_webhook_secret: str = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")

    # LLM provider: "anthropic" (default) | "gemini"
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic").lower()
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    # Gemini aceita tanto GOOGLE_API_KEY quanto GEMINI_API_KEY (convenção da comunidade)
    google_api_key: str = (
        os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or ""
    )
    deepgram_api_key: str = os.getenv("DEEPGRAM_API_KEY", "")

    sofia_voice_url: str = os.getenv("SOFIA_VOICE_API_URL", "")
    sofia_voice_key: str = os.getenv("SOFIA_VOICE_API_KEY", "")

    # MedMonitor / TotalCare API (ADR-019)
    # Base URL: https://<tenant>.contactto.care/agent
    # Fornecido pela Tecnosenior em 2026-04-20 (tenant vf-totalcare).
    medmonitor_api_url: str = os.getenv("MEDMONITOR_API_URL", "")
    medmonitor_api_key: str = os.getenv("MEDMONITOR_API_KEY", "")

    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:5055")
    # Sem default wildcard — dev auto-populado com localhost em __post_init__.
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    tenant_id: str = os.getenv("TENANT_ID", "connectaiacare_demo")

    @property
    def is_production(self) -> bool:
        return self.env.lower() in PRODUCTION_ENVS

    def __post_init__(self) -> None:
        """Validação fail-closed para produção.

        Em ambiente de desenvolvimento, aplica defaults seguros (secret autogerado,
        origins localhost) para facilitar onboarding. Em produção, erro abortivo se
        qualquer configuração de segurança estiver ausente ou fraca.
        """
        errors: list[str] = []

        if self.is_production:
            if self.debug:
                errors.append(
                    "DEBUG=true é proibido em produção (Werkzeug debugger = RCE). "
                    "Setar DEBUG=false no .env."
                )

            if not self.secret_key:
                errors.append(
                    "SECRET_KEY deve estar setado em produção. "
                    "Gerar com `openssl rand -hex 32` e colocar no .env."
                )
            elif self.secret_key.startswith("dev-"):
                errors.append(
                    "SECRET_KEY não pode começar com 'dev-' em produção."
                )
            elif len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
                errors.append(
                    f"SECRET_KEY deve ter ≥{MIN_SECRET_KEY_LENGTH} caracteres em produção "
                    f"(atual: {len(self.secret_key)}). Usar `openssl rand -hex 32`."
                )

            if not self.allowed_origins:
                errors.append(
                    "ALLOWED_ORIGINS deve ser uma lista explícita de origens em produção "
                    "(ex: 'https://care.connectaia.com.br,https://demo.connectaia.com.br')."
                )
            elif "*" in self.allowed_origins:
                errors.append(
                    "ALLOWED_ORIGINS não pode conter '*' em produção (incompatível com "
                    "CORS autenticado e superfície de ataque expandida)."
                )

            # Validar key do provider LLM ativo
            if self.llm_provider == "anthropic" and not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY obrigatório em produção (LLM_PROVIDER=anthropic).")
            elif self.llm_provider == "gemini" and not self.google_api_key:
                errors.append("GOOGLE_API_KEY obrigatório em produção (LLM_PROVIDER=gemini).")
            elif self.llm_provider not in ("anthropic", "gemini"):
                errors.append(f"LLM_PROVIDER='{self.llm_provider}' inválido. Use 'anthropic' ou 'gemini'.")

            if not self.deepgram_api_key:
                errors.append("DEEPGRAM_API_KEY obrigatório em produção.")
            if not self.evolution_api_key:
                errors.append("EVOLUTION_API_KEY obrigatório em produção.")
        else:
            # Dev conveniences: autogenera secret e CORS localhost se vazios.
            if not self.secret_key:
                self.secret_key = "dev-autogenerated-" + secrets.token_hex(16)
            if not self.allowed_origins:
                self.allowed_origins = (
                    "http://localhost:3000,http://localhost:3030,http://localhost:5055"
                )

        if errors:
            raise RuntimeError(
                "Configuração inválida para produção:\n  - " + "\n  - ".join(errors)
            )


settings = Settings()
