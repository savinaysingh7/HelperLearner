from django import forms

from .models import Comment, HelpRequest, Rating, Skill, Tag


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
