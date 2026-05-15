from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import FreelanceJob, JobMilestone, PayoutRequest, Skill, WalletLedger


class PaidJobsFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client_user = CustomUser.objects.create_user(
            username='client_user',
            password='pw',
            wallet_inr=Decimal('5000.00'),
            compliance_verified=True,
        )
        self.freelancer = CustomUser.objects.create_user(
            username='freelancer_user',
            password='pw',
            wallet_inr=Decimal('100.00'),
            compliance_verified=True,
        )
        self.skill = Skill.objects.create(name='Backend')

    def test_post_freelance_job_debits_wallet_and_funds_escrow(self):
        self.client.login(username='client_user', password='pw')
        response = self.client.post(
            reverse('post_freelance_job'),
            {
                'title': 'Build secure auth module',
                'description': 'Need JWT auth + refresh token support',
                'skill_needed': self.skill.pk,
                'payment_type': 'fixed',
                'budget_inr': '1200.00',
                'response_sla_hours': 24,
                'tags_input': 'django,auth',
            },
        )

        self.assertEqual(response.status_code, 302)
        job = FreelanceJob.objects.get(title='Build secure auth module')
        self.client_user.refresh_from_db()
        self.assertEqual(job.escrow_inr, Decimal('1200.00'))
        self.assertEqual(self.client_user.wallet_inr, Decimal('3800.00'))
        self.assertEqual(job.milestones.count(), 1)
        self.assertTrue(WalletLedger.objects.filter(user=self.client_user, source_type='job_escrow').exists())

    def test_claim_submit_release_milestone_credits_freelancer_and_completes_job(self):
        job = FreelanceJob.objects.create(
            title='Fix production bug',
            description='Need urgent fix',
            client=self.client_user,
            skill_needed=self.skill,
            payment_type='fixed',
            budget_inr=Decimal('900.00'),
            escrow_inr=Decimal('900.00'),
        )
        milestone = JobMilestone.objects.create(job=job, title='Deliver patch', amount_inr=Decimal('900.00'), sequence=1)

        self.client.login(username='freelancer_user', password='pw')
        claim_response = self.client.post(reverse('claim_freelance_job', args=[job.pk]))
        self.assertEqual(claim_response.status_code, 302)
        submit_response = self.client.post(reverse('submit_job_milestone', args=[job.pk, milestone.pk]))
        self.assertEqual(submit_response.status_code, 302)

        self.client.logout()
        self.client.login(username='client_user', password='pw')
        release_response = self.client.post(reverse('release_job_milestone', args=[job.pk, milestone.pk]))
        self.assertEqual(release_response.status_code, 302)

        job.refresh_from_db()
        milestone.refresh_from_db()
        self.freelancer.refresh_from_db()
        self.assertEqual(milestone.status, 'released')
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.escrow_inr, Decimal('0.00'))
        self.assertEqual(self.freelancer.wallet_inr, Decimal('1000.00'))

    def test_non_client_cannot_release_milestone(self):
        job = FreelanceJob.objects.create(
            title='Refactor service',
            description='Cleanup code',
            client=self.client_user,
            freelancer=self.freelancer,
            status='in_progress',
            skill_needed=self.skill,
            budget_inr=Decimal('600.00'),
            escrow_inr=Decimal('600.00'),
        )
        milestone = JobMilestone.objects.create(
            job=job,
            title='Submit refactor',
            amount_inr=Decimal('600.00'),
            sequence=1,
            status='submitted',
        )
        self.client.login(username='freelancer_user', password='pw')
        response = self.client.post(reverse('release_job_milestone', args=[job.pk, milestone.pk]))

        self.assertEqual(response.status_code, 302)
        milestone.refresh_from_db()
        self.assertEqual(milestone.status, 'submitted')


class WalletPayoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username='wallet_user',
            password='pw',
            wallet_inr=Decimal('1500.00'),
            compliance_verified=False,
        )

    def test_payout_request_requires_compliance_then_succeeds(self):
        self.client.login(username='wallet_user', password='pw')
        blocked_response = self.client.post(reverse('wallet_overview'), {'amount_inr': '500.00', 'note': 'Weekly payout'})
        self.assertEqual(blocked_response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.wallet_inr, Decimal('1500.00'))
        self.assertEqual(PayoutRequest.objects.count(), 0)

        self.user.compliance_verified = True
        self.user.save(update_fields=['compliance_verified'])
        allowed_response = self.client.post(reverse('wallet_overview'), {'amount_inr': '500.00', 'note': 'Weekly payout'})
        self.assertEqual(allowed_response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.wallet_inr, Decimal('1000.00'))
        self.assertEqual(PayoutRequest.objects.count(), 1)


class PaidJobsApiTests(TestCase):
    def setUp(self):
        self.client_user = CustomUser.objects.create_user(username='api_client', password='pw', wallet_inr=Decimal('2000.00'))
        self.skill = Skill.objects.create(name='Django API')
        FreelanceJob.objects.create(
            title='API endpoint optimization',
            description='Need query optimization and pagination',
            client=self.client_user,
            skill_needed=self.skill,
            payment_type='fixed',
            budget_inr=Decimal('1000.00'),
            escrow_inr=Decimal('1000.00'),
            status='open',
        )

    def test_api_jobs_list_supports_filtering(self):
        response = self.client.get(reverse('api-job-list'), {'status': 'open'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['results'][0]['title'], 'API endpoint optimization')
