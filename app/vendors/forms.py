from django import forms
from .models import VendorAssessment


class VendorAssessmentForm(forms.ModelForm):
    class Meta:
        model = VendorAssessment
        fields = ['assessment_date', 'score', 'status', 'findings']
        widgets = {
            'assessment_date': forms.DateInput(attrs={'type': 'date'}),
            'findings': forms.Textarea(attrs={'rows': 5}),
            'score': forms.NumberInput(attrs={'min': 0, 'max': 100}),
        }
