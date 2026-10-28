from django import forms

from .settings_model import EmailSettings, UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            'timezone', 'date_format', 'time_format',
            'theme', 'items_per_page',
            'email_notifications_enabled', 'email_digest_frequency',
            'email_on_ticket_assigned', 'email_on_risk_breach',
            'email_on_audit_finding', 'email_on_kri_red', 'email_on_vuln_sla',
            'email_on_escalation', 'email_on_incident',
        ]
        widgets = {
            'theme': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')


class EmailSettingsForm(forms.ModelForm):
    """SMTP configuration form. The password is write-only."""

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                'class': 'form-control',
                'autocomplete': 'new-password',
                'placeholder': 'Leave blank to keep the current password',
            },
        ),
        help_text='Stored encrypted with a key derived from SECRET_KEY. '
                  'Leave blank to keep the current password.',
    )

    class Meta:
        model = EmailSettings
        fields = [
            'is_enabled', 'host', 'port', 'security', 'username',
            'from_name', 'from_email', 'timeout', 'notify_on_new',
        ]
        widgets = {
            'host': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '192.168.56.10 or mail.everest.local',
            }),
            'port': forms.NumberInput(attrs={'class': 'form-control'}),
            'security': forms.Select(attrs={'class': 'form-select'}),
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'off',
            }),
            'from_name': forms.TextInput(attrs={'class': 'form-control'}),
            'from_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'no-reply@everest.local',
            }),
            'timeout': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_on_new': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(field.widget, (forms.TextInput, forms.NumberInput,
                                           forms.EmailInput, forms.PasswordInput)):
                field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned = super().clean()
        enabled = cleaned.get('is_enabled')
        host = (cleaned.get('host') or '').strip()
        from_email = (cleaned.get('from_email') or '').strip()

        if enabled and not host:
            self.add_error('host', 'A host is required when SMTP delivery is enabled.')
        if enabled and not from_email:
            self.add_error(
                'from_email',
                'A From address is required when SMTP delivery is enabled.',
            )

        port = cleaned.get('port')
        if port is not None and not (1 <= port <= 65535):
            self.add_error('port', 'Port must be between 1 and 65535.')

        if cleaned.get('security') == 'ssl' and port == 587:
            self.add_error(
                'port',
                'Port 587 is normally used with STARTTLS. Use port 465 for '
                'SSL/TLS, or choose STARTTLS.',
            )

        return cleaned
