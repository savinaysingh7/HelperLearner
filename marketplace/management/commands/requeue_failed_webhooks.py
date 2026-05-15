import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from marketplace.models import WebhookDelivery
from marketplace.tasks import dispatch_webhook_delivery_task
from marketplace.webhooks import RetryableWebhookDeliveryError, deliver_webhook_to_endpoint

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Requeue failed webhook deliveries for retry."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=60,
            help="Look back window in minutes (default: 60).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Maximum failed deliveries to process (default: 200).",
        )
        parser.add_argument(
            "--event",
            type=str,
            default="",
            help="Optional event_type filter.",
        )
        parser.add_argument(
            "--endpoint-id",
            type=int,
            default=0,
            help="Optional endpoint id filter.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List candidate deliveries without enqueueing retries.",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Run delivery retries synchronously instead of enqueueing Celery tasks.",
        )

    def _candidate_queryset(self, minutes, event_type="", endpoint_id=0):
        cutoff = timezone.now() - timedelta(minutes=max(1, minutes))
        queryset = (
            WebhookDelivery.objects.filter(succeeded=False, created_at__gte=cutoff)
            .filter(Q(status_code__isnull=True) | Q(status_code=429) | Q(status_code__gte=500))
            .select_related("endpoint")
        )
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if endpoint_id:
            queryset = queryset.filter(endpoint_id=endpoint_id)
        return queryset.order_by("-created_at")

    def handle(self, *args, **options):
        minutes = options["minutes"]
        limit = max(1, options["limit"])
        event_type = (options.get("event") or "").strip()
        endpoint_id = options.get("endpoint_id") or 0
        dry_run = bool(options.get("dry_run"))
        sync_mode = bool(options.get("sync"))

        candidates = list(self._candidate_queryset(minutes, event_type=event_type, endpoint_id=endpoint_id)[:limit])
        self.stdout.write(
            f"Found {len(candidates)} retryable failed webhook deliveries in last {minutes} minute(s)."
        )

        if dry_run:
            for delivery in candidates[:25]:
                self.stdout.write(
                    f"- delivery_id={delivery.pk} endpoint_id={delivery.endpoint_id} "
                    f"event={delivery.event_type} status={delivery.status_code} "
                    f"created_at={delivery.created_at.isoformat()}"
                )
            self.stdout.write(self.style.SUCCESS("Dry run complete."))
            return

        use_async = bool(getattr(settings, "WEBHOOK_ASYNC_ENABLED", True)) and not sync_mode
        processed = 0
        skipped = 0

        for delivery in candidates:
            endpoint = delivery.endpoint
            if not endpoint or not endpoint.is_active:
                skipped += 1
                continue

            if use_async and hasattr(dispatch_webhook_delivery_task, "delay"):
                dispatch_webhook_delivery_task.delay(endpoint.pk, delivery.event_type, delivery.payload)
                processed += 1
                continue

            try:
                deliver_webhook_to_endpoint(
                    endpoint_id=endpoint.pk,
                    event_type=delivery.event_type,
                    payload=delivery.payload,
                    attempt=1,
                )
            except RetryableWebhookDeliveryError:
                logger.warning(
                    "Sync requeue retryable failure endpoint_id=%s event=%s delivery_id=%s",
                    endpoint.pk,
                    delivery.event_type,
                    delivery.pk,
                )
            processed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Requeue completed: processed={processed}, skipped={skipped}, async={use_async}."
            )
        )
