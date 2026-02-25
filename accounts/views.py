from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from marketplace.models import HelpRequest

from .forms import DeveloperSignUpForm, KPTransferLookupForm, UserUpdateForm
from .models import CustomUser


def _profile_queryset():
    """Return users annotated with rating aggregates and prefetched skills."""
    return CustomUser.objects.prefetch_related('skills').annotate(
        avg_rating=Avg('ratings_received__score'),
        ratings_count=Count('ratings_received'),
    )


def _month_start(reference, months_ago):
    """Return a datetime at the first day of the month N months before reference."""
    year = reference.year
    month = reference.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    return reference.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_bonus_hours(user, now):
    """Return hours remaining until the next daily KP claim, or zero if available."""
    if not user.last_kp_claim:
        return 0

    next_claim_at = user.last_kp_claim + timedelta(hours=24)
    if next_claim_at <= now:
        return 0

    remaining_seconds = (next_claim_at - now).total_seconds()
    return max(1, int((remaining_seconds + 3599) // 3600))


@csrf_protect
def signup(request):
    """Register a new user account and immediately authenticate the user."""
    if request.method == 'POST':
        form = DeveloperSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('home')
    else:
        form = DeveloperSignUpForm()

    return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile(request):
    """Render the authenticated user's profile with tasks, ratings, and listed skills."""
    profile_user = get_object_or_404(_profile_queryset(), pk=request.user.pk)
    context = {
        'profile_user': profile_user,
        'my_posts': HelpRequest.objects.filter(user=request.user).order_by('-created_at'),
        'my_tasks': HelpRequest.objects.filter(accepted_by=request.user).order_by('-created_at'),
    }
    return render(request, 'accounts/profile.html', context)


def public_profile(request, username):
    """Render the public profile view for a user including skills and rating summary."""
    profile_user = get_object_or_404(_profile_queryset(), username=username)
    context = {
        'profile_user': profile_user,
        'posted_count': HelpRequest.objects.filter(user=profile_user).count(),
        'helped_count': HelpRequest.objects.filter(accepted_by=profile_user, status='resolved').count(),
    }
    return render(request, 'accounts/public_profile.html', context)


@login_required
@csrf_protect
def edit_profile(request):
    """Update the authenticated user's email, bio, and skills list."""
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {'form': form})


@login_required
def dashboard(request):
    """Render KPI dashboard, six-month activity trends, and KP action shortcuts."""
    posted_qs = HelpRequest.objects.filter(user=request.user)
    helped_qs = HelpRequest.objects.filter(accepted_by=request.user)
    resolved_helped_qs = helped_qs.filter(status='resolved')

    total_kp_earned = resolved_helped_qs.aggregate(total=Coalesce(Sum('kp_bounty'), 0))['total']
    total_kp_spent = posted_qs.filter(status__in=['resolved', 'canceled']).aggregate(total=Coalesce(Sum('kp_bounty'), 0))['total']

    requests_posted_count = posted_qs.count()
    requests_helped_count = helped_qs.count()
    resolved_posted_count = posted_qs.filter(status='resolved').count()
    success_rate = round((resolved_posted_count / requests_posted_count) * 100, 2) if requests_posted_count else 0

    average_rating_received = request.user.ratings_received.aggregate(avg=Avg('score'))['avg']

    now = timezone.now()
    first_month = _month_start(now, 5)

    posted_by_month = {
        row['month'].date().replace(day=1): row['count']
        for row in posted_qs.filter(created_at__gte=first_month)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    }

    helped_by_month = {
        row['month'].date().replace(day=1): row['count']
        for row in resolved_helped_qs.filter(updated_at__gte=first_month)
        .annotate(month=TruncMonth('updated_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    }

    monthly_activity = []
    for months_ago in range(5, -1, -1):
        month_start = _month_start(now, months_ago)
        month_key = month_start.date().replace(day=1)
        posted_count = posted_by_month.get(month_key, 0)
        helped_count = helped_by_month.get(month_key, 0)
        total_count = posted_count + helped_count
        monthly_activity.append(
            {
                'label': month_start.strftime('%b %Y'),
                'posted_count': posted_count,
                'helped_count': helped_count,
                'total_count': total_count,
            }
        )

    max_total = max([entry['total_count'] for entry in monthly_activity], default=0)
    for entry in monthly_activity:
        entry['progress_pct'] = round((entry['total_count'] / max_total) * 100, 2) if max_total else 0

    context = {
        'total_kp_earned': total_kp_earned,
        'total_kp_spent': total_kp_spent,
        'requests_posted_count': requests_posted_count,
        'requests_helped_count': requests_helped_count,
        'success_rate': success_rate,
        'average_rating_received': average_rating_received,
        'monthly_activity': monthly_activity,
        'next_bonus_hours': _next_bonus_hours(request.user, now),
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
@csrf_protect
def claim_daily_kp(request):
    """Allow users to claim a 10 KP daily bonus once every 24 hours."""
    now = timezone.now()

    if request.method == 'POST':
        with transaction.atomic():
            locked_user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
            next_bonus_hours = _next_bonus_hours(locked_user, now)
            if next_bonus_hours == 0:
                locked_user.knowledge_points += 10
                locked_user.last_kp_claim = now
                locked_user.save(update_fields=['knowledge_points', 'last_kp_claim'])
                messages.success(request, 'Daily bonus claimed: +10 KP.')
            else:
                messages.error(request, f'Bonus already claimed. Next bonus in {next_bonus_hours} hour(s).')
        return redirect('claim_daily_kp')

    refreshed_user = CustomUser.objects.get(pk=request.user.pk)
    next_bonus_hours = _next_bonus_hours(refreshed_user, now)
    return render(
        request,
        'accounts/claim_daily_kp.html',
        {
            'next_bonus_hours': next_bonus_hours,
            'can_claim': next_bonus_hours == 0,
        },
    )


@login_required
@csrf_protect
def transfer_kp(request):
    """Confirm and execute an atomic KP transfer from the current user to another user."""
    if request.method == 'POST':
        form = KPTransferLookupForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Please provide a valid recipient and amount.')
            return render(request, 'accounts/transfer_kp.html', {'form': form})

        recipient = get_object_or_404(CustomUser, username=form.cleaned_data['recipient_username'])
        amount = form.cleaned_data['amount']
        if recipient.pk == request.user.pk:
            messages.error(request, 'You cannot transfer KP to yourself.')
            return render(request, 'accounts/transfer_kp.html', {'form': KPTransferLookupForm()})

        with transaction.atomic():
            sender_id = request.user.pk
            receiver_id = recipient.pk
            locked_users = list(
                CustomUser.objects.select_for_update()
                .filter(pk__in=[sender_id, receiver_id])
                .order_by('pk')
            )
            locked_map = {user.pk: user for user in locked_users}
            sender = locked_map[sender_id]
            receiver = locked_map[receiver_id]

            if sender.knowledge_points < amount:
                messages.error(request, 'Insufficient KP for this transfer.')
                return redirect('transfer_kp')

            sender.knowledge_points -= amount
            receiver.knowledge_points += amount
            sender.save(update_fields=['knowledge_points'])
            receiver.save(update_fields=['knowledge_points'])

        messages.success(request, f'Successfully transferred {amount} KP to {receiver.username}.')
        return redirect('dashboard')

    if request.GET.get('recipient_username') and request.GET.get('amount'):
        form = KPTransferLookupForm(request.GET)
        if form.is_valid():
            recipient = get_object_or_404(CustomUser, username=form.cleaned_data['recipient_username'])
            if recipient.pk == request.user.pk:
                messages.error(request, 'You cannot transfer KP to yourself.')
                return render(request, 'accounts/transfer_kp.html', {'form': KPTransferLookupForm()})
            return render(
                request,
                'accounts/transfer_kp.html',
                {
                    'form': KPTransferLookupForm(initial=form.cleaned_data),
                    'confirmation': True,
                    'recipient': recipient,
                    'amount': form.cleaned_data['amount'],
                },
            )
        messages.error(request, 'Please provide a valid recipient and amount (minimum 5 KP).')

    return render(request, 'accounts/transfer_kp.html', {'form': KPTransferLookupForm()})
