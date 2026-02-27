"""Background task wrappers for Celery workers."""

from django.core.management import call_command

from .webhooks import RetryableWebhookDeliveryError, deliver_webhook_to_endpoint

try:  # pragma: no cover - optional dependency
    from celery import shared_task
except Exception:  # pragma: no cover - optional dependency
    def shared_task(*args, **kwargs):  # type: ignore
        """Fallback decorator when Celery is not installed."""

        def decorator(func):
            return func

        return decorator


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    name="marketplace.tasks.expire_open_requests_task",
)
def expire_open_requests_task(self):
    """Run request expiry/refund workflow from background scheduler."""
    call_command("expire_requests")
    return {"ok": True, "command": "expire_requests"}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    name="marketplace.tasks.notify_saved_searches_task",
)
def notify_saved_searches_task(self):
    """Run saved-search notification workflow from background scheduler."""
    call_command("notify_saved_searches")
    return {"ok": True, "command": "notify_saved_searches"}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    name="marketplace.tasks.run_sla_engine_task",
)
def run_sla_engine_task(self):
    """Run SLA reminder/auto-release workflow from background scheduler."""
    call_command("run_sla_engine")
    return {"ok": True, "command": "run_sla_engine"}


@shared_task(
    bind=True,
    autoretry_for=(RetryableWebhookDeliveryError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    name="marketplace.tasks.dispatch_webhook_delivery_task",
)
def dispatch_webhook_delivery_task(self, endpoint_id, event_type, payload):
    """Dispatch one webhook endpoint delivery with retry on transient failures."""
    attempt = (getattr(self.request, "retries", 0) or 0) + 1
    return deliver_webhook_to_endpoint(
        endpoint_id=endpoint_id,
        event_type=event_type,
        payload=payload,
        attempt=attempt,
    )
