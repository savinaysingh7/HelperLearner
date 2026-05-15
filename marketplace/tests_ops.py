from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from notifications.models import Notification

from .models import ChatMessage, ChatThread, ChatThreadParticipant, WebhookDelivery, WebhookEndpoint


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

    @patch(
        "marketplace.advanced_views.collect_runtime_snapshot",
        return_value={
            "status": "healthy",
            "healthy": True,
            "critical_failures": [],
            "warnings": [],
            "checks": {"database": {"ok": True, "critical": True, "detail": "Database connection OK."}},
            "environment": {"debug": False, "database_engine": "django.db.backends.postgresql", "cache_backend": "locmem", "timezone": "UTC"},
            "checked_at": "2026-02-28T10:00:00+00:00",
        },
    )
    def test_ops_runtime_status_staff_can_access(self, _mock_snapshot):
        self.client.login(username="ops_admin", password="pw")
        response = self.client.get(reverse("ops_runtime_status"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["service"], "runtime")
        self.assertIn("checks", payload)

    def test_ops_runtime_status_requires_staff(self):
        self.client.login(username="regular_user", password="pw")
        response = self.client.get(reverse("ops_runtime_status"))
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


class DiagnoseRuntimeCommandTests(TestCase):
    @patch(
        "marketplace.management.commands.diagnose_runtime.collect_runtime_snapshot",
        return_value={
            "status": "warning",
            "healthy": True,
            "critical_failures": [],
            "warnings": ["ai_assist"],
            "checks": {
                "database": {"ok": True, "critical": True, "detail": "Database connection OK."},
                "ai_assist": {"ok": False, "critical": False, "detail": "GEMINI_API_KEY is not configured."},
            },
            "environment": {},
            "checked_at": "2026-02-28T10:00:00+00:00",
        },
    )
    def test_diagnose_runtime_reports_warnings_without_failing(self, _mock_snapshot):
        output = StringIO()
        call_command("diagnose_runtime", stdout=output)
        rendered = output.getvalue()
        self.assertIn("Runtime status: warning", rendered)
        self.assertIn("Non-critical warnings", rendered)

    @patch(
        "marketplace.management.commands.diagnose_runtime.collect_runtime_snapshot",
        return_value={
            "status": "degraded",
            "healthy": False,
            "critical_failures": ["database"],
            "warnings": [],
            "checks": {
                "database": {"ok": False, "critical": True, "detail": "Database connection failed."},
            },
            "environment": {},
            "checked_at": "2026-02-28T10:00:00+00:00",
        },
    )
    def test_diagnose_runtime_fails_when_critical_checks_fail(self, _mock_snapshot):
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command("diagnose_runtime", stdout=output)


class LiveNavStatusEndpointTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="nav_user",
            password="pw",
            knowledge_points=145,
            wallet_inr="98.50",
        )
        self.other = CustomUser.objects.create_user(username="nav_other", password="pw")

    def test_live_nav_status_requires_login(self):
        response = self.client.get(reverse("live_nav_status"))
        self.assertEqual(response.status_code, 302)

    def test_live_nav_status_returns_current_counts(self):
        Notification.objects.create(user=self.user, message="Unread", link="/")
        thread = ChatThread.objects.create(
            thread_type="request",
            title="Live nav thread",
            created_by=self.user,
        )
        ChatThreadParticipant.objects.create(thread=thread, user=self.user)
        ChatThreadParticipant.objects.create(thread=thread, user=self.other)
        ChatMessage.objects.create(thread=thread, sender=self.other, content="Fresh update")

        self.client.login(username="nav_user", password="pw")
        response = self.client.get(reverse("live_nav_status"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["unread_notifications_count"], 1)
        self.assertEqual(payload["unread_chat_threads_count"], 1)
        self.assertEqual(payload["knowledge_points"], 145)
        self.assertEqual(payload["wallet_inr"], "98.50")

    def test_live_nav_status_reflects_read_updates(self):
        notification = Notification.objects.create(user=self.user, message="Unread", link="/")
        thread = ChatThread.objects.create(
            thread_type="request",
            title="Read thread",
            created_by=self.user,
        )
        participation = ChatThreadParticipant.objects.create(thread=thread, user=self.user)
        ChatThreadParticipant.objects.create(thread=thread, user=self.other)
        ChatMessage.objects.create(thread=thread, sender=self.other, content="Need refresh")

        notification.is_read = True
        notification.save(update_fields=["is_read"])
        participation.last_read_at = timezone.now()
        participation.save(update_fields=["last_read_at"])

        self.client.login(username="nav_user", password="pw")
        response = self.client.get(reverse("live_nav_status"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["unread_notifications_count"], 0)
        self.assertEqual(payload["unread_chat_threads_count"], 0)
