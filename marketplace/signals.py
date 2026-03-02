"""Django signals for the marketplace app — lifecycle, trust, cache, and email notifications."""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.trust import update_user_trust_score
from notifications.emailing import send_templated_email
from .ai_assistant import generate_request_summary
from .models import (
    FreelanceJob,
    FreelanceJobProposal,
    HelpRequest,
    HelpRequestProposal,
    JobDispute,
    JobMilestone,
)

logger = logging.getLogger(__name__)

User = get_user_model()


def _site_url():
    """Return base site URL for email links."""
    return getattr(settings, 'SITE_URL', 'https://helperlearner.onrender.com')


def _invalidate_home_cache():
    """Bust homepage cache fragments after request/job mutations."""
    cache.delete_many(
        [
            "home:stats:v1",
            "home:recent_requests:v1",
            "home:recent_paid_jobs:v1",
        ]
    )


# ── Welcome email on signup ──────────────────────────────────────────────────

@receiver(post_save, sender=User)
def send_welcome_email_on_signup(sender, instance, created, **kwargs):
    """Send welcome email when a new user signs up."""
    if not created or not instance.email:
        return
    send_templated_email(
        subject='Welcome to HelperLearner! 🎉',
        template_name='emails/welcome.html',
        context={'username': instance.username, 'site_url': _site_url()},
        recipient_email=instance.email,
    )


# ── AI summary on creation ───────────────────────────────────────────────────

@receiver(post_save, sender=HelpRequest)
def generate_ai_summary_on_creation(sender, instance, created, **kwargs):
    """Automatically generate a one-sentence AI summary for new requests."""
    if not created or instance.ai_summary:
        return
    if not getattr(settings, 'AI_SUMMARY_ENABLED', True):
        return

    try:
        summary = generate_request_summary(instance.title, instance.description)
    except Exception as exc:
        logger.debug('AI summary skipped due to error: %s', exc)
        return

    if summary:
        HelpRequest.objects.filter(pk=instance.pk).update(ai_summary=summary)


# ── Request lifecycle emails ─────────────────────────────────────────────────

@receiver(post_save, sender=HelpRequest)
def send_request_lifecycle_emails(sender, instance, created, **kwargs):
    """Send email when a request is claimed or resolved."""
    if created:
        return

    if instance.status == 'in_progress' and instance.accepted_by and instance.user.email:
        send_templated_email(
            subject=f'Your request "{instance.title}" has been claimed!',
            template_name='emails/request_claimed.html',
            context={
                'helper_username': instance.accepted_by.username,
                'request_title': instance.title,
                'kp_bounty': instance.kp_bounty,
                'request_url': f'{_site_url()}/requests/{instance.pk}/',
            },
            recipient_email=instance.user.email,
        )

    if instance.status == 'resolved' and instance.accepted_by and instance.user.email:
        send_templated_email(
            subject=f'Request "{instance.title}" has been resolved! ✅',
            template_name='emails/request_resolved.html',
            context={
                'helper_username': instance.accepted_by.username,
                'request_title': instance.title,
                'kp_bounty': instance.kp_bounty,
                'request_url': f'{_site_url()}/requests/{instance.pk}/',
            },
            recipient_email=instance.user.email,
        )


# ── Trust updates ────────────────────────────────────────────────────────────

@receiver(post_save, sender=FreelanceJob)
def trigger_trust_update_on_job_status_change(sender, instance, created, **kwargs):
    if instance.status == 'completed' and instance.freelancer:
        update_user_trust_score(instance.freelancer)
    _invalidate_home_cache()


@receiver(post_save, sender=HelpRequest)
def trigger_trust_update_on_request_resolved(sender, instance, created, **kwargs):
    if instance.status == 'resolved' and instance.accepted_by:
        update_user_trust_score(instance.accepted_by)
    _invalidate_home_cache()


@receiver(post_delete, sender=HelpRequest)
def invalidate_home_cache_on_request_delete(sender, instance, **kwargs):
    _invalidate_home_cache()


@receiver(post_delete, sender=FreelanceJob)
def invalidate_home_cache_on_job_delete(sender, instance, **kwargs):
    _invalidate_home_cache()


@receiver(post_save, sender=JobDispute)
def trigger_trust_update_on_dispute(sender, instance, created, **kwargs):
    if instance.job and instance.job.freelancer:
        update_user_trust_score(instance.job.freelancer)


@receiver(post_save, sender=HelpRequestProposal)
def trigger_trust_update_on_request_proposal(sender, instance, created, **kwargs):
    if created and instance.applicant:
        update_user_trust_score(instance.applicant)


@receiver(post_save, sender=FreelanceJobProposal)
def trigger_trust_update_on_job_proposal(sender, instance, created, **kwargs):
    if created and instance.applicant:
        update_user_trust_score(instance.applicant)


# ── Milestone email notifications ────────────────────────────────────────────

@receiver(post_save, sender=JobMilestone)
def send_milestone_emails(sender, instance, created, **kwargs):
    """Send email notifications for milestone status changes."""
    job = instance.job
    if not job:
        return

    if instance.status == 'submitted' and job.client and job.client.email:
        send_templated_email(
            subject=f'Milestone submitted on "{job.title}"',
            template_name='emails/job_milestone_submitted.html',
            context={
                'freelancer_username': job.freelancer.username if job.freelancer else 'Freelancer',
                'job_title': job.title,
                'milestone_title': instance.title,
                'milestone_amount': str(instance.amount_inr),
                'job_url': f'{_site_url()}/jobs/{job.pk}/',
            },
            recipient_email=job.client.email,
        )

    if instance.status == 'released' and job.freelancer and job.freelancer.email:
        send_templated_email(
            subject=f'Payment released for milestone on "{job.title}" 💰',
            template_name='emails/job_milestone_released.html',
            context={
                'job_title': job.title,
                'milestone_title': instance.title,
                'milestone_amount': str(instance.amount_inr),
                'job_url': f'{_site_url()}/jobs/{job.pk}/',
            },
            recipient_email=job.freelancer.email,
        )
