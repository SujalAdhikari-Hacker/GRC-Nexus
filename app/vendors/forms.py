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
            'financial_risk', 'operational_risk', 'regulatory_risk',
            'cybersecurity_risk', 'reputational_risk',
            'assessment_date', 'next_assessment_date',
            'assessor', 'status',
            'key_findings', 'recommended_mitigation',
        ]
        widgets = {
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'next_assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'key_findings': forms.Textarea(attrs={'rows': 5}),
            'recommended_mitigation': forms.Textarea(attrs={'rows': 5}),
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
