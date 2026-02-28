from unittest.mock import patch

from django.test import TestCase

from accounts.models import CustomUser

from .models import HelpRequest, Skill
from .services import RequestLifecycleError, cancel_help_request, claim_help_request, resolve_help_request


class HelpRequestLifecycleServiceTests(TestCase):
    def setUp(self):
        self.poster = CustomUser.objects.create_user(
            username='poster_service',
            password='pw',
            knowledge_points=80,
        )
        self.helper = CustomUser.objects.create_user(
            username='helper_service',
            password='pw',
            knowledge_points=40,
        )
        self.other = CustomUser.objects.create_user(
            username='other_service',
            password='pw',
            knowledge_points=25,
        )
        self.skill = Skill.objects.create(name='Service Testing')
        self.open_request = HelpRequest.objects.create(
            title='Need service layer help',
            description='Refactor transitions into service methods',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
        )

    @patch('marketplace.services.dispatch_webhook_event')
    def test_claim_help_request_updates_state(self, mocked_dispatch):
        claim_help_request(self.open_request.pk, self.helper)

        self.open_request.refresh_from_db()
        self.assertEqual(self.open_request.status, 'in_progress')
        self.assertEqual(self.open_request.accepted_by, self.helper)
        mocked_dispatch.assert_called_once()

    def test_claim_help_request_rejects_self_claim(self):
        with self.assertRaises(RequestLifecycleError) as exc_info:
            claim_help_request(self.open_request.pk, self.poster)

        self.assertEqual(exc_info.exception.code, 'self_claim')

    @patch('marketplace.services.dispatch_webhook_event')
    def test_resolve_help_request_transfers_kp(self, mocked_dispatch):
        self.open_request.status = 'in_progress'
        self.open_request.accepted_by = self.helper
        self.open_request.save(update_fields=['status', 'accepted_by', 'updated_at'])

        resolve_help_request(self.open_request.pk, self.poster)

        self.open_request.refresh_from_db()
        self.helper.refresh_from_db()
        self.assertEqual(self.open_request.status, 'resolved')
        self.assertEqual(self.helper.knowledge_points, 60)
        mocked_dispatch.assert_called_once()

    @patch('marketplace.services.dispatch_webhook_event')
    def test_cancel_help_request_refunds_kp(self, mocked_dispatch):
        cancel_help_request(self.open_request.pk, self.poster)

        self.open_request.refresh_from_db()
        self.poster.refresh_from_db()
        self.assertEqual(self.open_request.status, 'canceled')
        self.assertEqual(self.poster.knowledge_points, 100)
        mocked_dispatch.assert_called_once()

    def test_cancel_help_request_rejects_non_poster(self):
        with self.assertRaises(RequestLifecycleError) as exc_info:
            cancel_help_request(self.open_request.pk, self.other)

        self.assertEqual(exc_info.exception.code, 'forbidden')
