from datetime import timedelta

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
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    sender_window = KPTransfer.objects.filter(sender=sender, created_at__gte=one_hour_ago)
    sender_count = sender_window.count()
    sender_total = sender_window.aggregate(total=Sum('amount'))['total'] or 0

    if sender_count >= 5 or sender_total >= 500:
        create_fraud_alert(
            alert_type='transfer_velocity',
            severity='high' if sender_total >= 1000 else 'medium',
            user=sender,
            description='High KP transfer velocity detected within 1 hour.',
            metadata={'count_1h': sender_count, 'total_1h': int(sender_total)},
        )

    pair_window = KPTransfer.objects.filter(
        created_at__gte=one_day_ago,
        sender_id__in=[sender.pk, recipient.pk],
        recipient_id__in=[sender.pk, recipient.pk],
    )
    pair_count = pair_window.count()
    pair_total = pair_window.aggregate(total=Sum('amount'))['total'] or 0
    if pair_count >= 8 or pair_total >= 1200:
        create_fraud_alert(
            alert_type='unusual_pattern',
            severity='high',
            user=sender,
            related_user=recipient,
            description='Unusual bilateral KP transfer pattern detected in 24h.',
            metadata={'pair_count_24h': pair_count, 'pair_total_24h': int(pair_total)},
        )

    if amount >= 300:
        create_fraud_alert(
            alert_type='unusual_pattern',
            severity='medium',
            user=sender,
            related_user=recipient,
            description='Single large KP transfer detected.',
            metadata={'amount': int(amount)},
        )
