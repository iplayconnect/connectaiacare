"""voice-call-service — configuração via env vars.

Reusa credenciais SIP da conta `5130624656@revendapbx.flux.net.br` da outra
plataforma na fase 1 — se houver conflito de chamadas simultâneas, pedir
sub-ramal próprio ao operador.
"""
import os


class Config:
    # ─── HTTP server ───
    HTTP_PORT = int(os.getenv("VOICE_CALL_HTTP_PORT", "5040"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # ─── SIP / Trunk ───
    SIP_DOMAIN = os.getenv("VOIP_SIP_DOMAIN", "revendapbx.flux.net.br")
    SIP_PORT = int(os.getenv("VOIP_SIP_PORT", "5060"))
    # Porta SIP que pjsua escuta DENTRO do container. Fixa (não ephemeral)
    # pra que o Contact anunciado seja estável entre rebuilds e o Flux
    # não acumule "ghost registrations" (4+ contatos da mesma linha).
    SIP_LISTEN_PORT = int(os.getenv("VOICE_SIP_LISTEN_PORT", "5060"))
    # Porta externa mapeada pelo docker-compose (5061 host → 5060
    # container). Anunciada no Contact via tp_cfg.publicAddress pra que
    # INVITE inbound da Flux chegue até a borda Docker.
    SIP_PUBLIC_PORT = int(os.getenv("VOICE_SIP_PUBLIC_PORT", "5061"))
    SIP_TRANSPORT = os.getenv("VOIP_SIP_TRANSPORT", "UDP")
    SIP_USER = os.getenv("VOIP_SIP_USER", "")
    SIP_PASSWORD = os.getenv("VOIP_SIP_PASSWORD", "")
    # Caller ID a aparecer no destinatário. Pode ser diferente do SIP_USER:
    # nVoip exige que seja um Número Virtual (DID) alocado à conta — auth
    # é feita pelo SIP_USER, mas o From/CID precisa ser o DID. Default
    # vazio = usa SIP_USER (Flux aceita).
    SIP_CALLER_ID = os.getenv("VOIP_SIP_CALLER_ID", "")
    # IP público do host (Docker está atrás de NAT bridge). Anunciado no
    # SDP/Contact pra que RTP de retorno chegue. Sem isso pjsua anuncia
    # 172.x interno → trunk envia RTP pra IP errado → áudio inbound zera.
    PUBLIC_IP = os.getenv("VOIP_PUBLIC_IP", "")
    # Faixa RTP DIFERENTE do voip-service (10000-10100) pra evitar conflito
    RTP_PORT_MIN = int(os.getenv("VOICE_RTP_PORT_MIN", "10500"))
    RTP_PORT_MAX = int(os.getenv("VOICE_RTP_PORT_MAX", "10600"))
    # PCMU (G.711 µ-law 8k) é universal — funciona com qualquer trunk BR.
    CODEC_PRIORITY = os.getenv("VOICE_CODEC_PRIORITY", "PCMU,PCMA")
    MAX_CONCURRENT_CALLS = int(os.getenv("VOICE_MAX_CONCURRENT_CALLS", "5"))
    REGISTRATION_INTERVAL = int(os.getenv("VOICE_REGISTRATION_INTERVAL", "300"))

    # ─── Grok Realtime (xAI) ───
    XAI_API_KEY = os.getenv("XAI_API_KEY", "")
    GROK_REALTIME_URL = os.getenv(
        "GROK_REALTIME_URL", "wss://api.x.ai/v1/realtime"
    )
    GROK_VOICE_MODEL = os.getenv(
        "SOFIA_GROK_VOICE_MODEL", "grok-voice-think-fast-1.0"
    )
    GROK_VOICE_NAME = os.getenv("SOFIA_GROK_VOICE", "ara")

    # ─── DB (mesmo PG do api/sofia-service) ───
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/connectaiacare",
    )

    # ─── Sofia API HTTP (pra chamar tools/memory caso quisermos via REST
    # em vez de DB direto — opcional, primeira versão usa DB direto) ───
    SOFIA_SERVICE_URL = os.getenv("SOFIA_SERVICE_URL", "http://sofia-service:5031")
    BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://api:5055")

    # ─── Tenant default + audio specs ───
    DEFAULT_TENANT = os.getenv("VOICE_DEFAULT_TENANT", "connectaiacare_demo")
    SIP_AUDIO_RATE = 8000      # PCMU/PCMA mono 8kHz, sempre
    GROK_AUDIO_RATE = 24000    # PCM16 mono 24kHz, sempre

    # ─── Fallback se Grok cair ───
    # Mensagem TTS pré-gravada (gerar via Gemini TTS uma vez e salvar
    # em /app/storage/grok_failure_pt.wav). NA FASE 1 a mensagem é só
    # texto e a Sofia desliga limpo.
    FALLBACK_HANGUP_MESSAGE = os.getenv(
        "VOICE_FALLBACK_MSG",
        "Tive um problema técnico. Vou retornar a ligação em instantes. Obrigada!"
    )

    @classmethod
    def validate(cls) -> list[str]:
        """Retorna lista de campos críticos faltando."""
        missing = []
        for field in ("SIP_USER", "SIP_PASSWORD", "XAI_API_KEY"):
            if not getattr(cls, field):
                missing.append(field)
        return missing
