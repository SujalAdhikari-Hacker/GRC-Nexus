from django import forms

from .models import (
    Framework, FrameworkControl,
    ComplianceAssessment, ComplianceAssessmentItem,
)


# ============================================================
# FRAMEWORK
# ============================================================

class FrameworkForm(forms.ModelForm):
    class Meta:
        model = Framework
        fields = ['name', 'version', 'description']
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Short description of the framework and what it covers.',
            }),
        }
        help_texts = {
            'name':        'e.g. ISO/IEC 27001, NIST CSF, SOC 2',
            'version':     'e.g. 2022, v2.0, 2017 TSC',
            'description': 'What this framework covers and who issues it.',
        }

    def clean_name(self):
        name = (self.cleaned_data.get('name') or '').strip()
        if len(name) < 3:
            raise forms.ValidationError('Framework name must be at least 3 characters.')
        return name


# ============================================================
# FRAMEWORK CONTROL
# ============================================================

class FrameworkControlForm(forms.ModelForm):
    class Meta:
        model = FrameworkControl
        fields = ['framework', 'code', 'title', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }
        help_texts = {
            'code':  'Short code or clause reference — e.g. A.5.1, ID.AM-1, CC6.1',
            'title': 'Brief summary of the requirement.',
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code:
            raise forms.ValidationError('Code is required.')
        return code

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if len(title) < 5:
            raise forms.ValidationError('Title must be at least 5 characters.')
        return title


# ============================================================
# COMPLIANCE ASSESSMENT
# ============================================================

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
            'description':            forms.Textarea(attrs={'rows': 3}),
            'notes':                  forms.Textarea(attrs={'rows': 3}),
            'assessment_date':        forms.DateInput(attrs={'type': 'date'}),
            'target_completion_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date':         forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'name':      'Give this assessment a clear name, e.g. "ISO 27001 Readiness Q4 2026".',
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
