"""Form for composing a notification from the app."""
from django import forms

from .announcements import (
    AUDIENCE_DEPARTMENTS,
    AUDIENCE_MY_DEPARTMENT,
    AUDIENCE_USERS,
    allowed_audiences,
    audience_label,
    audience_options,
    selectable_users,
    visible_departments,
)
from .models import Department, User


class NotificationComposeForm(forms.Form):
    """Title, message, audience and an optional email copy.

    The querysets are scoped in ``__init__`` so a crafted POST cannot reach a
    department or person the sender is not allowed to address —
    ``ModelMultipleChoiceField`` rejects any pk outside its queryset.
    """

    title = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Phishing drill on Friday at 10:00',
            'autofocus': True,
        }),
    )
    body = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'What do you need people to know or do?',
        }),
        help_text='Optional. Shown under the title in the notification list.',
    )
    audience = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=[],
    )
    departments = forms.ModelMultipleChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Departments',
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='People',
    )
    send_email = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Also send by email',
        help_text='Sends one copy to each recipient whose account allows email. '
                  'Requires SMTP to be enabled in Settings → Email delivery.',
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        audiences = allowed_audiences(user) if user else []
        self.fields['audience'].choices = [
            (key, audience_label(user, key)) for key in audiences
        ]
        # Rendered by the template as cards with an explanation under each
        # label; the widget itself is never printed directly.
        self.audience_options = (
            audience_options(user) if user else []
        )
        self.fields['departments'].queryset = (
            visible_departments(user) if user else Department.objects.none()
        )
        self.fields['users'].queryset = (
            selectable_users(user) if user else User.objects.none()
        )
        if user is not None and not user.is_superuser:
            self.fields['departments'].help_text = (
                'You can notify your own department only.'
            )
            self.fields['users'].help_text = (
                'You can message people in your own department only.'
            )

    def clean(self):
        cleaned = super().clean()
        user = self.user
        audience = cleaned.get('audience')

        if user is None:
            raise forms.ValidationError('No sender was supplied.')

        if audience not in allowed_audiences(user):
            raise forms.ValidationError(
                'You are not allowed to notify that audience.'
            )

        if audience == AUDIENCE_MY_DEPARTMENT and not user.department_id:
            self.add_error(
                'audience',
                'Your account has no department. Ask an administrator to assign '
                'one, or message specific people instead.',
            )

        if audience == AUDIENCE_DEPARTMENTS and not cleaned.get('departments'):
            self.add_error('departments', 'Choose at least one department.')

        if audience == AUDIENCE_USERS and not cleaned.get('users'):
            self.add_error('users', 'Choose at least one person.')

        return cleaned

    def targets(self):
        """The cleaned audience payload, ready for ``send_announcement``."""
        return {
            'audience': self.cleaned_data['audience'],
            'departments': self.cleaned_data.get('departments') or [],
            'users': self.cleaned_data.get('users') or [],
            'email': self.cleaned_data.get('send_email', False),
        }
