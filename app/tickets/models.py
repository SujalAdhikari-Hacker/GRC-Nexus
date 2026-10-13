from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import Department


class Ticket(models.Model):
    """
    A trackable work item — either auto-generated from an alert, or manually
    created by a HOD/superuser. Belongs to a department, can be assigned to a
    user, tracks status through to resolution.
    """
    SOURCE_CHOICES = [
        ('alert',         'Auto-generated Alert'),
        ('manual',        'Manually Created'),
        ('risk',          'Risk Assignment'),
        ('audit',         'Audit Finding'),
        ('vulnerability', 'Vulnerability Remediation'),
    ]

    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
    ]

    STATUS_CHOICES = [
        ('open',        'Open — Unassigned'),
        ('assigned',    'Assigned'),
        ('in_progress', 'In Progress'),
        ('blocked',     'Blocked'),
        ('resolved',    'Resolved'),
        ('closed',      'Closed'),
        ('cancelled',   'Cancelled'),
    ]

    # Identification
    ticket_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like TKT-0001.'
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    # Source & linkage
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='manual'
    )
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='tickets'
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    linked_object = GenericForeignKey('content_type', 'object_id')

    # Priority & status
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    # Ownership & assignment
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='tickets'
    )
    assigned_to = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_tickets',
        help_text='The user currently responsible for this ticket'
    )
    assigned_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_out_tickets',
        help_text='Who assigned it'
    )

    # Dates
    due_date = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Resolution
    resolution_notes = models.TextField(blank=True)

    # Accountability
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tickets', editable=False
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_tickets', editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-priority', 'due_date', '-created_at']
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'

    def __str__(self):
        return f"{self.ticket_id or 'NEW'} — {self.title[:60]}"

    def save(self, *args, **kwargs):
        # Auto-generate ID
        if not self.ticket_id:
            last = Ticket.objects.exclude(ticket_id__isnull=True).exclude(ticket_id='').order_by('-id').first()
            next_num = 1
            if last and last.ticket_id:
                try:
                    next_num = int(last.ticket_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = Ticket.objects.count() + 1
            while Ticket.objects.filter(ticket_id=f'TKT-{next_num:04d}').exists():
                next_num += 1
            self.ticket_id = f'TKT-{next_num:04d}'

        # Auto-set resolved_at
        if self.status == 'resolved' and not self.resolved_at:
            from django.utils import timezone
            self.resolved_at = timezone.now()
        if self.status == 'closed' and not self.closed_at:
            from django.utils import timezone
            self.closed_at = timezone.now()

        super().save(*args, **kwargs)

    # ---------- Properties for templates ----------
    @property
    def priority_color(self):
        return {1: '#6B7280', 2: '#0284C7', 3: '#D97706', 4: '#DC2626'}.get(self.priority, '#6B7280')

    @property
    def status_color(self):
        return {
            'open':        '#DC2626',
            'assigned':    '#D97706',
            'in_progress': '#0284C7',
            'blocked':     '#EA580C',
            'resolved':    '#059669',
            'closed':      '#6B7280',
            'cancelled':   '#94A3B8',
        }.get(self.status, '#6B7280')

    @property
    def is_overdue(self):
        if self.status in ('resolved', 'closed', 'cancelled'):
            return False
        if not self.due_date:
            return False
        from django.utils import timezone
        return self.due_date < timezone.now().date()

    @property
    def is_open(self):
        return self.status not in ('resolved', 'closed', 'cancelled')


class TicketComment(models.Model):
    """A threaded comment on a ticket — plain text, timestamped, attributed."""
    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name='comments'
    )
    author = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ticket_comments'
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Ticket comment'
        verbose_name_plural = 'Ticket comments'

    def __str__(self):
        return f"Comment on {self.ticket.ticket_id} by {self.author}"