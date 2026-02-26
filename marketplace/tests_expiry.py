from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from notifications.models import Notification

from .models import HelpRequest, Skill


class RequestExpiryTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username='poster', password='pw', knowledge_points=80)
        self.helper = CustomUser.objects.create_user(username='helper', password='pw')
        self.skill = Skill.objects.create(name='Django')

    def test_expires_at_is_auto_assigned_on_request_save(self):
        request_obj = HelpRequest.objects.create(
            title='Expiry default',
            description='desc',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=10,
        )

        self.assertIsNotNone(request_obj.expires_at)
        delta = request_obj.expires_at - timezone.now()
        self.assertGreater(delta.total_seconds(), 6 * 24 * 3600)
        self.assertLess(delta.total_seconds(), 8 * 24 * 3600)

    def test_expire_requests_command_cancels_refunds_and_notifies(self):
        request_obj = HelpRequest.objects.create(
            title='Should expire',
            description='desc',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=15,
            status='open',
            expires_at=timezone.now() - timedelta(days=1),
        )

        call_command('expire_requests')

        request_obj.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(request_obj.status, 'canceled')
        self.assertEqual(self.user.knowledge_points, 95)

        notification = Notification.objects.get(user=self.user)
        self.assertIn('expired', notification.message.lower())
        self.assertEqual(notification.link, reverse('request_detail', args=[request_obj.pk]))

    def test_expire_requests_command_skips_non_open_or_not_overdue_requests(self):
        future_open = HelpRequest.objects.create(
            title='Still valid',
            description='desc',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=10,
            status='open',
            expires_at=timezone.now() + timedelta(days=3),
        )
        in_progress_overdue = HelpRequest.objects.create(
            title='In progress overdue',
            description='desc',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=12,
            status='in_progress',
            accepted_by=self.helper,
            expires_at=timezone.now() - timedelta(days=2),
        )

        call_command('expire_requests')

        future_open.refresh_from_db()
        in_progress_overdue.refresh_from_db()

        self.assertEqual(future_open.status, 'open')
        self.assertEqual(in_progress_overdue.status, 'in_progress')
        self.assertEqual(Notification.objects.count(), 0)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_expire_requests_respects_notification_preferences(self):
        self.user.notification_preference = CustomUser.NotificationPreference.NONE
        self.user.save(update_fields=['notification_preference'])
        HelpRequest.objects.create(
            title='No notify on expiry',
            description='desc',
            user=self.user,
            skill_needed=self.skill,
            kp_bounty=8,
            status='open',
            expires_at=timezone.now() - timedelta(hours=2),
        )

        mail.outbox.clear()
        call_command('expire_requests')

        self.assertEqual(Notification.objects.filter(user=self.user).count(), 0)
        self.assertEqual(len(mail.outbox), 0)
