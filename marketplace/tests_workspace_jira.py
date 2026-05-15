from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from notifications.models import Notification

from .models import (
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceMembership,
    WorkspaceProject,
)


class WorkspaceJiraBoardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = CustomUser.objects.create_user(username='workspace_owner', password='password123')
        self.member = CustomUser.objects.create_user(username='workspace_member', password='password123')
        self.outsider = CustomUser.objects.create_user(username='workspace_outsider', password='password123')

        self.workspace = Workspace.objects.create(
            name='Delta Systems',
            owner=self.owner,
            description='Delivery pod for enterprise integrations',
        )
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member, role='member')

    def test_owner_can_create_project_and_issue_then_see_it_on_board(self):
        self.client.login(username='workspace_owner', password='password123')

        project_create = self.client.post(
            reverse('workspace_projects', args=[self.workspace.slug]),
            {
                'name': 'Payments Platform',
                'key': 'pay',
                'description': 'Track payment gateway migration tasks',
                'is_active': 'on',
            },
            follow=True,
        )
        self.assertEqual(project_create.status_code, 200)
        project = WorkspaceProject.objects.get(workspace=self.workspace, key='PAY')

        issue_create = self.client.post(
            reverse('workspace_issue_create', args=[self.workspace.slug, project.pk]),
            {
                'title': 'Integrate webhook retries',
                'description': 'Add exponential backoff and idempotency handling.',
                'status': 'todo',
                'priority': 'high',
                'assignee': self.member.pk,
                'estimate_points': 5,
                'due_date': '2026-03-15',
            },
            follow=True,
        )
        self.assertEqual(issue_create.status_code, 200)

        issue = WorkspaceIssue.objects.get(project=project)
        self.assertEqual(issue.issue_number, 1)
        self.assertEqual(issue.issue_key, 'PAY-1')
        self.assertTrue(
            WorkspaceIssueActivity.objects.filter(issue=issue, action='created').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.member, message__contains='assigned issue PAY-1').exists()
        )

        board = self.client.get(reverse('workspace_project_board', args=[self.workspace.slug, project.pk]))
        self.assertContains(board, 'Integrate webhook retries')
        self.assertContains(board, 'PAY-1')

    def test_outsider_cannot_access_workspace_project_or_issue_views(self):
        project = WorkspaceProject.objects.create(
            workspace=self.workspace,
            name='Ops Board',
            key='OPS',
            created_by=self.owner,
        )

        self.client.login(username='workspace_outsider', password='password123')

        projects_response = self.client.get(reverse('workspace_projects', args=[self.workspace.slug]))
        self.assertRedirects(projects_response, reverse('workspace_list'))

        board_response = self.client.get(reverse('workspace_project_board', args=[self.workspace.slug, project.pk]))
        self.assertRedirects(board_response, reverse('workspace_list'))

        issue_create_response = self.client.post(
            reverse('workspace_issue_create', args=[self.workspace.slug, project.pk]),
            {
                'title': 'Unauthorized issue',
                'description': 'Should never be created',
                'status': 'todo',
                'priority': 'medium',
            },
        )
        self.assertRedirects(issue_create_response, reverse('workspace_list'))
        self.assertEqual(WorkspaceIssue.objects.filter(project=project).count(), 0)

    def test_member_can_transition_assigned_issue_and_reporter_gets_notification(self):
        project = WorkspaceProject.objects.create(
            workspace=self.workspace,
            name='Mobile API',
            key='API',
            created_by=self.owner,
        )
        issue = WorkspaceIssue.objects.create(
            project=project,
            title='Optimize profile endpoint',
            description='Reduce p95 latency under 120ms.',
            status='todo',
            priority='medium',
            reporter=self.owner,
            assignee=self.member,
        )

        self.client.login(username='workspace_member', password='password123')
        transition = self.client.post(
            reverse('workspace_issue_transition', args=[self.workspace.slug, project.pk, issue.pk]),
            {'status': 'in_progress'},
            follow=True,
        )
        self.assertEqual(transition.status_code, 200)

        issue.refresh_from_db()
        self.assertEqual(issue.status, 'in_progress')
        self.assertTrue(
            WorkspaceIssueActivity.objects.filter(
                issue=issue,
                action='status_changed',
                from_value='todo',
                to_value='in_progress',
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.owner,
                message__contains='moved from todo to in_progress',
            ).exists()
        )

    def test_issue_form_rejects_assignee_outside_workspace(self):
        project = WorkspaceProject.objects.create(
            workspace=self.workspace,
            name='Docs',
            key='DOC',
            created_by=self.owner,
        )
        self.client.login(username='workspace_owner', password='password123')

        response = self.client.post(
            reverse('workspace_issue_create', args=[self.workspace.slug, project.pk]),
            {
                'title': 'Write runbook',
                'description': 'Document deployment rollback procedure',
                'status': 'todo',
                'priority': 'low',
                'assignee': self.outsider.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkspaceIssue.objects.filter(project=project).count(), 0)
