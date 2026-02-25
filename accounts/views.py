from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from marketplace.models import HelpRequest

from .forms import DeveloperSignUpForm, UserUpdateForm
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
    """Render KPI dashboard and six-month activity trends for the authenticated user."""
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
    }
    return render(request, 'accounts/dashboard.html', context)
