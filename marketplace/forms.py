from django import forms
from .models import HelpRequest, Comment, Skill


class HelpRequestForm(forms.ModelForm):
    class Meta:
        model = HelpRequest
        fields = ['title', 'description', 'skill_needed', 'kp_bounty']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Python script bug'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'skill_needed': forms.Select(attrs={'class': 'form-select'}),
            'kp_bounty': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def clean_kp_bounty(self):
        kp = self.cleaned_data.get('kp_bounty')
        if kp is None or kp < 1:
            raise forms.ValidationError('The bounty must be at least 1 KP.')
        return kp


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content', 'is_private']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Ask a question or provide an update...'
            }),
            'is_private': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_private': 'Private (only visible to requester and helper)'
        }

class SearchForm(forms.Form):
    q = forms.CharField(label='Search', required=False)
    skill = forms.ModelChoiceField(
        queryset=Skill.objects.all(),
        required=False,
        empty_label="All Skills"
    )
