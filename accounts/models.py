from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce


class CustomUser(AbstractUser):
    class NotificationPreference(models.TextChoices):
        BOTH = 'both', 'In-app + Email'
        IN_APP = 'in_app', 'In-app only'
        EMAIL = 'email', 'Email only'
        NONE = 'none', 'Disable all'

    bio = models.TextField(max_length=500, blank=True)
    knowledge_points = models.IntegerField(default=100)
    last_kp_claim = models.DateTimeField(null=True, blank=True)
    skills = models.ManyToManyField('marketplace.Skill', blank=True, related_name='users')
    wallet_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    compliance_verified = models.BooleanField(default=False)
    notification_preference = models.CharField(
        max_length=12,
        choices=NotificationPreference.choices,
        default=NotificationPreference.BOTH,
    )

    def allows_in_app_notifications(self):
        """Return True when the user allows in-app notification delivery."""
        return self.notification_preference in {
            self.NotificationPreference.BOTH,
            self.NotificationPreference.IN_APP,
        }

    def allows_email_notifications(self):
        """Return True when the user allows email notification delivery."""
        return self.notification_preference in {
            self.NotificationPreference.BOTH,
            self.NotificationPreference.EMAIL,
        }

    @property
    def trust_signal_score(self):
        """Return cumulative trust score from structured trust signals."""
        if not self.pk:
            return 0
        return self.trust_signals.aggregate(total=Coalesce(Sum('score_delta'), 0))['total']

    def __str__(self):
        return self.username

    class Meta:
        ordering = ['username']
        indexes = [
            models.Index(fields=['knowledge_points']),
            models.Index(fields=['wallet_inr']),
            models.Index(fields=['compliance_verified']),
            models.Index(fields=['last_kp_claim']),
            models.Index(fields=['notification_preference']),
        ]
