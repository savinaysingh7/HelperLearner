import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from marketplace.models import HelpRequest
from notifications.emailing import send_templated_email
from notifications.models import Notification
from notifications.utils import allows_email, allows_in_app

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Expire overdue open requests, refund KP, create notifications, and send expiry emails.'

    def handle(self, *args, **options):
        now = timezone.now()
        expired_candidates = HelpRequest.objects.filter(status='open', expires_at__lt=now).values_list('pk', flat=True)

        expired_count = 0
        for request_id in expired_candidates:
            with transaction.atomic():
                help_request = (
                    HelpRequest.objects.select_for_update()
                    .select_related('user')
                    .filter(pk=request_id)
                    .first()
                )
                if not help_request:
                    continue
                if help_request.status != 'open' or not help_request.expires_at or help_request.expires_at >= now:
                    continue

                poster = CustomUser.objects.select_for_update().get(pk=help_request.user_id)
                poster.knowledge_points += help_request.kp_bounty
                poster.save(update_fields=['knowledge_points'])

                help_request.status = 'canceled'
                help_request.save(update_fields=['status', 'updated_at'])

                if allows_in_app(poster):
                    Notification.objects.create(
                        user=poster,
                        message='Your request expired and your KP was refunded.',
                        link=reverse('request_detail', args=[help_request.pk]),
                    )

                try:
                    if poster.email and allows_email(poster):
                        html_body = render_to_string(
                            'emails/expiry_notification.html',
                            {'request_obj': help_request, 'poster': poster},
                        )
                        send_mail(
                            subject=f"Your request '{help_request.title}' expired and your KP was refunded.",
                            message=strip_tags(html_body),
                            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                            recipient_list=[poster.email],
                            html_message=html_body,
                            fail_silently=False,
                        )
                except Exception:
                    logger.exception(
                        'Failed to send expiry email for request=%s user=%s',
                        help_request.pk,
                        poster.username,
                    )

                logger.info(
                    'Expired request %s and refunded %s KP to %s',
                    help_request.pk,
                    help_request.kp_bounty,
                    poster.username,
                )
                expired_count += 1

        self.stdout.write(self.style.SUCCESS(f'Expired {expired_count} request(s).'))
