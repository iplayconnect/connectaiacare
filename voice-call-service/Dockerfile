# ============================================================================
# voice-call-service Dockerfile — Container PJSIP + Grok Voice Realtime
# ============================================================================
# Container DEDICADO da ConnectaIACare pra ligações telefônicas via SIP +
# Sofia (Grok Voice Realtime). Isolado do voip-service da outra plataforma
# (que usa Deepgram+ElevenLabs) — zero risco de regressão.
#
# Pipeline: PJSIP RTP (PCMU 8k) ↔ AudioBridge (resample 8k↔24k) ↔
#           Grok Realtime WS (PCM 24k) — speech-to-speech end-to-end.
#
# Build pattern copiado do voip-service da outra plataforma (já validado em
# produção). Python 3.11 obrigatório (pjsua2 egg compilado pra essa ABI).

# ─────────── STAGE 1: Builder (compila PJSIP nativo) ───────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    swig \
    python3-dev \
    libssl-dev \
    wget \
    tar \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN wget https://github.com/pjsip/pjproject/archive/refs/tags/2.14.tar.gz -O pjsip.tar.gz && \
    tar -xzf pjsip.tar.gz && \
    cd pjproject-2.14 && \
    ./configure --enable-shared --disable-video --disable-v4l2 \
        --disable-g7221-codec --disable-ilbc-codec && \
    make dep && make && make install

WORKDIR /build/pjproject-2.14/pjsip-apps/src/swig/python
RUN make && python3 setup.py install


# ─────────── STAGE 2: Runtime ───────────
FROM python:3.11-slim

LABEL maintainer="ConnectaIACare voice-call-service"
LABEL version="0.1.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LD_LIBRARY_PATH=/usr/local/lib \
    PYTHONPATH=/usr/local/lib/python3.11/site-packages/pjsua2-2.14-py3.11-linux-x86_64.egg

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copia PJSIP do builder
COPY --from=builder /usr/local/lib/ /usr/local/lib/
COPY --from=builder /usr/local/include/ /usr/local/include/
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código aplicativo
COPY config.py .
COPY voice_call_app.py .
COPY services/ ./services/
COPY routes/ ./routes/
COPY shared/ ./shared/

RUN mkdir -p /app/storage /app/logs && \
    useradd -m -u 1000 voiceuser && \
    chown -R voiceuser:voiceuser /app

USER voiceuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5040/health || exit 1

# Portas:
#   5040 — HTTP API (POST /dial, GET /status, GET /health)
#   5060 — SIP signaling (UDP) — só se for ATENDER chamadas inbound (Fase 2)
#   10500-10600 — RTP (faixa diferente do voip-service pra não conflitar)
EXPOSE 5040 5060/udp

CMD ["python", "voice_call_app.py"]
