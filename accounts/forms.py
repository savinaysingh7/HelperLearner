from django import forms
from django.contrib.auth.forms import UserCreationForm

from marketplace.models import Skill

from .models import CustomUser


class DeveloperSignUpForm(UserCreationForm):
    """Registration form with bootstrap widgets for account creation."""

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "bio")
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tell others what you can help with'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Create a strong password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Repeat your password'})


class UserUpdateForm(forms.ModelForm):
    """Form for editing profile details."""

    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'bio', 'skills']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class KPTransferLookupForm(forms.Form):
    """Form for preparing a KP transfer confirmation request."""

    recipient_username = forms.CharField(
        label='Recipient Username',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'recipient_username'}),
    )
    amount = forms.IntegerField(
        min_value=5,
        label='Amount (KP)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 5, 'step': 1}),
    )
