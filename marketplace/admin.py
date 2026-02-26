from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser

from . import services
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


class JobMilestoneInline(admin.TabularInline):
    """Inline milestone management within paid job admin pages."""

    model = JobMilestone
    extra = 0
    fields = ('sequence', 'title', 'amount_inr', 'status', 'submitted_at', 'released_at')
    readonly_fields = ('submitted_at', 'released_at')


@admin.register(FreelanceJob)
class FreelanceJobAdmin(admin.ModelAdmin):
    """Admin listing for paid freelance jobs and escrow lifecycle."""

    list_display = (
        'title',
        'client',
        'freelancer',
        'payment_type',
        'budget_inr',
        'escrow_inr',
        'status',
        'created_at',
    )
    list_filter = ('status', 'payment_type', 'skill_needed')
    search_fields = ('title', 'description', 'client__username', 'freelancer__username')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('tags',)
    inlines = [JobMilestoneInline]


@admin.register(JobMilestone)
class JobMilestoneAdmin(admin.ModelAdmin):
    """Admin listing for paid job milestone states."""

    list_display = ('job', 'sequence', 'title', 'amount_inr', 'status', 'submitted_at', 'released_at')
    list_filter = ('status',)
    search_fields = ('job__title', 'title')


@admin.register(JobDispute)
class JobDisputeAdmin(admin.ModelAdmin):
    """Admin listing for paid job disputes and resolution tracking."""

    list_display = ('job', 'opened_by', 'against_user', 'status', 'resolution_type', 'resolved_by', 'resolved_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('job__title', 'opened_by__username', 'reason')
    readonly_fields = ('created_at', 'updated_at')
    actions = ('resolve_refund_client', 'resolve_pay_freelancer', 'resolve_split')

    @admin.action(description='Resolve disputes: refund client')
    def resolve_refund_client(self, request, queryset):
        resolved = 0
        for dispute in queryset:
            try:
                services.resolve_dispute(dispute, 'refund_client', actor=request.user, note='Resolved via admin action')
                resolved += 1
            except ValueError:
                continue
        self.message_user(request, f'Resolved {resolved} dispute(s) with client refund.')

    @admin.action(description='Resolve disputes: pay freelancer')
    def resolve_pay_freelancer(self, request, queryset):
        resolved = 0
        for dispute in queryset:
            try:
                services.resolve_dispute(dispute, 'pay_freelancer', actor=request.user, note='Resolved via admin action')
                resolved += 1
            except ValueError:
                continue
        self.message_user(request, f'Resolved {resolved} dispute(s) with freelancer payout.')

    @admin.action(description='Resolve disputes: split escrow 50/50')
    def resolve_split(self, request, queryset):
        resolved = 0
        for dispute in queryset:
            try:
                services.resolve_dispute(dispute, 'split', actor=request.user, note='Resolved via admin split action')
                resolved += 1
            except ValueError:
                continue
        self.message_user(request, f'Resolved {resolved} dispute(s) with split payouts.')


@admin.register(WalletLedger)
class WalletLedgerAdmin(admin.ModelAdmin):
    """Admin listing for INR wallet debits and credits."""

    list_display = ('user', 'direction', 'amount_inr', 'source_type', 'reference_id', 'created_at')
    list_filter = ('direction', 'source_type')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    """Admin listing and bulk actions for payout processing."""

    list_display = ('user', 'amount_inr', 'status', 'processed_by', 'processed_at', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'note')
    readonly_fields = ('processed_by', 'processed_at', 'created_at', 'updated_at')
    actions = ('mark_approved', 'mark_paid', 'mark_rejected')

    @admin.action(description='Mark selected requests as approved')
    def mark_approved(self, request, queryset):
        updated = 0
        for payout in queryset:
            try:
                services.process_payout_request(payout, 'approve', actor=request.user, note='Approved by admin')
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f'Approved {updated} payout request(s).')

    @admin.action(description='Mark selected requests as paid')
    def mark_paid(self, request, queryset):
        updated = 0
        for payout in queryset:
            try:
                services.process_payout_request(payout, 'pay', actor=request.user, note='Marked paid by admin')
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f'Marked {updated} payout request(s) as paid.')

    @admin.action(description='Mark selected requests as rejected')
    def mark_rejected(self, request, queryset):
        updated = 0
        for payout in queryset:
            try:
                services.process_payout_request(payout, 'reject', actor=request.user, note='Rejected by admin')
                updated += 1
            except ValueError:
                continue
        self.message_user(request, f'Rejected {updated} payout request(s).')


@admin.register(TrustSignal)
class TrustSignalAdmin(admin.ModelAdmin):
    """Admin listing for trust/fraud signal auditing."""

    list_display = ('user', 'signal_type', 'score_delta', 'related_job', 'created_at')
    list_filter = ('signal_type',)
    search_fields = ('user__username', 'detail', 'related_job__title')
