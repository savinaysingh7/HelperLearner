"""Notification background tasks."""

from .emailing import send_templated_email_now

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
    name="notifications.tasks.send_templated_email_task",
)
def send_templated_email_task(self, subject, template_name, context, recipient_email):
    """Send one notification email with retry semantics for transient errors."""
    success = send_templated_email_now(
        subject=subject,
        template_name=template_name,
        context=context or {},
        recipient_email=recipient_email,
    )
    return {"ok": bool(success), "template_name": template_name, "recipient_email": recipient_email}
