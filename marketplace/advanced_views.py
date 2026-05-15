import logging
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from accounts.models import CustomUser
from accounts.query_utils import annotate_user_metrics
from accounts.trust import compute_trust_score_v2
from accounts.utils import get_client_ip, log_event
from helperlearner_root.runtime_checks import collect_runtime_snapshot
from notifications.models import Notification

from .forms import (
    ApiKeyCreateForm,
    AttachmentUploadForm,
    DeliverableRevisionForm,
    DeliverableSubmissionForm,
    ModerationFlagForm,
    PortfolioItemForm,
    WebhookEndpointForm,
    WorkspaceCreateForm,
    WorkspaceInviteForm,
    WorkspaceTransferForm,
)
from .models import (
    Comment,
    ChatThreadParticipant,
    Experiment,
    FraudAlert,
    FreelanceJob,
    FreelanceJobProposal,
    HelpRequest,
    HelpRequestProposal,
    IntegrationApiKey,
    JobDispute,
    JobMilestone,
    MilestoneDeliverable,
    ModerationFlag,
    PortfolioItem,
    SavedSearch,
    WebhookDelivery,
    WebhookEndpoint,
    Workspace,
    WorkspaceMembership,
    WorkspaceWalletEntry,
)
from .realtime import emit_user_event
from .webhooks import dispatch_webhook_event

logger = logging.getLogger(__name__)


def _mask_broker_url(raw_url):
    """Mask credentials from broker URL for safe diagnostics output."""
    if not raw_url:
        return ''
    try:
        parsed = urlsplit(raw_url)
        netloc = parsed.netloc
        if '@' not in netloc:
            return raw_url
        creds, host = netloc.split('@', 1)
        if ':' in creds:
            username = creds.split(':', 1)[0]
        else:
            username = creds
        masked_netloc = f'{username}:***@{host}'
        return urlunsplit((parsed.scheme, masked_netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return raw_url


def _collect_celery_worker_snapshot():
    """Collect celery worker availability and queue activity snapshot."""
    from helperlearner_root.celery import celery_app

    if celery_app is None:
        return {
            'healthy': False,
            'configured': False,
            'workers': [],
            'totals': {'active': 0, 'reserved': 0, 'scheduled': 0},
            'error': 'celery_not_configured',
        }

    try:
        inspector = celery_app.control.inspect(timeout=settings.CELERY_MONITOR_TIMEOUT_SECONDS)
        ping = inspector.ping() or {}
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
    except Exception as exc:
        return {
            'healthy': False,
            'configured': True,
            'workers': [],
            'totals': {'active': 0, 'reserved': 0, 'scheduled': 0},
            'error': str(exc),
        }

    worker_names = sorted(set(list(ping.keys()) + list(active.keys()) + list(reserved.keys()) + list(scheduled.keys())))
    workers = []
    for name in worker_names:
        workers.append(
            {
                'name': name,
                'online': name in ping,
                'active': len(active.get(name, [])),
                'reserved': len(reserved.get(name, [])),
                'scheduled': len(scheduled.get(name, [])),
            }
        )

    total_active = sum(item['active'] for item in workers)
    total_reserved = sum(item['reserved'] for item in workers)
    total_scheduled = sum(item['scheduled'] for item in workers)
    healthy = bool(workers and all(item['online'] for item in workers))

    return {
        'healthy': healthy,
        'configured': True,
        'workers': workers,
        'totals': {
            'active': total_active,
            'reserved': total_reserved,
            'scheduled': total_scheduled,
        },
        'error': '',
    }


def _completion_rate_for_user(user):
    """Compute completion rate across KP and paid work contributions."""
    help_total = HelpRequest.objects.filter(accepted_by=user).count()
    help_done = HelpRequest.objects.filter(accepted_by=user, status='resolved').count()
    job_total = FreelanceJob.objects.filter(freelancer=user).count()
    job_done = FreelanceJob.objects.filter(freelancer=user, status='completed').count()
    total = help_total + job_total
    if total == 0:
        return 0.0
    return round(((help_done + job_done) / total) * 100, 2)


def _unread_chat_threads_for_user(user):
    """Return unread chat-thread count for a user."""
    participations = ChatThreadParticipant.objects.filter(user=user).annotate(
        latest_incoming_at=Max(
            'thread__messages__created_at',
            filter=~Q(thread__messages__sender=user),
        )
    )
    unread = 0
    for participation in participations:
        latest_incoming_at = participation.latest_incoming_at
        if latest_incoming_at and (
            participation.last_read_at is None or latest_incoming_at > participation.last_read_at
        ):
            unread += 1
    return unread


@login_required
def compare_request_proposals(request, pk):
    """Display side-by-side comparison of proposals for a single help request."""
    help_request = get_object_or_404(HelpRequest.objects.select_related('user', 'skill_needed'), pk=pk)
    if request.user != help_request.user:
        messages.error(request, 'Only the requester can compare proposals.')
        return redirect('request_detail', pk=pk)

    proposal_qs = (
        HelpRequestProposal.objects.filter(request=help_request)
        .select_related('applicant')
        .order_by('proposed_kp', 'created_at')
    )

    # Batch-annotate all applicant metrics in one query
    applicant_ids = [p.applicant_id for p in proposal_qs]
    annotated_map = {}
    if applicant_ids:
        for user_obj in annotate_user_metrics(CustomUser.objects.filter(pk__in=applicant_ids)):
            annotated_map[user_obj.pk] = user_obj

    rows = []
    for proposal in proposal_qs:
        applicant = annotated_map.get(proposal.applicant_id, proposal.applicant)
        rows.append(
            {
                'proposal': proposal,
                'applicant': applicant,
                'completion_rate': _completion_rate_for_user(proposal.applicant),
            }
        )

    return render(
        request,
        'marketplace/compare_request_proposals.html',
        {
            'request_obj': help_request,
            'rows': rows,
        },
    )


@login_required
def compare_job_proposals(request, pk):
    """Display side-by-side comparison of proposals for a paid freelance job."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client', 'skill_needed'), pk=pk)
    if request.user != job.client:
        messages.error(request, 'Only the client can compare proposals.')
        return redirect('freelance_job_detail', pk=pk)

    proposal_qs = (
        FreelanceJobProposal.objects.filter(job=job)
        .select_related('applicant')
        .prefetch_related('milestones')
        .order_by('proposed_total_inr', 'created_at')
    )

    # Batch-annotate all applicant metrics in one query
    applicant_ids = [p.applicant_id for p in proposal_qs]
    annotated_map = {}
    if applicant_ids:
        for user_obj in annotate_user_metrics(CustomUser.objects.filter(pk__in=applicant_ids)):
            annotated_map[user_obj.pk] = user_obj

    rows = []
    for proposal in proposal_qs:
        applicant = annotated_map.get(proposal.applicant_id, proposal.applicant)
        rows.append(
            {
                'proposal': proposal,
                'applicant': applicant,
                'completion_rate': _completion_rate_for_user(proposal.applicant),
                'milestone_total': proposal.milestones.aggregate(total=Sum('amount_inr'))['total'] or Decimal('0.00'),
            }
        )

    return render(
        request,
        'marketplace/compare_job_proposals.html',
        {
            'job': job,
            'rows': rows,
        },
    )


@login_required
@csrf_protect
def submit_milestone_deliverable(request, pk, milestone_id):
    """Allow freelancer to submit milestone proof and mark milestone submitted."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client', 'freelancer'), pk=pk)
    milestone = get_object_or_404(JobMilestone, pk=milestone_id, job=job)

    if request.user != job.freelancer:
        messages.error(request, 'Only the assigned freelancer can submit deliverables.')
        return redirect('freelance_job_detail', pk=pk)

    if job.status != 'in_progress':
        messages.error(request, 'Deliverables can only be submitted while the job is in progress.')
        return redirect('freelance_job_detail', pk=pk)

    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('freelance_job_detail', pk=pk)

    form = DeliverableSubmissionForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return redirect('freelance_job_detail', pk=pk)

    with transaction.atomic():
        milestone = JobMilestone.objects.select_for_update().get(pk=milestone.pk)
        deliverable, _ = MilestoneDeliverable.objects.select_for_update().get_or_create(
            milestone=milestone,
            defaults={'submitted_by': request.user},
        )
        deliverable.submitted_by = request.user
        deliverable.proof_text = form.cleaned_data['proof_text']
        if form.cleaned_data.get('proof_file'):
            deliverable.proof_file = form.cleaned_data['proof_file']
        deliverable.status = 'submitted'
        deliverable.revision_note = ''
        deliverable.requested_revision_at = None
        deliverable.save()

        milestone.status = 'submitted'
        milestone.submitted_at = timezone.now()
        milestone.save(update_fields=['status', 'submitted_at'])

    Notification.objects.create(
        user=job.client,
        message=f'Deliverable submitted for milestone "{milestone.title}".',
        link=f'/jobs/{job.pk}/',
    )
    emit_user_event(
        job.client_id,
        'milestone.submitted',
        {'job_id': job.pk, 'milestone_id': milestone.pk, 'title': milestone.title},
    )

    dispatch_webhook_event(
        job.client,
        'milestone.submitted',
        {
            'job_id': job.pk,
            'milestone_id': milestone.pk,
            'milestone_title': milestone.title,
            'freelancer': request.user.username,
        },
    )

    messages.success(request, 'Deliverable submitted successfully.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def request_milestone_revision(request, pk, milestone_id):
    """Allow client to request revisions on a submitted deliverable."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client', 'freelancer'), pk=pk)
    milestone = get_object_or_404(JobMilestone, pk=milestone_id, job=job)

    if request.user != job.client:
        messages.error(request, 'Only the client can request revisions.')
        return redirect('freelance_job_detail', pk=pk)

    deliverable = get_object_or_404(MilestoneDeliverable, milestone=milestone)
    form = DeliverableRevisionForm(request.POST, instance=deliverable)
    if not form.is_valid():
        messages.error(request, 'Please provide a revision note.')
        return redirect('freelance_job_detail', pk=pk)

    with transaction.atomic():
        deliverable = MilestoneDeliverable.objects.select_for_update().get(pk=deliverable.pk)
        deliverable.revision_note = form.cleaned_data['revision_note']
        deliverable.status = 'revision_requested'
        deliverable.requested_revision_at = timezone.now()
        deliverable.save(update_fields=['revision_note', 'status', 'requested_revision_at', 'updated_at'])

        milestone = JobMilestone.objects.select_for_update().get(pk=milestone.pk)
        milestone.status = 'pending'
        milestone.save(update_fields=['status'])

    if job.freelancer_id:
        Notification.objects.create(
            user=job.freelancer,
            message=f'Revision requested for milestone "{milestone.title}".',
            link=f'/jobs/{job.pk}/',
        )
        emit_user_event(
            job.freelancer_id,
            'milestone.revision_requested',
            {'job_id': job.pk, 'milestone_id': milestone.pk, 'title': milestone.title},
        )

    dispatch_webhook_event(
        job.client,
        'milestone.revision_requested',
        {
            'job_id': job.pk,
            'milestone_id': milestone.pk,
            'milestone_title': milestone.title,
            'note': deliverable.revision_note,
        },
    )

    messages.success(request, 'Revision request sent to freelancer.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def approve_milestone_deliverable(request, pk, milestone_id):
    """Allow client to approve submitted deliverable before payment release."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client', 'freelancer'), pk=pk)
    milestone = get_object_or_404(JobMilestone, pk=milestone_id, job=job)
    if request.user != job.client:
        messages.error(request, 'Only the client can approve deliverables.')
        return redirect('freelance_job_detail', pk=pk)

    deliverable = get_object_or_404(MilestoneDeliverable, milestone=milestone)
    if milestone.status != 'submitted':
        messages.error(request, 'Only submitted milestones can be approved.')
        return redirect('freelance_job_detail', pk=pk)

    deliverable.status = 'approved'
    deliverable.approved_at = timezone.now()
    deliverable.save(update_fields=['status', 'approved_at', 'updated_at'])

    dispatch_webhook_event(
        job.client,
        'milestone.approved',
        {
            'job_id': job.pk,
            'milestone_id': milestone.pk,
            'milestone_title': milestone.title,
        },
    )

    messages.success(request, 'Deliverable approved. You can now release payment.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def upload_attachment(request, target_type, target_id):
    """Attach files to requests/jobs/comments through a generic uploader endpoint."""
    target_map = {
        'request': HelpRequest,
        'job': FreelanceJob,
        'comment': Comment,
    }
    if target_type not in target_map:
        messages.error(request, 'Unsupported attachment target.')
        return redirect('home')

    model_cls = target_map[target_type]
    target_obj = get_object_or_404(model_cls, pk=target_id)

    # Ownership check: verify user is involved with the target entity
    if target_type == 'request':
        if request.user.pk not in {target_obj.user_id, target_obj.accepted_by_id}:
            messages.error(request, 'You can only attach files to your own requests.')
            return redirect(request.META.get('HTTP_REFERER', 'home'))
    elif target_type == 'job':
        if request.user.pk not in {target_obj.client_id, target_obj.freelancer_id}:
            messages.error(request, 'You can only attach files to jobs you are involved in.')
            return redirect(request.META.get('HTTP_REFERER', 'home'))
    elif target_type == 'comment':
        if request.user.pk != target_obj.user_id:
            messages.error(request, 'You can only attach files to your own comments.')
            return redirect(request.META.get('HTTP_REFERER', 'home'))

    form = AttachmentUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Please upload a valid file.')
        return redirect(request.META.get('HTTP_REFERER', 'home'))

    attachment = form.save(commit=False)
    attachment.uploaded_by = request.user
    attachment.content_type = ContentType.objects.get_for_model(model_cls)
    attachment.object_id = target_obj.pk
    attachment.save()

    messages.success(request, 'Attachment uploaded successfully.')
    return redirect(request.META.get('HTTP_REFERER', 'home'))


def _workspace_membership(workspace, user):
    """Return membership for a user in a workspace or None."""
    if not user.is_authenticated:
        return None
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()


@login_required
@csrf_protect
def workspace_list(request):
    """List and create team workspaces for the authenticated user."""
    memberships = WorkspaceMembership.objects.filter(user=request.user).select_related('workspace').order_by('-joined_at')

    if request.method == 'POST':
        form = WorkspaceCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                workspace = form.save(commit=False)
                workspace.owner = request.user
                workspace.save()
                WorkspaceMembership.objects.create(workspace=workspace, user=request.user, role='owner')
            messages.success(request, 'Workspace created successfully.')
            return redirect('workspace_detail', slug=workspace.slug)
    else:
        form = WorkspaceCreateForm()

    return render(
        request,
        'marketplace/workspace_list.html',
        {
            'memberships': memberships,
            'form': form,
        },
    )


@login_required
@csrf_protect
def workspace_detail(request, slug):
    """Show workspace members, shared wallet history, and management actions."""
    workspace = get_object_or_404(Workspace.objects.prefetch_related('memberships__user', 'wallet_entries'), slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    invite_form = WorkspaceInviteForm()
    transfer_form = WorkspaceTransferForm()
    can_manage_members = membership.role in {'owner', 'admin'}

    return render(
        request,
        'marketplace/workspace_detail.html',
        {
            'workspace': workspace,
            'membership': membership,
            'can_manage_members': can_manage_members,
            'invite_form': invite_form,
            'transfer_form': transfer_form,
            'entries': workspace.wallet_entries.all()[:20],
        },
    )


@login_required
@csrf_protect
@require_POST
def workspace_invite_member(request, slug):
    """Add a user to workspace with role-based access control."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None or membership.role not in {'owner', 'admin'}:
        messages.error(request, 'Only workspace owners/admins can add members.')
        return redirect('workspace_detail', slug=slug)

    form = WorkspaceInviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Provide a valid username and role.')
        return redirect('workspace_detail', slug=slug)

    member = get_object_or_404(CustomUser, username=form.cleaned_data['username'])
    role = form.cleaned_data['role']

    membership_obj, created = WorkspaceMembership.objects.get_or_create(
        workspace=workspace,
        user=member,
        defaults={'role': role},
    )
    if not created:
        membership_obj.role = role
        membership_obj.save(update_fields=['role'])

    messages.success(request, f'{member.username} added to workspace as {role}.')
    return redirect('workspace_detail', slug=slug)

@login_required
@csrf_protect
@require_POST
def workspace_deposit(request, slug):
    """Move INR from personal wallet into shared workspace wallet."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'Only workspace members can deposit funds.')
        return redirect('workspace_detail', slug=slug)

    form = WorkspaceTransferForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid deposit amount.')
        return redirect('workspace_detail', slug=slug)

    amount = form.cleaned_data['amount_inr']
    with transaction.atomic():
        user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
        workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
        if user.wallet_inr < amount:
            messages.error(request, 'Insufficient personal wallet balance.')
            return redirect('workspace_detail', slug=slug)
        user.wallet_inr -= amount
        workspace.wallet_inr += amount
        user.save(update_fields=['wallet_inr'])
        workspace.save(update_fields=['wallet_inr', 'updated_at'])
        WorkspaceWalletEntry.objects.create(
            workspace=workspace,
            actor=request.user,
            direction='credit',
            amount_inr=amount,
            source_type='personal_deposit',
            note='Deposit from personal wallet',
        )

    messages.success(request, f'Deposited INR {amount} into workspace wallet.')
    return redirect('workspace_detail', slug=slug)


@login_required
@csrf_protect
@require_POST
def workspace_withdraw(request, slug):
    """Move INR from workspace wallet back to personal wallet for managers."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None or membership.role not in {'owner', 'admin'}:
        messages.error(request, 'Only workspace owners/admins can withdraw funds.')
        return redirect('workspace_detail', slug=slug)

    form = WorkspaceTransferForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Invalid withdrawal amount.')
        return redirect('workspace_detail', slug=slug)

    amount = form.cleaned_data['amount_inr']
    with transaction.atomic():
        user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
        workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
        if workspace.wallet_inr < amount:
            messages.error(request, 'Workspace wallet does not have enough balance.')
            return redirect('workspace_detail', slug=slug)
        workspace.wallet_inr -= amount
        user.wallet_inr += amount
        workspace.save(update_fields=['wallet_inr', 'updated_at'])
        user.save(update_fields=['wallet_inr'])
        WorkspaceWalletEntry.objects.create(
            workspace=workspace,
            actor=request.user,
            direction='debit',
            amount_inr=amount,
            source_type='personal_withdraw',
            note='Withdrawal to personal wallet',
        )

    messages.success(request, f'Withdrew INR {amount} from workspace wallet.')
    return redirect('workspace_detail', slug=slug)


@login_required
def recommendations(request):
    """Show ranked request/job opportunities personalized by skills and saved filters."""
    algo_variant = getattr(request, 'experiments', {}).get('matching_algo', 'control')
    skill_weight = 55 if algo_variant == 'skill_boost' else 45
    saved_skill_weight = 30 if algo_variant == 'skill_boost' else 25

    skill_ids = list(request.user.skills.values_list('id', flat=True))
    saved_searches = list(
        SavedSearch.objects.filter(user=request.user, is_active=True).select_related('skill', 'tag')
    )

    query_terms = [search.query.lower() for search in saved_searches if search.query]
    tag_ids = {search.tag_id for search in saved_searches if search.tag_id}
    saved_skill_ids = {search.skill_id for search in saved_searches if search.skill_id}

    requests = HelpRequest.objects.filter(status='open').select_related('user', 'skill_needed').prefetch_related('tags')[:120]
    jobs = FreelanceJob.objects.filter(status='open').select_related('client', 'skill_needed').prefetch_related('tags')[:120]

    ranked_requests = []
    for item in requests:
        score = 0
        if item.skill_needed_id in skill_ids:
            score += skill_weight
        if item.skill_needed_id in saved_skill_ids:
            score += saved_skill_weight
        tag_match = len([tag for tag in item.tags.all() if tag.id in tag_ids])
        score += min(20, tag_match * 8)
        text_blob = f'{item.title} {item.description}'.lower()
        if any(term and term in text_blob for term in query_terms):
            score += 15
        if item.user_id == request.user.pk:
            score = -1
        ranked_requests.append((score, item))

    ranked_jobs = []
    for item in jobs:
        score = 0
        if item.skill_needed_id in skill_ids:
            score += skill_weight
        if item.skill_needed_id in saved_skill_ids:
            score += saved_skill_weight
        tag_match = len([tag for tag in item.tags.all() if tag.id in tag_ids])
        score += min(20, tag_match * 8)
        text_blob = f'{item.title} {item.description}'.lower()
        if any(term and term in text_blob for term in query_terms):
            score += 15
        if item.client_id == request.user.pk:
            score = -1
        ranked_jobs.append((score, item))

    ranked_requests.sort(key=lambda row: row[0], reverse=True)
    ranked_jobs.sort(key=lambda row: row[0], reverse=True)

    return render(
        request,
        'marketplace/recommendations.html',
        {
            'top_requests': [item for score, item in ranked_requests if score > 0][:15],
            'top_jobs': [item for score, item in ranked_jobs if score > 0][:15],
            'saved_searches': saved_searches,
        },
    )


@login_required
@csrf_protect
def manage_portfolio(request):
    """Create and list public portfolio items for the authenticated user."""
    if request.method == 'POST':
        form = PortfolioItemForm(request.POST)
        if form.is_valid():
            portfolio_item = form.save(commit=False)
            portfolio_item.user = request.user
            portfolio_item.save()
            messages.success(request, 'Portfolio item added.')
            return redirect('manage_portfolio')
    else:
        form = PortfolioItemForm()

    items = request.user.portfolio_items.select_related('primary_skill').all()
    return render(
        request,
        'marketplace/manage_portfolio.html',
        {
            'form': form,
            'items': items,
        },
    )


@login_required
@csrf_protect
@require_POST
def delete_portfolio_item(request, item_id):
    """Delete a portfolio item owned by the authenticated user."""
    item = get_object_or_404(PortfolioItem, pk=item_id, user=request.user)
    item.delete()
    messages.success(request, 'Portfolio item deleted.')
    return redirect('manage_portfolio')


@login_required
@csrf_protect
def integrations_settings(request):
    """Manage API keys and webhook endpoints for external integrations."""
    raw_key_once = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_api_key':
            key_form = ApiKeyCreateForm(request.POST)
            webhook_form = WebhookEndpointForm()
            if key_form.is_valid():
                _, raw_key_once = IntegrationApiKey.create_key(request.user, key_form.cleaned_data['name'])
                messages.success(request, 'API key created. Copy it now; it will not be shown again.')
            else:
                messages.error(request, 'Provide a valid API key name.')
        elif action == 'create_webhook':
            webhook_form = WebhookEndpointForm(request.POST)
            key_form = ApiKeyCreateForm()
            if webhook_form.is_valid():
                endpoint = webhook_form.save(commit=False)
                endpoint.user = request.user
                endpoint.save()
                messages.success(request, 'Webhook endpoint created.')
            else:
                messages.error(request, 'Provide a valid webhook URL.')
        else:
            key_form = ApiKeyCreateForm()
            webhook_form = WebhookEndpointForm()
    else:
        key_form = ApiKeyCreateForm()
        webhook_form = WebhookEndpointForm()

    return render(
        request,
        'marketplace/integrations_settings.html',
        {
            'key_form': key_form,
            'webhook_form': webhook_form,
            'api_keys': request.user.api_keys.all()[:20],
            'webhooks': request.user.webhook_endpoints.all()[:20],
            'deliveries': WebhookDelivery.objects.filter(endpoint__user=request.user).select_related('endpoint')[:30],
            'raw_key_once': raw_key_once,
        },
    )


@login_required
@csrf_protect
@require_POST
def revoke_api_key(request, key_id):
    """Revoke an API key owned by the authenticated user."""
    api_key = get_object_or_404(IntegrationApiKey, pk=key_id, user=request.user)
    api_key.is_active = False
    api_key.revoked_at = timezone.now()
    api_key.save(update_fields=['is_active', 'revoked_at'])
    messages.success(request, 'API key revoked.')
    return redirect('integrations_settings')


@login_required
@csrf_protect
@require_POST
def delete_webhook(request, endpoint_id):
    """Delete a webhook endpoint owned by the authenticated user."""
    endpoint = get_object_or_404(WebhookEndpoint, pk=endpoint_id, user=request.user)
    endpoint.delete()
    messages.success(request, 'Webhook endpoint deleted.')
    return redirect('integrations_settings')


@login_required
@csrf_protect
@require_POST
def test_webhook(request, endpoint_id):
    """Send a test webhook payload to verify endpoint delivery."""
    endpoint = get_object_or_404(WebhookEndpoint, pk=endpoint_id, user=request.user)
    dispatch_webhook_event(
        request.user,
        'webhook.test',
        {
            'message': 'HelperLearner webhook test event',
            'endpoint_id': endpoint.pk,
            'timestamp': timezone.now().isoformat(),
        },
    )
    messages.success(request, 'Test webhook dispatched. Check delivery logs below.')
    return redirect('integrations_settings')

@login_required
@csrf_protect
def report_content(request, target_type, target_id):
    """Allow users to report content for moderation review."""
    if target_type not in {'request', 'job', 'comment', 'user', 'dispute'}:
        messages.error(request, 'Unsupported report target.')
        return redirect('home')

    if request.method == 'POST':
        form = ModerationFlagForm(request.POST)
        if form.is_valid():
            ModerationFlag.objects.create(
                reported_by=request.user,
                target_type=target_type,
                target_id=target_id,
                reason=form.cleaned_data['reason'],
            )
            messages.success(request, 'Report submitted. Moderators will review it shortly.')
            return redirect(request.META.get('HTTP_REFERER', 'home'))
    else:
        form = ModerationFlagForm()

    return render(
        request,
        'marketplace/report_content.html',
        {
            'form': form,
            'target_type': target_type,
            'target_id': target_id,
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def moderation_console(request):
    """Show moderation queue with open flags, fraud alerts, and dispute audit list."""
    open_flags = ModerationFlag.objects.filter(status='open').select_related('reported_by')[:100]
    open_disputes = JobDispute.objects.filter(status='open').select_related('job', 'opened_by', 'against_user')[:100]
    active_alerts = FraudAlert.objects.filter(is_resolved=False).select_related('user', 'related_user')[:100]
    recent_users = CustomUser.objects.order_by('-date_joined')[:20]

    return render(
        request,
        'marketplace/moderation_console.html',
        {
            'open_flags': open_flags,
            'open_disputes': open_disputes,
            'active_alerts': active_alerts,
            'recent_users': recent_users,
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
@csrf_protect
@require_POST
def moderation_flag_action(request, pk, action):
    """Resolve or dismiss a moderation flag from the moderation console."""
    flag = get_object_or_404(ModerationFlag, pk=pk)
    if action not in {'reviewed', 'dismissed', 'actioned'}:
        messages.error(request, 'Unsupported moderation action.')
        return redirect('moderation_console')

    flag.status = action
    flag.reviewed_by = request.user
    flag.resolution_note = (request.POST.get('note') or '').strip()
    flag.resolved_at = timezone.now()
    flag.save(update_fields=['status', 'reviewed_by', 'resolution_note', 'resolved_at'])
    messages.success(request, f'Flag marked as {action}.')
    return redirect('moderation_console')


@login_required
@user_passes_test(lambda user: user.is_staff)
@csrf_protect
@require_POST
def suspend_user_account(request, user_id):
    """Suspend a user account via moderation tools."""
    target = get_object_or_404(CustomUser, pk=user_id)
    duration_days = int(request.POST.get('duration_days') or 7)
    reason = (request.POST.get('reason') or 'Suspended by moderation action.').strip()

    target.is_suspended = True
    target.suspended_until = timezone.now() + timedelta(days=max(1, duration_days))
    target.suspension_reason = reason
    target.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

    log_event(
        user=request.user,
        action='account_suspension',
        target_user=target,
        ip_address=get_client_ip(request),
        metadata={
            'duration_days': duration_days,
            'reason': reason,
            'suspended_until': target.suspended_until.isoformat(),
        }
    )

    messages.success(request, f'User {target.username} suspended for {duration_days} day(s).')
    return redirect('moderation_console')


@login_required
@user_passes_test(lambda user: user.is_staff)
@csrf_protect
@require_POST
def unsuspend_user_account(request, user_id):
    """Lift suspension on a user account."""
    target = get_object_or_404(CustomUser, pk=user_id)
    target.is_suspended = False
    target.suspended_until = None
    target.suspension_reason = ''
    target.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

    log_event(
        user=request.user,
        action='account_unsuspension',
        target_user=target,
        ip_address=get_client_ip(request),
    )

    messages.success(request, f'User {target.username} unsuspended.')
    return redirect('moderation_console')


@login_required
@user_passes_test(lambda user: user.is_staff)
def advanced_analytics(request):
    """Render product analytics: funnel, timing, disputes, and conversion trends."""
    request_funnel = {
        'open': HelpRequest.objects.filter(status='open').count(),
        'in_progress': HelpRequest.objects.filter(status='in_progress').count(),
        'resolved': HelpRequest.objects.filter(status='resolved').count(),
        'canceled': HelpRequest.objects.filter(status='canceled').count(),
    }
    job_funnel = {
        'open': FreelanceJob.objects.filter(status='open').count(),
        'in_progress': FreelanceJob.objects.filter(status='in_progress').count(),
        'completed': FreelanceJob.objects.filter(status='completed').count(),
        'disputed': FreelanceJob.objects.filter(status='disputed').count(),
        'canceled': FreelanceJob.objects.filter(status='canceled').count(),
    }

    resolution_time = (
        HelpRequest.objects.filter(status='resolved')
        .annotate(duration=F('updated_at') - F('created_at'))
        .aggregate(avg_duration=Avg('duration'))['avg_duration']
    )

    paid_resolution_time = (
        FreelanceJob.objects.filter(status='completed')
        .annotate(duration=F('updated_at') - F('created_at'))
        .aggregate(avg_duration=Avg('duration'))['avg_duration']
    )

    months = (
        JobDispute.objects.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Count('id'))
        .order_by('-month')[:6]
    )

    total_requests = sum(request_funnel.values()) or 1
    total_jobs = sum(job_funnel.values()) or 1

    conversion = {
        'request_resolution_rate': round((request_funnel['resolved'] / total_requests) * 100, 2),
        'job_completion_rate': round((job_funnel['completed'] / total_jobs) * 100, 2),
        'job_dispute_rate': round((job_funnel['disputed'] / total_jobs) * 100, 2),
    }

    return render(
        request,
        'marketplace/advanced_analytics.html',
        {
            'request_funnel': request_funnel,
            'job_funnel': job_funnel,
            'resolution_time': resolution_time,
            'paid_resolution_time': paid_resolution_time,
            'dispute_trends': list(months),
            'conversion': conversion,
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def ops_celery_status(request):
    """Return staff-only Celery worker/queue status for ops monitoring."""
    snapshot = _collect_celery_worker_snapshot()
    status_code = 200 if snapshot['healthy'] else 503
    payload = {
        'status': 'healthy' if snapshot['healthy'] else 'degraded',
        'service': 'celery',
        'configured': snapshot['configured'],
        'broker_url': _mask_broker_url(getattr(settings, 'CELERY_BROKER_URL', '')),
        'workers': snapshot['workers'],
        'totals': snapshot['totals'],
        'error': snapshot.get('error') or '',
        'checked_at': timezone.now().isoformat(),
    }
    return JsonResponse(payload, status=status_code)


@login_required
@user_passes_test(lambda user: user.is_staff)
def ops_webhook_status(request):
    """Return staff-only webhook delivery backlog and failure metrics."""
    now = timezone.now()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    threshold = int(getattr(settings, 'WEBHOOK_FAILURE_ALERT_THRESHOLD', 20))

    failed_last_hour = WebhookDelivery.objects.filter(succeeded=False, created_at__gte=hour_ago).count()
    failed_last_day = WebhookDelivery.objects.filter(succeeded=False, created_at__gte=day_ago).count()
    delivered_last_hour = WebhookDelivery.objects.filter(succeeded=True, created_at__gte=hour_ago).count()

    recent_failed = list(
        WebhookDelivery.objects.filter(succeeded=False)
        .select_related('endpoint')
        .order_by('-created_at')[:10]
        .values(
            'id',
            'endpoint_id',
            'endpoint__name',
            'event_type',
            'status_code',
            'created_at',
        )
    )
    for item in recent_failed:
        item['created_at'] = item['created_at'].isoformat()

    degraded = failed_last_hour >= threshold
    payload = {
        'status': 'degraded' if degraded else 'healthy',
        'service': 'webhooks',
        'failed_last_hour': failed_last_hour,
        'failed_last_day': failed_last_day,
        'delivered_last_hour': delivered_last_hour,
        'failure_alert_threshold': threshold,
        'recent_failed_deliveries': recent_failed,
        'checked_at': now.isoformat(),
    }
    return JsonResponse(payload, status=503 if degraded else 200)


@login_required
@require_GET
def live_nav_status(request):
    """Return authenticated navbar counters for realtime UI sync."""
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False).count()
    unread_chat_threads = _unread_chat_threads_for_user(request.user)
    return JsonResponse(
        {
            'unread_notifications_count': unread_notifications,
            'unread_chat_threads_count': unread_chat_threads,
            'knowledge_points': request.user.knowledge_points,
            'wallet_inr': str(request.user.wallet_inr),
            'checked_at': timezone.now().isoformat(),
        }
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
def ops_runtime_status(request):
    """Return staff-only consolidated runtime diagnostics snapshot."""
    snapshot = collect_runtime_snapshot()
    status_code = 200 if snapshot['healthy'] else 503
    payload = {
        'service': 'runtime',
        **snapshot,
    }
    return JsonResponse(payload, status=status_code)


@login_required
def trust_score_breakdown(request, username=None):
    """Show detailed trust score v2 breakdown for a user profile."""
    target_user = request.user
    if username:
        target_user = get_object_or_404(CustomUser, username=username)

    metrics = compute_trust_score_v2(target_user)
    return render(
        request,
        'marketplace/trust_score_breakdown.html',
        {
            'target_user': target_user,
            'metrics': metrics,
        },
    )


@login_required
@user_passes_test(lambda user: user.is_staff)
@csrf_protect
def experiment_console(request):
    """Create simple A/B experiments and variants from a lightweight web console."""
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        slug = (request.POST.get('slug') or '').strip()
        variant_a = (request.POST.get('variant_a') or 'control').strip()
        variant_b = (request.POST.get('variant_b') or 'treatment').strip()

        if not name or not slug:
            messages.error(request, 'Name and slug are required.')
        else:
            experiment, created = Experiment.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': name,
                    'description': 'Created from experiment console.',
                    'is_active': True,
                },
            )
            if created:
                experiment.variants.create(key=variant_a, label=variant_a.title(), weight=50)
                experiment.variants.create(key=variant_b, label=variant_b.title(), weight=50)
                messages.success(request, 'Experiment created with two variants.')
            else:
                messages.info(request, 'Experiment slug already exists.')

    return render(
        request,
        'marketplace/experiment_console.html',
        {
            'experiments': Experiment.objects.prefetch_related('variants').all(),
        },
    )


def public_portfolio(request, username):
    """Public portfolio page for a user — accessible without login."""
    profile_user = get_object_or_404(CustomUser, username=username, is_active=True)
    portfolio_items = PortfolioItem.objects.filter(user=profile_user).select_related('primary_skill')
    return render(request, 'marketplace/public_portfolio.html', {
        'profile_user': profile_user,
        'portfolio_items': portfolio_items,
    })


@login_required
@require_GET
def recommended_helpers(request, pk):
    """Return JSON list of recommended helpers for a help request."""
    help_request = get_object_or_404(HelpRequest, pk=pk)
    from .matching import get_recommended_helpers
    helpers = get_recommended_helpers(help_request, limit=5)
    data = [
        {
            'username': user.username,
            'score': score,
            'trust_score': str(getattr(user, 'trust_score', 0)),
            'resolved_count': getattr(user, 'resolved_count', 0),
        }
        for user, score in helpers
    ]
    return JsonResponse({'helpers': data})


@login_required
@require_GET
def sprint_burndown_data(request, slug, project_id, sprint_id):
    """Return JSON burn-down data for a sprint."""
    from .models import WorkspaceSprint, WorkspaceIssue

    sprint = get_object_or_404(WorkspaceSprint, pk=sprint_id, project__pk=project_id)
    if not sprint.started_at:
        return JsonResponse({'error': 'Sprint not started'}, status=400)

    issues = WorkspaceIssue.objects.filter(sprint=sprint)
    total_points = sum(i.story_points or 0 for i in issues)

    # Build daily data from sprint start
    start = sprint.started_at.date()
    end = (sprint.completed_at or timezone.now()).date()
    current = start
    daily_data = []
    while current <= end:
        done_points = sum(
            i.story_points or 0
            for i in issues
            if i.status == 'done' and i.updated_at and i.updated_at.date() <= current
        )
        remaining = total_points - done_points
        daily_data.append({'date': str(current), 'remaining': remaining, 'ideal': 0})
        current += timedelta(days=1)

    # Calculate ideal burndown line
    total_days = len(daily_data)
    if total_days > 1:
        for i, point in enumerate(daily_data):
            point['ideal'] = round(total_points * (1 - i / (total_days - 1)), 1)

    return JsonResponse({
        'sprint_name': sprint.name,
        'total_points': total_points,
        'daily': daily_data,
    })
