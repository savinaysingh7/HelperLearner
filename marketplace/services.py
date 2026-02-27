from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.utils import log_event
from .models import FreelanceJob, FraudAlert, JobDispute, PayoutRequest, TrustSignal, WalletLedger
from .webhooks import dispatch_webhook_event


def record_wallet_entry(user, direction, amount_inr, source_type, reference_id=None, description=''):
    """Persist a wallet ledger entry for INR balance traceability."""
    return WalletLedger.objects.create(
        user=user,
        direction=direction,
        amount_inr=amount_inr,
        source_type=source_type,
        reference_id=reference_id,
        description=description,
    )


def evaluate_job_collusion(job, threshold=3, window_days=30):
    """Create fraud flags when a client-freelancer pair resolves too many jobs in a short window."""
    if not job.client_id or not job.freelancer_id:
        return False

    window_start = timezone.now() - timedelta(days=window_days)
    pair_count = FreelanceJob.objects.filter(
        client_id=job.client_id,
        freelancer_id=job.freelancer_id,
        status='completed',
        updated_at__gte=window_start,
    ).count()
    if pair_count < threshold:
        return False

    created = False
    for user_id in [job.client_id, job.freelancer_id]:
        exists = TrustSignal.objects.filter(
            user_id=user_id,
            signal_type='fraud_flag',
            related_job_id=job.pk,
        ).exists()
        if not exists:
            TrustSignal.objects.create(
                user_id=user_id,
                signal_type='fraud_flag',
                score_delta=-4,
                detail=f'High-frequency completions between same pair in {window_days} days.',
                related_job=job,
            )
            FraudAlert.objects.create(
                user_id=user_id,
                related_user_id=job.freelancer_id if user_id == job.client_id else job.client_id,
                alert_type='collusion',
                severity='high',
                description=f'Potential collusion detected on job #{job.pk}.',
                metadata={'window_days': window_days, 'pair_count': pair_count},
            )
            created = True
    return created


def process_payout_request(payout_request, action, actor=None, note=''):
    """Advance payout request status with proper wallet compensation rules."""
    if action not in {'approve', 'pay', 'reject'}:
        raise ValueError('Unsupported payout action.')

    with transaction.atomic():
        payout = (
            PayoutRequest.objects.select_for_update()
            .select_related('user')
            .get(pk=payout_request.pk)
        )
        user = payout.user.__class__.objects.select_for_update().get(pk=payout.user_id)

        if action == 'approve':
            if payout.status != 'pending':
                raise ValueError('Only pending requests can be approved.')
            payout.status = 'approved'

        elif action == 'pay':
            if payout.status not in {'approved', 'pending'}:
                raise ValueError('Only pending/approved requests can be marked as paid.')
            payout.status = 'paid'

        elif action == 'reject':
            if payout.status == 'paid':
                raise ValueError('Paid requests cannot be rejected.')
            if payout.status != 'rejected':
                user.wallet_inr += payout.amount_inr
                user.save(update_fields=['wallet_inr'])
                record_wallet_entry(
                    user=user,
                    direction='credit',
                    amount_inr=payout.amount_inr,
                    source_type='payout_reversal',
                    reference_id=payout.pk,
                    description='Payout request rejected and amount returned to wallet.',
                )
            payout.status = 'rejected'

        if note:
            payout.note = note
        payout.processed_by = actor
        payout.processed_at = timezone.now()
        payout.save(update_fields=['status', 'note', 'processed_by', 'processed_at', 'updated_at'])

    dispatch_webhook_event(
        payout.user,
        'payout.processed',
        {
            'payout_request_id': payout.pk,
            'status': payout.status,
            'amount_inr': str(payout.amount_inr),
            'processed_by': actor.username if actor else 'system',
        },
    )
    return payout


def resolve_dispute(dispute_obj, outcome, actor=None, note=''):
    """Resolve a dispute by refunding client, paying freelancer, or splitting escrow."""
    if outcome not in {'refund_client', 'pay_freelancer', 'split'}:
        raise ValueError('Unsupported dispute outcome.')

    with transaction.atomic():
        dispute = (
            JobDispute.objects.select_for_update()
            .select_related('job', 'opened_by', 'against_user')
            .get(pk=dispute_obj.pk)
        )
        job = FreelanceJob.objects.select_for_update().get(pk=dispute.job_id)
        client = job.client.__class__.objects.select_for_update().get(pk=job.client_id)
        freelancer = None
        if job.freelancer_id:
            freelancer = job.client.__class__.objects.select_for_update().get(pk=job.freelancer_id)

        if dispute.status != 'open':
            raise ValueError('Only open disputes can be resolved.')
        escrow_remaining = job.escrow_inr
        if escrow_remaining <= 0:
            raise ValueError('No escrow available for dispute resolution.')

        refund_amount = Decimal('0.00')
        payout_amount = Decimal('0.00')

        if outcome == 'refund_client':
            refund_amount = escrow_remaining
            client.wallet_inr += refund_amount
            client.save(update_fields=['wallet_inr'])
            record_wallet_entry(
                user=client,
                direction='credit',
                amount_inr=refund_amount,
                source_type='dispute_refund',
                reference_id=dispute.pk,
                description=f'Dispute #{dispute.pk} resolved in client favor.',
            )
            job.status = 'canceled'

        elif outcome == 'pay_freelancer':
            if not freelancer:
                raise ValueError('Cannot pay freelancer because no freelancer is assigned.')
            payout_amount = escrow_remaining
            freelancer.wallet_inr += payout_amount
            freelancer.save(update_fields=['wallet_inr'])
            record_wallet_entry(
                user=freelancer,
                direction='credit',
                amount_inr=payout_amount,
                source_type='dispute_payout',
                reference_id=dispute.pk,
                description=f'Dispute #{dispute.pk} resolved in freelancer favor.',
            )
            job.status = 'completed'

        elif outcome == 'split':
            if not freelancer:
                raise ValueError('Cannot split without an assigned freelancer.')
            payout_amount = (escrow_remaining / Decimal('2')).quantize(Decimal('0.01'))
            refund_amount = (escrow_remaining - payout_amount).quantize(Decimal('0.01'))
            client.wallet_inr += refund_amount
            freelancer.wallet_inr += payout_amount
            client.save(update_fields=['wallet_inr'])
            freelancer.save(update_fields=['wallet_inr'])
            record_wallet_entry(
                user=client,
                direction='credit',
                amount_inr=refund_amount,
                source_type='dispute_split_refund',
                reference_id=dispute.pk,
                description=f'Dispute #{dispute.pk} split resolution (client portion).',
            )
            record_wallet_entry(
                user=freelancer,
                direction='credit',
                amount_inr=payout_amount,
                source_type='dispute_split_payout',
                reference_id=dispute.pk,
                description=f'Dispute #{dispute.pk} split resolution (freelancer portion).',
            )
            job.status = 'completed'

        job.escrow_inr = Decimal('0.00')
        job.save(update_fields=['status', 'escrow_inr', 'updated_at'])

        dispute.status = 'resolved'
        dispute.resolution_type = outcome
        dispute.refund_amount_inr = refund_amount
        dispute.payout_amount_inr = payout_amount
        dispute.resolution_note = note
        dispute.resolved_by = actor
        dispute.resolved_at = timezone.now()
        dispute.save(
            update_fields=[
                'status',
                'resolution_type',
                'refund_amount_inr',
                'payout_amount_inr',
                'resolution_note',
                'resolved_by',
                'resolved_at',
                'updated_at',
            ]
        )

    dispatch_webhook_event(
        client,
        'dispute.resolved',
        {
            'dispute_id': dispute.pk,
            'job_id': job.pk,
            'resolution_type': dispute.resolution_type,
            'refund_amount_inr': str(dispute.refund_amount_inr),
            'payout_amount_inr': str(dispute.payout_amount_inr),
        },
    )
    return dispute
