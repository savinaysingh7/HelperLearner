from datetime import timedelta

from django.conf import settings as django_settings
from django.db.models import Sum
from django.utils import timezone

from .models import FraudAlert, KPTransfer


def create_fraud_alert(alert_type, description, user=None, related_user=None, severity='medium', metadata=None):
    """Create a fraud alert with basic deduplication for noisy repeated events."""
    metadata = metadata or {}
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_exists = FraudAlert.objects.filter(
        alert_type=alert_type,
        user=user,
        related_user=related_user,
        description=description,
        created_at__gte=one_hour_ago,
        is_resolved=False,
    ).exists()
    if recent_exists:
        return None
    return FraudAlert.objects.create(
        alert_type=alert_type,
        severity=severity,
        user=user,
        related_user=related_user,
        description=description,
        metadata=metadata,
    )


def evaluate_kp_transfer_risk(sender, recipient, amount):
    """Run simple velocity and pattern checks for KP transfers."""
    now = timezone.now()

    velocity_window_hours = getattr(django_settings, 'KP_VELOCITY_WINDOW_HOURS', 1)
    velocity_max_count = getattr(django_settings, 'KP_VELOCITY_MAX_COUNT', 5)
    velocity_max_total = getattr(django_settings, 'KP_VELOCITY_MAX_TOTAL', 500)
    pair_window_hours = getattr(django_settings, 'KP_PAIR_WINDOW_HOURS', 24)
    pair_max_count = getattr(django_settings, 'KP_PAIR_MAX_COUNT', 8)
    pair_max_total = getattr(django_settings, 'KP_PAIR_MAX_TOTAL', 1200)
    large_transfer_threshold = getattr(django_settings, 'KP_LARGE_TRANSFER_THRESHOLD', 300)

    velocity_window_start = now - timedelta(hours=velocity_window_hours)
    pair_window_start = now - timedelta(hours=pair_window_hours)

    sender_window = KPTransfer.objects.filter(sender=sender, created_at__gte=velocity_window_start)
    sender_count = sender_window.count()
    sender_total = sender_window.aggregate(total=Sum('amount'))['total'] or 0

    if sender_count >= velocity_max_count or sender_total >= velocity_max_total:
        create_fraud_alert(
            alert_type='transfer_velocity',
            severity='high' if sender_total >= (velocity_max_total * 2) else 'medium',
            user=sender,
            description=f'High KP transfer velocity detected within {velocity_window_hours}h.',
            metadata={'count': sender_count, 'total': int(sender_total)},
        )

    pair_window = KPTransfer.objects.filter(
        created_at__gte=pair_window_start,
        sender_id__in=[sender.pk, recipient.pk],
        recipient_id__in=[sender.pk, recipient.pk],
    )
    pair_count = pair_window.count()
    pair_total = pair_window.aggregate(total=Sum('amount'))['total'] or 0
    if pair_count >= pair_max_count or pair_total >= pair_max_total:
        create_fraud_alert(
            alert_type='unusual_pattern',
            severity='high',
            user=sender,
            related_user=recipient,
            description=f'Unusual bilateral KP transfer pattern detected in {pair_window_hours}h.',
            metadata={'pair_count': pair_count, 'pair_total': int(pair_total)},
        )

    if amount >= large_transfer_threshold:
        create_fraud_alert(
            alert_type='unusual_pattern',
            severity='medium',
            user=sender,
            related_user=recipient,
            description='Single large KP transfer detected.',
            metadata={'amount': int(amount)},
        )
