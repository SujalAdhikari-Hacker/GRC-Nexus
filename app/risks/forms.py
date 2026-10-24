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
            'next_review_date', 'approved_by', 'closure_notes',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'impact_description': forms.Textarea(attrs={'rows': 2}),
            'closure_notes': forms.Textarea(attrs={'rows': 3}),
            'identified_date': forms.DateInput(attrs={'type': 'date'}),
            'target_close_date': forms.DateInput(attrs={'type': 'date'}),
            'next_review_date': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'likelihood': 'How often the event is expected: 1 Rare → 5 Almost certain.',
            'impact': 'How bad it would be: 1 Insignificant → 5 Severe.',
            'target_close_date': 'When this risk must be treated or accepted by. Drives overdue reporting.',
            'next_review_date': 'When this risk should next be reviewed.',
            'approved_by': 'A named approver is required to close a risk that breaches appetite.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        risk = self.instance
        # Only offer legal status transitions from the current state.
        if risk and risk.pk:
            allowed = risk.allowed_transitions() | {risk.status}
            self.fields['status'].choices = [
                (value, label)
                for value, label in Risk.STATUS_CHOICES
                if value in allowed
            ]

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        approved_by = cleaned.get('approved_by')
        instance = self.instance

        # 1) State-machine guard — no illegal jumps.
        if instance.pk and status and not instance.can_transition_to(status):
            self.add_error(
                'status',
                f'Cannot move a risk from '
                f'"{instance.get_status_display()}" to '
                f'"{dict(Risk.STATUS_CHOICES).get(status, status)}".',
            )

        # 2) Sign-off required to close an over-appetite / escalated risk.
        if status == 'closed' and (instance.appetite_breached or instance.escalated):
            if not (approved_by or instance.approved_by_id or cleaned.get('closure_notes')):
                self.add_error(
                    'approved_by',
                    'This risk breaches appetite — a named approver (or closure '
                    'rationale) is required before it can be closed.',
                )

        # 3) Risk appetite capacity — block registering a risk beyond capacity.
        likelihood = cleaned.get('likelihood')
        impact = cleaned.get('impact')
        if likelihood and impact:
            from .services import find_applicable_appetite
            probe = Risk(
                owner_dept=cleaned.get('owner_dept'),
                category=cleaned.get('category'),
            )
            appetite = find_applicable_appetite(probe)
            inherent = likelihood * impact
            if appetite and inherent > appetite.risk_capacity:
                self.add_error(
                    'impact',
                    f'Inherent score {inherent} exceeds the risk capacity '
                    f'({appetite.risk_capacity}) for this scope. Escalate or '
                    f'raise the appetite before registering it.',
                )
        return cleaned


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
        if review_date and review_date < timezone.localdate():
            if not self.instance.pk:
                raise forms.ValidationError(
                    'Review date must be in the future for a new appetite record.'
                )
        return review_date
