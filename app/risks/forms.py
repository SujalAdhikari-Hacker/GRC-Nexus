from django import forms

from .models import Risk, RiskTreatment, RiskException, RiskAppetite


# ============================================================
# RISK FORM
# ============================================================

class RiskForm(forms.ModelForm):
    class Meta:
        model = Risk
        fields = [
            'title', 'description',
            'threat', 'vulnerability', 'impact_description',
            'category', 'owner_dept', 'owner_user',
            'likelihood', 'impact', 'treatment_strategy', 'status',
            'assets', 'controls', 'identified_date', 'target_close_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'impact_description': forms.Textarea(attrs={'rows': 2}),
            'identified_date': forms.DateInput(attrs={'type': 'date'}),
            'target_close_date': forms.DateInput(attrs={'type': 'date'}),
        }


# ============================================================
# TREATMENT FORMS
# ============================================================

class RiskTreatmentForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = [
            'strategy', 'action_plan', 'owner_user',
            'controls', 'due_date', 'status', 'notes'
        ]
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'due_date': 'Target date',
            'action_plan': 'Plan / Description',
        }


class RiskTreatmentUpdateForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = [
            'strategy', 'action_plan', 'owner_user', 'controls',
            'due_date', 'completed_date', 'status', 'notes'
        ]
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'due_date': 'Target date',
            'action_plan': 'Plan / Description',
        }


# ============================================================
# RISK EXCEPTION
# ============================================================

class RiskExceptionForm(forms.ModelForm):
    class Meta:
        model = RiskException
        fields = [
            'title', 'risk', 'justification',
            'approver', 'approval_date',
            'expiry_date', 'review_date', 'status',
            'compensating_controls', 'conditions', 'notes',
        ]
        widgets = {
            'justification': forms.Textarea(attrs={'rows': 4}),
            'conditions': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'approval_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'review_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['risk'].disabled = True


# ============================================================
# RISK APPETITE
# ============================================================

class RiskAppetiteForm(forms.ModelForm):
    class Meta:
        model = RiskAppetite
        fields = [
            'department', 'category',
            'appetite_level', 'appetite_statement',
            'max_inherent_score', 'max_residual_score', 'risk_capacity',
            'board_approved', 'approved_by', 'review_date',
            'description',
        ]
        widgets = {
            'appetite_statement': forms.Textarea(attrs={'rows': 3}),
            'description':        forms.Textarea(attrs={'rows': 3}),
            'review_date':        forms.DateInput(attrs={'type': 'date'}),
            'max_inherent_score': forms.NumberInput(attrs={'min': 1, 'max': 25}),
            'max_residual_score': forms.NumberInput(attrs={'min': 1, 'max': 25}),
            'risk_capacity':      forms.NumberInput(attrs={'min': 1, 'max': 25}),
        }
        help_texts = {
            'review_date':        'Date when this appetite should be re-reviewed by the board.',
            'max_inherent_score': 'Maximum acceptable inherent score (1–25).',
            'max_residual_score': 'Maximum acceptable residual score (1–25).',
            'risk_capacity':      'Maximum risk the org can absorb before significant failure.',
        }

    def clean(self):
        cleaned = super().clean()
        inherent = cleaned.get('max_inherent_score')
        residual = cleaned.get('max_residual_score')
        capacity = cleaned.get('risk_capacity')

        if inherent and residual and residual > inherent:
            self.add_error('max_residual_score',
                           'Max residual cannot exceed max inherent.')

        if inherent and capacity and capacity < inherent:
            self.add_error('risk_capacity',
                           'Risk capacity must be at least the max inherent score.')

        return cleaned

    def clean_review_date(self):
        from django.utils import timezone
        review_date = self.cleaned_data.get('review_date')
        if review_date and review_date < timezone.now().date():
            if not self.instance.pk:
                raise forms.ValidationError(
                    'Review date must be in the future for a new appetite record.'
                )
        return review_date
