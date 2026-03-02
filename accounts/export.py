"""GDPR-compliant data export: download all user data as a JSON zip archive."""

import json
import logging
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone

from marketplace.models import (
    Attachment,
    ChatMessage,
    Comment,
    FreelanceJob,
    FreelanceJobProposal,
    HelpRequest,
    HelpRequestProposal,
    KPTransfer,
    PortfolioItem,
    Rating,
)
from notifications.models import Notification

logger = logging.getLogger(__name__)


def _serialize_qs(queryset, fields):
    """Serialize a queryset to a list of dicts."""
    return list(queryset.values(*fields))


@login_required
def export_my_data(request):
    """Generate and return a zip archive of all the authenticated user's data."""
    user = request.user

    # Rate limit: 1 export per 24 hours
    cache_key = f'data_export:{user.pk}'
    from django.core.cache import cache
    if cache.get(cache_key):
        return HttpResponse(
            'You can only export your data once every 24 hours.',
            status=429,
            content_type='text/plain',
        )

    data = {
        'profile': {
            'username': user.username,
            'email': user.email,
            'date_joined': str(user.date_joined),
            'knowledge_points': user.knowledge_points,
            'wallet_inr': str(user.wallet_inr),
            'bio': getattr(user, 'bio', ''),
            'trust_score': str(getattr(user, 'trust_score', 0)),
        },
        'help_requests_posted': _serialize_qs(
            HelpRequest.objects.filter(user=user),
            ['id', 'title', 'description', 'status', 'kp_bounty', 'created_at'],
        ),
        'help_requests_claimed': _serialize_qs(
            HelpRequest.objects.filter(accepted_by=user),
            ['id', 'title', 'status', 'kp_bounty', 'created_at'],
        ),
        'proposals_submitted': _serialize_qs(
            HelpRequestProposal.objects.filter(applicant=user),
            ['id', 'request_id', 'proposed_kp', 'message', 'created_at'],
        ),
        'freelance_jobs_as_client': _serialize_qs(
            FreelanceJob.objects.filter(client=user),
            ['id', 'title', 'status', 'budget_inr', 'created_at'],
        ),
        'freelance_jobs_as_freelancer': _serialize_qs(
            FreelanceJob.objects.filter(freelancer=user),
            ['id', 'title', 'status', 'budget_inr', 'created_at'],
        ),
        'job_proposals': _serialize_qs(
            FreelanceJobProposal.objects.filter(applicant=user),
            ['id', 'job_id', 'proposed_total_inr', 'message', 'created_at'],
        ),
        'comments': _serialize_qs(
            Comment.objects.filter(user=user),
            ['id', 'request_id', 'content', 'created_at'],
        ),
        'chat_messages': _serialize_qs(
            ChatMessage.objects.filter(sender=user),
            ['id', 'thread_id', 'content', 'created_at'],
        ),
        'kp_transfers_sent': _serialize_qs(
            KPTransfer.objects.filter(sender=user),
            ['id', 'recipient_id', 'amount', 'reason', 'created_at'],
        ),
        'kp_transfers_received': _serialize_qs(
            KPTransfer.objects.filter(recipient=user),
            ['id', 'sender_id', 'amount', 'reason', 'created_at'],
        ),
        'ratings_given': _serialize_qs(
            Rating.objects.filter(rater=user),
            ['id', 'rated_user_id', 'score', 'comment', 'created_at'],
        ),
        'ratings_received': _serialize_qs(
            Rating.objects.filter(rated_user=user),
            ['id', 'rater_id', 'score', 'comment', 'created_at'],
        ),
        'portfolio_items': _serialize_qs(
            PortfolioItem.objects.filter(user=user),
            ['id', 'title', 'description', 'tech_stack', 'url', 'created_at'],
        ),
        'notifications': _serialize_qs(
            Notification.objects.filter(user=user).order_by('-created_at')[:200],
            ['id', 'message', 'is_read', 'created_at'],
        ),
    }

    # Build zip archive
    buffer = BytesIO()
    with ZipFile(buffer, 'w') as zf:
        zf.writestr(
            'helperlearner_data_export.json',
            json.dumps(data, indent=2, default=str),
        )

    buffer.seek(0)

    # Set rate limit
    cache.set(cache_key, True, timeout=86400)

    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="helperlearner_data_{user.username}.zip"'
    return response
