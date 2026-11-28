from django import forms
from django.utils import timezone

from core.models import Department

from .models import Incident

_STATUS_FLOW = [s for s, _ in Incident.STATUS_CHOICES]


class IncidentForm(forms.ModelForm):
    """Create / edit an incident.

    ``owner_dept`` is pinned by the view (``DepartmentPinnedMixin``) and the
    lifecycle timestamps are stamped by the model, so neither is editable
    here. The status selector only offers the current status and the stages
    after it - incidents do not flow backwards through the form.
    """

    class Meta:
        model = Incident
        fields = [
            'title', 'description',
            'incident_type', 'source', 'severity', 'status',
            'handler', 'detected_at',
            'affected_assets',
            'data_subjects_affected',
            'regulatory_notification_required', 'regulatory_notified_at',
            'nis2_significant',
            'nis2_early_warning_submitted_at',
            'nis2_notification_submitted_at',
            'nis2_final_report_submitted_at',
            'root_cause', 'lessons_learned',
            'risks',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'root_cause': forms.Textarea(attrs={'rows': 3}),
            'lessons_learned': forms.Textarea(attrs={'rows': 3}),
            'detected_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'
            ),
            'regulatory_notified_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'
            ),
            'nis2_early_warning_submitted_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'
            ),
            'nis2_notification_submitted_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'
            ),
            'nis2_final_report_submitted_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        # Department-less superusers (and superusers in general) need to pick
        # the owning department when filing an incident, since there is no
        # user.department to pin to.
        if (not self.instance or not self.instance.pk) and user and user.is_superuser:
            self.fields['owner_dept'] = forms.ModelChoiceField(
                queryset=Department.objects.order_by('name'),
                required=True,
                label='Department',
                initial=user.department_id,
                empty_label='Select department...',
            )
        # datetime-local inputs want the *local* value, not the stored UTC.
        if self.instance and self.instance.detected_at:
            self.initial['detected_at'] = timezone.localtime(self.instance.detected_at)
        if self.instance and self.instance.regulatory_notified_at:
            self.initial['regulatory_notified_at'] = timezone.localtime(
                self.instance.regulatory_notified_at
            )
        for field in (
            'nis2_early_warning_submitted_at',
            'nis2_notification_submitted_at',
            'nis2_final_report_submitted_at',
        ):
            value = getattr(self.instance, field, None)
            if value:
                self.initial[field] = timezone.localtime(value)
        self.fields['root_cause'].widget.attrs['placeholder'] = (
            'Fill in when known; required before closure.'
        )

        if self.instance and self.instance.pk:
            current = self.instance.status
            remaining = _STATUS_FLOW[_STATUS_FLOW.index(current):]
            self.fields['status'].choices = [
                (s, label) for s, label in Incident.STATUS_CHOICES
                if s in remaining
            ]
        else:
            # A new incident starts at "detected"; the reporter may already
            # have done initial triage, so offer one step forward at most.
            self.fields['status'].initial = 'detected'
            self.fields['status'].choices = [
                (s, label) for s, label in Incident.STATUS_CHOICES
                if s in ('detected', 'triaged')
            ]

    def clean(self):
        cleaned = super().clean()
        if (
            (not self.instance or not self.instance.pk)
            and self.user is not None
            and not self.user.is_superuser
            and not self.user.department_id
        ):
            raise forms.ValidationError(
                'Your account has no assigned department. Ask an administrator '
                'to assign your department before filing an incident.'
            )
        return cleaned
