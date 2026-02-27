import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.trust import update_user_trust_score
from .ai_assistant import generate_request_summary
from .models import (
    FreelanceJob,
    FreelanceJobProposal,
    HelpRequest,
    HelpRequestProposal,
    JobDispute,
)

logger = logging.getLogger(__name__)


def _invalidate_home_cache():
    """Bust homepage cache fragments after request/job mutations."""
    cache.delete_many(
        [
            "home:stats:v1",
            "home:recent_requests:v1",
            "home:recent_paid_jobs:v1",
        ]
    )


@receiver(post_save, sender=HelpRequest)
def generate_ai_summary_on_creation(sender, instance, created, **kwargs):
    """Automatically generate a one-sentence AI summary for new requests."""
    if not created or instance.ai_summary:
        return
    if not getattr(settings, 'AI_SUMMARY_ENABLED', True):
        return

    try:
        summary = generate_request_summary(instance.title, instance.description)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.debug('AI summary skipped due to error: %s', exc)
        return

    if summary:
        # Use update to avoid re-triggering signals
        HelpRequest.objects.filter(pk=instance.pk).update(ai_summary=summary)


@receiver(post_save, sender=FreelanceJob)
def trigger_trust_update_on_job_status_change(sender, instance, created, **kwargs):
    """Update trust score when a freelance job is completed."""
    if instance.status == 'completed' and instance.freelancer:
        update_user_trust_score(instance.freelancer)
    _invalidate_home_cache()


@receiver(post_save, sender=HelpRequest)
def trigger_trust_update_on_request_resolved(sender, instance, created, **kwargs):
    """Update trust score when a help request is resolved."""
    if instance.status == 'resolved' and instance.accepted_by:
        update_user_trust_score(instance.accepted_by)
    _invalidate_home_cache()


@receiver(post_delete, sender=HelpRequest)
def invalidate_home_cache_on_request_delete(sender, instance, **kwargs):
    """Invalidate homepage cache when a help request is deleted."""
    _invalidate_home_cache()


@receiver(post_delete, sender=FreelanceJob)
def invalidate_home_cache_on_job_delete(sender, instance, **kwargs):
    """Invalidate homepage cache when a paid job is deleted."""
    _invalidate_home_cache()


@receiver(post_save, sender=JobDispute)
def trigger_trust_update_on_dispute(sender, instance, created, **kwargs):
    """Update trust score when a dispute is created or changed."""
    if instance.job and instance.job.freelancer:
        update_user_trust_score(instance.job.freelancer)


@receiver(post_save, sender=HelpRequestProposal)
def trigger_trust_update_on_request_proposal(sender, instance, created, **kwargs):
    """Update responsiveness metrics when a help request proposal is submitted."""
    if created and instance.applicant:
        update_user_trust_score(instance.applicant)


@receiver(post_save, sender=FreelanceJobProposal)
def trigger_trust_update_on_job_proposal(sender, instance, created, **kwargs):
    """Update responsiveness metrics when a job proposal is submitted."""
    if created and instance.applicant:
        update_user_trust_score(instance.applicant)
