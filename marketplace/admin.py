from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser

from . import services
from .models import (
    Attachment,
    ChatMessage,
    ChatThread,
    ChatThreadParticipant,
    Comment,
    Experiment,
    ExperimentAssignment,
    ExperimentVariant,
    FraudAlert,
    FreelanceJob,
    FreelanceJobProposal,
    FreelanceJobProposalMilestone,
    HelpRequest,
    HelpRequestProposal,
    IntegrationApiKey,
    JobDispute,
    JobMilestone,
    KPTransfer,
    MilestoneDeliverable,
    ModerationFlag,
    PayoutRequest,
    PortfolioItem,
    Rating,
    SavedSearch,
    Skill,
    Tag,
    TrustSignal,
    WebhookDelivery,
    WebhookEndpoint,
    WalletLedger,
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueActivity,
    WorkspaceIssueComment,
    WorkspaceMembership,
    WorkspaceProject,
    WorkspaceSprint,
    WorkspaceWalletEntry,
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


@admin.register(FreelanceJobProposal)
class FreelanceJobProposalAdmin(admin.ModelAdmin):
    """Admin listing for paid job proposals."""

    list_display = ('job', 'applicant', 'proposed_total_inr', 'status', 'created_at', 'selected_at')
    list_filter = ('status', 'created_at')
    search_fields = ('job__title', 'applicant__username', 'cover_note')


@admin.register(FreelanceJobProposalMilestone)
class FreelanceJobProposalMilestoneAdmin(admin.ModelAdmin):
    """Admin listing for milestones proposed by freelancers."""

    list_display = ('proposal', 'sequence', 'title', 'amount_inr', 'due_date', 'created_at')
    list_filter = ('due_date',)
    search_fields = ('proposal__job__title', 'proposal__applicant__username', 'title')


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


@admin.register(MilestoneDeliverable)
class MilestoneDeliverableAdmin(admin.ModelAdmin):
    """Admin listing for milestone deliverables and revision workflow."""

    list_display = ('milestone', 'submitted_by', 'status', 'requested_revision_at', 'approved_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('milestone__title', 'submitted_by__username', 'revision_note')


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    """Admin listing for file attachments across models."""

    list_display = ('id', 'uploaded_by', 'content_type', 'object_id', 'caption', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('caption', 'uploaded_by__username', 'file')


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    """Admin listing for fraud and risk alerts."""

    list_display = ('alert_type', 'severity', 'user', 'related_user', 'is_resolved', 'created_at')
    list_filter = ('alert_type', 'severity', 'is_resolved')
    search_fields = ('description', 'user__username', 'related_user__username')
    actions = ('mark_resolved',)

    @admin.action(description='Mark selected alerts as resolved')
    def mark_resolved(self, request, queryset):
        updated = queryset.filter(is_resolved=False).update(is_resolved=True)
        self.message_user(request, f'Resolved {updated} alert(s).')


@admin.register(KPTransfer)
class KPTransferAdmin(admin.ModelAdmin):
    """Admin listing for KP transfers between users."""

    list_display = ('sender', 'recipient', 'amount', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('sender__username', 'recipient__username')


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    """Admin listing for team workspaces."""

    list_display = ('name', 'slug', 'owner', 'wallet_inr', 'created_at')
    search_fields = ('name', 'slug', 'owner__username')


@admin.register(WorkspaceProject)
class WorkspaceProjectAdmin(admin.ModelAdmin):
    """Admin listing for workspace project boards."""

    list_display = ('name', 'key', 'workspace', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active', 'workspace')
    search_fields = ('name', 'key', 'workspace__name')


@admin.register(WorkspaceIssue)
class WorkspaceIssueAdmin(admin.ModelAdmin):
    """Admin listing for workspace issues."""

    list_display = (
        'issue_key',
        'title',
        'project',
        'status',
        'priority',
        'reporter',
        'assignee',
        'updated_at',
    )
    list_filter = ('status', 'priority', 'project')
    search_fields = ('title', 'description', 'project__name', 'project__key', 'reporter__username', 'assignee__username')


@admin.register(WorkspaceIssueActivity)
class WorkspaceIssueActivityAdmin(admin.ModelAdmin):
    """Admin listing for issue status/assignment audit actions."""

    list_display = ('issue', 'action', 'actor', 'from_value', 'to_value', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('issue__title', 'issue__project__key', 'actor__username', 'note')


@admin.register(WorkspaceSprint)
class WorkspaceSprintAdmin(admin.ModelAdmin):
    """Admin listing for sprint windows per workspace project."""

    list_display = ('name', 'project', 'status', 'start_date', 'end_date', 'created_by', 'created_at')
    list_filter = ('status', 'project')
    search_fields = ('name', 'project__name', 'project__key')


@admin.register(WorkspaceIssueComment)
class WorkspaceIssueCommentAdmin(admin.ModelAdmin):
    """Admin listing for issue comments."""

    list_display = ('issue', 'author', 'created_at', 'updated_at')
    list_filter = ('created_at',)
    search_fields = ('issue__title', 'issue__project__key', 'author__username', 'content')


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    """Admin listing for workspace member roles."""

    list_display = ('workspace', 'user', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('workspace__name', 'user__username')


@admin.register(WorkspaceWalletEntry)
class WorkspaceWalletEntryAdmin(admin.ModelAdmin):
    """Admin listing for workspace wallet ledger events."""

    list_display = ('workspace', 'direction', 'amount_inr', 'source_type', 'actor', 'created_at')
    list_filter = ('direction', 'source_type')
    search_fields = ('workspace__name', 'actor__username', 'note')


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    """Admin listing for public portfolio items."""

    list_display = ('user', 'title', 'primary_skill', 'is_featured', 'created_at')
    list_filter = ('is_featured', 'primary_skill')
    search_fields = ('user__username', 'title', 'summary')


@admin.register(IntegrationApiKey)
class IntegrationApiKeyAdmin(admin.ModelAdmin):
    """Admin listing for issued API keys."""

    list_display = ('user', 'name', 'prefix', 'is_active', 'last_used_at', 'created_at', 'revoked_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'name', 'prefix')


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    """Admin listing for webhook destinations."""

    list_display = ('user', 'name', 'url', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('user__username', 'name', 'url')


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    """Admin listing for webhook delivery attempts."""

    list_display = ('endpoint', 'event_type', 'status_code', 'succeeded', 'created_at')
    list_filter = ('succeeded', 'event_type')
    search_fields = ('endpoint__name', 'event_type', 'response_excerpt')


@admin.register(ModerationFlag)
class ModerationFlagAdmin(admin.ModelAdmin):
    """Admin listing for moderation reports."""

    list_display = ('target_type', 'target_id', 'reported_by', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'target_type')
    search_fields = ('reason', 'reported_by__username', 'reviewed_by__username')


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    """Admin listing for A/B experiments."""

    list_display = ('name', 'slug', 'is_active', 'traffic_percentage', 'starts_at', 'ends_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')


@admin.register(ExperimentVariant)
class ExperimentVariantAdmin(admin.ModelAdmin):
    """Admin listing for experiment variants."""

    list_display = ('experiment', 'key', 'label', 'weight')
    search_fields = ('experiment__slug', 'key', 'label')


@admin.register(ExperimentAssignment)
class ExperimentAssignmentAdmin(admin.ModelAdmin):
    """Admin listing for variant assignments."""

    list_display = ('experiment', 'variant', 'user', 'session_key', 'created_at')
    search_fields = ('experiment__slug', 'variant__key', 'user__username', 'session_key')
