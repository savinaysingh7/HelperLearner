from datetime import timedelta
from decimal import Decimal
import hashlib
import secrets

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Skill(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    def save(self, *args, **kwargs):
        """Slugify tag names and enforce unique slugs."""
        base_slug = slugify(self.name) or 'tag'
        slug = base_slug
        counter = 2
        while Tag.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
        self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
        ]


class HelpRequest(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('canceled', 'Canceled'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    skill_needed = models.ForeignKey(Skill, on_delete=models.SET_NULL, null=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='helprequests')
    kp_bounty = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    ai_summary = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accepted_tasks',
    )

    def save(self, *args, **kwargs):
        """Set expiry to seven days after creation for requests without an explicit expiry."""
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} ({self.skill_needed})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['status', 'expires_at']),
        ]


class HelpRequestProposal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('selected', 'Selected'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    request = models.ForeignKey(HelpRequest, on_delete=models.CASCADE, related_name='proposals')
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='help_request_proposals')
    cover_note = models.TextField(blank=True)
    proposed_kp = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    eta_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    selected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Block invalid self-proposals and invalid bounty ranges."""
        if self.request_id and self.applicant_id and self.request.user_id == self.applicant_id:
            raise ValidationError('You cannot apply to your own request.')
        if self.request_id and self.proposed_kp > self.request.kp_bounty:
            raise ValidationError('Proposed KP cannot exceed the request bounty.')

    def __str__(self):
        return f'Proposal by {self.applicant.username} for request #{self.request_id}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', 'status']),
            models.Index(fields=['applicant', 'status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['request', 'applicant'], name='unique_help_request_applicant'),
        ]


class Comment(models.Model):
    request = models.ForeignKey(HelpRequest, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Comment by {self.user.username} on {self.request.title}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', 'is_private']),
            models.Index(fields=['created_at']),
        ]


class Rating(models.Model):
    SCORE_CHOICES = [
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
    ]

    request = models.OneToOneField(HelpRequest, on_delete=models.CASCADE, related_name='rating')
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings_given')
    given_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings_received')
    score = models.IntegerField(choices=SCORE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.given_by} rated {self.given_to} {self.score}/5'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['given_to']),
            models.Index(fields=['created_at']),
        ]


class SavedSearch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_searches')
    query = models.CharField(max_length=120, blank=True)
    skill = models.ForeignKey(Skill, on_delete=models.SET_NULL, null=True, blank=True, related_name='saved_searches')
    tag = models.ForeignKey(Tag, on_delete=models.SET_NULL, null=True, blank=True, related_name='saved_searches')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        """Require at least one filter criterion for saved searches."""
        has_query = bool((self.query or '').strip())
        if not has_query and not self.skill_id and not self.tag_id:
            raise ValidationError('Provide at least one filter (query, skill, or tag).')

    def save(self, *args, **kwargs):
        """Normalize query text for stable deduplication and filtering."""
        self.query = (self.query or '').strip()
        super().save(*args, **kwargs)

    def __str__(self):
        parts = []
        if self.query:
            parts.append(f"q='{self.query}'")
        if self.skill:
            parts.append(f'skill={self.skill.name}')
        if self.tag:
            parts.append(f'tag={self.tag.name}')
        criteria = ', '.join(parts) if parts else 'no filters'
        return f'{self.user.username}: {criteria}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['last_notified_at']),
        ]


class FreelanceJob(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),
        ('disputed', 'Disputed'),
    ]
    PAYMENT_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly'),
    ]

    title = models.CharField(max_length=220)
    description = models.TextField()
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='freelance_jobs_posted')
    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='freelance_jobs_taken',
    )
    skill_needed = models.ForeignKey(Skill, on_delete=models.SET_NULL, null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='freelance_jobs')
    payment_type = models.CharField(max_length=12, choices=PAYMENT_CHOICES, default='fixed')
    budget_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('100.00'))])
    escrow_inr = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    deadline = models.DateField(null=True, blank=True)
    response_sla_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1)])
    response_due_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    last_sla_reminder_at = models.DateTimeField(null=True, blank=True)
    auto_release_hours = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Prevent self-assignment and negative escrow conditions."""
        if self.freelancer_id and self.freelancer_id == self.client_id:
            raise ValidationError('Client and freelancer must be different users.')
        if self.escrow_inr < 0:
            raise ValidationError('Escrow cannot be negative.')

    def save(self, *args, **kwargs):
        """Initialize escrow from budget for new jobs when not explicitly provided."""
        if self._state.adding and not self.escrow_inr:
            self.escrow_inr = self.budget_inr
        if self._state.adding and self.response_due_at is None:
            self.response_due_at = timezone.now() + timedelta(hours=self.response_sla_hours)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['payment_type']),
            models.Index(fields=['skill_needed']),
            models.Index(fields=['client']),
            models.Index(fields=['freelancer']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['response_due_at']),
            models.Index(fields=['first_response_at']),
        ]


class FreelanceJobProposal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('selected', 'Selected'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    job = models.ForeignKey(FreelanceJob, on_delete=models.CASCADE, related_name='proposals')
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='freelance_job_proposals')
    cover_note = models.TextField(blank=True)
    proposed_total_inr = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('100.00'))],
    )
    eta_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    selected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Block invalid self-proposals and out-of-budget asks."""
        if self.job_id and self.applicant_id and self.job.client_id == self.applicant_id:
            raise ValidationError('You cannot apply to your own freelance job.')
        if self.job_id and self.proposed_total_inr > self.job.budget_inr:
            raise ValidationError('Proposed total cannot exceed the listed budget.')

    def __str__(self):
        return f'Job proposal by {self.applicant.username} for job #{self.job_id}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job', 'status']),
            models.Index(fields=['applicant', 'status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['job', 'applicant'], name='unique_job_applicant'),
        ]


class FreelanceJobProposalMilestone(models.Model):
    proposal = models.ForeignKey(FreelanceJobProposal, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=140)
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('1.00'))])
    due_date = models.DateField(null=True, blank=True)
    sequence = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.proposal.applicant.username} - M{self.sequence}: {self.title}'

    class Meta:
        ordering = ['sequence', 'created_at']
        indexes = [
            models.Index(fields=['proposal', 'sequence']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['proposal', 'sequence'], name='unique_job_proposal_sequence'),
        ]


class JobMilestone(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('released', 'Released'),
        ('disputed', 'Disputed'),
    ]

    job = models.ForeignKey(FreelanceJob, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=140)
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('1.00'))])
    sequence = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Ensure milestone totals do not exceed job budget."""
        existing_total = (
            JobMilestone.objects.filter(job=self.job)
            .exclude(pk=self.pk)
            .aggregate(total=models.Sum('amount_inr'))['total']
            or Decimal('0.00')
        )
        if existing_total + (self.amount_inr or Decimal('0.00')) > self.job.budget_inr:
            raise ValidationError('Total milestone amount cannot exceed job budget.')

    def __str__(self):
        return f'{self.job.title} - M{self.sequence}: {self.title}'

    class Meta:
        ordering = ['sequence', 'created_at']
        indexes = [
            models.Index(fields=['job', 'sequence']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['job', 'sequence'], name='unique_job_milestone_sequence'),
        ]


class JobDispute(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    ]
    RESOLUTION_CHOICES = [
        ('', 'Unresolved'),
        ('refund_client', 'Refund Client'),
        ('pay_freelancer', 'Pay Freelancer'),
        ('split', 'Split 50/50'),
    ]

    job = models.ForeignKey(FreelanceJob, on_delete=models.CASCADE, related_name='disputes')
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='job_disputes_opened')
    against_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='job_disputes_received',
    )
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    resolution_type = models.CharField(max_length=20, choices=RESOLUTION_CHOICES, blank=True, default='')
    refund_amount_inr = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    payout_amount_inr = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_job_disputes',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Dispute #{self.pk} - {self.job.title}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]


class WalletLedger(models.Model):
    DIRECTION_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet_entries')
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    source_type = models.CharField(max_length=40)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} {self.direction} INR {self.amount_inr}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['source_type']),
        ]


class PayoutRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payout_requests')
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('100.00'))])
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    note = models.CharField(max_length=255, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payout_requests',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Require sufficient wallet balance at request time."""
        if self.user_id and self.user.wallet_inr < self.amount_inr:
            raise ValidationError('Insufficient wallet balance for payout request.')

    def __str__(self):
        return f'Payout {self.amount_inr} by {self.user.username} ({self.status})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]


class TrustSignal(models.Model):
    SIGNAL_CHOICES = [
        ('job_completed', 'Job Completed'),
        ('milestone_released', 'Milestone Released'),
        ('dispute_opened', 'Dispute Opened'),
        ('fraud_flag', 'Fraud Flag'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trust_signals')
    signal_type = models.CharField(max_length=24, choices=SIGNAL_CHOICES)
    score_delta = models.IntegerField()
    detail = models.CharField(max_length=255, blank=True)
    related_job = models.ForeignKey(FreelanceJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='trust_signals')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} {self.signal_type} ({self.score_delta:+d})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['signal_type']),
        ]


class MilestoneDeliverable(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('revision_requested', 'Revision Requested'),
        ('approved', 'Approved'),
    ]

    milestone = models.OneToOneField(JobMilestone, on_delete=models.CASCADE, related_name='deliverable')
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_deliverables',
    )
    proof_text = models.TextField(blank=True)
    proof_file = models.FileField(upload_to='deliverables/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    revision_note = models.TextField(blank=True)
    requested_revision_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Deliverable for milestone #{self.milestone_id} ({self.status})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['requested_revision_at']),
        ]


class Attachment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_attachments',
    )
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    caption = models.CharField(max_length=140, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Attachment #{self.pk} by {self.uploaded_by}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]


class FraudAlert(models.Model):
    ALERT_CHOICES = [
        ('collusion', 'Collusion Risk'),
        ('transfer_velocity', 'Transfer Velocity'),
        ('unusual_pattern', 'Unusual Pattern'),
        ('sla_breach', 'SLA Breach'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fraud_alerts',
        null=True,
        blank=True,
    )
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='fraud_alerts_related',
        null=True,
        blank=True,
    )
    alert_type = models.CharField(max_length=24, choices=ALERT_CHOICES)
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES, default='medium')
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        who = self.user.username if self.user_id else 'system'
        return f'Fraud alert ({self.alert_type}) for {who}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_type', 'is_resolved']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['severity']),
        ]


class KPTransfer(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kp_transfers_sent',
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kp_transfers_received',
    )
    amount = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.sender} -> {self.recipient}: {self.amount} KP'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['recipient', 'created_at']),
        ]


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_workspaces',
    )
    description = models.TextField(blank=True)
    wallet_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        base_slug = slugify(self.name) or 'workspace'
        slug = base_slug
        counter = 2
        while Workspace.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
        self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['owner']),
            models.Index(fields=['wallet_inr']),
        ]


class WorkspaceMembership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_memberships',
    )
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} in {self.workspace} ({self.role})'

    class Meta:
        ordering = ['workspace__name', 'user__username']
        indexes = [
            models.Index(fields=['workspace', 'role']),
            models.Index(fields=['user']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member'),
        ]


class WorkspaceWalletEntry(models.Model):
    DIRECTION_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='wallet_entries')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workspace_wallet_actions',
    )
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)
    amount_inr = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    source_type = models.CharField(max_length=40)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.workspace.slug} {self.direction} INR {self.amount_inr}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['source_type']),
        ]


class PortfolioItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='portfolio_items')
    title = models.CharField(max_length=160)
    summary = models.TextField()
    project_url = models.URLField(blank=True)
    evidence_url = models.URLField(blank=True)
    primary_skill = models.ForeignKey(Skill, on_delete=models.SET_NULL, null=True, blank=True, related_name='portfolio_items')
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}: {self.title}'

    class Meta:
        ordering = ['-is_featured', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_featured']),
            models.Index(fields=['created_at']),
        ]


class IntegrationApiKey(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=80)
    prefix = models.CharField(max_length=12)
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash_key(raw_key):
        """Return deterministic SHA256 hash for API key lookup."""
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    @classmethod
    def create_key(cls, user, name):
        """Create and return a new API key instance plus the raw token."""
        raw_token = secrets.token_urlsafe(32)
        prefix = raw_token[:8]
        instance = cls.objects.create(
            user=user,
            name=name,
            prefix=prefix,
            key_hash=cls.hash_key(raw_token),
        )
        return instance, raw_token

    def __str__(self):
        return f'{self.user.username} key {self.prefix}...'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['prefix']),
        ]


class WebhookEndpoint(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='webhook_endpoints')
    name = models.CharField(max_length=100)
    url = models.URLField()
    secret = models.CharField(max_length=64, blank=True)
    subscribed_events = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(16)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.username} webhook: {self.name}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['created_at']),
        ]


class WebhookDelivery(models.Model):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    response_excerpt = models.TextField(blank=True)
    succeeded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Delivery {self.event_type} -> {self.endpoint.name}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['endpoint', 'created_at']),
            models.Index(fields=['event_type']),
            models.Index(fields=['succeeded']),
        ]


class ModerationFlag(models.Model):
    TARGET_CHOICES = [
        ('request', 'Request'),
        ('job', 'Paid Job'),
        ('comment', 'Comment'),
        ('user', 'User'),
        ('dispute', 'Dispute'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('reviewed', 'Reviewed'),
        ('dismissed', 'Dismissed'),
        ('actioned', 'Actioned'),
    ]

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='moderation_flags_created',
    )
    target_type = models.CharField(max_length=20, choices=TARGET_CHOICES)
    target_id = models.PositiveIntegerField()
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderation_flags_reviewed',
    )
    resolution_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Flag #{self.pk} {self.target_type}:{self.target_id} ({self.status})'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['reported_by']),
        ]


class Experiment(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    traffic_percentage = models.PositiveIntegerField(default=100, validators=[MinValueValidator(1)])
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_live(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]


class ExperimentVariant(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='variants')
    key = models.CharField(max_length=40)
    label = models.CharField(max_length=80)
    weight = models.PositiveIntegerField(default=50, validators=[MinValueValidator(1)])

    def __str__(self):
        return f'{self.experiment.slug}:{self.key}'

    class Meta:
        ordering = ['experiment', 'key']
        indexes = [
            models.Index(fields=['experiment', 'key']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['experiment', 'key'], name='unique_experiment_variant_key'),
        ]


class ExperimentAssignment(models.Model):
    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='assignments')
    variant = models.ForeignKey(ExperimentVariant, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='experiment_assignments',
    )
    session_key = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        identity = self.user.username if self.user_id else self.session_key
        return f'{self.experiment.slug}:{self.variant.key} -> {identity}'

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['experiment', 'user']),
            models.Index(fields=['experiment', 'session_key']),
        ]
