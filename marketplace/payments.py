"""Razorpay payment gateway integration for HelperLearner.

Handles:
- Wallet top-ups (user adds INR to their wallet)
- Milestone escrow payments (client funds a milestone)
- Payment verification via webhook + signature validation
"""

import hashlib
import hmac
import json
import logging
from decimal import Decimal

import razorpay
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from marketplace.models import FreelanceJob, JobMilestone

logger = logging.getLogger(__name__)


def _get_client():
    """Return a configured Razorpay client instance."""
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
    if not key_id or not key_secret:
        raise RuntimeError('Razorpay credentials not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.')
    return razorpay.Client(auth=(key_id, key_secret))


# ── Wallet Top-Up ────────────────────────────────────────────────────────────

@login_required
def wallet_topup(request):
    """Show wallet top-up page and create a Razorpay order."""
    amount_inr = Decimal('0')
    order = None
    error = None

    if request.method == 'POST':
        try:
            amount_inr = Decimal(request.POST.get('amount', '0'))
            if amount_inr < 10:
                error = 'Minimum top-up amount is ₹10.'
            elif amount_inr > 50000:
                error = 'Maximum top-up amount is ₹50,000.'
            else:
                client = _get_client()
                order = client.order.create({
                    'amount': int(amount_inr * 100),  # Razorpay uses paise
                    'currency': 'INR',
                    'receipt': f'topup_{request.user.pk}_{int(amount_inr)}',
                    'notes': {
                        'user_id': str(request.user.pk),
                        'type': 'wallet_topup',
                    },
                })
        except (ValueError, TypeError):
            error = 'Invalid amount.'
        except Exception as e:
            logger.exception('Razorpay order creation failed')
            error = f'Payment gateway error: {e}'

    return render(request, 'marketplace/wallet_topup.html', {
        'amount': amount_inr,
        'order': order,
        'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'user': request.user,
        'error': error,
    })


@login_required
@require_POST
def wallet_topup_verify(request):
    """Verify a Razorpay payment for wallet top-up and credit the user."""
    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    razorpay_signature = request.POST.get('razorpay_signature', '')

    if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
        return JsonResponse({'status': 'error', 'message': 'Missing payment details'}, status=400)

    try:
        client = _get_client()
        client.utility.verify_payment_signature({
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_order_id': razorpay_order_id,
            'razorpay_signature': razorpay_signature,
        })

        # Fetch order to get amount
        order = client.order.fetch(razorpay_order_id)
        amount_paise = order.get('amount', 0)
        amount_inr = Decimal(str(amount_paise)) / Decimal('100')

        # Credit wallet
        with transaction.atomic():
            user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            user.wallet_inr += amount_inr
            user.save(update_fields=['wallet_inr'])

        logger.info('Wallet top-up successful: user=%s amount=₹%s payment=%s',
                     request.user.username, amount_inr, razorpay_payment_id)

        return JsonResponse({
            'status': 'success',
            'message': f'₹{amount_inr} added to your wallet!',
            'new_balance': str(user.wallet_inr),
        })

    except razorpay.errors.SignatureVerificationError:
        logger.warning('Razorpay signature verification failed: order=%s', razorpay_order_id)
        return JsonResponse({'status': 'error', 'message': 'Payment verification failed'}, status=400)
    except Exception as e:
        logger.exception('Wallet top-up verification error')
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ── Milestone Escrow Funding ─────────────────────────────────────────────────

@login_required
def fund_milestone(request, job_pk, milestone_id):
    """Create a Razorpay order to fund a specific milestone escrow."""
    job = get_object_or_404(FreelanceJob, pk=job_pk, client=request.user)
    milestone = get_object_or_404(JobMilestone, pk=milestone_id, job=job)

    if milestone.status != 'pending':
        return JsonResponse({'error': 'Milestone cannot be funded in its current state'}, status=400)

    try:
        client = _get_client()
        order = client.order.create({
            'amount': int(milestone.amount_inr * 100),
            'currency': 'INR',
            'receipt': f'milestone_{milestone.pk}',
            'notes': {
                'user_id': str(request.user.pk),
                'milestone_id': str(milestone.pk),
                'job_id': str(job.pk),
                'type': 'milestone_escrow',
            },
        })
        return JsonResponse({
            'order_id': order['id'],
            'amount': int(milestone.amount_inr * 100),
            'currency': 'INR',
            'razorpay_key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        })
    except Exception as e:
        logger.exception('Milestone funding order creation failed')
        return JsonResponse({'error': str(e)}, status=500)


# ── Razorpay Webhook ─────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Handle Razorpay payment event webhooks with signature verification."""
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not webhook_secret:
        return HttpResponse('Webhook not configured', status=503)

    # Verify signature
    signature = request.headers.get('X-Razorpay-Signature', '')
    body = request.body

    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning('Razorpay webhook signature mismatch')
        return HttpResponse('Invalid signature', status=400)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    event = payload.get('event', '')
    logger.info('Razorpay webhook received: event=%s', event)

    if event == 'payment.captured':
        _handle_payment_captured(payload)

    return HttpResponse('OK', status=200)


def _handle_payment_captured(payload):
    """Process a captured payment — credit wallet or fund milestone escrow."""
    entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    notes = entity.get('notes', {})
    payment_type = notes.get('type', '')

    if payment_type == 'wallet_topup':
        user_id = notes.get('user_id')
        amount_paise = entity.get('amount', 0)
        amount_inr = Decimal(str(amount_paise)) / Decimal('100')

        from accounts.models import CustomUser
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().get(pk=user_id)
            user.wallet_inr += amount_inr
            user.save(update_fields=['wallet_inr'])
            logger.info('Webhook wallet credit: user=%s amount=₹%s', user.username, amount_inr)

    elif payment_type == 'milestone_escrow':
        milestone_id = notes.get('milestone_id')
        with transaction.atomic():
            milestone = JobMilestone.objects.select_for_update().get(pk=milestone_id)
            if milestone.status == 'pending':
                milestone.status = 'funded'
                milestone.save(update_fields=['status'])
                logger.info('Webhook milestone funded: milestone=%s', milestone_id)
