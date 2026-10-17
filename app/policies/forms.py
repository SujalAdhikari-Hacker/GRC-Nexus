from django import forms

from core.validators import validate_evidence_file

from .models import Policy


class PolicyForm(forms.ModelForm):
    class Meta:
        model = Policy
        fields = [
            'code', 'title', 'category',
            'description', 'content',
            'version', 'status',
            'owner_dept', 'approved_by',
            'approval_date', 'next_review_date',
            'document',
            'applies_to_departments',
        ]
        widgets = {
            'description':  forms.Textarea(attrs={'rows': 3, 'placeholder': 'Short summary of what this policy covers.'}),
            'content':      forms.Textarea(attrs={'rows': 8, 'placeholder': 'Full policy body text (optional if you attach a PDF below).'}),
            'approval_date': forms.DateInput(attrs={'type': 'date'}),
            'next_review_date': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'code':          'Short identifier — e.g. POL-ISMS-001. Must be unique.',
            'title':         'Human-readable policy title.',
            'category':      'Grouping (Information Security, Data Protection, etc.).',
            'version':       'Version string — e.g. 1.0, 2.1.',
            'status':        'Workflow stage: Draft → Review → Approved → Retired.',
            'owner_dept':    'Department responsible for maintaining this policy.',
            'approved_by':   'Who signed off on this policy (optional).',
            'approval_date': 'When this policy was approved.',
            'next_review_date': 'When this policy must be re-reviewed.',
            'document':      'Optional PDF of the policy document.',
            'applies_to_departments': 'Departments this policy applies to. Leave empty for org-wide. Hold Ctrl/Cmd to select multiple.',
            'content':       'Policy body text. Leave empty if you uploaded a PDF above.',
        }

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip().upper()
        if len(code) < 3:
            raise forms.ValidationError('Policy code must be at least 3 characters.')
        return code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Policy documents are user uploads served back through core.media;
        # restrict them to the same vetted types and size cap as evidence.
        self.fields['document'].validators.append(validate_evidence_file)
        policy = self.instance
        if policy and policy.pk:
            allowed = policy.allowed_transitions() | {policy.status}
            self.fields['status'].choices = [
                (value, label)
                for value, label in Policy.STATUS_CHOICES
                if value in allowed
            ]

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if len(title) < 5:
            raise forms.ValidationError('Title must be at least 5 characters.')
        return title

    def clean(self):
        cleaned = super().clean()
        approval = cleaned.get('approval_date')
        review = cleaned.get('next_review_date')
        status = cleaned.get('status')
        instance = self.instance

        # State-machine guard.
        if instance.pk and status and not instance.can_transition_to(status):
            self.add_error(
                'status',
                f'Cannot move a policy from "{instance.get_status_display()}" '
                f'to "{(dict(Policy.STATUS_CHOICES).get(status, status))}".',
            )

        # Approval requires a named approver and a date.
        if status == 'approved' and not (cleaned.get('approved_by') or instance.approved_by_id):
            self.add_error('approved_by', 'A named approver is required to approve a policy.')
        if status == 'approved' and not (approval or instance.approval_date):
            self.add_error('approval_date', 'An approval date is required to approve a policy.')

        if approval and review and review < approval:
            self.add_error('next_review_date', 'Next review date cannot be before approval date.')
        return cleaned
