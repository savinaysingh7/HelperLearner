from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from .models import WebhookDelivery, WebhookEndpoint


class OpsEndpointTests(TestCase):
    def setUp(self):
        self.staff_user = CustomUser.objects.create_user(
            username="ops_admin",
            password="pw",
            is_staff=True,
        )
        self.regular_user = CustomUser.objects.create_user(
            username="regular_user",
            password="pw",
        )

    @patch(
        "marketplace.advanced_views._collect_celery_worker_snapshot",
        return_value={
            "healthy": True,
            "configured": True,
            "workers": [{"name": "celery@worker1", "online": True, "active": 1, "reserved": 0, "scheduled": 2}],
            "totals": {"active": 1, "reserved": 0, "scheduled": 2},
            "error": "",
        },
    )
    def test_ops_celery_status_staff_can_access(self, _mock_snapshot):
        self.client.login(username="ops_admin", password="pw")
        response = self.client.get(reverse("ops_celery_status"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["totals"]["active"], 1)

    def test_ops_celery_status_requires_staff(self):
        self.client.login(username="regular_user", password="pw")
        response = self.client.get(reverse("ops_celery_status"))
        self.assertEqual(response.status_code, 302)

    @override_settings(WEBHOOK_FAILURE_ALERT_THRESHOLD=1)
    def test_ops_webhooks_status_degrades_when_threshold_crossed(self):
        endpoint = WebhookEndpoint.objects.create(
            user=self.staff_user,
            name="Ops webhook",
            url="https://example.com/webhook",
            is_active=True,
        )
        WebhookDelivery.objects.create(
            endpoint=endpoint,
            event_type="request.status_changed",
            payload={"id": 1},
            status_code=503,
            succeeded=False,
        )

        self.client.login(username="ops_admin", password="pw")
        response = self.client.get(reverse("ops_webhook_status"))
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertGreaterEqual(payload["failed_last_hour"], 1)


class RequeueFailedWebhooksCommandTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(username="owner", password="pw")
        self.endpoint = WebhookEndpoint.objects.create(
            user=self.owner,
            name="Primary",
            url="https://example.com/notify",
            is_active=True,
            subscribed_events=["request.status_changed"],
        )

    def test_requeue_failed_webhooks_dry_run_lists_candidates(self):
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type="request.status_changed",
            payload={"request_id": 42},
            status_code=503,
            succeeded=False,
        )
        output = StringIO()
        call_command("requeue_failed_webhooks", "--dry-run", stdout=output)
        rendered = output.getvalue()
        self.assertIn("Found 1 retryable failed webhook deliveries", rendered)
        self.assertIn("Dry run complete", rendered)

    @override_settings(WEBHOOK_ASYNC_ENABLED=True)
    @patch("marketplace.management.commands.requeue_failed_webhooks.dispatch_webhook_delivery_task")
    def test_requeue_failed_webhooks_enqueues_task(self, mocked_task):
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type="request.status_changed",
            payload={"request_id": 108},
            status_code=503,
            succeeded=False,
        )
        output = StringIO()
        call_command("requeue_failed_webhooks", stdout=output)
        mocked_task.delay.assert_called_once_with(
            self.endpoint.pk,
            "request.status_changed",
            {"request_id": 108},
        )
