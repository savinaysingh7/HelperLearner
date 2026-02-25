import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def highlight(value, query):
    """Wrap case-insensitive query matches in <mark> tags for search result highlighting."""
    if not value:
        return ''
    if not query:
        return conditional_escape(value)

    safe_value = conditional_escape(value)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    highlighted = pattern.sub(lambda match: f'<mark>{match.group(0)}</mark>', str(safe_value))
    return mark_safe(highlighted)
