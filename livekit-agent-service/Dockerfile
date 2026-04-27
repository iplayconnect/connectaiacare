FROM python:3.11-slim

# libs nativas exigidas por silero (numpy/scipy) e por dependências de áudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-baixa modelo Silero VAD pra não atrasar primeiro call
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" || true

COPY . .

# Worker registra como agent worker; dispatcher expõe HTTP /dial
COPY supervisord.conf /etc/supervisor/conf.d/livekit-agent.conf

EXPOSE 5042

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5042/health || exit 1

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/livekit-agent.conf", "-n"]
