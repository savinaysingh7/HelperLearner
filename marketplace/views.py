import logging
from urllib.parse import urlencode

import django_filters
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import CustomUser
from accounts.query_utils import annotate_user_metrics

from .forms import CommentForm, HelpRequestForm, RatingForm, SavedSearchForm, SearchForm
from .models import Comment, HelpRequest, Rating, SavedSearch, Skill, Tag
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
        annotate_user_metrics(CustomUser.objects.prefetch_related('skills'))
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


def _saved_search_params(query, skill, tag):
    """Build normalized query params dict for request browsing filters."""
    params = {}
    if query:
        params['q'] = query
    if skill:
        params['skill'] = skill.pk if hasattr(skill, 'pk') else skill
    if tag:
        params['tag'] = tag.slug if hasattr(tag, 'slug') else tag
    return params


def _request_list_redirect(params):
    """Return redirect response to request list with optional querystring params."""
    base_url = reverse('request_list')
    if not params:
        return redirect('request_list')
    return redirect(f'{base_url}?{urlencode(params)}')


def _create_or_reactivate_saved_search(user, query, skill, tag):
    """Create or reactivate a saved search for the same criteria."""
    saved_search = SavedSearch.objects.filter(user=user, query=query, skill=skill, tag=tag).first()
    if saved_search:
        if not saved_search.is_active:
            saved_search.is_active = True
            saved_search.save(update_fields=['is_active'])
        return saved_search, False
    return SavedSearch.objects.create(user=user, query=query, skill=skill, tag=tag), True


def request_list(request):
    """List discoverable requests with keyword, skill, and tag filters."""
    form = SearchForm(request.GET)
    form_is_valid = form.is_valid()
    base_queryset = (
        HelpRequest.objects.select_related('skill_needed', 'user', 'accepted_by')
        .prefetch_related('tags')
        .annotate(skill_user_count=Count('skill_needed__users', distinct=True))
    )

    query = ''
    skill_filter = None
    selected_tag = None
    if form_is_valid:
        query = (form.cleaned_data.get('q') or '').strip()
        skill_filter = form.cleaned_data.get('skill')
        selected_tag = form.cleaned_data.get('tag')

    if selected_tag:
        all_requests = base_queryset.filter(tags=selected_tag).distinct()
    else:
        all_requests = base_queryset.filter(status__in=['open', 'in_progress'])

    if query:
        all_requests = all_requests.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )
    if skill_filter:
        all_requests = all_requests.filter(skill_needed=skill_filter)

    paginator = Paginator(all_requests.order_by('-created_at'), 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    current_filter_params = _saved_search_params(query, skill_filter, selected_tag)
    has_active_filters = bool(current_filter_params)

    context = {
        'requests': page_obj,
        'form': form,
        'page_obj': page_obj,
        'current_filter_params': current_filter_params,
        'has_active_filters': has_active_filters,
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


@login_required
@csrf_protect
def saved_searches(request):
    """Create and manage saved request filters for the authenticated user."""
    if request.method == 'POST':
        form = SavedSearchForm(request.POST)
        if form.is_valid():
            search_obj, created = _create_or_reactivate_saved_search(
                user=request.user,
                query=form.cleaned_data['query'],
                skill=form.cleaned_data.get('skill'),
                tag=form.cleaned_data.get('tag'),
            )
            if created:
                messages.success(request, 'Saved search created.')
            else:
                messages.info(request, 'This saved search already existed and is now active.')
            return redirect('saved_searches')
    else:
        initial_tag = request.GET.get('tag', '')
        if initial_tag and not str(initial_tag).isdigit():
            initial_tag_obj = Tag.objects.filter(slug=initial_tag).only('pk').first()
            initial_tag = initial_tag_obj.pk if initial_tag_obj else ''
        initial = {
            'query': request.GET.get('q', ''),
            'skill': request.GET.get('skill', ''),
            'tag': initial_tag,
        }
        form = SavedSearchForm(initial=initial)

    searches = list(request.user.saved_searches.select_related('skill', 'tag').all())
    for search_obj in searches:
        search_obj.query_params = _saved_search_params(search_obj.query, search_obj.skill, search_obj.tag)
        search_obj.browse_url = f"{reverse('request_list')}?{urlencode(search_obj.query_params)}"

    context = {
        'form': form,
        'searches': searches,
    }
    return render(request, 'marketplace/saved_searches.html', context)


@login_required
@csrf_protect
@require_POST
def save_current_search(request):
    """Save the active request list filters as a reusable saved search."""
    query = (request.POST.get('query') or '').strip()
    skill_id = request.POST.get('skill') or ''
    tag_slug = request.POST.get('tag') or ''
    skill_obj = Skill.objects.filter(pk=skill_id).first() if skill_id else None
    tag_obj = Tag.objects.filter(slug=tag_slug).first() if tag_slug else None
    fallback_params = _saved_search_params(query, skill_obj or skill_id, tag_obj or tag_slug)

    if not query and not skill_obj and not tag_obj:
        messages.error(request, 'Could not save search. Add at least one valid filter.')
        return _request_list_redirect(fallback_params)

    _, created = _create_or_reactivate_saved_search(
        user=request.user,
        query=query,
        skill=skill_obj,
        tag=tag_obj,
    )
    if created:
        messages.success(request, 'Current filters saved.')
    else:
        messages.info(request, 'Those filters were already saved.')
    return _request_list_redirect(_saved_search_params(query, skill_obj, tag_obj))


@login_required
@csrf_protect
@require_POST
def toggle_saved_search(request, pk):
    """Toggle a saved search on or off for the owner."""
    saved_search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    saved_search.is_active = not saved_search.is_active
    saved_search.save(update_fields=['is_active'])
    state = 'activated' if saved_search.is_active else 'paused'
    messages.success(request, f'Saved search {state}.')
    return redirect('saved_searches')


@login_required
@csrf_protect
@require_POST
def delete_saved_search(request, pk):
    """Delete a saved search owned by the current user."""
    saved_search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    saved_search.delete()
    messages.success(request, 'Saved search deleted.')
    return redirect('saved_searches')


def leaderboard(request):
    """Render the public leaderboard with KP, helped-count, and rating tabs."""
    resolved_skill_subquery = (
        Skill.objects.filter(helprequest__accepted_by=OuterRef('pk'), helprequest__status='resolved')
        .annotate(total=Count('helprequest'))
        .order_by('-total', 'name')
        .values('name')[:1]
    )
    listed_skill_subquery = Skill.objects.filter(users=OuterRef('pk')).order_by('name').values('name')[:1]

    annotated_users = annotate_user_metrics(CustomUser.objects.all()).annotate(
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
def activity_feed(request):
    """Render a personalized feed based on interactions, skills, and commented request resolutions."""
    current_user = request.user

    interacted_user_ids = set(
        HelpRequest.objects.filter(accepted_by=current_user).values_list('user_id', flat=True)
    )
    interacted_user_ids.update(
        HelpRequest.objects.filter(user=current_user, accepted_by__isnull=False).values_list('accepted_by_id', flat=True)
    )
    interacted_user_ids.discard(current_user.pk)

    user_skill_ids = list(current_user.skills.values_list('id', flat=True))
    commented_request_ids = list(Comment.objects.filter(user=current_user).values_list('request_id', flat=True))

    interacted_posts = (
        HelpRequest.objects.filter(user_id__in=interacted_user_ids)
        .select_related('user', 'skill_needed')
        .order_by('-created_at')[:100]
    )

    matching_skill_requests = (
        HelpRequest.objects.filter(status='open', skill_needed_id__in=user_skill_ids)
        .exclude(user=current_user)
        .select_related('user', 'skill_needed')
        .order_by('-created_at')[:100]
        if user_skill_ids
        else HelpRequest.objects.none()
    )

    recent_resolutions = (
        HelpRequest.objects.filter(pk__in=commented_request_ids, status='resolved')
        .select_related('user', 'accepted_by', 'skill_needed')
        .order_by('-updated_at')[:100]
        if commented_request_ids
        else HelpRequest.objects.none()
    )

    feed_items = []
    dedupe_keys = set()

    for help_request in interacted_posts:
        dedupe_key = ('interaction_post', help_request.pk)
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)
        feed_items.append(
            {
                'type': 'interaction_post',
                'icon': 'bi-people-fill',
                'request': help_request,
                'timestamp': help_request.created_at,
                'description': f"{help_request.user.username} posted a new request: {help_request.title}",
            }
        )

    for help_request in matching_skill_requests:
        dedupe_key = ('skill_match_open', help_request.pk)
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)
        feed_items.append(
            {
                'type': 'skill_match_open',
                'icon': 'bi-lightning-charge-fill',
                'request': help_request,
                'timestamp': help_request.created_at,
                'description': f"New open request matching your skills: {help_request.title}",
            }
        )

    for help_request in recent_resolutions:
        dedupe_key = ('commented_resolution', help_request.pk)
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)
        feed_items.append(
            {
                'type': 'commented_resolution',
                'icon': 'bi-check-circle-fill',
                'request': help_request,
                'timestamp': help_request.updated_at,
                'description': f"A request you commented on was resolved: {help_request.title}",
            }
        )

    feed_items.sort(key=lambda item: item['timestamp'], reverse=True)
    paginator = Paginator(feed_items, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    seen_request_ids = set(commented_request_ids)
    seen_request_ids.update(HelpRequest.objects.filter(user=current_user).values_list('pk', flat=True))
    suggested_requests = (
        HelpRequest.objects.filter(status='open', skill_needed_id__in=user_skill_ids)
        .exclude(pk__in=seen_request_ids)
        .exclude(user=current_user)
        .select_related('user', 'skill_needed')
        .order_by('-created_at')[:3]
    )

    context = {
        'page_obj': page_obj,
        'feed_items': page_obj.object_list,
        'suggested_requests': suggested_requests,
    }
    return render(request, 'marketplace/activity_feed.html', context)


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
    with transaction.atomic():
        help_req = get_object_or_404(
            HelpRequest.objects.select_for_update().select_related('user'),
            pk=pk,
        )

        if help_req.user_id == request.user.pk:
            messages.warning(request, 'You cannot claim your own request.')
            return redirect('request_detail', pk=pk)

        if help_req.status != 'open':
            messages.error(request, 'This request is no longer open for claiming.')
            return redirect('request_detail', pk=pk)

        help_req.status = 'in_progress'
        help_req.accepted_by = request.user
        help_req.save(update_fields=['status', 'accepted_by', 'updated_at'])

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
        help_req = get_object_or_404(
            HelpRequest.objects.select_for_update().select_related('user', 'accepted_by'),
            pk=pk,
        )

        if help_req.user_id != request.user.pk:
            messages.error(request, 'Only the poster can resolve this request.')
            return redirect('request_detail', pk=pk)

        if help_req.status == 'resolved':
            messages.info(request, 'This request has already been resolved.')
            return redirect('request_detail', pk=pk)

        if not (help_req.status == 'in_progress' and help_req.accepted_by_id):
            messages.error(request, "Request must be 'In Progress' with a helper to be resolved.")
            return redirect('request_detail', pk=pk)

        helper = CustomUser.objects.select_for_update().get(pk=help_req.accepted_by_id)
        CustomUser.objects.filter(pk=helper.pk).update(knowledge_points=F('knowledge_points') + help_req.kp_bounty)

        help_req.status = 'resolved'
        help_req.save(update_fields=['status', 'updated_at'])

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
        help_req = get_object_or_404(
            HelpRequest.objects.select_for_update().select_related('user'),
            pk=pk,
        )

        if help_req.user_id != request.user.pk:
            messages.error(request, 'Only the poster can cancel this request.')
            return redirect('request_detail', pk=pk)

        if help_req.status not in ['open', 'in_progress']:
            messages.error(request, "Only 'Open' or 'In Progress' requests can be canceled.")
            return redirect('request_detail', pk=pk)

        poster = CustomUser.objects.select_for_update().get(pk=help_req.user_id)
        CustomUser.objects.filter(pk=poster.pk).update(knowledge_points=F('knowledge_points') + help_req.kp_bounty)
        help_req.status = 'canceled'
        help_req.save(update_fields=['status', 'updated_at'])

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

    queryset = annotate_user_metrics(CustomUser.objects.prefetch_related('skills')).order_by(
        '-knowledge_points',
        'username',
    )
    serializer_class = PublicUserSerializer


class SkillViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Browsable API endpoint for skills and their request counts."""

    queryset = Skill.objects.annotate(request_count=Count('helprequest', distinct=True)).order_by('name')
    serializer_class = SkillSerializer


class SearchViewSet(viewsets.ViewSet):
    """Browsable API endpoint for grouped full-text search across requests, users, and skills."""

    def list(self, request):
        """Return grouped JSON search results for query param `q`."""
        query = request.query_params.get('q', '').strip()
        request_results, user_results, skill_results = _search_querysets(query)

        return Response(
            {
                'query': query,
                'requests': HelpRequestSerializer(request_results[:10], many=True).data if query else [],
                'users': PublicUserSerializer(user_results[:10], many=True).data if query else [],
                'skills': SkillSerializer(skill_results[:10], many=True).data if query else [],
            }
        )
