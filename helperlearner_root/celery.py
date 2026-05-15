"""Celery application bootstrap (optional runtime dependency)."""

import os

from decouple import config

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    config("DJANGO_SETTINGS_MODULE", default="helperlearner_root.settings.dev"),
)

try:  # pragma: no cover - optional dependency
    from celery import Celery
except Exception:  # pragma: no cover - optional dependency
    celery_app = None
else:
    celery_app = Celery("helperlearner_root")
    celery_app.config_from_object("django.conf:settings", namespace="CELERY")
    celery_app.autodiscover_tasks()
