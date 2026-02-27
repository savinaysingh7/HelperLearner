from django.db.models.signals import post_save
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


@receiver(post_save, sender=HelpRequest)
def generate_ai_summary_on_creation(sender, instance, created, **kwargs):
    """Automatically generate a one-sentence AI summary for new requests."""
    if created and not instance.ai_summary:
        summary = generate_request_summary(instance.title, instance.description)
        if summary:
            # Use update to avoid re-triggering signals
            HelpRequest.objects.filter(pk=instance.pk).update(ai_summary=summary)


@receiver(post_save, sender=FreelanceJob)
def trigger_trust_update_on_job_status_change(sender, instance, created, **kwargs):
    """Update trust score when a freelance job is completed."""
    if instance.status == 'completed' and instance.freelancer:
        update_user_trust_score(instance.freelancer)


@receiver(post_save, sender=HelpRequest)
def trigger_trust_update_on_request_resolved(sender, instance, created, **kwargs):
    """Update trust score when a help request is resolved."""
    if instance.status == 'resolved' and instance.accepted_by:
        update_user_trust_score(instance.accepted_by)


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
