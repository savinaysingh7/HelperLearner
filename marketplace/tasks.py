"""Background task wrappers for Celery workers."""

from django.core.management import call_command

try:  # pragma: no cover - optional dependency
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency
    def shared_task(*args, **kwargs):  # type: ignore
        """Fallback decorator when Celery is not installed."""

        def decorator(func):
            return func

        return decorator


@shared_task(name="marketplace.tasks.expire_open_requests_task")
def expire_open_requests_task():
    """Run request expiry/refund workflow from background scheduler."""
    call_command("expire_requests")
    return {"ok": True, "command": "expire_requests"}


@shared_task(name="marketplace.tasks.notify_saved_searches_task")
def notify_saved_searches_task():
    """Run saved-search notification workflow from background scheduler."""
    call_command("notify_saved_searches")
    return {"ok": True, "command": "notify_saved_searches"}


@shared_task(name="marketplace.tasks.run_sla_engine_task")
def run_sla_engine_task():
    """Run SLA reminder/auto-release workflow from background scheduler."""
    call_command("run_sla_engine")
    return {"ok": True, "command": "run_sla_engine"}
