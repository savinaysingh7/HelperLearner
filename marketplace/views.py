from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from rest_framework import viewsets

from accounts.models import CustomUser

from .forms import CommentForm, HelpRequestForm, SearchForm
from .models import HelpRequest
from .serializers import HelpRequestSerializer


def home(request):
    """Render the homepage with live user and open-request stats."""
    context = {
        'total_users': CustomUser.objects.count(),
        'open_requests': HelpRequest.objects.filter(status='open').count(),
        'recent_requests': HelpRequest.objects.filter(status='open').order_by('-created_at')[:3],
    }
    return render(request, 'marketplace/home.html', context)


def request_list(request):
    """List open and in-progress requests with search filters and pagination."""
    all_requests = HelpRequest.objects.filter(status__in=['open', 'in_progress']).order_by('-created_at')
    form = SearchForm(request.GET)

    if form.is_valid():
        query = form.cleaned_data.get('q')
        skill_filter = form.cleaned_data.get('skill')

        if query:
            all_requests = all_requests.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )
        if skill_filter:
            all_requests = all_requests.filter(skill_needed=skill_filter)

    paginator = Paginator(all_requests, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'requests': page_obj,
        'form': form,
        'page_obj': page_obj,
    }
    return render(request, 'marketplace/request_list.html', context)


@login_required
@csrf_protect
@ratelimit(key='ip', rate='10/m', block=True)
def create_request(request):
    """Create a request and escrow bounty points from the posting user."""
    if request.method == 'POST':
        form = HelpRequestForm(request.POST)
        if form.is_valid():
            help_req = form.save(commit=False)

            if request.user.knowledge_points < help_req.kp_bounty:
                messages.error(request, "You don't have enough Knowledge Points for this bounty!")
                return render(request, 'marketplace/create_request.html', {'form': form})

            with transaction.atomic():
                request.user.knowledge_points -= help_req.kp_bounty
                request.user.save()

                help_req.user = request.user
                help_req.save()

            messages.success(request, 'Your request has been posted and the bounty is in escrow.')
            return redirect('request_list')
    else:
        form = HelpRequestForm()

    return render(request, 'marketplace/create_request.html', {'form': form})


@csrf_protect
def request_detail(request, pk):
    """Display one request and allow authenticated users to add comments."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if request.user.is_authenticated and request.user in [help_req.user, help_req.accepted_by]:
        comments = help_req.comments.all().order_by('-created_at')
    else:
        comments = help_req.comments.filter(is_private=False).order_by('-created_at')

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.warning(request, 'You must be logged in to comment.')
            return redirect('login')

        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.request = help_req

            if comment.is_private and (
                request.user not in [help_req.user, help_req.accepted_by] or help_req.status != 'in_progress'
            ):
                comment.is_private = False

            comment.save()
            return redirect('request_detail', pk=pk)
    else:
        form = CommentForm()

    return render(
        request,
        'marketplace/request_detail.html',
        {
            'req': help_req,
            'comments': comments,
            'form': form,
        },
    )


@login_required
@csrf_protect
@ratelimit(key='ip', rate='20/m', block=True)
@require_POST
def claim_request(request, pk):
    """Claim an open request for the current user (POST-only endpoint)."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user == request.user:
        messages.warning(request, 'You cannot claim your own request.')
        return redirect('request_detail', pk=pk)

    if help_req.status != 'open':
        messages.error(request, 'This request is no longer open for claiming.')
        return redirect('request_detail', pk=pk)

    help_req.status = 'in_progress'
    help_req.accepted_by = request.user
    help_req.save()
    messages.success(request, f'You have accepted the request: {help_req.title}')
    return redirect('request_detail', pk=pk)


@login_required
@csrf_protect
def resolve_request(request, pk):
    """Resolve an in-progress request and transfer escrowed points to the helper."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user != request.user:
        messages.error(request, 'Only the poster can resolve this request.')
        return redirect('request_detail', pk=pk)

    if help_req.status == 'resolved':
        messages.info(request, 'This request has already been resolved.')
        return redirect('request_detail', pk=pk)

    if not (help_req.status == 'in_progress' and help_req.accepted_by):
        messages.error(request, "Request must be 'In Progress' with a helper to be resolved.")
        return redirect('request_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_resolve.html', {'req': help_req})

    with transaction.atomic():
        help_req = get_object_or_404(HelpRequest.objects.select_for_update(), pk=pk)
        helper = help_req.accepted_by
        helper.knowledge_points += help_req.kp_bounty
        helper.save()

        help_req.status = 'resolved'
        help_req.save()

        messages.success(request, f'Task resolved. {help_req.kp_bounty} KP transferred to {helper.username}.')

    return redirect('request_detail', pk=pk)


@login_required
@csrf_protect
def cancel_request(request, pk):
    """Cancel an open/in-progress request and refund escrowed points to the poster."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user != request.user:
        messages.error(request, 'Only the poster can cancel this request.')
        return redirect('request_detail', pk=pk)

    if help_req.status not in ['open', 'in_progress']:
        messages.error(request, "Only 'Open' or 'In Progress' requests can be canceled.")
        return redirect('request_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_cancel.html', {'req': help_req})

    with transaction.atomic():
        help_req = get_object_or_404(HelpRequest.objects.select_for_update(), pk=pk)
        help_req.user.knowledge_points += help_req.kp_bounty
        help_req.user.save()
        help_req.status = 'canceled'
        help_req.save()

        messages.success(
            request,
            f"Request '{help_req.title}' has been canceled. {help_req.kp_bounty} KP refunded.",
        )

    return redirect('request_detail', pk=pk)


class HelpRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API endpoint for listing and retrieving help requests."""

    queryset = HelpRequest.objects.all().order_by('-created_at')
    serializer_class = HelpRequestSerializer
