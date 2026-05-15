from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


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

    def __str__(self):
        return self.username

    class Meta:
        ordering = ['username']
        indexes = [
            models.Index(fields=['knowledge_points']),
            models.Index(fields=['wallet_inr']),
            models.Index(fields=['compliance_verified']),
            models.Index(fields=['is_suspended']),
            models.Index(fields=['suspended_until']),
            models.Index(fields=['last_kp_claim']),
            models.Index(fields=['notification_preference']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(knowledge_points__gte=0),
                name='customuser_kp_non_negative',
            ),
            models.CheckConstraint(
                condition=models.Q(wallet_inr__gte=0),
                name='customuser_wallet_non_negative',
            ),
        ]


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_actions'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_targets'
    )
    action = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.action} by {self.user} at {self.created_at}"
