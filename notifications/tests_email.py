from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import CustomUser
from marketplace.models import HelpRequest, Skill


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailNotificationTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.poster = CustomUser.objects.create_user(
            username='poster',
            password='pw',
            email='poster@example.com',
        )
        self.helper = CustomUser.objects.create_user(
            username='helper',
            password='pw',
            email='helper@example.com',
        )
        self.skill = Skill.objects.create(name='Django')

    def test_claim_transition_sends_email_to_request_poster(self):
        help_request = HelpRequest.objects.create(
            title='Need claim',
            description='Claim me',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=15,
            status='open',
        )

        help_request.status = 'in_progress'
        help_request.accepted_by = self.helper
        help_request.save()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("has been accepted by helper", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['poster@example.com'])

    def test_resolved_transition_sends_email_to_request_poster(self):
        help_request = HelpRequest.objects.create(
            title='Need resolve',
            description='Resolve me',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
            accepted_by=self.helper,
        )

        help_request.status = 'resolved'
        help_request.save()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("was resolved. 20 KP were paid to helper", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['poster@example.com'])

    def test_cancel_transition_sends_email_to_helper(self):
        help_request = HelpRequest.objects.create(
            title='Need cancel',
            description='Cancel me',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=12,
            status='in_progress',
            accepted_by=self.helper,
        )

        help_request.status = 'canceled'
        help_request.save()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("was canceled", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['helper@example.com'])

    def test_expire_requests_command_sends_expiry_email(self):
        help_request = HelpRequest.objects.create(
            title='Expire me',
            description='Old request',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=10,
            status='open',
            expires_at=timezone.now() - timedelta(hours=1),
        )

        call_command('expire_requests')

        help_request.refresh_from_db()
        self.assertEqual(help_request.status, 'canceled')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("expired and your KP was refunded", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['poster@example.com'])

    @override_settings(NOTIFICATION_EMAIL_ASYNC_ENABLED=True)
    @patch('notifications.tasks.send_templated_email_task')
    def test_claim_transition_queues_async_email_task_when_enabled(self, mocked_task):
        help_request = HelpRequest.objects.create(
            title='Need async claim mail',
            description='Claim me',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=25,
            status='open',
        )

        help_request.status = 'in_progress'
        help_request.accepted_by = self.helper
        help_request.save()

        mocked_task.delay.assert_called_once()
