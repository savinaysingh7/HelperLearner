from rest_framework.test import APIClient, APITestCase

from accounts.models import CustomUser

from .models import (
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueComment,
    WorkspaceMembership,
    WorkspaceProject,
)


class WorkspaceJiraApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = CustomUser.objects.create_user(username='api_member', password='pw')
        self.owner = CustomUser.objects.create_user(username='api_owner', password='pw')
        self.outsider = CustomUser.objects.create_user(username='api_outsider', password='pw')

        self.workspace_a = Workspace.objects.create(name='Alpha Ops', owner=self.owner)
        self.workspace_b = Workspace.objects.create(name='Beta Ops', owner=self.outsider)

        WorkspaceMembership.objects.create(workspace=self.workspace_a, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.workspace_a, user=self.member, role='member')
        WorkspaceMembership.objects.create(workspace=self.workspace_b, user=self.outsider, role='owner')

        self.project_a = WorkspaceProject.objects.create(
            workspace=self.workspace_a,
            name='Platform',
            key='PLAT',
            created_by=self.owner,
        )
        self.project_b = WorkspaceProject.objects.create(
            workspace=self.workspace_b,
            name='Growth',
            key='GROW',
            created_by=self.outsider,
        )

        self.issue_a = WorkspaceIssue.objects.create(
            project=self.project_a,
            title='Tune queue consumers',
            description='Lower processing latency for payouts',
            status='todo',
            priority='high',
            reporter=self.owner,
            assignee=self.member,
        )
        self.issue_b = WorkspaceIssue.objects.create(
            project=self.project_b,
            title='External issue',
            description='Should not be visible to non-members',
            status='todo',
            priority='low',
            reporter=self.outsider,
            assignee=self.outsider,
        )
        WorkspaceIssueComment.objects.create(
            issue=self.issue_a,
            author=self.member,
            content='I will ship this in two phases.',
        )

    def test_workspace_api_requires_authentication(self):
        response = self.client.get('/api/workspace-projects/')
        self.assertIn(response.status_code, [401, 403])

    def test_member_only_sees_projects_from_member_workspaces(self):
        self.client.force_authenticate(user=self.member)
        response = self.client.get('/api/workspace-projects/')

        self.assertEqual(response.status_code, 200)
        project_keys = {item['key'] for item in response.data['results']}
        self.assertIn('PLAT', project_keys)
        self.assertNotIn('GROW', project_keys)

    def test_issue_filters_and_comments_are_scoped_to_workspace_members(self):
        self.client.force_authenticate(user=self.member)

        issues_response = self.client.get(
            '/api/workspace-issues/',
            {'workspace': self.workspace_a.slug, 'status': 'todo'},
        )
        self.assertEqual(issues_response.status_code, 200)
        self.assertEqual(len(issues_response.data['results']), 1)
        self.assertEqual(issues_response.data['results'][0]['issue_key'], self.issue_a.issue_key)

        comments_response = self.client.get(f'/api/workspace-issues/{self.issue_a.pk}/comments/')
        self.assertEqual(comments_response.status_code, 200)
        self.assertEqual(len(comments_response.data['results']), 1)
        self.assertIn('two phases', comments_response.data['results'][0]['content'])

        blocked_response = self.client.get(f'/api/workspace-issues/{self.issue_b.pk}/')
        self.assertEqual(blocked_response.status_code, 404)
