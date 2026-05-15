from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from notifications.models import Notification

from .forms import (
    WorkspaceIssueCommentForm,
    WorkspaceIssueForm,
    WorkspaceProjectForm,
    WorkspaceSprintForm,
)
from .models import (
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceMembership,
    WorkspaceProject,
    WorkspaceSprint,
)
from .realtime import emit_user_event


def _workspace_membership(workspace, user):
    """Return the membership row for a user in a workspace."""
    if not user.is_authenticated:
        return None
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()


def _can_manage_workspace_projects(membership):
    """Return True when the membership role can manage projects."""
    return membership is not None and membership.role in {'owner', 'admin'}


def _can_edit_issue(membership, issue, user):
    """Return True when user can edit/transition the issue."""
    if membership is None:
        return False
    if membership.role in {'owner', 'admin'}:
        return True
    return issue.reporter_id == user.pk or issue.assignee_id == user.pk


def _notify_issue_assignment(issue, actor):
    """Notify assignee when a new issue is assigned to them."""
    if not issue.assignee_id or issue.assignee_id == actor.pk:
        return
    link = reverse(
        'workspace_issue_detail',
        args=[issue.project.workspace.slug, issue.project_id, issue.pk],
    )
    Notification.objects.create(
        user=issue.assignee,
        message=f'You were assigned issue {issue.issue_key}: {issue.title}',
        link=link,
    )
    emit_user_event(
        issue.assignee_id,
        'workspace.issue_assigned',
        {
            'issue_id': issue.pk,
            'issue_key': issue.issue_key,
            'title': issue.title,
            'link': link,
        },
    )


def _notify_issue_status_change(issue, actor, from_status, to_status):
    """Notify reporter when issue status changes."""
    if issue.reporter_id == actor.pk or from_status == to_status:
        return
    link = reverse(
        'workspace_issue_detail',
        args=[issue.project.workspace.slug, issue.project_id, issue.pk],
    )
    Notification.objects.create(
        user=issue.reporter,
        message=f'Issue {issue.issue_key} moved from {from_status} to {to_status}.',
        link=link,
    )
    emit_user_event(
        issue.reporter_id,
        'workspace.issue_status_changed',
        {
            'issue_id': issue.pk,
            'issue_key': issue.issue_key,
            'from_status': from_status,
            'to_status': to_status,
            'link': link,
        },
    )


def _notify_issue_comment(issue, actor, comment):
    """Notify issue stakeholders when a new comment is posted."""
    link = reverse(
        'workspace_issue_detail',
        args=[issue.project.workspace.slug, issue.project_id, issue.pk],
    )
    recipient_ids = {issue.reporter_id}
    if issue.assignee_id:
        recipient_ids.add(issue.assignee_id)
    recipient_ids.discard(actor.pk)

    for user_id in recipient_ids:
        Notification.objects.create(
            user_id=user_id,
            message=f'New comment on {issue.issue_key} by {actor.username}: {comment.content[:80]}',
            link=link,
        )
        emit_user_event(
            user_id,
            'workspace.issue_commented',
            {
                'issue_id': issue.pk,
                'issue_key': issue.issue_key,
                'author': actor.username,
                'excerpt': comment.content[:120],
                'link': link,
            },
        )


@login_required
@csrf_protect
def workspace_projects(request, slug):
    """List workspace projects and allow owners/admins to create new ones."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    can_manage_projects = _can_manage_workspace_projects(membership)
    if request.method == 'POST':
        if not can_manage_projects:
            messages.error(request, 'Only workspace owners/admins can create projects.')
            return redirect('workspace_projects', slug=workspace.slug)
        form = WorkspaceProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.workspace = workspace
            project.created_by = request.user
            project.save()
            messages.success(request, f'Project {project.name} created.')
            return redirect('workspace_project_board', slug=workspace.slug, project_id=project.pk)
    else:
        form = WorkspaceProjectForm()

    projects = (
        workspace.projects.annotate(
            issue_count=Count('issues', distinct=True),
            open_count=Count('issues', filter=~Q(issues__status='done'), distinct=True),
        )
        .order_by('name')
    )

    return render(
        request,
        'marketplace/workspace_projects.html',
        {
            'workspace': workspace,
            'membership': membership,
            'can_manage_projects': can_manage_projects,
            'form': form,
            'projects': projects,
        },
    )


@login_required
def workspace_project_board(request, slug, project_id):
    """Render Kanban board for a workspace project with grouped issues."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    project = get_object_or_404(
        WorkspaceProject.objects.select_related('workspace', 'created_by'),
        pk=project_id,
        workspace=workspace,
    )
    sprints = list(project.sprints.order_by('-start_date', '-created_at'))
    active_sprint = next((item for item in sprints if item.status == 'active'), None)
    scope = (request.GET.get('scope') or 'all').strip()

    issues_qs = project.issues.select_related('reporter', 'assignee', 'sprint').order_by('-priority', '-updated_at')
    if scope == 'active' and active_sprint:
        issues_qs = issues_qs.filter(sprint=active_sprint)
    elif scope == 'backlog':
        issues_qs = issues_qs.filter(sprint__isnull=True)
    issues = list(issues_qs)
    status_columns = [
        ('todo', 'To Do'),
        ('in_progress', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Done'),
    ]
    board = {key: [] for key, _ in status_columns}
    for issue in issues:
        board.setdefault(issue.status, []).append(issue)

    recent_activity = (
        WorkspaceIssueActivity.objects.filter(issue__project=project)
        .select_related('actor', 'issue')
        .order_by('-created_at')[:20]
    )
    sprint_scope_qs = project.issues.all()
    if active_sprint:
        sprint_scope_qs = sprint_scope_qs.filter(sprint=active_sprint)

    sprint_metrics = sprint_scope_qs.aggregate(
        total_issues=Count('id'),
        done_issues=Count('id', filter=Q(status='done')),
        total_points=Coalesce(Sum('estimate_points'), 0),
        done_points=Coalesce(
            Sum(
                Case(
                    When(status='done', then='estimate_points'),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            0,
        ),
    )
    total_basis = sprint_metrics['total_points'] or sprint_metrics['total_issues'] or 0
    done_basis = sprint_metrics['done_points'] or sprint_metrics['done_issues'] or 0
    sprint_progress_pct = int((done_basis / total_basis) * 100) if total_basis else 0

    breakdown_rows = (
        sprint_scope_qs.values('status').annotate(count=Count('id')).order_by('status')
        if sprint_scope_qs.exists()
        else []
    )
    max_breakdown = max((row['count'] for row in breakdown_rows), default=1)
    status_labels = dict(WorkspaceIssue.STATUS_CHOICES)
    status_breakdown = [
        {
            'status': row['status'],
            'label': status_labels.get(row['status'], row['status']),
            'count': row['count'],
            'pct': int((row['count'] / max_breakdown) * 100) if max_breakdown else 0,
        }
        for row in breakdown_rows
    ]

    return render(
        request,
        'marketplace/workspace_project_board.html',
        {
            'workspace': workspace,
            'membership': membership,
            'project': project,
            'status_columns': status_columns,
            'board': board,
            'can_manage_projects': _can_manage_workspace_projects(membership),
            'recent_activity': recent_activity,
            'scope': scope,
            'sprints': sprints,
            'active_sprint': active_sprint,
            'sprint_form': WorkspaceSprintForm(),
            'sprint_metrics': sprint_metrics,
            'sprint_progress_pct': sprint_progress_pct,
            'status_breakdown': status_breakdown,
        },
    )


@login_required
@csrf_protect
def workspace_issue_create(request, slug, project_id):
    """Create a new issue inside a workspace project."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    project = get_object_or_404(WorkspaceProject, pk=project_id, workspace=workspace)
    if request.method == 'POST':
        form = WorkspaceIssueForm(request.POST, workspace=workspace, project=project)
        if form.is_valid():
            with transaction.atomic():
                issue = form.save(commit=False)
                issue.project = project
                issue.reporter = request.user
                issue.save()
                WorkspaceIssueActivity.objects.create(
                    issue=issue,
                    actor=request.user,
                    action='created',
                    to_value=issue.status,
                    note='Issue created',
                )
            _notify_issue_assignment(issue, request.user)
            messages.success(request, f'Issue {issue.issue_key} created.')
            return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project.pk, issue_id=issue.pk)
    else:
        form = WorkspaceIssueForm(workspace=workspace, project=project)

    return render(
        request,
        'marketplace/workspace_issue_form.html',
        {
            'workspace': workspace,
            'project': project,
            'form': form,
            'form_mode': 'create',
        },
    )


@login_required
@csrf_protect
def workspace_issue_edit(request, slug, project_id, issue_id):
    """Edit issue fields for authorized workspace collaborators."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    issue = get_object_or_404(
        WorkspaceIssue.objects.select_related('project', 'reporter', 'assignee'),
        pk=issue_id,
        project_id=project_id,
        project__workspace=workspace,
    )
    if not _can_edit_issue(membership, issue, request.user):
        messages.error(request, 'You do not have permission to edit this issue.')
        return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project_id, issue_id=issue.pk)

    previous_status = issue.status
    previous_assignee_id = issue.assignee_id
    previous_sprint_id = issue.sprint_id

    if request.method == 'POST':
        form = WorkspaceIssueForm(request.POST, instance=issue, workspace=workspace, project=issue.project)
        if form.is_valid():
            with transaction.atomic():
                updated_issue = form.save()
                if previous_status != updated_issue.status:
                    WorkspaceIssueActivity.objects.create(
                        issue=updated_issue,
                        actor=request.user,
                        action='status_changed',
                        from_value=previous_status,
                        to_value=updated_issue.status,
                    )
                if previous_assignee_id != updated_issue.assignee_id:
                    WorkspaceIssueActivity.objects.create(
                        issue=updated_issue,
                        actor=request.user,
                        action='assignee_changed',
                        from_value=str(previous_assignee_id or ''),
                        to_value=str(updated_issue.assignee_id or ''),
                    )
                if previous_sprint_id != updated_issue.sprint_id:
                    WorkspaceIssueActivity.objects.create(
                        issue=updated_issue,
                        actor=request.user,
                        action='sprint_changed',
                        from_value=str(previous_sprint_id or ''),
                        to_value=str(updated_issue.sprint_id or ''),
                    )
            _notify_issue_status_change(updated_issue, request.user, previous_status, updated_issue.status)
            if previous_assignee_id != updated_issue.assignee_id:
                _notify_issue_assignment(updated_issue, request.user)
            messages.success(request, f'Issue {updated_issue.issue_key} updated.')
            return redirect(
                'workspace_issue_detail',
                slug=workspace.slug,
                project_id=updated_issue.project_id,
                issue_id=updated_issue.pk,
            )
    else:
        form = WorkspaceIssueForm(instance=issue, workspace=workspace, project=issue.project)

    return render(
        request,
        'marketplace/workspace_issue_form.html',
        {
            'workspace': workspace,
            'project': issue.project,
            'issue': issue,
            'form': form,
            'form_mode': 'edit',
        },
    )


@login_required
@csrf_protect
def workspace_issue_detail(request, slug, project_id, issue_id):
    """Display issue details, assignee, status, and activity history."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    issue = get_object_or_404(
        WorkspaceIssue.objects.select_related('project', 'reporter', 'assignee'),
        pk=issue_id,
        project_id=project_id,
        project__workspace=workspace,
    )
    if request.method == 'POST':
        comment_form = WorkspaceIssueCommentForm(request.POST)
        if comment_form.is_valid():
            with transaction.atomic():
                comment = comment_form.save(commit=False)
                comment.issue = issue
                comment.author = request.user
                comment.save()
                WorkspaceIssueActivity.objects.create(
                    issue=issue,
                    actor=request.user,
                    action='commented',
                    note=comment.content[:220],
                )
            _notify_issue_comment(issue, request.user, comment)
            messages.success(request, 'Comment posted on issue.')
            return redirect(
                'workspace_issue_detail',
                slug=workspace.slug,
                project_id=issue.project_id,
                issue_id=issue.pk,
            )
    else:
        comment_form = WorkspaceIssueCommentForm()

    activities = issue.activity.select_related('actor').all()[:60]
    comments = issue.comments.select_related('author').all()
    return render(
        request,
        'marketplace/workspace_issue_detail.html',
        {
            'workspace': workspace,
            'project': issue.project,
            'issue': issue,
            'activities': activities,
            'can_edit': _can_edit_issue(membership, issue, request.user),
            'comments': comments,
            'comment_form': comment_form,
        },
    )


@login_required
@csrf_protect
@require_POST
def workspace_issue_transition(request, slug, project_id, issue_id):
    """Transition issue status across To Do/In Progress/Blocked/Done lanes."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if membership is None:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspace_list')

    issue = get_object_or_404(
        WorkspaceIssue.objects.select_related('project', 'reporter', 'assignee'),
        pk=issue_id,
        project_id=project_id,
        project__workspace=workspace,
    )
    if not _can_edit_issue(membership, issue, request.user):
        messages.error(request, 'You do not have permission to transition this issue.')
        return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project_id, issue_id=issue.pk)

    target_status = (request.POST.get('status') or '').strip()
    valid_statuses = {choice[0] for choice in WorkspaceIssue.STATUS_CHOICES}
    if target_status not in valid_statuses:
        messages.error(request, 'Invalid status transition.')
        return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project_id, issue_id=issue.pk)

    previous_status = issue.status
    if previous_status == target_status:
        messages.info(request, 'Issue is already in that status.')
        return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project_id, issue_id=issue.pk)

    with transaction.atomic():
        issue.status = target_status
        issue.save(update_fields=['status', 'resolved_at', 'updated_at'])
        WorkspaceIssueActivity.objects.create(
            issue=issue,
            actor=request.user,
            action='status_changed',
            from_value=previous_status,
            to_value=target_status,
        )

    _notify_issue_status_change(issue, request.user, previous_status, target_status)
    messages.success(request, f'Issue {issue.issue_key} moved to {issue.get_status_display()}.')
    return redirect('workspace_issue_detail', slug=workspace.slug, project_id=project_id, issue_id=issue.pk)


@login_required
@csrf_protect
@require_POST
def workspace_sprint_create(request, slug, project_id):
    """Create a sprint for a workspace project (owner/admin only)."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if not _can_manage_workspace_projects(membership):
        messages.error(request, 'Only workspace owners/admins can create sprints.')
        return redirect('workspace_project_board', slug=workspace.slug, project_id=project_id)

    project = get_object_or_404(WorkspaceProject, pk=project_id, workspace=workspace)
    form = WorkspaceSprintForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            sprint = form.save(commit=False)
            sprint.project = project
            sprint.created_by = request.user
            if sprint.status == 'active':
                WorkspaceSprint.objects.filter(project=project, status='active').update(status='completed')
            sprint.save()
        messages.success(request, f'Sprint {sprint.name} created.')
    else:
        messages.error(request, 'Could not create sprint. Check the form values.')

    return redirect('workspace_project_board', slug=workspace.slug, project_id=project.pk)


@login_required
@csrf_protect
@require_POST
def workspace_sprint_start(request, slug, project_id, sprint_id):
    """Activate a sprint and complete any currently active sprint."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if not _can_manage_workspace_projects(membership):
        messages.error(request, 'Only workspace owners/admins can manage sprint status.')
        return redirect('workspace_project_board', slug=workspace.slug, project_id=project_id)

    sprint = get_object_or_404(
        WorkspaceSprint.objects.select_related('project', 'project__workspace'),
        pk=sprint_id,
        project_id=project_id,
        project__workspace=workspace,
    )
    with transaction.atomic():
        WorkspaceSprint.objects.filter(project=sprint.project, status='active').exclude(pk=sprint.pk).update(status='completed')
        sprint.status = 'active'
        sprint.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Sprint {sprint.name} is now active.')
    return redirect('workspace_project_board', slug=workspace.slug, project_id=project_id)


@login_required
@csrf_protect
@require_POST
def workspace_sprint_complete(request, slug, project_id, sprint_id):
    """Mark a sprint as completed."""
    workspace = get_object_or_404(Workspace, slug=slug)
    membership = _workspace_membership(workspace, request.user)
    if not _can_manage_workspace_projects(membership):
        messages.error(request, 'Only workspace owners/admins can manage sprint status.')
        return redirect('workspace_project_board', slug=workspace.slug, project_id=project_id)

    sprint = get_object_or_404(
        WorkspaceSprint.objects.select_related('project', 'project__workspace'),
        pk=sprint_id,
        project_id=project_id,
        project__workspace=workspace,
    )
    sprint.status = 'completed'
    sprint.save(update_fields=['status', 'updated_at'])
    messages.success(request, f'Sprint {sprint.name} marked as completed.')
    return redirect('workspace_project_board', slug=workspace.slug, project_id=project_id)
