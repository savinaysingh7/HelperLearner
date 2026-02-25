from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CustomUser


class KpClaimTransferTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.sender = CustomUser.objects.create_user(
            username='sender',
            password='pw',
            email='sender@example.com',
            knowledge_points=100,
        )
        self.recipient = CustomUser.objects.create_user(
            username='receiver',
            password='pw',
            email='receiver@example.com',
            knowledge_points=50,
        )

    def test_daily_claim_adds_kp_once_available(self):
        self.client.login(username='sender', password='pw')

        response = self.client.post(reverse('claim_daily_kp'))

        self.assertEqual(response.status_code, 302)
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.knowledge_points, 110)
        self.assertIsNotNone(self.sender.last_kp_claim)

    def test_daily_claim_is_blocked_within_24_hours(self):
        self.sender.last_kp_claim = timezone.now()
        self.sender.save(update_fields=['last_kp_claim'])
        self.client.login(username='sender', password='pw')

        response = self.client.post(reverse('claim_daily_kp'))

        self.assertEqual(response.status_code, 302)
        self.sender.refresh_from_db()
        self.assertEqual(self.sender.knowledge_points, 100)

    def test_transfer_flow_confirms_and_transfers_kp(self):
        self.client.login(username='sender', password='pw')

        review_response = self.client.get(reverse('transfer_kp'), {'recipient_username': 'receiver', 'amount': 15})
        self.assertEqual(review_response.status_code, 200)
        self.assertContains(review_response, 'Confirm transfer of')

        transfer_response = self.client.post(reverse('transfer_kp'), {'recipient_username': 'receiver', 'amount': 15})
        self.assertEqual(transfer_response.status_code, 302)

        self.sender.refresh_from_db()
        self.recipient.refresh_from_db()
        self.assertEqual(self.sender.knowledge_points, 85)
        self.assertEqual(self.recipient.knowledge_points, 65)

    def test_transfer_fails_when_sender_has_insufficient_kp(self):
        self.sender.knowledge_points = 6
        self.sender.save(update_fields=['knowledge_points'])
        self.client.login(username='sender', password='pw')

        response = self.client.post(reverse('transfer_kp'), {'recipient_username': 'receiver', 'amount': 10})

        self.assertEqual(response.status_code, 302)
        self.sender.refresh_from_db()
        self.recipient.refresh_from_db()
        self.assertEqual(self.sender.knowledge_points, 6)
        self.assertEqual(self.recipient.knowledge_points, 50)
