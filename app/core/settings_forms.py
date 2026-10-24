from django import forms
from .settings_model import UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            'language', 'timezone', 'date_format', 'time_format',
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
