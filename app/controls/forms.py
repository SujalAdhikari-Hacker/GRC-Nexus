from django import forms

from core.validators import validate_evidence_file

from .models import Control, ControlEvidence, ControlFrameworkMapping


class ControlForm(forms.ModelForm):
    class Meta:
        model = Control
        fields = [
            'name', 'code', 'description',
            'control_type', 'category', 'frequency',
            'status', 'lifecycle_status', 'effectiveness_rating',
            'primary_framework', 'reference', 'framework_controls',
            'owner_dept', 'owner_user', 'is_shared',
            'last_tested', 'next_test_date', 'implementation_notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'implementation_notes': forms.Textarea(attrs={'rows': 3}),
            'last_tested': forms.DateInput(attrs={'type': 'date'}),
            'next_test_date': forms.DateInput(attrs={'type': 'date'}),
        }


class ControlEvidenceForm(forms.ModelForm):
    class Meta:
        model = ControlEvidence
        fields = ['file', 'description']

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            validate_evidence_file(f)
        return f


class ControlFrameworkMappingForm(forms.ModelForm):
    class Meta:
        model = ControlFrameworkMapping
        fields = ['framework_control', 'relationship', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
