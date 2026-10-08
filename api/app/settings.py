"""Application settings.

Kept dependency-light (plain stdlib) so the API runs without pydantic-settings;
a later phase can swap this for ``pydantic_settings.BaseSettings`` once the full
configuration surface (DB, Redis, vault, OIDC) is wired.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = "PrivacyMon"
    environment: str = os.getenv("PRIVACYMON_ENV", "development")
    api_prefix: str = "/api/v1"
    # Platform database (SRS 8). The async engine is built from this in a later slice;
    # the secret lives only in the environment, never in a committed file (SRS 11.2).
    database_url: str = os.getenv(
        "PRIVACYMON_DB_URL",
        "postgresql+psycopg://privacymon:privacymon@localhost:5432/privacymon")
    # Confidence thresholds (SRS 4.4); overridable per deployment.
    likely_threshold: float = float(os.getenv("PRIVACYMON_LIKELY", "0.80"))
    review_threshold: float = float(os.getenv("PRIVACYMON_REVIEW", "0.50"))
    # Expose OpenAPI docs only outside production unless explicitly enabled.
    enable_docs: bool = os.getenv("PRIVACYMON_ENV", "development") != "production"


settings = Settings()
