from datetime import date, timedelta

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from notifications.models import Notification

from .models import (
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceIssueComment,
    WorkspaceMembership,
    WorkspaceProject,
    WorkspaceSprint,
)


class WorkspaceJiraSprintAndCommentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = CustomUser.objects.create_user(username='owner_jira', password='password123')
        self.member = CustomUser.objects.create_user(username='member_jira', password='password123')
        self.outsider = CustomUser.objects.create_user(username='outsider_jira', password='password123')

        self.workspace = Workspace.objects.create(
            name='Orbit Labs',
            owner=self.owner,
            description='Platform delivery workspace',
        )
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member, role='member')

        self.project = WorkspaceProject.objects.create(
            workspace=self.workspace,
            name='Billing Core',
            key='BILL',
            created_by=self.owner,
        )

    def test_owner_can_create_and_activate_sprint(self):
        self.client.login(username='owner_jira', password='password123')
        start = date.today()
        end = start + timedelta(days=14)

        create_response = self.client.post(
            reverse('workspace_sprint_create', args=[self.workspace.slug, self.project.pk]),
            {
                'name': 'Sprint 01',
                'goal': 'Stabilize billing sync service',
                'start_date': start.isoformat(),
                'end_date': end.isoformat(),
                'status': 'planned',
            },
            follow=True,
        )
        self.assertEqual(create_response.status_code, 200)

        sprint = WorkspaceSprint.objects.get(project=self.project, name='Sprint 01')
        self.assertEqual(sprint.status, 'planned')

        start_response = self.client.post(
            reverse('workspace_sprint_start', args=[self.workspace.slug, self.project.pk, sprint.pk]),
            follow=True,
        )
        self.assertEqual(start_response.status_code, 200)

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, 'active')

        board = self.client.get(
            reverse('workspace_project_board', args=[self.workspace.slug, self.project.pk]),
            {'scope': 'active'},
        )
        self.assertContains(board, 'Sprint Progress')
        self.assertContains(board, 'Sprint 01')

    def test_member_cannot_manage_sprints(self):
        sprint = WorkspaceSprint.objects.create(
            project=self.project,
            name='Sprint Locked',
            goal='Owner only',
            start_date=date.today(),
            end_date=date.today() + timedelta(days=10),
            status='planned',
            created_by=self.owner,
        )

        self.client.login(username='member_jira', password='password123')
        denied_create = self.client.post(
            reverse('workspace_sprint_create', args=[self.workspace.slug, self.project.pk]),
            {
                'name': 'Illegal Sprint',
                'goal': '',
                'start_date': date.today().isoformat(),
                'end_date': (date.today() + timedelta(days=7)).isoformat(),
                'status': 'planned',
            },
            follow=True,
        )
        self.assertEqual(denied_create.status_code, 200)
        self.assertFalse(WorkspaceSprint.objects.filter(project=self.project, name='Illegal Sprint').exists())

        denied_start = self.client.post(
            reverse('workspace_sprint_start', args=[self.workspace.slug, self.project.pk, sprint.pk]),
            follow=True,
        )
        self.assertEqual(denied_start.status_code, 200)
        sprint.refresh_from_db()
        self.assertEqual(sprint.status, 'planned')

    def test_issue_comment_posts_and_notifies_assignee(self):
        issue = WorkspaceIssue.objects.create(
            project=self.project,
            title='Fix tax rounding',
            description='Rounding mismatch in invoice line totals.',
            status='in_progress',
            priority='high',
            reporter=self.owner,
            assignee=self.member,
            estimate_points=3,
        )

        self.client.login(username='owner_jira', password='password123')
        response = self.client.post(
            reverse('workspace_issue_detail', args=[self.workspace.slug, self.project.pk, issue.pk]),
            {'content': 'Please include unit tests for corner-case decimals.'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            WorkspaceIssueComment.objects.filter(issue=issue, author=self.owner, content__contains='unit tests').exists()
        )
        self.assertTrue(
            WorkspaceIssueActivity.objects.filter(issue=issue, action='commented').exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.member, message__contains='New comment on BILL-1').exists()
        )

    def test_outsider_cannot_access_issue_comment_flow(self):
        issue = WorkspaceIssue.objects.create(
            project=self.project,
            title='Document retry strategy',
            description='Add docs for retry policies',
            reporter=self.owner,
            assignee=self.member,
        )

        self.client.login(username='outsider_jira', password='password123')
        response = self.client.post(
            reverse('workspace_issue_detail', args=[self.workspace.slug, self.project.pk, issue.pk]),
            {'content': 'I should not post here'},
            follow=True,
        )
        self.assertRedirects(response, reverse('workspace_list'))
        self.assertEqual(WorkspaceIssueComment.objects.filter(issue=issue).count(), 0)
