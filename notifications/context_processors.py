def unread_notifications_count(request):
    """Expose unread notification count for authenticated users in templates."""
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}

    return {
        'unread_notifications_count': request.user.notifications.filter(is_read=False).count(),
    }
