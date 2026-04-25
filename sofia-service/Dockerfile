FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 5031 = Flask REST (chat texto, TTS one-shot, history, usage, greeting)
# 5032 = uvicorn ASGI WebSocket (voz Live bidirecional)
EXPOSE 5031 5032

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5031/health && curl -fsS http://localhost:5032/health || exit 1

CMD ["supervisord", "-c", "/app/supervisord.conf"]
