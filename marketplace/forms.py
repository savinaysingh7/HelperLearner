from django import forms

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
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Build JWT auth module'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'skill_needed': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'budget_inr': forms.NumberInput(attrs={'class': 'form-control', 'min': 100, 'step': '0.01'}),
            'deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'response_sla_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
