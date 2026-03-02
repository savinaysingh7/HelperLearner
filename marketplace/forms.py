from decimal import Decimal, InvalidOperation

from pathlib import Path

from django import forms
from django.conf import settings

from .models import (
    Attachment,
    ChatMessage,
    Comment,
    FreelanceJob,
    FreelanceJobProposal,
    FreelanceJobProposalMilestone,
    HelpRequest,
    HelpRequestProposal,
    JobDispute,
    JobMilestone,
    MilestoneDeliverable,
    ModerationFlag,
    PayoutRequest,
    PortfolioItem,
    Rating,
    SavedSearch,
    Skill,
    Tag,
    WebhookEndpoint,
    Workspace,
    WorkspaceIssue,
    WorkspaceIssueComment,
    WorkspaceProject,
    WorkspaceSprint,
)


class HelpRequestForm(forms.ModelForm):
    """Form for creating/updating help requests with comma-separated tags."""

    tags_input = forms.CharField(
        required=False,
        label='Tags',
        help_text='Comma-separated, e.g. django, api, debugging',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'django, api, debugging',
            }
        ),
    )

    class Meta:
        model = HelpRequest
        fields = ['title', 'description', 'skill_needed', 'kp_bounty']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Python script bug'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'skill_needed': forms.Select(attrs={'class': 'form-select'}),
            'kp_bounty': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['tags_input'].initial = ', '.join(
                self.instance.tags.order_by('name').values_list('name', flat=True)
            )

    def clean_kp_bounty(self):
        kp = self.cleaned_data.get('kp_bounty')
        if kp is None or kp < 1:
            raise forms.ValidationError('The bounty must be at least 1 KP.')
        return kp

    def clean_tags_input(self):
        raw_value = self.cleaned_data.get('tags_input', '')
        if not raw_value:
            return []

        parsed = [piece.strip().lower() for piece in raw_value.split(',') if piece.strip()]
        unique_tags = []
        seen = set()
        for tag_name in parsed:
            if tag_name in seen:
                continue
            seen.add(tag_name)
            unique_tags.append(tag_name)

        return unique_tags

    def save_tags(self, request_obj):
        """Persist parsed tags for a saved request object."""
        tag_names = self.cleaned_data.get('tags_input', [])
        tags = [Tag.objects.get_or_create(name=tag_name)[0] for tag_name in tag_names]
        request_obj.tags.set(tags)


class CommentForm(forms.ModelForm):
    """Form for request discussion comments."""

    class Meta:
        model = Comment
        fields = ['content', 'is_private']
        widgets = {
            'content': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2,
                    'placeholder': 'Ask a question or provide an update...',
                }
            ),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_private': 'Private (only visible to requester and helper)',
        }


class ChatMessageForm(forms.ModelForm):
    """Form for sending chat messages in a thread."""

    class Meta:
        model = ChatMessage
        fields = ['content']
        widgets = {
            'content': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2,
                    'placeholder': 'Write a message...',
                    'maxlength': 2000,
                }
            ),
        }

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if not content:
            raise forms.ValidationError('Message cannot be empty.')
        return content


class SearchForm(forms.Form):
    """Search and filter form for discovery views."""

    q = forms.CharField(
        label='Search',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search title or description'}),
    )
    skill = forms.ModelChoiceField(
        queryset=Skill.objects.all(),
        required=False,
        empty_label='All Skills',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    tag = forms.ModelChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        to_field_name='slug',
        empty_label='All Tags',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class RatingForm(forms.ModelForm):
    """Form for rating a resolved helper interaction."""

    class Meta:
        model = Rating
        fields = ['score']
        widgets = {
            'score': forms.Select(attrs={'class': 'form-select'}),
        }


class HelpRequestProposalForm(forms.ModelForm):
    """Form for helpers to submit a proposal on an open KP request."""

    class Meta:
        model = HelpRequestProposal
        fields = ['proposed_kp', 'eta_days', 'cover_note']
        widgets = {
            'proposed_kp': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'eta_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'cover_note': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Share your approach and expected turnaround.',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.request_obj = kwargs.pop('request_obj', None)
        super().__init__(*args, **kwargs)
        if self.request_obj:
            self.fields['proposed_kp'].help_text = f'Maximum allowed: {self.request_obj.kp_bounty} KP'
        self.fields['eta_days'].help_text = 'Estimated delivery timeline in days (optional).'

    def clean_proposed_kp(self):
        proposed_kp = self.cleaned_data.get('proposed_kp')
        if self.request_obj and proposed_kp and proposed_kp > self.request_obj.kp_bounty:
            raise forms.ValidationError('Proposed KP cannot exceed the posted bounty.')
        return proposed_kp


class FreelanceJobProposalForm(forms.ModelForm):
    """Form for freelancers to submit proposal + optional milestone plan."""

    milestones_input = forms.CharField(
        required=False,
        label='Proposed milestones',
        help_text='Optional. One per line: Title | Amount | YYYY-MM-DD',
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'API scaffold | 5000 | 2026-03-12',
            }
        ),
    )

    class Meta:
        model = FreelanceJobProposal
        fields = ['proposed_total_inr', 'eta_days', 'cover_note']
        widgets = {
            'proposed_total_inr': forms.NumberInput(attrs={'class': 'form-control', 'min': 100, 'step': '0.01'}),
            'eta_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'cover_note': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Outline your delivery plan and communication rhythm.',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.job_obj = kwargs.pop('job_obj', None)
        super().__init__(*args, **kwargs)
        if self.job_obj:
            self.fields['proposed_total_inr'].help_text = f'Maximum allowed: INR {self.job_obj.budget_inr}'
        self.fields['eta_days'].help_text = 'Estimated delivery timeline in days (optional).'

    def clean_proposed_total_inr(self):
        proposed_total = self.cleaned_data.get('proposed_total_inr')
        if self.job_obj and proposed_total and proposed_total > self.job_obj.budget_inr:
            raise forms.ValidationError('Proposed total cannot exceed the posted budget.')
        return proposed_total

    def clean_milestones_input(self):
        raw = (self.cleaned_data.get('milestones_input') or '').strip()
        if not raw:
            return []

        parsed = []
        date_parser = forms.DateField()
        for index, line in enumerate([value.strip() for value in raw.splitlines() if value.strip()], start=1):
            parts = [part.strip() for part in line.split('|')]
            if len(parts) < 2:
                raise forms.ValidationError(f'Line {index} must include Title | Amount.')

            title = parts[0]
            try:
                amount = Decimal(parts[1])
            except (InvalidOperation, TypeError):
                raise forms.ValidationError(f'Line {index} has an invalid amount.')

            if amount <= 0:
                raise forms.ValidationError(f'Line {index} amount must be positive.')

            due_date = None
            if len(parts) > 2 and parts[2]:
                try:
                    due_date = date_parser.clean(parts[2])
                except forms.ValidationError:
                    raise forms.ValidationError(f'Line {index} has invalid due date (use YYYY-MM-DD).')

            parsed.append(
                {
                    'title': title,
                    'amount_inr': amount.quantize(Decimal('0.01')),
                    'due_date': due_date,
                    'sequence': index,
                }
            )

        return parsed

    def clean(self):
        cleaned_data = super().clean()
        milestones = cleaned_data.get('milestones_input', [])
        proposed_total = cleaned_data.get('proposed_total_inr')
        if milestones and proposed_total:
            milestone_total = sum(item['amount_inr'] for item in milestones)
            if milestone_total > proposed_total:
                raise forms.ValidationError('Milestone total cannot exceed your proposed total.')
        return cleaned_data

    def save_milestones(self, proposal_obj):
        """Persist parsed milestones for a saved job proposal."""
        proposal_obj.milestones.all().delete()
        for item in self.cleaned_data.get('milestones_input', []):
            FreelanceJobProposalMilestone.objects.create(
                proposal=proposal_obj,
                title=item['title'],
                amount_inr=item['amount_inr'],
                due_date=item['due_date'],
                sequence=item['sequence'],
            )


class SavedSearchForm(forms.ModelForm):
    """Form for creating saved discovery filters."""

    class Meta:
        model = SavedSearch
        fields = ['query', 'skill', 'tag']
        widgets = {
            'query': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Optional keyword',
                }
            ),
            'skill': forms.Select(attrs={'class': 'form-select'}),
            'tag': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        query = (cleaned_data.get('query') or '').strip()
        skill = cleaned_data.get('skill')
        tag = cleaned_data.get('tag')
        if not query and not skill and not tag:
            raise forms.ValidationError('Provide at least one filter (query, skill, or tag).')
        cleaned_data['query'] = query
        return cleaned_data


class FreelanceJobForm(forms.ModelForm):
    """Form for posting/editing paid freelance jobs with comma-separated tags."""

    tags_input = forms.CharField(
        required=False,
        label='Tags',
        help_text='Comma-separated, e.g. django, api, backend',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'django, api, backend',
            }
        ),
    )

    class Meta:
        model = FreelanceJob
        fields = [
            'title',
            'description',
            'skill_needed',
            'payment_type',
            'budget_inr',
            'deadline',
            'response_sla_hours',
            'auto_release_hours',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Build JWT auth module'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'skill_needed': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'budget_inr': forms.NumberInput(attrs={'class': 'form-control', 'min': 100, 'step': '0.01'}),
            'deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'response_sla_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'auto_release_hours': forms.NumberInput(
                attrs={'class': 'form-control', 'min': 0, 'step': 1, 'placeholder': '0 to disable'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['auto_release_hours'].required = False
        if self.instance and self.instance.pk:
            self.fields['tags_input'].initial = ', '.join(
                self.instance.tags.order_by('name').values_list('name', flat=True)
            )

    def clean_tags_input(self):
        raw_value = self.cleaned_data.get('tags_input', '')
        if not raw_value:
            return []
        parsed = [piece.strip().lower() for piece in raw_value.split(',') if piece.strip()]
        unique = []
        seen = set()
        for name in parsed:
            if name in seen:
                continue
            seen.add(name)
            unique.append(name)
        return unique

    def clean_auto_release_hours(self):
        value = self.cleaned_data.get('auto_release_hours')
        if value in [None, '']:
            return 0
        return value

    def save_tags(self, job_obj):
        """Persist parsed tags for a saved freelance job."""
        tag_names = self.cleaned_data.get('tags_input', [])
        tags = [Tag.objects.get_or_create(name=name)[0] for name in tag_names]
        job_obj.tags.set(tags)


class JobMilestoneForm(forms.ModelForm):
    """Form for clients to add milestones to a freelance job."""

    class Meta:
        model = JobMilestone
        fields = ['title', 'amount_inr']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Deliver API endpoints'}),
            'amount_inr': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '0.01'}),
        }


class JobDisputeForm(forms.ModelForm):
    """Form for opening a dispute on a paid freelance job."""

    class Meta:
        model = JobDispute
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 4,
                    'placeholder': 'Explain the issue, timeline, and expected resolution.',
                }
            ),
        }


class PayoutRequestForm(forms.ModelForm):
    """Form for users to request INR withdrawals from their wallet."""

    class Meta:
        model = PayoutRequest
        fields = ['amount_inr', 'note']
        widgets = {
            'amount_inr': forms.NumberInput(attrs={'class': 'form-control', 'min': 100, 'step': '0.01'}),
            'note': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Optional note for payout processing'}
            ),
        }


class DeliverableSubmissionForm(forms.ModelForm):
    """Form for freelancers to submit proof against a milestone."""

    class Meta:
        model = MilestoneDeliverable
        fields = ['proof_text', 'proof_file']
        widgets = {
            'proof_text': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Share links, commit hashes, demo notes, or testing evidence.',
                }
            ),
            'proof_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        proof_text = (cleaned_data.get('proof_text') or '').strip()
        proof_file = cleaned_data.get('proof_file')
        if not proof_text and not proof_file:
            raise forms.ValidationError('Provide proof text or upload a file before submitting.')
        return cleaned_data


class DeliverableRevisionForm(forms.ModelForm):
    """Form for clients to request specific revisions on a deliverable."""

    class Meta:
        model = MilestoneDeliverable
        fields = ['revision_note']
        widgets = {
            'revision_note': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Describe the requested changes clearly.',
                }
            ),
        }


class AttachmentUploadForm(forms.ModelForm):
    """Generic attachment form for requests, jobs, and comments."""

    ALLOWED_EXTENSIONS = {
        '.png',
        '.jpg',
        '.jpeg',
        '.gif',
        '.webp',
        '.pdf',
        '.txt',
        '.md',
        '.log',
        '.csv',
        '.json',
        '.zip',
        '.doc',
        '.docx',
        '.xlsx',
        '.pptx',
    }

    class Meta:
        model = Attachment
        fields = ['file', 'caption']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'caption': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional caption'}),
        }

    def clean_file(self):
        """Validate uploaded attachment extension and file size."""
        uploaded = self.cleaned_data.get('file')
        if not uploaded:
            return uploaded

        extension = Path(uploaded.name or '').suffix.lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ', '.join(sorted(ext.lstrip('.') for ext in self.ALLOWED_EXTENSIONS))
            raise forms.ValidationError(f'Unsupported file type. Allowed types: {allowed}.')

        max_mb = int(getattr(settings, 'ATTACHMENT_MAX_UPLOAD_MB', 5))
        if uploaded.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f'File too large. Maximum allowed size is {max_mb} MB.')

        return uploaded


class WorkspaceCreateForm(forms.ModelForm):
    """Form for creating a team workspace."""

    class Meta:
        model = Workspace
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Acme Product Team'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class WorkspaceInviteForm(forms.Form):
    """Invite or add a member to a workspace by username."""

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'username'}),
    )
    role = forms.ChoiceField(
        choices=[('admin', 'Admin'), ('member', 'Member')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class WorkspaceTransferForm(forms.Form):
    """Transfer INR between personal wallet and workspace wallet."""

    amount_inr = forms.DecimalField(
        min_value=Decimal('1.00'),
        decimal_places=2,
        max_digits=10,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '0.01'}),
    )


class WorkspaceProjectForm(forms.ModelForm):
    """Form for creating and updating Jira-style workspace projects."""

    class Meta:
        model = WorkspaceProject
        fields = ['name', 'key', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Platform Revamp'}),
            'key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PLAT'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_key(self):
        key = (self.cleaned_data.get('key') or '').strip().upper().replace(' ', '-')
        if not key:
            raise forms.ValidationError('Project key is required.')
        if len(key) < 2:
            raise forms.ValidationError('Project key should be at least 2 characters.')
        return key


class WorkspaceIssueForm(forms.ModelForm):
    """Form for creating and editing workspace issues."""

    class Meta:
        model = WorkspaceIssue
        fields = ['title', 'description', 'status', 'priority', 'assignee', 'estimate_points', 'sprint', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Issue title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'assignee': forms.Select(attrs={'class': 'form-select'}),
            'estimate_points': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'sprint': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.workspace = kwargs.pop('workspace', None)
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        if self.workspace:
            member_ids = self.workspace.memberships.values_list('user_id', flat=True)
            self.fields['assignee'].queryset = self.fields['assignee'].queryset.filter(pk__in=member_ids)
            sprint_qs = WorkspaceSprint.objects.filter(project__workspace=self.workspace)
            if self.project:
                sprint_qs = sprint_qs.filter(project=self.project)
            self.fields['sprint'].queryset = sprint_qs.order_by('-start_date', '-created_at')


class WorkspaceSprintForm(forms.ModelForm):
    """Form for creating/editing a project sprint window."""

    class Meta:
        model = WorkspaceSprint
        fields = ['name', 'goal', 'start_date', 'end_date', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Sprint 12'}),
            'goal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Primary sprint goal'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class WorkspaceIssueCommentForm(forms.ModelForm):
    """Form for posting comments on workspace issues."""

    class Meta:
        model = WorkspaceIssueComment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Add context, blockers, links, or acceptance notes...',
                    'maxlength': 2000,
                }
            ),
        }

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if not content:
            raise forms.ValidationError('Comment cannot be empty.')
        return content


class PortfolioItemForm(forms.ModelForm):
    """Form for managing public portfolio entries."""

    class Meta:
        model = PortfolioItem
        fields = ['title', 'summary', 'primary_skill', 'project_url', 'evidence_url', 'is_featured']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'summary': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'primary_skill': forms.Select(attrs={'class': 'form-select'}),
            'project_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://project.example'}),
            'evidence_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://github.com/...'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ApiKeyCreateForm(forms.Form):
    """Form for creating a named API key."""

    name = forms.CharField(
        max_length=80,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Production integration key'}),
    )


class WebhookEndpointForm(forms.ModelForm):
    """Form for managing outbound webhook destinations."""

    subscribed_events = forms.CharField(
        required=False,
        help_text='Comma-separated events, e.g. request.status_changed,payout.processed',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = WebhookEndpoint
        fields = ['name', 'url', 'subscribed_events', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'url': forms.URLInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['subscribed_events'].initial = ', '.join(self.instance.subscribed_events)

    def clean_subscribed_events(self):
        raw = (self.cleaned_data.get('subscribed_events') or '').strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(',') if item.strip()]


class ModerationFlagForm(forms.ModelForm):
    """Form for reporting a user-generated entity to moderators."""

    class Meta:
        model = ModerationFlag
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 3,
                    'placeholder': 'Describe why this content should be reviewed.',
                }
            ),
        }
