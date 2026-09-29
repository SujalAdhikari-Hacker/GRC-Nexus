from django import forms
from .models import Risk, RiskTreatment
from .models import RiskException


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


class RiskTreatmentForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = [
            'strategy', 'status', 'owner_user',
            'due_date', 'action_plan', 'controls', 'notes',
        ]
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Describe the plan to address this risk...'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'due_date': 'Target date',
            'action_plan': 'Plan / Description',
        }
        help_texts = {
            'controls': 'Select the controls that will implement this treatment. These are the same controls that will reduce the risk\'s residual score.',
            'strategy': 'Mitigate = reduce likelihood/impact · Accept = acknowledge · Transfer = insurance/outsource · Avoid = stop the activity',
        }


class RiskTreatmentUpdateForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = [
            'strategy', 'status', 'owner_user',
            'due_date', 'completed_date', 'action_plan', 'controls', 'notes',
        ]
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 5}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'due_date': 'Target date',
            'action_plan': 'Plan / Description',
        }
        help_texts = {
            'controls': 'Controls that implement this treatment.',
        }
class RiskExceptionForm(forms.ModelForm):
    class Meta:
        model = RiskException
        fields = [
            'title', 'risk', 'justification',
            'requested_by', 'approver', 'approval_date',
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
        help_texts = {
            'justification': 'Why accept this risk? (min 30 characters)',
            'approver': 'Who formally accepts this risk on behalf of the org?',
            'expiry_date': 'When does this exception expire? Risk must be re-evaluated after.',
            'compensating_controls': 'Extra controls reducing the residual risk while accepted.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['risk'].disabled = True
from .models import RiskException


class RiskExceptionForm(forms.ModelForm):
    class Meta:
        model = RiskException
        fields = [
            'title', 'risk', 'justification',
            'requested_by', 'approver', 'approval_date',
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
