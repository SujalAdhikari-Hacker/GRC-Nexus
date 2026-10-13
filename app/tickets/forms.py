from django import forms

from .models import Ticket, TicketComment


class TicketForm(forms.ModelForm):
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
