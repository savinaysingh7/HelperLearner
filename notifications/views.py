from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def notification_list(request):
    """List all notifications for the current user and mark unread ones as read."""
    notifications = list(request.user.notifications.all().order_by('-created_at'))
    unread_ids = [item.pk for item in notifications if not item.is_read]
    if unread_ids:
        request.user.notifications.filter(pk__in=unread_ids, is_read=False).update(is_read=True)

    for item in notifications:
        item.was_unread = item.pk in unread_ids

    return render(
        request,
        'notifications/notification_list.html',
        {'notifications': notifications},
    )
