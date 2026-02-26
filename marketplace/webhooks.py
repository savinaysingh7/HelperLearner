import hashlib
import hmac
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)


def _sign_payload(secret, payload_text):
    """Return HMAC signature for outbound webhook body."""
    return hmac.new(secret.encode('utf-8'), payload_text.encode('utf-8'), hashlib.sha256).hexdigest()


def dispatch_webhook_event(owner, event_type, payload):
    """Deliver webhook event to all active endpoints subscribed for the owner."""
    if owner is None:
        return 0

    payload_text = json.dumps(payload, separators=(',', ':'), default=str)
    delivered = 0

    endpoints = WebhookEndpoint.objects.filter(user=owner, is_active=True)
    for endpoint in endpoints:
        subscribed = endpoint.subscribed_events or []
        if subscribed and event_type not in subscribed and '*' not in subscribed:
            continue

        signature = _sign_payload(endpoint.secret, payload_text)
        request_obj = Request(
            endpoint.url,
            data=payload_text.encode('utf-8'),
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'X-Webhook-Event': event_type,
                'X-Webhook-Signature': signature,
            },
        )

        status_code = None
        response_excerpt = ''
        succeeded = False
        try:
            with urlopen(request_obj, timeout=5) as response:
                status_code = response.getcode()
                response_excerpt = (response.read(400) or b'').decode('utf-8', errors='ignore')
                succeeded = 200 <= status_code < 300
        except HTTPError as exc:
            status_code = exc.code
            response_excerpt = (exc.read(400) or b'').decode('utf-8', errors='ignore')
            logger.warning('Webhook HTTP error for endpoint=%s event=%s status=%s', endpoint.pk, event_type, status_code)
        except URLError as exc:
            response_excerpt = str(exc)
            logger.warning('Webhook URL error for endpoint=%s event=%s error=%s', endpoint.pk, event_type, exc)
        except Exception:
            logger.exception('Unexpected webhook dispatch failure endpoint=%s event=%s', endpoint.pk, event_type)

        WebhookDelivery.objects.create(
            endpoint=endpoint,
            event_type=event_type,
            payload=payload,
            status_code=status_code,
            response_excerpt=response_excerpt[:600],
            succeeded=succeeded,
        )
        delivered += 1

    return delivered
