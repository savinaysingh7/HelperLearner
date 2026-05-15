from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import CustomUser

from .models import FreelanceJob, JobDispute, PayoutRequest, Skill, TrustSignal
from .services import evaluate_job_collusion, process_payout_request, resolve_dispute


class DisputeResolutionServiceTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(username='admin', password='pw', email='admin@example.com')
        self.client_user = CustomUser.objects.create_user(username='client', password='pw', wallet_inr=Decimal('100.00'))
        self.freelancer = CustomUser.objects.create_user(username='freelancer', password='pw', wallet_inr=Decimal('50.00'))
        self.skill = Skill.objects.create(name='Backend')

    def test_resolve_dispute_refund_client_returns_escrow(self):
        job = FreelanceJob.objects.create(
            title='Paid bug fix',
            description='Fix production bug',
            client=self.client_user,
            freelancer=self.freelancer,
            skill_needed=self.skill,
            budget_inr=Decimal('500.00'),
            escrow_inr=Decimal('500.00'),
            status='disputed',
        )
        dispute = JobDispute.objects.create(
            job=job,
            opened_by=self.freelancer,
            against_user=self.client_user,
            reason='Scope mismatch',
        )

        resolve_dispute(dispute, 'refund_client', actor=self.admin, note='Client won')

        job.refresh_from_db()
        dispute.refresh_from_db()
        self.client_user.refresh_from_db()
        self.assertEqual(job.status, 'canceled')
        self.assertEqual(job.escrow_inr, Decimal('0.00'))
        self.assertEqual(dispute.status, 'resolved')
        self.assertEqual(dispute.resolution_type, 'refund_client')
        self.assertEqual(self.client_user.wallet_inr, Decimal('600.00'))

    def test_resolve_dispute_split_pays_both_parties(self):
        job = FreelanceJob.objects.create(
            title='API implementation',
            description='Need endpoint delivery',
            client=self.client_user,
            freelancer=self.freelancer,
            skill_needed=self.skill,
            budget_inr=Decimal('400.00'),
            escrow_inr=Decimal('400.00'),
            status='disputed',
        )
        dispute = JobDispute.objects.create(
            job=job,
            opened_by=self.client_user,
            against_user=self.freelancer,
            reason='Delivery concerns',
        )

        resolve_dispute(dispute, 'split', actor=self.admin, note='Split')

        job.refresh_from_db()
        dispute.refresh_from_db()
        self.client_user.refresh_from_db()
        self.freelancer.refresh_from_db()
        self.assertEqual(job.escrow_inr, Decimal('0.00'))
        self.assertEqual(dispute.refund_amount_inr, Decimal('200.00'))
        self.assertEqual(dispute.payout_amount_inr, Decimal('200.00'))
        self.assertEqual(self.client_user.wallet_inr, Decimal('300.00'))
        self.assertEqual(self.freelancer.wallet_inr, Decimal('250.00'))


class PayoutProcessingServiceTests(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(username='admin', password='pw', email='admin@example.com')
        self.user = CustomUser.objects.create_user(username='wallet_user', password='pw', wallet_inr=Decimal('700.00'))

    def test_reject_payout_refunds_wallet_balance(self):
        self.user.wallet_inr -= Decimal('300.00')
        self.user.save(update_fields=['wallet_inr'])
        payout = PayoutRequest.objects.create(user=self.user, amount_inr=Decimal('300.00'))

        process_payout_request(payout, 'reject', actor=self.admin, note='Invalid account details')

        payout.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(payout.status, 'rejected')
        self.assertEqual(self.user.wallet_inr, Decimal('700.00'))
        self.assertEqual(payout.processed_by, self.admin)
        self.assertIsNotNone(payout.processed_at)


class FraudSignalServiceTests(TestCase):
    def setUp(self):
        self.client_user = CustomUser.objects.create_user(username='pair_client', password='pw')
        self.freelancer = CustomUser.objects.create_user(username='pair_freelancer', password='pw')
        self.skill = Skill.objects.create(name='Django')

    def test_evaluate_job_collusion_creates_fraud_flags_at_threshold(self):
        jobs = []
        for idx in range(3):
            job = FreelanceJob.objects.create(
                title=f'Job {idx}',
                description='Repeated pair completion',
                client=self.client_user,
                freelancer=self.freelancer,
                skill_needed=self.skill,
                budget_inr=Decimal('300.00'),
                escrow_inr=Decimal('0.00'),
                status='completed',
            )
            jobs.append(job)

        created = evaluate_job_collusion(jobs[-1], threshold=3, window_days=30)

        self.assertTrue(created)
        self.assertEqual(
            TrustSignal.objects.filter(signal_type='fraud_flag', related_job=jobs[-1], user=self.client_user).count(),
            1,
        )
        self.assertEqual(
            TrustSignal.objects.filter(signal_type='fraud_flag', related_job=jobs[-1], user=self.freelancer).count(),
            1,
        )
