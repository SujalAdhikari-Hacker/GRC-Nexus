from django import forms

from core.validators import validate_evidence_file

from .models import (
    Audit, EvidenceItem, EvidenceScore, ControlTest,
    AuditFinding, ActionItem,
)


# ============================================================
# AUDIT
# ============================================================

class AuditForm(forms.ModelForm):
    class Meta:
        model = Audit
        fields = [
            'name', 'owner_dept', 'audit_type', 'status',
            'auditor_lead', 'start_date', 'end_date',
            'scope', 'frameworks', 'notes',
        ]
        widgets = {
            'scope':        forms.Textarea(attrs={'rows': 4}),
            'notes':        forms.Textarea(attrs={'rows': 3}),
            'start_date':   forms.DateInput(attrs={'type': 'date'}),
            'end_date':     forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'scope':      'What this audit covers — systems, processes, departments.',
            'start_date': 'Date the audit engagement begins.',
            'end_date':   'Expected or actual completion date.',
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'End date cannot be before start date.')
        return cleaned


# ============================================================
# EVIDENCE
# ============================================================

class EvidenceItemForm(forms.ModelForm):
    class Meta:
        model = EvidenceItem
        fields = [
            'title', 'evidence_type', 'related_control', 'audit',
            'owner_user', 'owner_dept', 'url_location', 'attachment', 'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Attachments are attacker-reachable uploads; same allowlist + size cap
        # as control evidence, so a .html/.exe payload cannot be stored here.
        self.fields['attachment'].validators.append(validate_evidence_file)


class EvidenceScoreForm(forms.ModelForm):
    class Meta:
        model = EvidenceScore
        fields = [
            'relevance', 'completeness', 'timeliness',
            'reliability', 'sufficiency', 'assessor_notes'
        ]
        widgets = {
            'relevance':        forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'completeness':     forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'timeliness':       forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'reliability':      forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'sufficiency':      forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'assessor_notes':   forms.Textarea(attrs={'rows': 3}),
        }


# ============================================================
# CONTROL TEST
# ============================================================

class ControlTestForm(forms.ModelForm):
    class Meta:
        model = ControlTest
        fields = [
            'control', 'test_date', 'result', 'tester',
            'procedure_notes', 'owner_dept', 'audit',
        ]
        widgets = {
            'test_date': forms.DateInput(attrs={'type': 'date'}),
            'procedure_notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import real_users
        # Who performed the test must be a real, active user.
        self.fields['tester'].queryset = (
            real_users(self.fields['tester'].queryset).filter(is_active=True).order_by('username')
        )
        self.fields['tester'].required = False


# ============================================================
# AUDIT FINDING
# ============================================================

class AuditFindingForm(forms.ModelForm):
    class Meta:
        model = AuditFinding
        fields = [
            'title', 'severity', 'status', 'source',
            'audit', 'related_control', 'owner_user', 'owner_dept',
            'due_date', 'closed_date', 'description', 'recommendation'
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'closed_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'recommendation': forms.Textarea(attrs={'rows': 4}),
        }
        help_texts = {
            'due_date': 'Optional. Defaults to the severity SLA (7/14/30/60 days).',
        }


# ============================================================
# ACTION ITEM
# ============================================================

class ActionItemForm(forms.ModelForm):
    class Meta:
        model = ActionItem
        fields = [
            'finding', 'title', 'description',
            'owner_user', 'owner_dept', 'priority',
            'status', 'progress_percent', 'due_date', 'completed_date',
            'notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
            'progress_percent': forms.NumberInput(attrs={'min': 0, 'max': 100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['finding'].disabled = True
