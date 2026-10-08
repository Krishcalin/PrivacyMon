"""Celery application for the scan worker (SRS 7.2).

Redis is both broker and result backend. ``PRIVACYMON_CELERY_EAGER=1`` runs tasks
inline (used by tests and a broker-less dev run). Importing this module needs Celery
installed, so only the worker image and the API's lazy enqueue path import it — never
the default test suite.
"""
from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.getenv("PRIVACYMON_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("PRIVACYMON_RESULT_BACKEND", BROKER_URL)

celery_app = Celery("privacymon", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_always_eager=os.getenv("PRIVACYMON_CELERY_EAGER") == "1",
    task_eager_propagates=True,
)

# Importing registers the tasks on the app.
from worker import tasks  # noqa: E402,F401
