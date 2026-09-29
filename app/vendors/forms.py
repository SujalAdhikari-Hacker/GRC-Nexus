from django import forms
from .models import Vendor, VendorAssessment


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'name', 'description', 'contact_name', 'contact_email', 'contact_phone',
            'tier', 'vendor_criticality', 'data_sensitivity', 'owner_dept',
            'provides_assets', 'contract_start', 'contract_end', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'contract_start': forms.DateInput(attrs={'type': 'date'}),
            'contract_end': forms.DateInput(attrs={'type': 'date'}),
        }


class VendorAssessmentForm(forms.ModelForm):
    class Meta:
        model = VendorAssessment
        fields = [
            'vendor', 'vendor_criticality',
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
        help_texts = {
            'vendor_criticality': 'Auto-fills from the vendor record.',
            'financial_risk': '1 = Low risk, 5 = Very Critical risk',
            'operational_risk': '1 = Low risk, 5 = Very Critical risk',
            'regulatory_risk': '1 = Low risk, 5 = Very Critical risk',
            'cybersecurity_risk': '1 = Low risk, 5 = Very Critical risk',
            'reputational_risk': '1 = Low risk, 5 = Very Critical risk',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['vendor'].disabled = True

    def clean(self):
        cleaned = super().clean()
        vendor = cleaned.get('vendor')
        if vendor and not cleaned.get('vendor_criticality'):
            cleaned['vendor_criticality'] = vendor.vendor_criticality
        return cleaned
