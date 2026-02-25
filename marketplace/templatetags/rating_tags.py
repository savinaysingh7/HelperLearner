from django import template

register = template.Library()


@register.filter
def star_display(value):
    """Render a numeric rating as a five-star string like '★★★★☆'."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0

    filled = max(0, min(5, int(round(numeric))))
    return ('★' * filled) + ('☆' * (5 - filled))
