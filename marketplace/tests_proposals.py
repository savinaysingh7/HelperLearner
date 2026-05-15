from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import (
    FreelanceJob,
    FreelanceJobProposal,
    FreelanceJobProposalMilestone,
    HelpRequest,
    HelpRequestProposal,
    JobMilestone,
    Skill,
    WalletLedger,
)


class HelpRequestProposalFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='poster_prop', password='pw', knowledge_points=80)
        self.helper_one = CustomUser.objects.create_user(username='helper_one', password='pw', knowledge_points=50)
        self.helper_two = CustomUser.objects.create_user(username='helper_two', password='pw', knowledge_points=50)
        self.skill = Skill.objects.create(name='Python')
        self.request_obj = HelpRequest.objects.create(
            title='Need help with flaky Django test',
            description='Investigate intermittent CI failures on serializer tests.',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=20,
            status='open',
        )

    def test_poster_selects_proposal_refunds_difference_and_starts_request(self):
        proposal_one = HelpRequestProposal.objects.create(
            request=self.request_obj,
            applicant=self.helper_one,
            proposed_kp=15,
            cover_note='I can debug this in under an hour.',
        )
        proposal_two = HelpRequestProposal.objects.create(
            request=self.request_obj,
            applicant=self.helper_two,
            proposed_kp=19,
            cover_note='I can reproduce and patch the root cause.',
        )

        self.client.login(username='poster_prop', password='pw')
        response = self.client.post(reverse('select_request_proposal', args=[self.request_obj.pk, proposal_one.pk]))

        self.assertEqual(response.status_code, 302)
        self.request_obj.refresh_from_db()
        self.poster.refresh_from_db()
        proposal_one.refresh_from_db()
        proposal_two.refresh_from_db()

        self.assertEqual(self.request_obj.status, 'in_progress')
        self.assertEqual(self.request_obj.accepted_by, self.helper_one)
        self.assertEqual(self.request_obj.kp_bounty, 15)
        self.assertEqual(self.poster.knowledge_points, 85)
        self.assertEqual(proposal_one.status, 'selected')
        self.assertEqual(proposal_two.status, 'rejected')

    def test_non_poster_cannot_select_request_proposal(self):
        proposal_one = HelpRequestProposal.objects.create(
            request=self.request_obj,
            applicant=self.helper_one,
            proposed_kp=16,
            cover_note='Can resolve quickly.',
        )

        self.client.login(username='helper_two', password='pw')
        response = self.client.post(reverse('select_request_proposal', args=[self.request_obj.pk, proposal_one.pk]))

        self.assertEqual(response.status_code, 302)
        self.request_obj.refresh_from_db()
        proposal_one.refresh_from_db()
        self.assertEqual(self.request_obj.status, 'open')
        self.assertIsNone(self.request_obj.accepted_by)
        self.assertEqual(proposal_one.status, 'pending')

    def test_helper_can_withdraw_pending_request_proposal(self):
        self.client.login(username='helper_one', password='pw')
        submit_response = self.client.post(
            reverse('submit_request_proposal', args=[self.request_obj.pk]),
            {'proposed_kp': 18, 'cover_note': 'Happy to help and share detailed notes.'},
        )
        self.assertEqual(submit_response.status_code, 302)

        withdraw_response = self.client.post(reverse('withdraw_request_proposal', args=[self.request_obj.pk]))
        self.assertEqual(withdraw_response.status_code, 302)

        proposal = HelpRequestProposal.objects.get(request=self.request_obj, applicant=self.helper_one)
        self.assertEqual(proposal.status, 'withdrawn')


class FreelanceJobProposalFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client_user = CustomUser.objects.create_user(
            username='client_prop',
            password='pw',
            wallet_inr=Decimal('3800.00'),
            compliance_verified=True,
        )
        self.freelancer_one = CustomUser.objects.create_user(username='free_one', password='pw')
        self.freelancer_two = CustomUser.objects.create_user(username='free_two', password='pw')
        self.skill = Skill.objects.create(name='Django REST')
        self.job = FreelanceJob.objects.create(
            title='Build webhook retry module',
            description='Need robust retries + dead-letter handling with audit logs.',
            client=self.client_user,
            skill_needed=self.skill,
            payment_type='fixed',
            budget_inr=Decimal('1200.00'),
            escrow_inr=Decimal('1200.00'),
            status='open',
        )

    def test_client_selects_job_proposal_refunds_and_converts_milestones(self):
        proposal_one = FreelanceJobProposal.objects.create(
            job=self.job,
            applicant=self.freelancer_one,
            proposed_total_inr=Decimal('1000.00'),
            cover_note='Deliver in two milestones with tests and docs.',
        )
        FreelanceJobProposalMilestone.objects.create(
            proposal=proposal_one,
            title='Retry orchestration and backoff policy',
            amount_inr=Decimal('600.00'),
            sequence=1,
        )
        FreelanceJobProposalMilestone.objects.create(
            proposal=proposal_one,
            title='Dead-letter queue and observability docs',
            amount_inr=Decimal('400.00'),
            sequence=2,
        )
        proposal_two = FreelanceJobProposal.objects.create(
            job=self.job,
            applicant=self.freelancer_two,
            proposed_total_inr=Decimal('1150.00'),
            cover_note='Can deliver in one phase.',
        )

        self.client.login(username='client_prop', password='pw')
        response = self.client.post(reverse('select_job_proposal', args=[self.job.pk, proposal_one.pk]))

        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        self.client_user.refresh_from_db()
        proposal_one.refresh_from_db()
        proposal_two.refresh_from_db()

        self.assertEqual(self.job.status, 'in_progress')
        self.assertEqual(self.job.freelancer, self.freelancer_one)
        self.assertEqual(self.job.budget_inr, Decimal('1000.00'))
        self.assertEqual(self.job.escrow_inr, Decimal('1000.00'))
        self.assertEqual(self.client_user.wallet_inr, Decimal('4000.00'))
        self.assertEqual(
            list(self.job.milestones.order_by('sequence').values_list('title', flat=True)),
            ['Retry orchestration and backoff policy', 'Dead-letter queue and observability docs'],
        )
        self.assertEqual(proposal_one.status, 'selected')
        self.assertEqual(proposal_two.status, 'rejected')
        self.assertTrue(WalletLedger.objects.filter(user=self.client_user, source_type='job_bid_refund').exists())

    def test_non_client_cannot_select_job_proposal(self):
        proposal_one = FreelanceJobProposal.objects.create(
            job=self.job,
            applicant=self.freelancer_one,
            proposed_total_inr=Decimal('1100.00'),
            cover_note='Can take this on immediately.',
        )

        self.client.login(username='free_two', password='pw')
        response = self.client.post(reverse('select_job_proposal', args=[self.job.pk, proposal_one.pk]))

        self.assertEqual(response.status_code, 302)
        self.job.refresh_from_db()
        proposal_one.refresh_from_db()
        self.assertEqual(self.job.status, 'open')
        self.assertIsNone(self.job.freelancer)
        self.assertEqual(proposal_one.status, 'pending')

    def test_freelancer_can_withdraw_pending_job_proposal(self):
        self.client.login(username='free_one', password='pw')
        submit_response = self.client.post(
            reverse('submit_job_proposal', args=[self.job.pk]),
            {
                'proposed_total_inr': '1100.00',
                'cover_note': 'I can deliver this with complete integration tests.',
                'milestones_input': 'Build retry core | 700 | 2026-03-15\nFinalize docs and QA | 400 | 2026-03-20',
            },
        )
        self.assertEqual(submit_response.status_code, 302)

        withdraw_response = self.client.post(reverse('withdraw_job_proposal', args=[self.job.pk]))
        self.assertEqual(withdraw_response.status_code, 302)

        proposal = FreelanceJobProposal.objects.get(job=self.job, applicant=self.freelancer_one)
        self.assertEqual(proposal.status, 'withdrawn')
        self.assertEqual(JobMilestone.objects.filter(job=self.job).count(), 0)
