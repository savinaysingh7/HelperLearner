from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from marketplace.models import HelpRequest

from .models import Notification


@receiver(pre_save, sender=HelpRequest)
def cache_previous_status(sender, instance, **kwargs):
    """Cache the previous status so post_save can detect status transitions."""
    if not instance.pk:
        instance._previous_status = None
        return

    previous_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
    instance._previous_status = previous_status


@receiver(post_save, sender=HelpRequest)
def create_help_request_notifications(sender, instance, created, **kwargs):
    """Create notifications when HelpRequest status transitions to key workflow states."""
    if created:
        return

    previous_status = getattr(instance, '_previous_status', None)
    if previous_status == instance.status:
        return

    detail_link = reverse('request_detail', args=[instance.pk])

    if instance.status == 'in_progress':
        Notification.objects.create(
            user=instance.user,
            message='Someone accepted your request!',
            link=detail_link,
        )
    elif instance.status == 'resolved' and instance.accepted_by:
        Notification.objects.create(
            user=instance.accepted_by,
            message=f'Your help was marked resolved! You earned {instance.kp_bounty} KP.',
            link=detail_link,
        )
    elif instance.status == 'canceled' and instance.accepted_by:
        Notification.objects.create(
            user=instance.accepted_by,
            message='The request you were working on was canceled.',
            link=detail_link,
        )
