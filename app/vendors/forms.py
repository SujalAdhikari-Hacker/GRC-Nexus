from django import forms
from .models import Vendor, VendorAssessment
from .services import CERTIFICATION_CHOICES


class VendorForm(forms.ModelForm):
    certifications = forms.MultipleChoiceField(
        choices=CERTIFICATION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'form-check-input'}
        ),
    )

    class Meta:
        model = Vendor
        fields = [
            'name', 'description', 'service', 'tier', 'data_sensitivity', 'status',
            'owner_dept', 'owner_user',
            'certifications', 'jurisdiction', 'security_clauses',
            'audit_rights', 'sla_defined', 'breach_notification_hours',
            'contact_name', 'contact_email', 'contact_phone',
            'contract_start', 'contract_renewal_date',
            'compliance_attestations', 'compliance_notes', 'notes',
            'provides_assets',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'compliance_notes': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'contract_start': forms.DateInput(attrs={'type': 'date'}),
            'contract_renewal_date': forms.DateInput(attrs={'type': 'date'}),
            'security_clauses': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}),
            'audit_rights': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}),
            'sla_defined': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}),
            'breach_notification_hours': forms.NumberInput(
                attrs={'min': 1, 'max': 720}),
        }


class VendorAssessmentForm(forms.ModelForm):
    class Meta:
        model = VendorAssessment
        fields = [
            'vendor', 'vendor_tier',
            'security_score', 'compliance_score', 'financial_score',
            'reputation_score', 'operational_score',
            'assessment_date', 'next_assessment_date',
            'status',
            'key_findings', 'recommended_mitigation',
        ]
        widgets = {
            'security_score':     forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'compliance_score':   forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'financial_score':    forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'reputation_score':   forms.NumberInput(attrs={'min': 0, 'max': 20}),
            'operational_score':  forms.NumberInput(attrs={'min': 0, 'max': 20}),
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
