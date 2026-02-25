from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from .models import HelpRequest, Comment, Skill
from .forms import HelpRequestForm, CommentForm, SearchForm
from accounts.models import CustomUser

# API imports moved to top
from rest_framework import viewsets
from .serializers import HelpRequestSerializer

# Rate limiting
from ratelimit.decorators import ratelimit
from django.views.decorators.csrf import csrf_protect


def home(request):
    """Render the homepage with live stats and recent open requests."""
    total_users = CustomUser.objects.count()
    open_requests = HelpRequest.objects.filter(status='open').count()
    recent_requests = HelpRequest.objects.filter(status='open').order_by('-created_at')[:3]

    context = {
        'total_users': total_users,
        'open_requests': open_requests,
        'recent_requests': recent_requests,
    }
    return render(request, 'marketplace/home.html', context)


def request_list(request):
    """List open and in-progress help requests with filtering and pagination."""
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

    paginator = Paginator(all_requests, 10)  # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

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
    """Create a help request; deduct bounty from user's points (escrow).

    Rate-limited to prevent abuse.
    """
    if request.method == 'POST':
        form = HelpRequestForm(request.POST)
        if form.is_valid():
            help_req = form.save(commit=False)
            
            # Check if user has enough points
            if request.user.knowledge_points < help_req.kp_bounty:
                messages.error(request, "You don't have enough Knowledge Points for this bounty!")
                return render(request, 'marketplace/create_request.html', {'form': form})

            # Use a transaction to ensure data integrity
            with transaction.atomic():
                # Deduct points from user (escrow)
                request.user.knowledge_points -= help_req.kp_bounty
                request.user.save()

                # Save the request
                help_req.user = request.user
                help_req.save()

            messages.success(request, "Your request has been posted and the bounty is in escrow.")
            return redirect('request_list')
    else:
        form = HelpRequestForm()
    return render(request, 'marketplace/create_request.html', {'form': form})


@csrf_protect
def request_detail(request, pk):
    """Show a single help request and its discussion/comments.

    Private comments are only visible to the requester and assigned helper.
    """
    help_req = get_object_or_404(HelpRequest, pk=pk)
    
    # Filter comments: show all public ones, but private ones only to the requester and the helper
    if request.user.is_authenticated:
        if request.user == help_req.user or request.user == help_req.accepted_by:
            # Requesters and helpers see all comments
            comments = help_req.comments.all().order_by('-created_at')
        else:
            # Others only see public comments
            comments = help_req.comments.filter(is_private=False).order_by('-created_at')
    else:
        # Unauthenticated users only see public comments
        comments = help_req.comments.filter(is_private=False).order_by('-created_at')

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.warning(request, "You must be logged in to comment.")
            return redirect('login')
        
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.request = help_req
            
            # Security: Only requester and helper can post private comments
            # And only if the request is 'in_progress'
            if comment.is_private:
                if request.user not in [help_req.user, help_req.accepted_by] or help_req.status != 'in_progress':
                    comment.is_private = False
                
            comment.save()
            return redirect('request_detail', pk=pk)
    else:
        form = CommentForm()

    return render(request, 'marketplace/request_detail.html', {
        'req': help_req,
        'comments': comments,
        'form': form
    })


@login_required
@csrf_protect
@ratelimit(key='ip', rate='20/m', block=True)
def claim_request(request, pk):
    """Allow an authenticated user to claim an open help request.

    Rate-limited to prevent mass claiming.
    """
    help_req = get_object_or_404(HelpRequest, pk=pk)
    if help_req.user == request.user:
        messages.warning(request, "You cannot claim your own request.")
        return redirect('request_detail', pk=pk)

    if help_req.status != 'open':
        messages.error(request, "This request is no longer open for claiming.")
        return redirect('request_detail', pk=pk)

    help_req.status = 'in_progress'
    help_req.accepted_by = request.user
    help_req.save()
    messages.success(request, f"You have accepted the request: {help_req.title}")

    return redirect('request_detail', pk=pk)


@login_required
@csrf_protect
def resolve_request(request, pk):
    """Mark an in-progress request as resolved and transfer escrowed KP to helper."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user != request.user:
        messages.error(request, "Only the poster can resolve this request.")
        return redirect('request_detail', pk=pk)

    if help_req.status == 'resolved':
        messages.info(request, "This request has already been resolved.")
        return redirect('request_detail', pk=pk)

    if not (help_req.status == 'in_progress' and help_req.accepted_by):
        messages.error(request, "Request must be 'In Progress' with a helper to be resolved.")
        return redirect('request_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_resolve.html', {'req': help_req})

    # POST logic
    with transaction.atomic():
        help_req = get_object_or_404(
            HelpRequest.objects.select_for_update(), pk=pk
        )
        
        # Points are already in escrow, so we just award them to the helper
        helper = help_req.accepted_by
        helper.knowledge_points += help_req.kp_bounty
        helper.save()

        help_req.status = 'resolved'
        help_req.save()

        messages.success(request, f"Task Resolved! {help_req.kp_bounty} KP transferred to {helper.username}.")

    return redirect('request_detail', pk=pk)

@login_required
@csrf_protect
def cancel_request(request, pk):
    """Cancel a user's request and refund escrowed KP to the poster."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user != request.user:
        messages.error(request, "Only the poster can cancel this request.")
        return redirect('request_detail', pk=pk)

    if help_req.status not in ['open', 'in_progress']:
        messages.error(request, "Only 'Open' or 'In Progress' requests can be canceled.")
        return redirect('request_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_cancel.html', {'req': help_req})

    # POST: refund and cancel
    with transaction.atomic():
        help_req = get_object_or_404(
            HelpRequest.objects.select_for_update(), pk=pk
        )
        # Refund the points to the user
        help_req.user.knowledge_points += help_req.kp_bounty
        help_req.user.save()
        help_req.status = 'canceled'
        help_req.save()

        messages.success(request, f"Request '{help_req.title}' has been canceled. {help_req.kp_bounty} KP refunded.")

    return redirect('request_detail', pk=pk)

# --- API Views ---

class HelpRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """A read-only API endpoint for listing and retrieving HelpRequests."""
    queryset = HelpRequest.objects.all().order_by('-created_at')
    serializer_class = HelpRequestSerializer

