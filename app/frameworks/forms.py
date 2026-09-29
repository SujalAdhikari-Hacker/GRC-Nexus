from django import forms
from .models import ComplianceAssessment, ComplianceAssessmentItem


class ComplianceAssessmentForm(forms.ModelForm):
    class Meta:
        model = ComplianceAssessment
        fields = [
            'name', 'framework', 'description', 'status',
            'assessor', 'owner_dept',
            'assessment_date', 'target_completion_date', 'completed_date',
            'notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'name': 'Give this assessment a clear name, e.g. "ISO 27001 Readiness Q4 2026"',
            'framework': 'All requirements from this framework will be added as checklist items.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['framework'].disabled = True


class ComplianceAssessmentItemForm(forms.ModelForm):
    class Meta:
        model = ComplianceAssessmentItem
        fields = [
            'status', 'owner_user', 'notes',
            'target_remediation_date',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
            'target_remediation_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'target_remediation_date': 'Target remediation date',
        }
