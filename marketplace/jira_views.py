from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from notifications.models import Notification

from .forms import WorkspaceIssueForm, WorkspaceProjectForm
from .models import (
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceMembership,
    WorkspaceProject,
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

    issues = list(
        project.issues.select_related('reporter', 'assignee')
        .order_by('-priority', '-updated_at')
    )
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
        form = WorkspaceIssueForm(request.POST, workspace=workspace)
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
        form = WorkspaceIssueForm(workspace=workspace)

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

    if request.method == 'POST':
        form = WorkspaceIssueForm(request.POST, instance=issue, workspace=workspace)
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
        form = WorkspaceIssueForm(instance=issue, workspace=workspace)

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
    activities = issue.activity.select_related('actor').all()[:60]
    return render(
        request,
        'marketplace/workspace_issue_detail.html',
        {
            'workspace': workspace,
            'project': issue.project,
            'issue': issue,
            'activities': activities,
            'can_edit': _can_edit_issue(membership, issue, request.user),
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
