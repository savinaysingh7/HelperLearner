"""Email delivery helpers with optional Celery-backed async dispatch."""

import json
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _normalize_context(context):
    """Return a JSON-safe copy of template context for async task payloads."""
    return json.loads(json.dumps(context or {}, default=str))


def send_templated_email_now(subject, template_name, context, recipient_email):
    """Send a templated email synchronously and return success status."""
    if not recipient_email:
        return False

    try:
        html_body = render_to_string(template_name, context or {})
        send_mail(
            subject=subject,
            message=strip_tags(html_body),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[recipient_email],
            html_message=html_body,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception(
            'Failed to send notification email synchronously subject=%s template=%s recipient=%s',
            subject,
            template_name,
            recipient_email,
        )
        return False


def send_templated_email(subject, template_name, context, recipient_email):
    """Queue templated email via Celery when enabled, with sync fallback on enqueue failure."""
    if not recipient_email:
        return False

    safe_context = _normalize_context(context)
    async_enabled = bool(getattr(settings, 'NOTIFICATION_EMAIL_ASYNC_ENABLED', True))
    if async_enabled:
        try:
            from .tasks import send_templated_email_task

            send_templated_email_task.delay(
                subject=subject,
                template_name=template_name,
                context=safe_context,
                recipient_email=recipient_email,
            )
            return True
        except Exception:
            logger.exception(
                'Failed to enqueue notification email subject=%s template=%s recipient=%s; falling back to sync',
                subject,
                template_name,
                recipient_email,
            )

    return send_templated_email_now(
        subject=subject,
        template_name=template_name,
        context=safe_context,
        recipient_email=recipient_email,
    )
