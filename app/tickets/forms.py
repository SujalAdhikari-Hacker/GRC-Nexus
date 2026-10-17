from django import forms
from django.contrib.contenttypes.models import ContentType

from .models import Ticket, TicketComment

# Linkable targets for a ticket.  Presented as four optional selects (no JS
# needed): pick at most one and the view stamps the GenericForeignKey.
LINK_FIELDS = (
    ('link_asset', 'Asset'),
    ('link_risk', 'Risk'),
    ('link_control', 'Control'),
    ('link_policy', 'Policy'),
)


class TicketForm(forms.ModelForm):
    link_asset = forms.ModelChoiceField(
        queryset=None, required=False, label='Linked asset',
        help_text='Optional — tie this ticket to a specific asset.',
    )
    link_risk = forms.ModelChoiceField(
        queryset=None, required=False, label='Linked risk',
        help_text='Optional — tie this ticket to a risk (e.g. a treatment action).',
    )
    link_control = forms.ModelChoiceField(
        queryset=None, required=False, label='Linked control',
        help_text='Optional — tie this ticket to a control.',
    )
    link_policy = forms.ModelChoiceField(
        queryset=None, required=False, label='Linked policy',
        help_text='Optional — tie this ticket to a policy.',
    )

    class Meta:
        model = Ticket
        fields = [
            'title', 'description',
            'priority', 'status',
            'owner_dept', 'assigned_to',
            'due_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        help_texts = {
            'title':       'Short description of the work to be done.',
            'description': 'Context, expected outcome, any relevant details.',
            'assigned_to': 'Leave blank to post to the department queue (anyone can self-claim).',
            'due_date':    'Optional target completion date.',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from assets.models import Asset
        from controls.models import Control
        from policies.models import Policy
        from risks.models import Risk

        from core.mixins import scope_queryset

        self._link_models = {
            'link_asset': Asset,
            'link_risk': Risk,
            'link_control': Control,
            'link_policy': Policy,
        }

        # Scope every picker to what the user may actually see, so the
        # dropdowns stay short and never leak another department's records.
        for field, model in self._link_models.items():
            qs = model.objects.all().order_by('pk')
            if user is not None and user.is_authenticated:
                qs = scope_queryset(qs, user)
            self.fields[field].queryset = qs

        # Pre-select the existing link when editing.
        if self.instance and self.instance.pk and self.instance.object_id and self.instance.content_type_id:
            model_name = self.instance.content_type.model
            for field, model in self._link_models.items():
                if model._meta.model_name == model_name:
                    self.fields[field].initial = self.instance.object_id
                    break

    def clean(self):
        cleaned = super().clean()
        chosen = [f for f in self._link_models if cleaned.get(f)]
        if len(chosen) > 1:
            raise forms.ValidationError(
                'Link the ticket to at most one object '
                '(asset, risk, control or policy).'
            )
        return cleaned

    def apply_link(self, instance):
        """Stamp the chosen GenericForeignKey onto ``instance``."""
        for field, model in self._link_models.items():
            obj = self.cleaned_data.get(field)
            if obj is not None:
                instance.content_type = ContentType.objects.get_for_model(model)
                instance.object_id = obj.pk
                from risks.models import Risk
                if model is Risk and instance.source == 'manual':
                    instance.source = 'risk'
                return
        # Nothing chosen (or cleared) — drop any existing link.
        instance.content_type = None
        instance.object_id = None

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if len(title) < 5:
            raise forms.ValidationError('Title must be at least 5 characters.')
        return title


class TicketCommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Add a comment...',
            }),
        }
        labels = {'body': ''}
