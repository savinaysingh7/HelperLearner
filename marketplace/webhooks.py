import hashlib
import hmac
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)


class RetryableWebhookDeliveryError(Exception):
    """Raised when webhook delivery failed due to transient/retryable conditions."""


def _sign_payload(secret, payload_text):
    """Return HMAC signature for outbound webhook body."""
    return hmac.new(secret.encode('utf-8'), payload_text.encode('utf-8'), hashlib.sha256).hexdigest()


def _is_retryable_http_status(status_code):
    """Return True when an HTTP status represents a transient delivery failure."""
    return status_code == 429 or 500 <= status_code < 600


def _endpoint_accepts_event(endpoint, event_type):
    """Return True when endpoint subscription allows the provided event type."""
    subscribed = endpoint.subscribed_events or []
    return not subscribed or event_type in subscribed or '*' in subscribed


def _build_request(endpoint, event_type, payload_text):
    """Build outbound webhook request for a single endpoint."""
    signature = _sign_payload(endpoint.secret, payload_text)
    return Request(
        endpoint.url,
        data=payload_text.encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Webhook-Event': event_type,
            'X-Webhook-Signature': signature,
        },
    )


def _execute_delivery(endpoint, event_type, payload_text, timeout_seconds):
    """Execute one HTTP delivery attempt and return result metadata."""
    request_obj = _build_request(endpoint, event_type, payload_text)
    status_code = None
    response_excerpt = ''
    succeeded = False
    retryable = False

    try:
        with urlopen(request_obj, timeout=timeout_seconds) as response:
            status_code = response.getcode()
            response_excerpt = (response.read(400) or b'').decode('utf-8', errors='ignore')
            succeeded = 200 <= status_code < 300
    except HTTPError as exc:
        status_code = exc.code
        response_excerpt = (exc.read(400) or b'').decode('utf-8', errors='ignore')
        retryable = _is_retryable_http_status(status_code)
        logger.warning(
            'Webhook HTTP error endpoint=%s event=%s status=%s retryable=%s',
            endpoint.pk,
            event_type,
            status_code,
            retryable,
        )
    except URLError as exc:
        response_excerpt = str(exc)
        retryable = True
        logger.warning(
            'Webhook URL error endpoint=%s event=%s error=%s',
            endpoint.pk,
            event_type,
            exc,
        )
    except Exception:
        retryable = True
        logger.exception('Unexpected webhook dispatch failure endpoint=%s event=%s', endpoint.pk, event_type)

    return {
        'status_code': status_code,
        'response_excerpt': response_excerpt[:600],
        'succeeded': succeeded,
        'retryable': retryable,
    }


def deliver_webhook_to_endpoint(endpoint_id, event_type, payload, attempt=1):
    """Deliver one webhook endpoint and raise on retryable failures."""
    endpoint = WebhookEndpoint.objects.filter(pk=endpoint_id, is_active=True).first()
    if endpoint is None:
        return {'ok': False, 'skipped': True, 'reason': 'missing_endpoint'}
    if not _endpoint_accepts_event(endpoint, event_type):
        return {'ok': False, 'skipped': True, 'reason': 'not_subscribed'}

    payload_text = json.dumps(payload, separators=(',', ':'), default=str)
    timeout_seconds = max(1, int(getattr(settings, 'WEBHOOK_DELIVERY_TIMEOUT_SECONDS', 5)))
    result = _execute_delivery(endpoint, event_type, payload_text, timeout_seconds)

    attempt_prefix = f'[attempt {attempt}] '
    WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload,
        status_code=result['status_code'],
        response_excerpt=(attempt_prefix + result['response_excerpt'])[:600],
        succeeded=result['succeeded'],
    )

    if not result['succeeded'] and result['retryable']:
        raise RetryableWebhookDeliveryError(
            f"Retryable webhook failure endpoint={endpoint.pk} event={event_type}"
        )

    return {'ok': result['succeeded'], 'skipped': False}


def _dispatch_sync_with_retry(endpoint_id, event_type, payload):
    """Synchronously deliver with bounded retries when async dispatch is unavailable."""
    max_attempts = max(1, int(getattr(settings, 'WEBHOOK_MAX_ATTEMPTS', 3)))
    for attempt in range(1, max_attempts + 1):
        try:
            deliver_webhook_to_endpoint(
                endpoint_id=endpoint_id,
                event_type=event_type,
                payload=payload,
                attempt=attempt,
            )
            return
        except RetryableWebhookDeliveryError:
            if attempt >= max_attempts:
                logger.warning(
                    'Webhook sync retries exhausted endpoint=%s event=%s attempts=%s',
                    endpoint_id,
                    event_type,
                    max_attempts,
                )
                return
            backoff_seconds = min(0.2 * (2 ** (attempt - 1)), 1.6)
            time.sleep(backoff_seconds)


def dispatch_webhook_event(owner, event_type, payload):
    """Deliver webhook event to all active endpoints subscribed for the owner."""
    if owner is None:
        return 0

    safe_payload = json.loads(json.dumps(payload, default=str))
    endpoints = WebhookEndpoint.objects.filter(user=owner, is_active=True)
    dispatched = 0
    async_enabled = bool(getattr(settings, 'WEBHOOK_ASYNC_ENABLED', True))

    for endpoint in endpoints:
        if not _endpoint_accepts_event(endpoint, event_type):
            continue

        if async_enabled:
            try:
                from .tasks import dispatch_webhook_delivery_task

                dispatch_webhook_delivery_task.delay(
                    endpoint.pk,
                    event_type,
                    safe_payload,
                )
                dispatched += 1
                continue
            except Exception:
                logger.exception(
                    'Failed to enqueue webhook delivery endpoint=%s event=%s; falling back to sync delivery',
                    endpoint.pk,
                    event_type,
                )

        _dispatch_sync_with_retry(endpoint.pk, event_type, safe_payload)
        dispatched += 1

    return dispatched
