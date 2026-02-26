from accounts.models import CustomUser


def allows_in_app(user):
    """Return whether in-app notifications should be created for a user."""
    if user is None:
        return False
    if hasattr(user, 'allows_in_app_notifications'):
        return user.allows_in_app_notifications()
    return getattr(user, 'notification_preference', CustomUser.NotificationPreference.BOTH) in {
        CustomUser.NotificationPreference.BOTH,
        CustomUser.NotificationPreference.IN_APP,
    }


def allows_email(user):
    """Return whether email notifications should be sent to a user."""
    if user is None:
        return False
    if hasattr(user, 'allows_email_notifications'):
        return user.allows_email_notifications()
    return getattr(user, 'notification_preference', CustomUser.NotificationPreference.BOTH) in {
        CustomUser.NotificationPreference.BOTH,
        CustomUser.NotificationPreference.EMAIL,
    }
