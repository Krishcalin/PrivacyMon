# PrivacyMon scan worker image (SRS 7.2). Build context is the repo root.
# Runs a Celery worker that drains the scan queue and writes findings to the platform
# DB. No FastAPI/Alembic here — the API image owns migrations and serving.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app
WORKDIR /app

RUN pip install --no-cache-dir \
    "sqlalchemy[asyncio]>=2.0" "psycopg[binary]>=3.1" \
    "celery>=5.3" "redis>=5.0" "cryptography>=42.0" \
    "GitPython>=3.1" "PyYAML>=6.0" "structlog>=24.1"

COPY dpia_core/ ./dpia_core/
COPY platform_db/ ./platform_db/
COPY worker/ ./worker/
COPY fixtures/ ./fixtures/

RUN useradd -r -u 10001 privacymon && chown -R privacymon /app
USER privacymon

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
