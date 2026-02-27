"""Project package initializer."""

try:  # pragma: no cover - optional dependency
    from .celery import celery_app
except Exception:
    celery_app = None

__all__ = ("celery_app",)
