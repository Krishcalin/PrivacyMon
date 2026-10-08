# PrivacyMon API image (SRS 12.1). Build context is the repo root (see
# infra/docker-compose.yml: build.context = ..). Runs the Alembic baseline on start
# so a fresh database is migrated, then serves the FastAPI app.
#
# Reporting deps (weasyprint/python-docx) and the Celery worker deps are intentionally
# NOT installed here — they land with the reporting and async-pipeline slices. This
# keeps the API image small and free of heavy native build dependencies.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app
WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.110" "uvicorn[standard]>=0.29" "pydantic>=2.6" \
    "sqlalchemy[asyncio]>=2.0" "alembic>=1.13" "psycopg[binary]>=3.1" \
    "celery>=5.3" "redis>=5.0" "cryptography>=42.0" \
    "PyMySQL>=1.1" "oracledb>=2.0" "pymssql>=2.3" \
    "structlog>=24.1" "python-multipart>=0.0.9" "GitPython>=3.1" "PyYAML>=6.0"

# The engine, persistence layer, worker (connectors + pipeline) and API.
COPY dpia_core/ ./dpia_core/
COPY platform_db/ ./platform_db/
COPY worker/ ./worker/
COPY api/ ./api/
COPY alembic.ini ./alembic.ini
COPY fixtures/ ./fixtures/

RUN useradd -r -u 10001 privacymon && chown -R privacymon /app
USER privacymon
EXPOSE 8000

# Migrate then serve. `alembic upgrade head` is idempotent, so a restart is safe.
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn api.app.main:app --host 0.0.0.0 --port 8000"]
