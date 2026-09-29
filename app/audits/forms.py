from django import forms
from .models import EvidenceItem, EvidenceScore, ControlTest, AuditFinding


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


class EvidenceScoreForm(forms.ModelForm):
    class Meta:
        model = EvidenceScore
        fields = [
            'relevance', 'completeness', 'timeliness',
            'reliability', 'sufficiency', 'assessor', 'assessor_notes'
        ]
        widgets = {
            'relevance':        forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'completeness':     forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'timeliness':       forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'reliability':      forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'sufficiency':      forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'assessor_notes':   forms.Textarea(attrs={'rows': 3}),
        }


class ControlTestForm(forms.ModelForm):
    class Meta:
        model = ControlTest
        fields = [
            'control', 'test_date', 'result', 'tester',
            'procedure_notes', 'owner_dept', 'audit'
        ]
        widgets = {
            'test_date': forms.DateInput(attrs={'type': 'date'}),
            'procedure_notes': forms.Textarea(attrs={'rows': 4}),
        }


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


from .models import ActionItem


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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['finding'].disabled = True
