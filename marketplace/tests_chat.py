from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from .models import (
    ChatMessage,
    ChatThread,
    ChatThreadParticipant,
    FreelanceJob,
    HelpRequest,
    Skill,
    Workspace,
    WorkspaceMembership,
)


class ChatFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.requester = CustomUser.objects.create_user(username='requester', password='password123')
        self.helper = CustomUser.objects.create_user(username='helper', password='password123')
        self.client_user = CustomUser.objects.create_user(username='client_user', password='password123')
        self.freelancer = CustomUser.objects.create_user(username='freelancer', password='password123')
        self.outsider = CustomUser.objects.create_user(username='outsider', password='password123')
        self.skill = Skill.objects.create(name='Python')

    def test_request_chat_message_flow_and_read_state(self):
        help_request = HelpRequest.objects.create(
            title='Need debugging help',
            description='Investigate failing tests after deployment.',
            user=self.requester,
            skill_needed=self.skill,
            kp_bounty=20,
            status='in_progress',
            accepted_by=self.helper,
        )

        self.client.login(username='requester', password='password123')
        response = self.client.get(reverse('request_chat', args=[help_request.pk]))
        self.assertEqual(response.status_code, 302)

        thread = ChatThread.objects.get(help_request=help_request)
        self.assertEqual(thread.thread_type, 'request')

        self.client.post(
            reverse('chat_thread_detail', args=[thread.pk]),
            {'content': 'Please share your debugging approach first.'},
            follow=True,
        )

        self.assertEqual(ChatMessage.objects.filter(thread=thread).count(), 1)

        self.client.logout()
        self.client.login(username='helper', password='password123')
        inbox = self.client.get(reverse('chat_inbox'))
        self.assertContains(inbox, 'Unread')
        self.assertContains(inbox, 'Please share your debugging approach first.')
        self.assertEqual(inbox.context['unread_chat_threads_count'], 1)

        self.client.get(reverse('chat_thread_detail', args=[thread.pk]))
        refreshed_participation = ChatThreadParticipant.objects.get(thread=thread, user=self.helper)
        self.assertIsNotNone(refreshed_participation.last_read_at)

        inbox_after_read = self.client.get(reverse('chat_inbox'))
        self.assertEqual(inbox_after_read.context['unread_chat_threads_count'], 0)

    def test_request_chat_blocks_unrelated_user(self):
        help_request = HelpRequest.objects.create(
            title='Need SQL optimization',
            description='Improve query speed for dashboard.',
            user=self.requester,
            skill_needed=self.skill,
            kp_bounty=25,
            status='in_progress',
            accepted_by=self.helper,
        )

        self.client.login(username='outsider', password='password123')
        response = self.client.get(reverse('request_chat', args=[help_request.pk]))
        self.assertRedirects(response, reverse('request_detail', args=[help_request.pk]))
        self.assertFalse(ChatThread.objects.filter(help_request=help_request).exists())

    def test_job_chat_flow(self):
        job = FreelanceJob.objects.create(
            title='Build invoicing dashboard',
            description='Need React + Django integration for invoices.',
            client=self.client_user,
            freelancer=self.freelancer,
            status='in_progress',
            budget_inr=Decimal('25000.00'),
            skill_needed=self.skill,
        )

        self.client.login(username='client_user', password='password123')
        response = self.client.get(reverse('job_chat', args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        thread = ChatThread.objects.get(job=job)

        self.client.logout()
        self.client.login(username='freelancer', password='password123')
        post_response = self.client.post(
            reverse('chat_thread_detail', args=[thread.pk]),
            {'content': 'I can deliver first milestone by Friday.'},
            follow=True,
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertTrue(
            ChatMessage.objects.filter(thread=thread, sender=self.freelancer, content__contains='first milestone').exists()
        )

    def test_workspace_chat_requires_membership(self):
        workspace = Workspace.objects.create(
            name='Acme Team',
            owner=self.client_user,
            description='Core product engineering squad.',
        )
        WorkspaceMembership.objects.create(workspace=workspace, user=self.client_user, role='owner')
        WorkspaceMembership.objects.create(workspace=workspace, user=self.helper, role='member')

        self.client.login(username='outsider', password='password123')
        denied = self.client.get(reverse('workspace_chat', args=[workspace.slug]))
        self.assertRedirects(denied, reverse('workspace_list'))
        self.assertFalse(ChatThread.objects.filter(workspace=workspace).exists())

        self.client.logout()
        self.client.login(username='helper', password='password123')
        allowed = self.client.get(reverse('workspace_chat', args=[workspace.slug]))
        self.assertEqual(allowed.status_code, 302)

        thread = ChatThread.objects.get(workspace=workspace)
        participant_usernames = set(
            ChatThreadParticipant.objects.filter(thread=thread).values_list('user__username', flat=True)
        )
        self.assertEqual(participant_usernames, {'client_user', 'helper'})
