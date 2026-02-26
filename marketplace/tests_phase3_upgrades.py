from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from marketplace.models import (
    FraudAlert,
    FreelanceJob,
    FreelanceJobProposal,
    HelpRequest,
    HelpRequestProposal,
    JobMilestone,
    MilestoneDeliverable,
    ModerationFlag,
    Skill,
    WorkspaceMembership,
)


class Phase3UpgradeTests(TestCase):
    def setUp(self):
        self.client_user = CustomUser.objects.create_user(
            username='clientx',
            password='pass12345',
            wallet_inr=Decimal('2000.00'),
            knowledge_points=200,
        )
        self.freelancer = CustomUser.objects.create_user(
            username='freelancerx',
            password='pass12345',
            wallet_inr=Decimal('100.00'),
            knowledge_points=150,
        )
        self.helper = CustomUser.objects.create_user(
            username='helperx',
            password='pass12345',
            knowledge_points=120,
        )
        self.skill = Skill.objects.create(name='Backend')

        self.request_obj = HelpRequest.objects.create(
            title='Need API optimization',
            description='Improve response latency under load.',
            user=self.client_user,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
        )
        self.job = FreelanceJob.objects.create(
            title='Build invoice module',
            description='Need milestone-based delivery.',
            client=self.client_user,
            skill_needed=self.skill,
            budget_inr=Decimal('1000.00'),
            escrow_inr=Decimal('1000.00'),
            status='open',
            response_sla_hours=1,
            auto_release_hours=0,
        )

    def test_compare_request_proposals_owner_only(self):
        HelpRequestProposal.objects.create(
            request=self.request_obj,
            applicant=self.helper,
            proposed_kp=18,
            eta_days=2,
            cover_note='Can ship quickly.',
        )
        self.client.force_login(self.helper)
        response = self.client.get(reverse('compare_request_proposals', args=[self.request_obj.pk]))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.client_user)
        response = self.client.get(reverse('compare_request_proposals', args=[self.request_obj.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Proposal Comparison')

    def test_compare_job_proposals_page(self):
        FreelanceJobProposal.objects.create(
            job=self.job,
            applicant=self.freelancer,
            proposed_total_inr=Decimal('900.00'),
            eta_days=4,
            cover_note='Will deliver with tests.',
        )
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('compare_job_proposals', args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bid Comparison')

    def test_deliverable_revision_approval_flow(self):
        self.job.freelancer = self.freelancer
        self.job.status = 'in_progress'
        self.job.save(update_fields=['freelancer', 'status'])
        milestone = JobMilestone.objects.create(job=self.job, title='First drop', amount_inr=Decimal('500.00'), sequence=1)

        self.client.force_login(self.freelancer)
        response = self.client.post(
            reverse('submit_milestone_deliverable', args=[self.job.pk, milestone.pk]),
            {'proof_text': 'Uploaded docs and screenshots.'},
        )
        self.assertEqual(response.status_code, 302)
        deliverable = MilestoneDeliverable.objects.get(milestone=milestone)
        self.assertEqual(deliverable.status, 'submitted')

        self.client.force_login(self.client_user)
        response = self.client.post(
            reverse('request_milestone_revision', args=[self.job.pk, milestone.pk]),
            {'revision_note': 'Please include load test evidence.'},
        )
        self.assertEqual(response.status_code, 302)
        deliverable.refresh_from_db()
        milestone.refresh_from_db()
        self.assertEqual(deliverable.status, 'revision_requested')
        self.assertEqual(milestone.status, 'pending')

        milestone.status = 'submitted'
        milestone.save(update_fields=['status'])
        response = self.client.post(reverse('approve_milestone_deliverable', args=[self.job.pk, milestone.pk]))
        self.assertEqual(response.status_code, 302)
        deliverable.refresh_from_db()
        self.assertEqual(deliverable.status, 'approved')

    def test_workspace_create_and_deposit(self):
        self.client.force_login(self.client_user)
        response = self.client.post(reverse('workspace_list'), {'name': 'Product Ops', 'description': 'Core squad'})
        self.assertEqual(response.status_code, 302)

        membership = WorkspaceMembership.objects.get(user=self.client_user)
        workspace = membership.workspace
        response = self.client.post(reverse('workspace_deposit', args=[workspace.slug]), {'amount_inr': '200.00'})
        self.assertEqual(response.status_code, 302)

        workspace.refresh_from_db()
        self.client_user.refresh_from_db()
        self.assertEqual(workspace.wallet_inr, Decimal('200.00'))
        self.assertEqual(self.client_user.wallet_inr, Decimal('1800.00'))

    def test_workspace_invite_requires_manager_role(self):
        self.client.force_login(self.client_user)
        self.client.post(reverse('workspace_list'), {'name': 'Team A', 'description': 'Alpha'})
        workspace = WorkspaceMembership.objects.get(user=self.client_user).workspace

        outsider = CustomUser.objects.create_user(username='outsider', password='pass12345')
        WorkspaceMembership.objects.create(workspace=workspace, user=outsider, role='member')
        self.client.force_login(outsider)
        response = self.client.post(
            reverse('workspace_invite_member', args=[workspace.slug]),
            {'username': self.helper.username, 'role': 'member'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WorkspaceMembership.objects.filter(workspace=workspace, user=self.helper).exists())

    def test_report_content_creates_flag(self):
        self.client.force_login(self.freelancer)
        response = self.client.post(
            reverse('report_content', args=['request', self.request_obj.pk]),
            {'reason': 'Spam or irrelevant content'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ModerationFlag.objects.filter(target_type='request', target_id=self.request_obj.pk).exists())

    def test_trust_score_breakdown_page(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('trust_score_breakdown_self'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trust Score v2')

    def test_service_worker_route(self):
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Service-Worker-Allowed', response.headers)

    def test_run_sla_engine_creates_reminder(self):
        self.job.response_due_at = timezone.now() - timedelta(hours=2)
        self.job.first_response_at = None
        self.job.status = 'open'
        self.job.save(update_fields=['response_due_at', 'first_response_at', 'status'])

        call_command('run_sla_engine')
        self.assertTrue(FraudAlert.objects.filter(alert_type='sla_breach', user=self.client_user).exists())

    def test_invalid_api_key_is_rejected(self):
        response = self.client.get('/api/requests/', HTTP_X_API_KEY='invalid-key')
        self.assertEqual(response.status_code, 403)

    def test_recommendations_requires_login(self):
        response = self.client.get(reverse('recommendations'))
        self.assertEqual(response.status_code, 302)

    def test_integrations_page_loads_for_user(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse('integrations_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API Keys & Webhooks')
