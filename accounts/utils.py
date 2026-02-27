from .models import AuditLog


def log_event(user, action, target_user=None, ip_address=None, metadata=None):
    """Utility to record a security or administrative action in the AuditLog."""
    return AuditLog.objects.create(
        user=user,
        target_user=target_user,
        action=action,
        ip_address=ip_address,
        metadata=metadata or {},
    )


def get_client_ip(request):
    """Extract client IP address from request metadata."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
