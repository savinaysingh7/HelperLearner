from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from .forms import ChatMessageForm
from .models import (
    ChatMessage,
    ChatThread,
    ChatThreadParticipant,
    FreelanceJob,
    HelpRequest,
    Workspace,
    WorkspaceMembership,
)
from .realtime import emit_user_event


def _is_ajax_request(request):
    """Return True when the request expects a JSON-style asynchronous response."""
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
    )


def _serialize_chat_message(chat_message):
    """Serialize a chat message for realtime and AJAX responses."""
    created_local = timezone.localtime(chat_message.created_at)
    return {
        'message_id': chat_message.pk,
        'thread_id': chat_message.thread_id,
        'sender_id': chat_message.sender_id,
        'sender': chat_message.sender.username,
        'content': chat_message.content,
        'message': chat_message.content[:160],
        'created_at_iso': chat_message.created_at.isoformat(),
        'created_at_label': created_local.strftime('%b %d, %H:%M'),
    }


def _sync_thread_participants(thread, participant_ids):
    """Ensure chat thread participants exactly match the provided user ids."""
    normalized_ids = {user_id for user_id in participant_ids if user_id}
    if not normalized_ids:
        return

    existing_ids = set(
        ChatThreadParticipant.objects.filter(thread=thread).values_list('user_id', flat=True)
    )
    missing_ids = [user_id for user_id in normalized_ids if user_id not in existing_ids]
    if missing_ids:
        ChatThreadParticipant.objects.bulk_create(
            [ChatThreadParticipant(thread=thread, user_id=user_id) for user_id in missing_ids]
        )

    ChatThreadParticipant.objects.filter(thread=thread).exclude(user_id__in=normalized_ids).delete()


def _broadcast_chat_message(chat_message):
    """Emit websocket event for all recipients in a thread except the sender."""
    thread = chat_message.thread
    link = reverse('chat_thread_detail', args=[thread.pk])
    payload = _serialize_chat_message(chat_message)
    payload.update(
        {
            'thread_title': thread.display_title,
            'link': link,
        }
    )

    recipient_ids = ChatThreadParticipant.objects.filter(thread=thread).exclude(
        user_id=chat_message.sender_id
    ).values_list('user_id', flat=True)
    for user_id in recipient_ids:
        emit_user_event(user_id, 'chat.message', payload)


def _mark_thread_as_read(participation):
    """Mark thread as read for a participant."""
    now = timezone.now()
    ChatThreadParticipant.objects.filter(pk=participation.pk).update(last_read_at=now)
    participation.last_read_at = now


@login_required
def chat_inbox(request):
    """List all chat threads for the logged-in user with unread indicators."""
    participations = list(
        ChatThreadParticipant.objects.filter(user=request.user)
        .select_related(
            'thread',
            'thread__help_request',
            'thread__job',
            'thread__workspace',
        )
        .annotate(
            latest_incoming_at=Max(
                'thread__messages__created_at',
                filter=~Q(thread__messages__sender=request.user),
            )
        )
        .order_by('-thread__last_message_at', '-thread__updated_at')
    )

    thread_ids = [item.thread_id for item in participations]
    latest_messages = (
        ChatMessage.objects.filter(thread_id__in=thread_ids)
        .select_related('sender')
        .order_by('thread_id', '-created_at')
    )
    latest_message_by_thread = {}
    for item in latest_messages:
        latest_message_by_thread.setdefault(item.thread_id, item)

    rows = []
    for participation in participations:
        latest_incoming = participation.latest_incoming_at
        is_unread = bool(
            latest_incoming and (participation.last_read_at is None or latest_incoming > participation.last_read_at)
        )
        rows.append(
            {
                'participation': participation,
                'thread': participation.thread,
                'latest_message': latest_message_by_thread.get(participation.thread_id),
                'is_unread': is_unread,
            }
        )

    return render(
        request,
        'marketplace/chat_inbox.html',
        {'rows': rows},
    )


@login_required
@csrf_protect
def chat_thread_detail(request, thread_id):
    """Render a chat thread and allow participants to post new messages."""
    participation = get_object_or_404(
        ChatThreadParticipant.objects.select_related(
            'thread',
            'thread__help_request',
            'thread__job',
            'thread__workspace',
        ),
        thread_id=thread_id,
        user=request.user,
    )
    thread = participation.thread

    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                chat_message = form.save(commit=False)
                chat_message.thread = thread
                chat_message.sender = request.user
                chat_message.save()
                ChatThread.objects.filter(pk=thread.pk).update(last_message_at=chat_message.created_at)
                ChatThreadParticipant.objects.filter(pk=participation.pk).update(last_read_at=chat_message.created_at)

            _broadcast_chat_message(chat_message)
            if _is_ajax_request(request):
                return JsonResponse({'ok': True, 'message': _serialize_chat_message(chat_message)})
            return redirect('chat_thread_detail', thread_id=thread.pk)
        if _is_ajax_request(request):
            return JsonResponse({'ok': False, 'errors': form.errors.get_json_data()}, status=400)
    else:
        form = ChatMessageForm()

    after_id_param = request.GET.get('after_id')
    if after_id_param is not None:
        try:
            after_id = int(after_id_param)
        except (TypeError, ValueError):
            return JsonResponse({'messages': []})

        new_messages = list(
            thread.messages.select_related('sender')
            .filter(pk__gt=after_id)
            .order_by('created_at')
        )
        if new_messages:
            _mark_thread_as_read(participation)
        return JsonResponse({'messages': [_serialize_chat_message(item) for item in new_messages]})

    chat_messages = list(
        thread.messages.select_related('sender').order_by('-created_at')[:120]
    )
    chat_messages.reverse()
    participants = thread.participations.select_related('user').order_by('user__username')
    _mark_thread_as_read(participation)

    origin_url = None
    origin_label = None
    if thread.help_request_id:
        origin_label = 'Back to request'
        origin_url = reverse('request_detail', args=[thread.help_request_id])
    elif thread.job_id:
        origin_label = 'Back to job'
        origin_url = reverse('freelance_job_detail', args=[thread.job_id])
    elif thread.workspace_id:
        origin_label = 'Back to workspace'
        origin_url = reverse('workspace_detail', args=[thread.workspace.slug])

    return render(
        request,
        'marketplace/chat_thread.html',
        {
            'thread': thread,
            'chat_messages': chat_messages,
            'participants': participants,
            'form': form,
            'origin_url': origin_url,
            'origin_label': origin_label,
        },
    )


@login_required
def request_chat(request, pk):
    """Open the chat room for a claimed help request."""
    help_request = get_object_or_404(
        HelpRequest.objects.select_related('user', 'accepted_by'),
        pk=pk,
    )
    if not help_request.accepted_by_id:
        messages.info(request, 'Chat will unlock when a helper is assigned.')
        return redirect('request_detail', pk=pk)

    if request.user.pk not in {help_request.user_id, help_request.accepted_by_id}:
        messages.error(request, 'Only the requester and assigned helper can open this chat.')
        return redirect('request_detail', pk=pk)

    thread, _ = ChatThread.objects.get_or_create(
        help_request=help_request,
        defaults={
            'thread_type': 'request',
            'title': f'Request: {help_request.title}',
            'created_by': request.user,
        },
    )
    _sync_thread_participants(thread, [help_request.user_id, help_request.accepted_by_id])
    return redirect('chat_thread_detail', thread_id=thread.pk)


@login_required
def job_chat(request, pk):
    """Open the chat room for a paid job once a freelancer is assigned."""
    job = get_object_or_404(
        FreelanceJob.objects.select_related('client', 'freelancer'),
        pk=pk,
    )
    if not job.freelancer_id:
        messages.info(request, 'Chat will unlock when a freelancer is assigned.')
        return redirect('freelance_job_detail', pk=pk)

    if request.user.pk not in {job.client_id, job.freelancer_id}:
        messages.error(request, 'Only the client and assigned freelancer can open this chat.')
        return redirect('freelance_job_detail', pk=pk)

    thread, _ = ChatThread.objects.get_or_create(
        job=job,
        defaults={
            'thread_type': 'job',
            'title': f'Job: {job.title}',
            'created_by': request.user,
        },
    )
    _sync_thread_participants(thread, [job.client_id, job.freelancer_id])
    return redirect('chat_thread_detail', thread_id=thread.pk)


@login_required
def workspace_chat(request, slug):
    """Open the workspace group chat for workspace members."""
    workspace = get_object_or_404(Workspace.objects.prefetch_related('memberships'), slug=slug)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    thread, _ = ChatThread.objects.get_or_create(
        workspace=workspace,
        defaults={
            'thread_type': 'workspace',
            'title': f'Workspace: {workspace.name}',
            'created_by': request.user,
        },
    )
    participant_ids = workspace.memberships.values_list('user_id', flat=True)
    _sync_thread_participants(thread, participant_ids)
    return redirect('chat_thread_detail', thread_id=thread.pk)
