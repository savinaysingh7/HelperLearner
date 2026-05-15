import logging

from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.db.models import Q

from accounts.models import CustomUser

from .models import Comment, HelpRequest, Rating, SavedSearch, Skill, Tag


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """Admin listing for skills."""

    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Admin listing for request tags."""

    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')


@admin.register(HelpRequest)
class HelpRequestAdmin(admin.ModelAdmin):
    """Admin configuration for request moderation and lifecycle controls."""

    list_display = ('title', 'user', 'skill_needed', 'status', 'kp_bounty', 'created_at', 'expires_at')
    list_filter = ('status', 'skill_needed')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('tags',)
    actions = ('mark_as_expired',)

    @admin.action(description='Mark selected open requests as expired and refund KP')
    def mark_as_expired(self, request, queryset):
        """Cancel selected open requests and refund escrowed KP to posters."""
        expired_count = 0
        for request_obj in queryset.filter(status='open').select_related('user'):
            with transaction.atomic():
                locked_request = HelpRequest.objects.select_for_update().select_related('user').get(pk=request_obj.pk)
                if locked_request.status != 'open':
                    continue
                locked_user = CustomUser.objects.select_for_update().get(pk=locked_request.user_id)
                locked_user.knowledge_points += locked_request.kp_bounty
                locked_user.save(update_fields=['knowledge_points'])
                locked_request.status = 'canceled'
                locked_request.save(update_fields=['status', 'updated_at'])
                expired_count += 1
        self.message_user(request, f'Expired {expired_count} request(s) and refunded KP.')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """Admin listing for request comments."""

    list_display = ('user', 'request', 'is_private', 'created_at')
    list_filter = ('is_private',)
    search_fields = ('content', 'user__username', 'request__title')


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    """Admin listing for chat threads tied to requests, jobs, or workspaces."""

    list_display = ('display_title', 'thread_type', 'created_by', 'last_message_at', 'created_at')
    list_filter = ('thread_type', 'created_at')
    search_fields = ('title', 'help_request__title', 'job__title', 'workspace__name')


@admin.register(ChatThreadParticipant)
class ChatThreadParticipantAdmin(admin.ModelAdmin):
    """Admin listing for chat thread participants and read state."""

    list_display = ('thread', 'user', 'joined_at', 'last_read_at')
    list_filter = ('joined_at',)
    search_fields = ('thread__title', 'user__username')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Admin listing for chat messages."""

    list_display = ('thread', 'sender', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('content', 'sender__username', 'thread__title')


@admin.register(HelpRequestProposal)
class HelpRequestProposalAdmin(admin.ModelAdmin):
    """Admin listing for KP request proposals."""

    list_display = ('request', 'applicant', 'proposed_kp', 'status', 'created_at', 'selected_at')
    list_filter = ('status', 'created_at')
    search_fields = ('request__title', 'applicant__username', 'cover_note')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    """Admin listing for helper ratings."""

    list_display = ('given_by', 'given_to', 'score', 'request_title', 'created_at')
    list_filter = ('score',)
    search_fields = ('given_by__username', 'given_to__username', 'request__title')

    @admin.display(description='Request Title')
    def request_title(self, obj):
        """Display request title in rating rows."""
        return obj.request.title


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    """Admin listing for saved search filters and notification status."""

    list_display = ('user', 'query', 'skill', 'tag', 'is_active', 'last_notified_at', 'created_at')
    list_filter = ('is_active', 'skill', 'tag')
    search_fields = ('user__username', 'query')
