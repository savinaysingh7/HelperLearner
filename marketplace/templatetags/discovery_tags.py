import math

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def expires_in_days(expires_at):
    """Return a friendly expiry string for request cards and details."""
    if not expires_at:
        return 'No expiry'

    delta = expires_at - timezone.now()
    days_left = math.ceil(delta.total_seconds() / 86400)

    if days_left < 0:
        return 'Expired'
    if days_left == 0:
        return 'Expires today'
    if days_left == 1:
        return 'Expires in 1 day'
    return f'Expires in {days_left} days'


@register.filter
def expiry_badge_class(expires_at):
    """Return a bootstrap badge class based on remaining expiry time."""
    if not expires_at:
        return 'text-bg-secondary'

    delta = expires_at - timezone.now()
    days_left = math.ceil(delta.total_seconds() / 86400)

    if days_left < 0:
        return 'text-bg-danger'
    if days_left <= 1:
        return 'text-bg-warning'
    return 'text-bg-info'


@register.filter
def get_item(mapping, key):
    """Template helper for dictionary key lookup."""
    if mapping is None:
        return None
    return mapping.get(key)
