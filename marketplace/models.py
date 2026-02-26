from datetime import timedelta
from decimal import Decimal

from django.conf import settings
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
