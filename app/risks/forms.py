from django import forms
from .models import Risk, RiskTreatment


class RiskForm(forms.ModelForm):
    class Meta:
        model = Risk
        fields = [
            'title', 'description', 'category', 'owner_dept', 'owner_user',
            'likelihood', 'impact', 'treatment_strategy', 'status',
            'assets', 'controls', 'identified_date', 'target_close_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'identified_date': forms.DateInput(attrs={'type': 'date'}),
            'target_close_date': forms.DateInput(attrs={'type': 'date'}),
        }


class RiskTreatmentForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = ['action_plan', 'owner_user', 'due_date', 'status', 'notes']
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class RiskTreatmentUpdateForm(forms.ModelForm):
    class Meta:
        model = RiskTreatment
        fields = ['action_plan', 'owner_user', 'due_date', 'completed_date', 'status', 'notes']
        widgets = {
            'action_plan': forms.Textarea(attrs={'rows': 4}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'completed_date': forms.DateInput(attrs={'type': 'date'}),
        }
