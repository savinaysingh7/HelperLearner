import logging

logger = logging.getLogger(__name__)

try:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
except Exception:  # pragma: no cover - optional runtime dependency
    async_to_sync = None
    get_channel_layer = None


def emit_user_event(user_id, event, payload):
    """Emit a real-time websocket event for a user when Channels is available."""
    if not user_id or async_to_sync is None or get_channel_layer is None:
        return False

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return False

    try:
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}',
            {
                'type': 'push.event',
                'event': event,
                'payload': payload,
            },
        )
        return True
    except Exception:
        logger.exception('Failed to emit realtime event user_id=%s event=%s', user_id, event)
        return False
