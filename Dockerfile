# Web UI: FastAPI + Uvicorn (see README for run and env vars).
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pillow / QR deps (wheels usually suffice; zlib/jpeg often needed at runtime)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY math_exercises.py .
COPY web/ web/

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENV WEB_PORT=8000 \
    HOST=0.0.0.0

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('WEB_PORT','8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=3)"

CMD ["sh", "-c", "exec uvicorn web.app:app --host ${HOST} --port ${WEB_PORT}"]
