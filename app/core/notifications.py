from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Notification(models.Model):
    """
    Department-scoped notification. Created by signals when a new record
    is added (or when a task is left incomplete). Auto-clears when the
    underlying condition is fixed.
    """
    KIND_CHOICES = [
        ('asset_needs_vendor',      'Asset needs a vendor'),
        ('asset_needs_owner',       'Asset needs an owner'),
        ('asset_needs_policies',    'Asset needs applicable policies'),
        ('risk_needs_assessment',   'Risk needs assessment'),
        ('risk_needs_controls',     'Risk needs mitigating controls'),
        ('vendor_needs_assessment', 'Vendor needs an assessment'),
        ('policy_needs_approval',   'Policy awaiting approval'),
        ('policy_review_due',       'Policy review due'),
        ('control_needs_testing',   'Control needs testing'),
        ('control_needs_mapping',   'Control needs framework mapping'),
        ('kri_needs_reading',       'KRI needs a fresh reading'),
        ('audit_needs_lead',        'Audit needs an auditor lead'),
        ('finding_needs_owner',     'Finding needs an owner'),
        ('finding_needs_actions',   'Finding needs remediation actions'),
        ('action_needs_owner',      'Action item needs an owner'),
        ('ticket_unassigned',       'Ticket is unassigned'),
    ]

    owner_dept = models.ForeignKey(
        'core.Department', on_delete=models.CASCADE,
        related_name='notifications'
    )
    kind = models.CharField(max_length=50, choices=KIND_CHOICES)
    title = models.CharField(max_length=300)
    action_url = models.CharField(max_length=500, blank=True)

    # What object this is about — used for auto-clearing
    ref_model = models.CharField(max_length=60, blank=True)
    ref_id = models.PositiveIntegerField(null=True, blank=True)

    # State
    is_read = models.BooleanField(default=False)
    is_cleared = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner_dept', 'is_read', 'is_cleared']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'[{self.kind}] {self.title[:60]}'

    @property
    def kind_icon(self):
        """Bootstrap icon class per kind."""
        icons = {
            'asset_needs_vendor':      'bi-truck',
            'asset_needs_owner':       'bi-person',
            'asset_needs_policies':    'bi-file-earmark-text',
            'risk_needs_assessment':   'bi-exclamation-triangle',
            'risk_needs_controls':     'bi-shield-check',
            'vendor_needs_assessment': 'bi-clipboard-check',
            'policy_needs_approval':   'bi-file-earmark-check',
            'policy_review_due':       'bi-calendar-check',
            'control_needs_testing':   'bi-clipboard-data',
            'control_needs_mapping':   'bi-diagram-3',
            'kri_needs_reading':       'bi-speedometer',
            'audit_needs_lead':        'bi-clipboard',
            'finding_needs_owner':     'bi-person-badge',
            'finding_needs_actions':   'bi-list-task',
            'action_needs_owner':      'bi-person-check',
            'ticket_unassigned':       'bi-ticket-detailed',
        }
        return icons.get(self.kind, 'bi-bell')

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_cleared(self):
        if not self.is_cleared:
            self.is_cleared = True
            self.cleared_at = timezone.now()
            self.save(update_fields=['is_cleared', 'cleared_at'])


def create_notification(kind, title, action_url, owner_dept, ref_obj=None):
    """Create a notification, skipping if an identical active one already exists."""
    if owner_dept is None:
        return None

    ref_model = ''
    ref_id = None
    if ref_obj is not None:
        ref_model = f'{ref_obj._meta.app_label}.{ref_obj._meta.object_name}'
        ref_id = ref_obj.pk

    # Skip if an active (uncleared) identical notification exists
    if Notification.objects.filter(
        kind=kind,
        owner_dept=owner_dept,
        ref_model=ref_model,
        ref_id=ref_id,
        is_cleared=False,
    ).exists():
        return None

    return Notification.objects.create(
        owner_dept=owner_dept,
        kind=kind,
        title=title,
        action_url=action_url,
        ref_model=ref_model,
        ref_id=ref_id,
    )
