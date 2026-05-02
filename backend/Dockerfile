FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV PORT=5055
EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:5055/health || exit 1

# Workers vs threads (Phase D escala 2026-05-02):
# Trabalho dominante = I/O-bound (LLM API ~2-9s, DB queries ~5-30ms).
# Threads são "free" em RAM (~10MB/thread) e GIL libera durante I/O wait.
# 2 workers × 16 threads = 32 conexões simultâneas em I/O. Pra subir
# threads sem esgotar pool de Postgres, ver postgres.py maxconn.
CMD ["gunicorn", "--bind", "0.0.0.0:5055", "--workers", "2", "--threads", "16", "--timeout", "120", "app:app"]
