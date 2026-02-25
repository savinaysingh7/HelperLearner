from datetime import timedelta

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
