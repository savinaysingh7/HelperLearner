import logging

import django_filters
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import CustomUser

from .forms import CommentForm, HelpRequestForm, RatingForm, SearchForm
from .models import Comment, HelpRequest, Rating, Skill, Tag
from .serializers import (
    HelpRequestSerializer,
    PublicCommentSerializer,
    PublicUserSerializer,
    SkillSerializer,
)

logger = logging.getLogger(__name__)


def home(request):
    """Render the homepage with live user/open-request stats and recent opportunities."""
    context = {
        'total_users': CustomUser.objects.count(),
        'open_requests': HelpRequest.objects.filter(status='open').count(),
        'recent_requests': (
            HelpRequest.objects.filter(status='open')
            .select_related('skill_needed')
            .prefetch_related('tags')
            .order_by('-created_at')[:3]
        ),
    }
    return render(request, 'marketplace/home.html', context)


def _search_querysets(query):
    """Return grouped request/user/skill search querysets for a single free-text query."""
    normalized_query = query.strip()
    if not normalized_query:
        return HelpRequest.objects.none(), CustomUser.objects.none(), Skill.objects.none()

    request_results = (
        HelpRequest.objects.select_related('user', 'accepted_by', 'skill_needed')
        .prefetch_related('tags')
        .filter(
            Q(title__icontains=normalized_query)
            | Q(description__icontains=normalized_query)
            | Q(tags__name__icontains=normalized_query)
            | Q(skill_needed__name__icontains=normalized_query)
            | Q(user__username__icontains=normalized_query)
            | Q(accepted_by__username__icontains=normalized_query)
        )
        .distinct()
        .order_by('-created_at')
    )

    user_results = (
        CustomUser.objects.prefetch_related('skills')
        .annotate(avg_rating=Avg('ratings_received__score'))
        .filter(Q(username__icontains=normalized_query) | Q(skills__name__icontains=normalized_query))
        .distinct()
        .order_by('username')
    )

    skill_results = (
        Skill.objects.annotate(request_count=Count('helprequest', distinct=True))
        .filter(name__icontains=normalized_query)
        .distinct()
        .order_by('name')
    )

    return request_results, user_results, skill_results


def unified_search(request):
    """Search requests, users, and skills together and render grouped discovery results."""
    query = request.GET.get('q', '').strip()
    request_results, user_results, skill_results = _search_querysets(query)
    has_results = request_results.exists() or user_results.exists() or skill_results.exists()

    context = {
        'query': query,
        'request_results': request_results[:20],
        'user_results': user_results[:20],
        'skill_results': skill_results[:20],
        'request_count': request_results.count() if query else 0,
        'user_count': user_results.count() if query else 0,
        'skill_count': skill_results.count() if query else 0,
        'has_results': has_results if query else False,
    }
    return render(request, 'marketplace/search_results.html', context)


def request_list(request):
    """List discoverable requests with keyword, skill, and tag filters."""
    form = SearchForm(request.GET)
    base_queryset = (
        HelpRequest.objects.select_related('skill_needed', 'user', 'accepted_by')
        .prefetch_related('tags')
        .annotate(skill_user_count=Count('skill_needed__users', distinct=True))
    )

    selected_tag = None
    if form.is_valid():
        selected_tag = form.cleaned_data.get('tag')

    if selected_tag:
        all_requests = base_queryset.filter(tags=selected_tag).distinct()
    else:
        all_requests = base_queryset.filter(status__in=['open', 'in_progress'])

    if form.is_valid():
        query = form.cleaned_data.get('q')
        skill_filter = form.cleaned_data.get('skill')

        if query:
            all_requests = all_requests.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )
        if skill_filter:
            all_requests = all_requests.filter(skill_needed=skill_filter)

    paginator = Paginator(all_requests.order_by('-created_at'), 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'requests': page_obj,
        'form': form,
        'page_obj': page_obj,
    }
    return render(request, 'marketplace/request_list.html', context)


def skill_browse(request):
    """Show all skills with request counts to help users discover topics."""
    skills = Skill.objects.annotate(request_count=Count('helprequest', distinct=True)).order_by('name')
    return render(request, 'marketplace/skill_browse.html', {'skills': skills})


def tag_browse(request):
    """Show all tags with request counts to help users discover topics."""
    tags = Tag.objects.annotate(request_count=Count('helprequests', distinct=True)).order_by('name')
    return render(request, 'marketplace/tag_browse.html', {'tags': tags})


def leaderboard(request):
    """Render the public leaderboard with KP, helped-count, and rating tabs."""
    resolved_skill_subquery = (
        Skill.objects.filter(helprequest__accepted_by=OuterRef('pk'), helprequest__status='resolved')
        .annotate(total=Count('helprequest'))
        .order_by('-total', 'name')
        .values('name')[:1]
    )
    listed_skill_subquery = Skill.objects.filter(users=OuterRef('pk')).order_by('name').values('name')[:1]

    annotated_users = CustomUser.objects.annotate(
        helped_count=Count('accepted_tasks', filter=Q(accepted_tasks__status='resolved'), distinct=True),
        avg_rating=Avg('ratings_received__score'),
        ratings_count=Count('ratings_received', distinct=True),
        top_skill=Coalesce(Subquery(resolved_skill_subquery), Subquery(listed_skill_subquery), Value('N/A')),
    )

    tab = request.GET.get('tab', 'kp')
    if tab not in {'kp', 'helped', 'rating'}:
        tab = 'kp'

    leaders_by_kp = annotated_users.order_by('-knowledge_points', 'username')[:10]
    leaders_by_helped = annotated_users.order_by('-helped_count', 'username')[:10]
    leaders_by_rating = annotated_users.filter(ratings_count__gt=0).order_by('-avg_rating', '-ratings_count', 'username')[:10]

    hall_of_fame = annotated_users.filter(ratings_count__gt=0).order_by('-avg_rating', '-ratings_count', 'username').first()

    context = {
        'tab': tab,
        'leaders_by_kp': leaders_by_kp,
        'leaders_by_helped': leaders_by_helped,
        'leaders_by_rating': leaders_by_rating,
        'active_leaders': {
            'kp': leaders_by_kp,
            'helped': leaders_by_helped,
            'rating': leaders_by_rating,
        }[tab],
        'hall_of_fame': hall_of_fame,
    }
    return render(request, 'marketplace/leaderboard.html', context)


@login_required
@csrf_protect
@ratelimit(key='ip', rate='10/m', block=True)
def create_request(request):
    """Create a request, escrow bounty points, and persist parsed tags."""
    if request.method == 'POST':
        form = HelpRequestForm(request.POST)
        if form.is_valid():
            help_req = form.save(commit=False)

            with transaction.atomic():
                poster = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                if poster.knowledge_points < help_req.kp_bounty:
                    messages.error(request, "You don't have enough Knowledge Points for this bounty!")
                    return render(request, 'marketplace/create_request.html', {'form': form})

                poster.knowledge_points -= help_req.kp_bounty
                poster.save(update_fields=['knowledge_points'])

                help_req.user = poster
                help_req.save()
                form.save_tags(help_req)

            messages.success(request, 'Your request has been posted and the bounty is in escrow.')
            return redirect('request_list')
    else:
        form = HelpRequestForm()

    return render(request, 'marketplace/create_request.html', {'form': form, 'is_edit': False})


@login_required
@csrf_protect
def edit_request(request, pk):
    """Edit an open request if and only if the current user is the request poster."""
    help_req = get_object_or_404(HelpRequest.objects.prefetch_related('tags'), pk=pk)

    if help_req.user != request.user:
        messages.error(request, 'Only the poster can edit this request.')
        return redirect('request_detail', pk=pk)

    if help_req.status != 'open':
        messages.error(request, 'Only open requests can be edited.')
        return redirect('request_detail', pk=pk)

    if request.method == 'POST':
        form = HelpRequestForm(request.POST, instance=help_req)
        if form.is_valid():
            with transaction.atomic():
                locked_request = get_object_or_404(HelpRequest.objects.select_for_update().prefetch_related('tags'), pk=pk)
                poster = CustomUser.objects.select_for_update().get(pk=request.user.pk)

                if locked_request.status != 'open':
                    messages.error(request, 'This request can no longer be edited.')
                    return redirect('request_detail', pk=pk)

                previous = {
                    'title': locked_request.title,
                    'description': locked_request.description,
                    'skill_needed_id': locked_request.skill_needed_id,
                    'kp_bounty': locked_request.kp_bounty,
                    'tags': list(locked_request.tags.order_by('name').values_list('name', flat=True)),
                }

                new_bounty = form.cleaned_data['kp_bounty']
                bounty_delta = new_bounty - locked_request.kp_bounty
                if bounty_delta > 0 and poster.knowledge_points < bounty_delta:
                    form.add_error('kp_bounty', 'You do not have enough KP for this bounty increase.')
                    return render(
                        request,
                        'marketplace/create_request.html',
                        {'form': form, 'is_edit': True, 'req': locked_request},
                    )

                if bounty_delta != 0:
                    poster.knowledge_points -= bounty_delta
                    poster.save(update_fields=['knowledge_points'])

                locked_request.title = form.cleaned_data['title']
                locked_request.description = form.cleaned_data['description']
                locked_request.skill_needed = form.cleaned_data['skill_needed']
                locked_request.kp_bounty = new_bounty
                locked_request.save()
                form.save_tags(locked_request)

                current = {
                    'title': locked_request.title,
                    'description': locked_request.description,
                    'skill_needed_id': locked_request.skill_needed_id,
                    'kp_bounty': locked_request.kp_bounty,
                    'tags': list(locked_request.tags.order_by('name').values_list('name', flat=True)),
                }

            changed_fields = {
                key: {'from': previous[key], 'to': current[key]}
                for key in previous
                if previous[key] != current[key]
            }
            logger.info(
                'Request %s edited by %s with changes=%s',
                help_req.pk,
                request.user.username,
                changed_fields,
            )
            messages.success(request, 'Request updated successfully.')
            return redirect('request_detail', pk=pk)
    else:
        form = HelpRequestForm(instance=help_req)

    return render(request, 'marketplace/create_request.html', {'form': form, 'is_edit': True, 'req': help_req})


@login_required
@csrf_protect
def delete_request(request, pk):
    """Delete a poster-owned request and refund escrow if the request is still open."""
    help_req = get_object_or_404(HelpRequest, pk=pk)

    if help_req.user != request.user:
        messages.error(request, 'Only the poster can delete this request.')
        return redirect('request_detail', pk=pk)

    if help_req.status not in ['open', 'canceled']:
        messages.error(request, 'Only open or canceled requests can be deleted.')
        return redirect('request_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_delete.html', {'req': help_req})

    with transaction.atomic():
        locked_request = get_object_or_404(HelpRequest.objects.select_for_update(), pk=pk)
        poster = CustomUser.objects.select_for_update().get(pk=request.user.pk)

        if locked_request.status == 'open':
            poster.knowledge_points += locked_request.kp_bounty
            poster.save(update_fields=['knowledge_points'])

        logger.info(
            'Request %s deleted by %s (status=%s)',
            locked_request.pk,
            request.user.username,
            locked_request.status,
        )
        locked_request.delete()

    messages.success(request, 'Request deleted successfully.')
    return redirect('request_list')


@csrf_protect
def request_detail(request, pk):
    """Display a request, rating state, and discussion with private-comment rules."""
    help_req = get_object_or_404(
        HelpRequest.objects.select_related('user', 'accepted_by', 'skill_needed').prefetch_related('tags'),
        pk=pk,
    )

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

    existing_rating = getattr(help_req, 'rating', None)
    can_rate = (
        request.user.is_authenticated
        and request.user == help_req.user
        and help_req.status == 'resolved'
        and help_req.accepted_by is not None
        and existing_rating is None
    )

    can_edit = request.user.is_authenticated and request.user == help_req.user and help_req.status == 'open'
    can_delete = request.user.is_authenticated and request.user == help_req.user and help_req.status in ['open', 'canceled']

    return render(
        request,
        'marketplace/request_detail.html',
        {
            'req': help_req,
            'comments': comments,
            'form': form,
            'can_rate': can_rate,
            'rating_form': RatingForm(),
            'existing_rating': existing_rating,
            'can_edit': can_edit,
            'can_delete': can_delete,
        },
    )


@login_required
@csrf_protect
@require_POST
def rate_request(request, pk):
    """Allow a request poster to rate their helper after resolution."""
    help_req = get_object_or_404(HelpRequest.objects.select_related('accepted_by', 'user'), pk=pk)

    if help_req.user != request.user:
        messages.error(request, 'Only the request poster can submit a rating.')
        return redirect('request_detail', pk=pk)

    if help_req.status != 'resolved' or help_req.accepted_by is None:
        messages.error(request, 'Ratings are available only for resolved requests with a helper.')
        return redirect('request_detail', pk=pk)

    if hasattr(help_req, 'rating'):
        messages.info(request, 'This request has already been rated.')
        return redirect('request_detail', pk=pk)

    form = RatingForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a valid rating between 1 and 5.')
        return redirect('request_detail', pk=pk)

    Rating.objects.create(
        request=help_req,
        given_by=request.user,
        given_to=help_req.accepted_by,
        score=form.cleaned_data['score'],
    )
    messages.success(request, 'Thanks! Your rating has been submitted.')
    return redirect('request_detail', pk=pk)


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


class HelpRequestFilter(django_filters.FilterSet):
    """Allow API filtering of requests by status and skill id."""

    status = django_filters.CharFilter(field_name='status')
    skill = django_filters.NumberFilter(field_name='skill_needed_id')

    class Meta:
        model = HelpRequest
        fields = ['status', 'skill']


class HelpRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """Browsable API endpoint for listing/retrieving requests with status+skill filtering."""

    queryset = (
        HelpRequest.objects.select_related('user', 'skill_needed')
        .prefetch_related('tags')
        .order_by('-created_at')
    )
    serializer_class = HelpRequestSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = HelpRequestFilter

    @action(detail=True, methods=['get'], url_path='comments')
    def comments(self, request, pk=None):
        """Return only public comments for a single request."""
        help_req = self.get_object()
        comments_qs = help_req.comments.filter(is_private=False).select_related('user').order_by('-created_at')

        page = self.paginate_queryset(comments_qs)
        if page is not None:
            serializer = PublicCommentSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PublicCommentSerializer(comments_qs, many=True)
        return Response(serializer.data)


class UserViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Browsable API endpoint for users with username, skills, KP, and average rating."""

    queryset = (
        CustomUser.objects.prefetch_related('skills')
        .annotate(avg_rating=Avg('ratings_received__score'))
        .order_by('-knowledge_points', 'username')
    )
    serializer_class = PublicUserSerializer


class SkillViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Browsable API endpoint for skills and their request counts."""

    queryset = Skill.objects.annotate(request_count=Count('helprequest', distinct=True)).order_by('name')
    serializer_class = SkillSerializer
