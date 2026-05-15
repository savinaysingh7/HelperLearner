from django.db.models import Max, Q

from .models import ChatThreadParticipant


def active_experiments(request):
    """Expose active experiment assignments to templates."""
    return {
        'active_experiments': getattr(request, 'experiments', {}),
    }


def unread_chat_threads_count(request):
    """Expose unread chat-thread count for authenticated users."""
    if not request.user.is_authenticated:
        return {'unread_chat_threads_count': 0}

    participations = ChatThreadParticipant.objects.filter(user=request.user).annotate(
        latest_incoming_at=Max(
            'thread__messages__created_at',
            filter=~Q(thread__messages__sender=request.user),
        )
    )

    unread = 0
    for participation in participations:
        latest_incoming_at = participation.latest_incoming_at
        if latest_incoming_at and (
            participation.last_read_at is None or latest_incoming_at > participation.last_read_at
        ):
            unread += 1

    return {'unread_chat_threads_count': unread}
