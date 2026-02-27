from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from marketplace.models import HelpRequest
from marketplace.realtime import emit_user_event

from .emailing import send_templated_email
from .models import Notification
from .utils import allows_email, allows_in_app


def _send_notification_email(subject, template_name, context, recipient_email):
    """Safely send notification email and log failures without raising."""
    if not recipient_email:
        return

    send_templated_email(
        subject=subject,
        template_name=template_name,
        context=context,
        recipient_email=recipient_email,
    )


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
    """Create in-app notifications and send email on request status transitions."""
    if created:
        return

    previous_status = getattr(instance, '_previous_status', None)
    if previous_status == instance.status:
        return

    detail_link = reverse('request_detail', args=[instance.pk])

    if instance.status == 'in_progress':
        if allows_in_app(instance.user):
            Notification.objects.create(
                user=instance.user,
                message='Someone accepted your request!',
                link=detail_link,
            )
        if instance.accepted_by and allows_email(instance.user):
            _send_notification_email(
                subject=f"Your request '{instance.title}' has been accepted by {instance.accepted_by.username}.",
                template_name='emails/claim_notification.html',
                context={
                    'request_obj': {'title': instance.title, 'kp_bounty': instance.kp_bounty},
                    'poster': {'username': instance.user.username},
                    'helper': {'username': instance.accepted_by.username},
                },
                recipient_email=instance.user.email,
            )

    elif instance.status == 'resolved' and instance.accepted_by:
        if allows_in_app(instance.accepted_by):
            Notification.objects.create(
                user=instance.accepted_by,
                message=f'Your help was marked resolved! You earned {instance.kp_bounty} KP.',
                link=detail_link,
            )
        if allows_email(instance.user):
            _send_notification_email(
                subject=f"Your request '{instance.title}' was resolved. {instance.kp_bounty} KP were paid to {instance.accepted_by.username}.",
                template_name='emails/resolve_notification.html',
                context={
                    'request_obj': {'title': instance.title, 'kp_bounty': instance.kp_bounty},
                    'poster': {'username': instance.user.username},
                    'helper': {'username': instance.accepted_by.username},
                },
                recipient_email=instance.user.email,
            )

    elif instance.status == 'canceled' and instance.accepted_by:
        if allows_in_app(instance.accepted_by):
            Notification.objects.create(
                user=instance.accepted_by,
                message='The request you were working on was canceled.',
                link=detail_link,
            )
        if allows_email(instance.accepted_by):
            _send_notification_email(
                subject=f"The request '{instance.title}' was canceled.",
                template_name='emails/cancel_notification.html',
                context={
                    'request_obj': {'title': instance.title, 'kp_bounty': instance.kp_bounty},
                    'poster': {'username': instance.user.username},
                    'helper': {'username': instance.accepted_by.username},
                },
                recipient_email=instance.accepted_by.email,
            )


@receiver(post_save, sender=Notification)
def push_realtime_notification(sender, instance, created, **kwargs):
    """Forward in-app notifications to websocket clients for realtime UX."""
    if not created:
        return
    emit_user_event(
        instance.user_id,
        'notification.created',
        {
            'notification_id': instance.pk,
            'message': instance.message,
            'link': instance.link,
        },
    )
