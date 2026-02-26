import json
import logging
from decimal import Decimal
from urllib.parse import urlencode

import django_filters
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import CustomUser
from accounts.query_utils import annotate_user_metrics
from notifications.models import Notification

from .ai_assistant import generate_request_assistance
from .forms import (
    CommentForm,
    FreelanceJobForm,
    HelpRequestForm,
    JobDisputeForm,
    JobMilestoneForm,
    PayoutRequestForm,
    RatingForm,
    SavedSearchForm,
    SearchForm,
)
from .models import (
    Comment,
    FreelanceJob,
    HelpRequest,
    JobDispute,
    JobMilestone,
    PayoutRequest,
    Rating,
    SavedSearch,
    Skill,
    Tag,
    TrustSignal,
    WalletLedger,
)
from .serializers import (
    FreelanceJobSerializer,
    HelpRequestSerializer,
    PublicCommentSerializer,
    PublicUserSerializer,
    SkillSerializer,
)
from .services import evaluate_job_collusion, record_wallet_entry

logger = logging.getLogger(__name__)


def home(request):
    """Render the homepage with live user/open-request stats and recent opportunities."""
    context = {
        'total_users': CustomUser.objects.count(),
        'open_requests': HelpRequest.objects.filter(status='open').count(),
        'open_paid_jobs': FreelanceJob.objects.filter(status='open').count(),
        'recent_requests': (
            HelpRequest.objects.filter(status='open')
            .select_related('skill_needed')
            .prefetch_related('tags')
            .order_by('-created_at')[:3]
        ),
        'recent_paid_jobs': (
            FreelanceJob.objects.filter(status='open')
            .select_related('client', 'skill_needed')
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


def _record_wallet_entry(user, direction, amount_inr, source_type, reference_id=None, description=''):
    """Persist a wallet ledger entry for auditability."""
    record_wallet_entry(
        user=user,
        direction=direction,
        amount_inr=amount_inr,
        source_type=source_type,
        reference_id=reference_id,
        description=description,
    )


def _notify_user(user, message, link):
    """Create an in-app notification when recipient exists."""
    if user:
        Notification.objects.create(user=user, message=message, link=link)


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
@require_POST
@ratelimit(key='ip', rate='15/m', block=True)
def ai_request_assist(request):
    """Generate AI-assisted improvements for a help-request draft via Gemini."""
    try:
        payload = json.loads((request.body or b'{}').decode('utf-8'))
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON payload.'}, status=400)

    title = str(payload.get('title') or '').strip()
    description = str(payload.get('description') or '').strip()
    if len(title) < 3 and len(description) < 10:
        return JsonResponse(
            {'ok': False, 'error': 'Please add a clearer title or description before using AI assist.'},
            status=400,
        )

    available_skills = list(Skill.objects.order_by('name').values_list('name', flat=True))
    try:
        suggestion = generate_request_assistance(title, description, available_skills)
    except RuntimeError as exc:
        logger.warning('AI request assist unavailable for user=%s: %s', request.user.username, exc)
        return JsonResponse({'ok': False, 'error': str(exc)}, status=503)

    return JsonResponse({'ok': True, 'suggestion': suggestion})


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


def freelance_job_list(request):
    """List paid freelance jobs with optional status, skill, and query filters."""
    all_jobs = (
        FreelanceJob.objects.select_related('client', 'freelancer', 'skill_needed')
        .prefetch_related('tags', 'milestones')
        .order_by('-created_at')
    )
    query = (request.GET.get('q') or '').strip()
    status_filter = (request.GET.get('status') or '').strip()
    skill_filter = (request.GET.get('skill') or '').strip()

    if query:
        all_jobs = all_jobs.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if status_filter in {'open', 'in_progress', 'completed', 'canceled', 'disputed'}:
        all_jobs = all_jobs.filter(status=status_filter)
    if skill_filter.isdigit():
        all_jobs = all_jobs.filter(skill_needed_id=int(skill_filter))

    paginator = Paginator(all_jobs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    context = {
        'jobs': page_obj,
        'page_obj': page_obj,
        'skills': Skill.objects.order_by('name'),
        'query': query,
        'status_filter': status_filter,
        'skill_filter': skill_filter,
    }
    return render(request, 'marketplace/job_list.html', context)


@login_required
@csrf_protect
@ratelimit(key='ip', rate='6/m', block=True)
def post_freelance_job(request):
    """Create a paid freelance job and move budget into INR escrow."""
    if request.method == 'POST':
        form = FreelanceJobForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                client = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                budget = form.cleaned_data['budget_inr']
                if client.wallet_inr < budget:
                    form.add_error('budget_inr', 'Insufficient INR wallet balance for escrow.')
                    return render(request, 'marketplace/job_create.html', {'form': form})

                client.wallet_inr -= budget
                client.save(update_fields=['wallet_inr'])

                job = form.save(commit=False)
                job.client = client
                job.escrow_inr = budget
                job.save()
                form.save_tags(job)

                JobMilestone.objects.create(
                    job=job,
                    title='Final delivery',
                    amount_inr=budget,
                    sequence=1,
                )
                _record_wallet_entry(
                    user=client,
                    direction='debit',
                    amount_inr=budget,
                    source_type='job_escrow',
                    reference_id=job.pk,
                    description=f'Escrow funded for freelance job #{job.pk}',
                )
            messages.success(request, 'Freelance job posted with INR escrow funded.')
            return redirect('freelance_job_detail', pk=job.pk)
    else:
        form = FreelanceJobForm()

    return render(request, 'marketplace/job_create.html', {'form': form})


def freelance_job_detail(request, pk):
    """Show paid job details, milestones, and participant actions."""
    job = get_object_or_404(
        FreelanceJob.objects.select_related('client', 'freelancer', 'skill_needed').prefetch_related('tags', 'milestones', 'disputes'),
        pk=pk,
    )
    can_claim = request.user.is_authenticated and job.status == 'open' and request.user != job.client
    can_manage = request.user.is_authenticated and request.user == job.client
    can_work = request.user.is_authenticated and request.user == job.freelancer and job.status == 'in_progress'
    can_dispute = request.user.is_authenticated and request.user in [job.client, job.freelancer]
    can_cancel = can_manage and job.status in {'open', 'in_progress', 'disputed'}
    can_add_milestone = can_manage and job.status in {'open', 'in_progress'}
    can_open_dispute = can_dispute and job.status in {'in_progress', 'disputed'}
    context = {
        'job': job,
        'can_claim': can_claim,
        'can_manage': can_manage,
        'can_work': can_work,
        'can_dispute': can_dispute,
        'can_cancel': can_cancel,
        'can_add_milestone': can_add_milestone,
        'can_open_dispute': can_open_dispute,
        'milestone_form': JobMilestoneForm(),
        'dispute_form': JobDisputeForm(),
    }
    return render(request, 'marketplace/job_detail.html', context)


@login_required
@csrf_protect
@require_POST
@ratelimit(key='ip', rate='20/m', block=True)
def claim_freelance_job(request, pk):
    """Allow a freelancer to claim an open paid job."""
    with transaction.atomic():
        job = get_object_or_404(FreelanceJob.objects.select_for_update().select_related('client'), pk=pk)
        if job.client_id == request.user.pk:
            messages.error(request, 'You cannot claim your own freelance job.')
            return redirect('freelance_job_detail', pk=pk)
        if job.status != 'open':
            messages.error(request, 'This job is no longer open.')
            return redirect('freelance_job_detail', pk=pk)

        job.freelancer = request.user
        job.status = 'in_progress'
        job.save(update_fields=['freelancer', 'status', 'updated_at'])

        _notify_user(job.client, 'A freelancer accepted your paid job.', reverse('freelance_job_detail', args=[job.pk]))
        messages.success(request, 'You accepted this freelance job.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def add_job_milestone(request, pk):
    """Add a milestone to a paid job (client only)."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client'), pk=pk)
    if request.user != job.client:
        messages.error(request, 'Only the client can add milestones.')
        return redirect('freelance_job_detail', pk=pk)
    if job.status not in {'open', 'in_progress'}:
        messages.error(request, 'Milestones can only be added while a job is active.')
        return redirect('freelance_job_detail', pk=pk)

    form = JobMilestoneForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Provide a valid milestone title and amount.')
        return redirect('freelance_job_detail', pk=pk)

    with transaction.atomic():
        locked_job = get_object_or_404(FreelanceJob.objects.select_for_update(), pk=pk)
        next_sequence = (locked_job.milestones.aggregate(max_seq=Coalesce(Max('sequence'), 0))['max_seq'] or 0) + 1
        milestone = form.save(commit=False)
        milestone.job = locked_job
        milestone.sequence = next_sequence
        milestone.full_clean()
        milestone.save()
    messages.success(request, 'Milestone added.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def submit_job_milestone(request, pk, milestone_id):
    """Allow assigned freelancer to mark a milestone as submitted."""
    with transaction.atomic():
        job = get_object_or_404(FreelanceJob.objects.select_for_update().select_related('freelancer', 'client'), pk=pk)
        milestone = get_object_or_404(JobMilestone.objects.select_for_update(), pk=milestone_id, job=job)
        if request.user != job.freelancer:
            messages.error(request, 'Only the assigned freelancer can submit milestones.')
            return redirect('freelance_job_detail', pk=pk)
        if job.status != 'in_progress':
            messages.error(request, 'Milestones can only be submitted while job is in progress.')
            return redirect('freelance_job_detail', pk=pk)
        if milestone.status != 'pending':
            messages.error(request, 'This milestone is not in pending state.')
            return redirect('freelance_job_detail', pk=pk)

        milestone.status = 'submitted'
        milestone.submitted_at = timezone.now()
        milestone.save(update_fields=['status', 'submitted_at'])
        _notify_user(job.client, f'Milestone "{milestone.title}" was submitted for review.', reverse('freelance_job_detail', args=[job.pk]))
    messages.success(request, 'Milestone submitted for client review.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def release_job_milestone(request, pk, milestone_id):
    """Release submitted milestone escrow to freelancer (client only)."""
    with transaction.atomic():
        job = get_object_or_404(FreelanceJob.objects.select_for_update().select_related('client', 'freelancer'), pk=pk)
        milestone = get_object_or_404(JobMilestone.objects.select_for_update(), pk=milestone_id, job=job)

        if request.user != job.client:
            messages.error(request, 'Only the client can release milestone payments.')
            return redirect('freelance_job_detail', pk=pk)
        if not job.freelancer:
            messages.error(request, 'No freelancer assigned to this job.')
            return redirect('freelance_job_detail', pk=pk)
        if milestone.status != 'submitted':
            messages.error(request, 'Only submitted milestones can be released.')
            return redirect('freelance_job_detail', pk=pk)
        if job.escrow_inr < milestone.amount_inr:
            messages.error(request, 'Escrow is insufficient for this release.')
            return redirect('freelance_job_detail', pk=pk)

        freelancer = CustomUser.objects.select_for_update().get(pk=job.freelancer_id)
        freelancer.wallet_inr += milestone.amount_inr
        freelancer.save(update_fields=['wallet_inr'])

        job.escrow_inr -= milestone.amount_inr
        milestone.status = 'released'
        milestone.released_at = timezone.now()
        milestone.save(update_fields=['status', 'released_at'])

        all_released = not job.milestones.exclude(status='released').exists()
        if all_released:
            job.status = 'completed'
            TrustSignal.objects.create(
                user=freelancer,
                signal_type='job_completed',
                score_delta=5,
                detail=f'Completed freelance job #{job.pk}',
                related_job=job,
            )
        TrustSignal.objects.create(
            user=freelancer,
            signal_type='milestone_released',
            score_delta=2,
            detail=f'Released milestone #{milestone.pk}',
            related_job=job,
        )
        job.save(update_fields=['escrow_inr', 'status', 'updated_at'])
        if all_released:
            evaluate_job_collusion(job)

        _record_wallet_entry(
            user=freelancer,
            direction='credit',
            amount_inr=milestone.amount_inr,
            source_type='job_milestone_release',
            reference_id=milestone.pk,
            description=f'Milestone release for job #{job.pk}',
        )
        _notify_user(freelancer, f'INR {milestone.amount_inr} released for milestone "{milestone.title}".', reverse('freelance_job_detail', args=[job.pk]))
        messages.success(request, f'Milestone released: INR {milestone.amount_inr} credited to freelancer wallet.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
@require_POST
def open_job_dispute(request, pk):
    """Open a dispute on an in-progress paid job."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client', 'freelancer'), pk=pk)
    if request.user not in [job.client, job.freelancer]:
        messages.error(request, 'Only job participants can open disputes.')
        return redirect('freelance_job_detail', pk=pk)
    if job.status not in {'in_progress', 'disputed'}:
        messages.error(request, 'Disputes can be opened only for active paid jobs.')
        return redirect('freelance_job_detail', pk=pk)

    form = JobDisputeForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a dispute reason.')
        return redirect('freelance_job_detail', pk=pk)

    with transaction.atomic():
        locked_job = get_object_or_404(FreelanceJob.objects.select_for_update(), pk=pk)
        dispute = form.save(commit=False)
        dispute.job = locked_job
        dispute.opened_by = request.user
        dispute.against_user = locked_job.freelancer if request.user == locked_job.client else locked_job.client
        dispute.save()

        locked_job.status = 'disputed'
        locked_job.save(update_fields=['status', 'updated_at'])

        TrustSignal.objects.create(
            user=request.user,
            signal_type='dispute_opened',
            score_delta=-2,
            detail=f'Dispute opened for job #{locked_job.pk}',
            related_job=locked_job,
        )
    messages.warning(request, 'Dispute opened. Admin review can be added in the next phase.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
def cancel_freelance_job(request, pk):
    """Cancel a paid job and refund remaining escrow to the client wallet."""
    job = get_object_or_404(FreelanceJob.objects.select_related('client'), pk=pk)
    if request.user != job.client:
        messages.error(request, 'Only the client can cancel this paid job.')
        return redirect('freelance_job_detail', pk=pk)
    if job.status not in {'open', 'in_progress', 'disputed'}:
        messages.error(request, 'Only active paid jobs can be canceled.')
        return redirect('freelance_job_detail', pk=pk)

    if request.method == 'GET':
        return render(request, 'marketplace/confirm_job_cancel.html', {'job': job})

    with transaction.atomic():
        locked_job = get_object_or_404(FreelanceJob.objects.select_for_update(), pk=pk)
        client = CustomUser.objects.select_for_update().get(pk=locked_job.client_id)
        refund_amount = locked_job.escrow_inr

        if refund_amount > 0:
            client.wallet_inr += refund_amount
            client.save(update_fields=['wallet_inr'])
            _record_wallet_entry(
                user=client,
                direction='credit',
                amount_inr=refund_amount,
                source_type='job_escrow_refund',
                reference_id=locked_job.pk,
                description=f'Escrow refund for canceled job #{locked_job.pk}',
            )

        locked_job.escrow_inr = Decimal('0.00')
        locked_job.status = 'canceled'
        locked_job.save(update_fields=['escrow_inr', 'status', 'updated_at'])
    messages.success(request, 'Paid job canceled and remaining escrow refunded.')
    return redirect('freelance_job_detail', pk=pk)


@login_required
@csrf_protect
def wallet_overview(request):
    """Display INR wallet activity and handle payout requests."""
    if request.method == 'POST':
        form = PayoutRequestForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                amount = form.cleaned_data['amount_inr']

                if not user.compliance_verified:
                    messages.error(request, 'Complete compliance verification before requesting payouts.')
                    return redirect('wallet_overview')
                if user.wallet_inr < amount:
                    messages.error(request, 'Insufficient wallet balance for this payout request.')
                    return redirect('wallet_overview')

                if user.payout_requests.filter(status='pending').count() >= 3:
                    TrustSignal.objects.create(
                        user=user,
                        signal_type='fraud_flag',
                        score_delta=-2,
                        detail='High number of pending payout requests.',
                    )

                user.wallet_inr -= amount
                user.save(update_fields=['wallet_inr'])
                payout = PayoutRequest.objects.create(
                    user=user,
                    amount_inr=amount,
                    note=form.cleaned_data.get('note', ''),
                )
                _record_wallet_entry(
                    user=user,
                    direction='debit',
                    amount_inr=amount,
                    source_type='payout_request',
                    reference_id=payout.pk,
                    description='Payout request submitted',
                )
            messages.success(request, 'Payout request submitted successfully.')
            return redirect('wallet_overview')
    else:
        form = PayoutRequestForm()

    context = {
        'wallet_entries': request.user.wallet_entries.all()[:30],
        'payout_requests': request.user.payout_requests.all()[:20],
        'form': form,
    }
    return render(request, 'marketplace/wallet.html', context)


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


class FreelanceJobFilter(django_filters.FilterSet):
    """Allow API filtering of paid jobs by status and skill id."""

    status = django_filters.CharFilter(field_name='status')
    skill = django_filters.NumberFilter(field_name='skill_needed_id')
    payment_type = django_filters.CharFilter(field_name='payment_type')

    class Meta:
        model = FreelanceJob
        fields = ['status', 'skill', 'payment_type']


class FreelanceJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Browsable API endpoint for listing/retrieving paid freelance jobs with milestones."""

    queryset = (
        FreelanceJob.objects.select_related('client', 'freelancer', 'skill_needed')
        .prefetch_related('tags', 'milestones')
        .order_by('-created_at')
    )
    serializer_class = FreelanceJobSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = FreelanceJobFilter


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
