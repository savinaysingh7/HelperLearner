from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def notification_list(request):
    """List all notifications for the current user and mark unread ones as read."""
    notifications = request.user.notifications.all().order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)

    return render(
        request,
        'notifications/notification_list.html',
        {'notifications': notifications},
    )
