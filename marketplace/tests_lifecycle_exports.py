from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser

from .models import HelpRequest, JobDispute, JobMilestone, Skill, WalletLedger, FreelanceJob


class LifecycleTimelineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.poster = CustomUser.objects.create_user(username='timeline_poster', password='pw')
        self.helper = CustomUser.objects.create_user(username='timeline_helper', password='pw')
        self.skill = Skill.objects.create(name='Timeline Skill')

    def test_request_detail_shows_request_lifecycle_section(self):
        req = HelpRequest.objects.create(
            title='Resolved request timeline',
            description='Need root-cause analysis and final fix notes.',
            user=self.poster,
            skill_needed=self.skill,
            kp_bounty=12,
            status='resolved',
            accepted_by=self.helper,
        )
        self.client.login(username='timeline_poster', password='pw')

        response = self.client.get(reverse('request_detail', args=[req.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Request Lifecycle')
        self.assertContains(response, 'Posted')
        self.assertContains(response, 'In Progress')
        self.assertContains(response, 'Resolved')
        self.assertContains(response, 'Canceled')

    def test_job_detail_shows_escrow_lifecycle_section(self):
        job = FreelanceJob.objects.create(
            title='Escrow timeline job',
            description='Ship webhook retries and observability.',
            client=self.poster,
            freelancer=self.helper,
            skill_needed=self.skill,
            budget_inr=Decimal('900.00'),
            escrow_inr=Decimal('900.00'),
            status='in_progress',
        )
        JobMilestone.objects.create(
            job=job,
            title='Implement retry loop',
            amount_inr=Decimal('900.00'),
            sequence=1,
            status='submitted',
            submitted_at=timezone.now(),
        )

        response = self.client.get(reverse('freelance_job_detail', args=[job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Escrow Lifecycle')
        self.assertContains(response, 'Posted')
        self.assertContains(response, 'Accepted')
        self.assertContains(response, 'Work Submitted')
        self.assertContains(response, 'Payout Released')

    def test_job_lifecycle_uses_disputed_closed_label(self):
        job = FreelanceJob.objects.create(
            title='Disputed job timeline',
            description='Delivery disagreement requires dispute handling.',
            client=self.poster,
            freelancer=self.helper,
            skill_needed=self.skill,
            budget_inr=Decimal('1100.00'),
            escrow_inr=Decimal('600.00'),
            status='disputed',
        )

        response = self.client.get(reverse('freelance_job_detail', args=[job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Disputed')


class CsvExportTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(username='csv_user', password='pw')
        self.other = CustomUser.objects.create_user(username='csv_other', password='pw')
        self.skill = Skill.objects.create(name='CSV Skill')

    def test_wallet_export_requires_authentication(self):
        response = self.client.get(reverse('wallet_export_csv'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response['Location'])

    def test_wallet_export_returns_only_logged_in_user_entries(self):
        WalletLedger.objects.create(
            user=self.user,
            direction='credit',
            amount_inr=Decimal('120.00'),
            source_type='job_milestone_release',
            reference_id=10,
            description='Milestone payout',
        )
        WalletLedger.objects.create(
            user=self.other,
            direction='credit',
            amount_inr=Decimal('999.00'),
            source_type='job_milestone_release',
            reference_id=99,
            description='Should not appear',
        )

        self.client.login(username='csv_user', password='pw')
        response = self.client.get(reverse('wallet_export_csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('wallet_ledger.csv', response['Content-Disposition'])
        csv_text = response.content.decode('utf-8')
        self.assertIn('Milestone payout', csv_text)
        self.assertNotIn('Should not appear', csv_text)

    def test_disputes_export_returns_only_related_disputes(self):
        related_job = FreelanceJob.objects.create(
            title='Related dispute job',
            description='User is client here.',
            client=self.user,
            freelancer=self.other,
            skill_needed=self.skill,
            budget_inr=Decimal('800.00'),
            escrow_inr=Decimal('800.00'),
            status='disputed',
        )
        unrelated_client = CustomUser.objects.create_user(username='csv_unrelated_client', password='pw')
        unrelated_freelancer = CustomUser.objects.create_user(username='csv_unrelated_freelancer', password='pw')
        unrelated_job = FreelanceJob.objects.create(
            title='Unrelated dispute job',
            description='User is not involved.',
            client=unrelated_client,
            freelancer=unrelated_freelancer,
            skill_needed=self.skill,
            budget_inr=Decimal('700.00'),
            escrow_inr=Decimal('700.00'),
            status='disputed',
        )

        JobDispute.objects.create(
            job=related_job,
            opened_by=self.user,
            against_user=self.other,
            reason='Milestone quality mismatch',
            status='open',
        )
        JobDispute.objects.create(
            job=unrelated_job,
            opened_by=unrelated_client,
            against_user=unrelated_freelancer,
            reason='Unrelated disagreement',
            status='open',
        )

        self.client.login(username='csv_user', password='pw')
        response = self.client.get(reverse('job_disputes_export_csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('job_disputes.csv', response['Content-Disposition'])
        csv_text = response.content.decode('utf-8')
        self.assertIn('Related dispute job', csv_text)
        self.assertNotIn('Unrelated dispute job', csv_text)
