from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Job


class UserRegistrationForm(UserCreationForm):
    """Form for user registration."""
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'Email'
    }))
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Last Name'
    }))

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Username'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirm Password'})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
        return user


class JobFilterForm(forms.Form):
    """Form for filtering jobs."""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search jobs...'
        })
    )
    work_mode = forms.ChoiceField(
        required=False,
        choices=[('', 'All Work Modes')] + list(Job.WORK_MODE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    job_type = forms.ChoiceField(
        required=False,
        choices=[('', 'All Job Types')] + list(Job.JOB_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    company = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Company name'
        })
    )
    active_only = forms.BooleanField(
        required=False,
        initial=True,
        label='Active jobs only',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )