import logging
from urllib.parse import urlencode

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from marketplace.models import HelpRequest, SavedSearch
from notifications.models import Notification

logger = logging.getLogger(__name__)


def _matching_requests(saved_search, since):
    """Return open requests matching a saved search created after `since`."""
    queryset = HelpRequest.objects.filter(status='open', created_at__gt=since)

    if saved_search.query:
        query = saved_search.query
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(skill_needed__name__icontains=query)
            | Q(user__username__icontains=query)
        )

    if saved_search.skill_id:
        queryset = queryset.filter(skill_needed_id=saved_search.skill_id)

    if saved_search.tag_id:
        queryset = queryset.filter(tags=saved_search.tag)

    return queryset.distinct()


class Command(BaseCommand):
    help = 'Notify users when new open requests match their active saved searches.'

    def handle(self, *args, **options):
        now = timezone.now()
        sent_count = 0

        active_searches = SavedSearch.objects.filter(is_active=True).select_related('user', 'skill', 'tag')
        for saved_search in active_searches:
            since = saved_search.last_notified_at or saved_search.created_at
            matches = _matching_requests(saved_search, since)
            match_count = matches.count()
            if match_count == 0:
                continue

            query_params = {}
            if saved_search.query:
                query_params['q'] = saved_search.query
            if saved_search.skill_id:
                query_params['skill'] = saved_search.skill_id
            if saved_search.tag_id and saved_search.tag:
                query_params['tag'] = saved_search.tag.slug

            link = reverse('request_list')
            if query_params:
                link = f'{link}?{urlencode(query_params)}'

            Notification.objects.create(
                user=saved_search.user,
                message=f'{match_count} new request(s) match your saved search.',
                link=link,
            )
            saved_search.last_notified_at = now
            saved_search.save(update_fields=['last_notified_at'])
            sent_count += 1

            logger.info(
                'Saved-search notification sent: search_id=%s user=%s matches=%s',
                saved_search.pk,
                saved_search.user.username,
                match_count,
            )

        self.stdout.write(self.style.SUCCESS(f'Sent {sent_count} saved-search notification(s).'))
