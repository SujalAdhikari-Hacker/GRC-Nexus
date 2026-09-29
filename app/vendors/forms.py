from django import forms
from .models import Vendor, VendorAssessment


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'name', 'description', 'service', 'tier', 'data_sensitivity', 'status',
            'owner_dept', 'owner_user',
            'contact_name', 'contact_email', 'contact_phone',
            'contract_start', 'contract_renewal_date',
            'compliance_attestations', 'compliance_notes', 'notes',
            'provides_assets',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'compliance_notes': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'contract_start': forms.DateInput(attrs={'type': 'date'}),
            'contract_renewal_date': forms.DateInput(attrs={'type': 'date'}),
        }


class VendorAssessmentForm(forms.ModelForm):
    class Meta:
        model = VendorAssessment
        fields = [
            'vendor', 'vendor_tier',
            'security_score', 'compliance_score', 'financial_score',
            'reputation_score', 'operational_score',
            'assessment_date', 'next_assessment_date',
            'assessor', 'status',
            'key_findings', 'recommended_mitigation',
        ]
        widgets = {
            'security_score':     forms.NumberInput(attrs={'min': 0, 'max': 25, 'class': 'dimension-input', 'data-dim': 'sec'}),
            'compliance_score':   forms.NumberInput(attrs={'min': 0, 'max': 25, 'class': 'dimension-input', 'data-dim': 'cmp'}),
            'financial_score':    forms.NumberInput(attrs={'min': 0, 'max': 25, 'class': 'dimension-input', 'data-dim': 'fin'}),
            'reputation_score':   forms.NumberInput(attrs={'min': 0, 'max': 25, 'class': 'dimension-input', 'data-dim': 'rep'}),
            'operational_score':  forms.NumberInput(attrs={'min': 0, 'max': 25, 'class': 'dimension-input', 'data-dim': 'ops'}),
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'next_assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'key_findings': forms.Textarea(attrs={'rows': 5}),
            'recommended_mitigation': forms.Textarea(attrs={'rows': 5}),
        }
        labels = {
            'security_score':     'Security risk (0-25)',
            'compliance_score':   'Compliance risk (0-25)',
            'financial_score':    'Financial risk (0-25)',
            'reputation_score':   'Reputation risk (0-25)',
            'operational_score':  'Operational risk (0-25)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['vendor'].disabled = True

    def clean(self):
        cleaned = super().clean()
        vendor = cleaned.get('vendor')
        if vendor and not cleaned.get('vendor_tier'):
            cleaned['vendor_tier'] = vendor.tier
        return cleaned
