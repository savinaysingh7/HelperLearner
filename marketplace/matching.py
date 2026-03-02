"""AI-powered helper matching — recommends the best helpers for a given request."""

import logging

from django.conf import settings
from django.db.models import Avg, Count, Q

from accounts.models import CustomUser
from .models import HelpRequest, Rating

logger = logging.getLogger(__name__)


def get_recommended_helpers(help_request, limit=5):
    """
    Score and rank helpers for a given help request.

    Scoring factors:
    - Skill match (has the needed skill): +40 points
    - Average rating: up to +25 points
    - Number of resolved requests: up to +20 points
    - Trust score: up to +15 points
    """
    if not help_request:
        return []

    skill = help_request.skill_needed
    poster = help_request.user

    # Base queryset: active users who are not the poster and not suspended
    candidates = (
        CustomUser.objects.filter(is_active=True, is_suspended=False)
        .exclude(pk=poster.pk)
        .annotate(
            resolved_count=Count(
                'claimed_requests',
                filter=Q(claimed_requests__status='resolved'),
            ),
            avg_rating=Avg(
                'ratings_received__score',
            ),
        )
    )

    scored = []
    for user in candidates.iterator():
        score = 0

        # Skill match
        if skill and user.skills.filter(pk=skill.pk).exists():
            score += 40

        # Average rating (0-5 scale → 0-25 points)
        avg = user.avg_rating or 0
        score += min(avg * 5, 25)

        # Resolved count (capped at 20 points)
        score += min(user.resolved_count * 2, 20)

        # Trust score (0-100 → 0-15 points)
        trust = float(getattr(user, 'trust_score', 0) or 0)
        score += min(trust * 0.15, 15)

        if score > 0:
            scored.append((user, round(score, 1)))

    # Sort by score descending and take top N
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
