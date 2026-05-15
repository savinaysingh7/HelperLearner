import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification

from marketplace.models import FraudAlert, FreelanceJob, JobMilestone, MilestoneDeliverable
from marketplace.services import evaluate_job_collusion, record_wallet_entry
from marketplace.webhooks import dispatch_webhook_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run SLA reminders and optional milestone auto-release rules.'

    def handle(self, *args, **options):
        now = timezone.now()
        reminder_count = 0
        auto_release_count = 0

        breached_jobs = FreelanceJob.objects.filter(
            status='open',
            first_response_at__isnull=True,
            response_due_at__isnull=False,
            response_due_at__lt=now,
        )

        for job in breached_jobs.select_related('client'):
            should_notify = (
                job.last_sla_reminder_at is None
                or (now - job.last_sla_reminder_at).total_seconds() >= 6 * 3600
            )
            if not should_notify:
                continue

            Notification.objects.create(
                user=job.client,
                message=f'SLA reminder: no freelancer response yet for "{job.title}".',
                link=f'/jobs/{job.pk}/',
            )
            FraudAlert.objects.create(
                user=job.client,
                alert_type='sla_breach',
                severity='low',
                description=f'No response received for job #{job.pk} before SLA deadline.',
                metadata={'job_id': job.pk, 'response_due_at': job.response_due_at.isoformat()},
            )
            job.last_sla_reminder_at = now
            job.save(update_fields=['last_sla_reminder_at', 'updated_at'])
            reminder_count += 1
            logger.info('SLA reminder created for job %s', job.pk)

        auto_release_jobs = FreelanceJob.objects.filter(status='in_progress', auto_release_hours__gt=0).select_related('client', 'freelancer')
        for job in auto_release_jobs:
            if not job.freelancer_id:
                continue

            cutoff = now - timedelta(hours=job.auto_release_hours)
            milestones = JobMilestone.objects.filter(
                job=job,
                status='submitted',
                submitted_at__lt=cutoff,
            ).order_by('sequence')

            for milestone in milestones:
                with transaction.atomic():
                    locked_job = FreelanceJob.objects.select_for_update().get(pk=job.pk)
                    locked_milestone = JobMilestone.objects.select_for_update().get(pk=milestone.pk)
                    if locked_job.status != 'in_progress' or locked_milestone.status != 'submitted':
                        continue
                    if locked_job.escrow_inr < locked_milestone.amount_inr:
                        continue

                    deliverable = MilestoneDeliverable.objects.filter(milestone=locked_milestone).first()
                    if deliverable and deliverable.status == 'revision_requested':
                        continue
                    if deliverable and deliverable.status != 'approved':
                        deliverable.status = 'approved'
                        deliverable.approved_at = now
                        deliverable.save(update_fields=['status', 'approved_at', 'updated_at'])

                    freelancer = locked_job.freelancer.__class__.objects.select_for_update().get(pk=locked_job.freelancer_id)
                    freelancer.wallet_inr += locked_milestone.amount_inr
                    freelancer.save(update_fields=['wallet_inr'])

                    locked_job.escrow_inr -= locked_milestone.amount_inr
                    locked_milestone.status = 'released'
                    locked_milestone.released_at = now
                    locked_milestone.save(update_fields=['status', 'released_at'])

                    all_released = not locked_job.milestones.exclude(status='released').exists()
                    if all_released:
                        locked_job.status = 'completed'
                    locked_job.save(update_fields=['escrow_inr', 'status', 'updated_at'])

                    record_wallet_entry(
                        user=freelancer,
                        direction='credit',
                        amount_inr=locked_milestone.amount_inr,
                        source_type='job_milestone_auto_release',
                        reference_id=locked_milestone.pk,
                        description=f'Auto-release after SLA window for job #{locked_job.pk}',
                    )
                    if all_released:
                        evaluate_job_collusion(locked_job)

                    Notification.objects.create(
                        user=freelancer,
                        message=f'Auto-release processed for milestone "{locked_milestone.title}".',
                        link=f'/jobs/{locked_job.pk}/',
                    )
                    Notification.objects.create(
                        user=locked_job.client,
                        message=f'Milestone "{locked_milestone.title}" auto-released after SLA window.',
                        link=f'/jobs/{locked_job.pk}/',
                    )
                    dispatch_webhook_event(
                        locked_job.client,
                        'milestone.auto_released',
                        {
                            'job_id': locked_job.pk,
                            'milestone_id': locked_milestone.pk,
                            'amount_inr': str(locked_milestone.amount_inr),
                        },
                    )
                    auto_release_count += 1
                    logger.info('Auto-released milestone %s for job %s', locked_milestone.pk, locked_job.pk)

        self.stdout.write(self.style.SUCCESS(f'SLA reminders sent: {reminder_count}, milestones auto-released: {auto_release_count}'))
