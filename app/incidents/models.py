"""Security-incident register.

An incident is an event that may compromise confidentiality, integrity or
availability. Recording, categorising and closing them is what ISO 27001
(A.5.24 - A.5.28) and the GDPR breach-notification deadline (72 hours from
awareness) require, and it is the primary feed into the audit-finding and
risk processes afterwards.

Resolved from three directions:

* **A risk can escalate into an incident** - a mitigating control fails, an
  accepted risk bites, or a vulnerability is actively exploited.
* **An incident can chill into a risk** - once investigated, its residual
  exposure is entered in the register so the same weakness cannot recur
  unnoticed (``Incident.escalate_to_risk`` / the *raise risk* action).
* **Every incident is stamped with a timeline** (detected / triaged /
  contained / resolved / closed) so the "how fast did we actually respond?"
  numbers come from the data rather than from memory.
"""
import datetime as _dt

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.models import Department

from .nis2 import PHASE_CHOICES, SUBMISSION_FIELDS, derive_phase, phase_clocks

# Added today - relative to detected_at - for each severity. Zero means "no
# deadline of its own"; the regulatory window (below) applies on top of it.
TRIAGE_SLA_HOURS = {'critical': 1, 'high': 4, 'medium': 24, 'low': 72}

# GDPR Art. 33: notify the supervisory authority within 72 hours of becoming
# aware of a breach, where the incident is one.
BREACH_NOTIFICATION_HOURS = 72

_OPEN_STATUSES = ('detected', 'triaged', 'contained')


class Incident(models.Model):
    """A single security incident, from first awareness through closure."""

    SEVERITY_CHOICES = [
        ('critical', 'Critical - confirmed compromise or ongoing attack'),
        ('high',     'High - significant loss of confidentiality / integrity'),
        ('medium',   'Medium - limited or reversible impact'),
        ('low',      'Low - negligible impact, logged for the record'),
    ]
    STATUS_CHOICES = [
        ('detected', 'Detected'),
        ('triaged',  'Triaged'),
        ('contained', 'Contained'),
        ('mitigated', 'Mitigated'),
        ('closed',   'Closed'),
    ]
    TYPE_CHOICES = [
        ('data_breach',          'Data breach or loss'),
        ('unauthorized_access',  'Unauthorised access'),
        ('ransomware',           'Ransomware'),
        ('malware',              'Malware infection'),
        ('phishing',             'Phishing / social engineering'),
        ('ddos',                 'Denial of service'),
        ('insider',              'Insider misuse'),
        ('lost_device',          'Lost or stolen device'),
        ('vendor_incident',      'Vendor / third-party reported'),
        ('policy_violation',     'Policy violation (no real harm)'),
        ('other',                'Other'),
    ]
    SOURCE_CHOICES = [
        ('employee',     'Employee report'),
        ('monitoring',   'Automated monitoring / SIEM'),
        ('third_party',  'Third party notification'),
        ('risk_event',   'Escalated from the risk register'),
        ('external',     'External report'),
        ('internal_test','Internal test / exercise'),
    ]

    reference = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(
        help_text='What happened, where, and how it was noticed.'
    )

    incident_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='other')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='employee')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='detected')

    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='incidents'
    )
    handler = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='handled_incidents',
        help_text='Person accountable for investigating and closing this incident.'
    )

    detected_at = models.DateTimeField(
        default=timezone.now,
        help_text='When the organisation first became aware of it.'
    )
    triaged_at = models.DateTimeField(null=True, blank=True)
    contained_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    affected_assets = models.ManyToManyField(
        'assets.Asset', blank=True, related_name='incidents',
        help_text='Systems confirmed or suspected to be involved.'
    )

    # --- personal-data breach, GDPR Art. 33 ---
    data_subjects_affected = models.PositiveIntegerField(
        default=0,
        help_text='Number of individuals whose personal data is affected.'
    )
    regulatory_notification_required = models.BooleanField(
        default=False,
        help_text='GDPR Art. 33 - does this need to go to the supervisory authority?'
    )
    regulatory_notified_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the supervisory authority was actually notified.'
    )

    # --- NIS2 Article 23 reports ---
    # Only significant incidents owe the 24 h / 72 h / 30-day reports. The
    # deadlines themselves are derived from ``detected_at`` on read, so
    # correcting the detection time moves the clock instead of leaving stale
    # dates behind.
    nis2_significant = models.BooleanField(
        default=False,
        help_text='Article 23 applies: significant impact, so the 24 h, 72 h '
                  'and 30-day reports are due.'
    )
    nis2_early_warning_submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the early warning (24 h) was filed with the CSIRT.'
    )
    nis2_notification_submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the incident notification (72 h) was filed.'
    )
    nis2_final_report_submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the final report (30 days) was filed.'
    )

    # --- closure record ---
    root_cause = models.TextField(
        blank=True, help_text='Technical or procedural cause, once established.'
    )
    lessons_learned = models.TextField(
        blank=True, help_text='What changes as a result - feeds the control library.'
    )

    # --- linkage ---
    risks = models.ManyToManyField(
        'risks.Risk', blank=True, related_name='incidents',
        help_text='Risk-register entries raised from or linked to this incident.'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reported_incidents', editable=False,
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_incidents', editable=False,
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-detected_at']
        verbose_name = 'Security incident'
        verbose_name_plural = 'Security incidents'
        constraints = [
            models.CheckConstraint(
                check=~models.Q(status__in=('closed',)) | models.Q(closed_at__isnull=False),
                name='incident_closed_requires_closed_at',
            ),
        ]

    def __str__(self):
        return f'{self.reference} - {self.title}'

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.next_reference()
        self._stamp_lifecycle_dates()
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.closed_at and not self.root_cause:
            errors['root_cause'] = 'An incident cannot be closed without a root cause.'
        if self.triaged_at and self.detected_at and self.triaged_at < self.detected_at:
            errors['triaged_at'] = 'Triage cannot happen before the incident was detected.'
        if self.contained_at and self.detected_at and self.contained_at < self.detected_at:
            errors['contained_at'] = 'Containment cannot happen before detection.'
        for phase, field in SUBMISSION_FIELDS.items():
            submitted_at = getattr(self, field)
            if submitted_at and self.detected_at and submitted_at < self.detected_at:
                errors[field] = (
                    'A NIS2 report cannot be filed before the incident was '
                    'detected.'
                )
        if errors:
            raise ValidationError({**errors})

    # -- reference ---------------------------------------------------------

    @classmethod
    def next_reference(cls):
        """Monotonic human reference, e.g. ``INC-2026-0007``."""
        year = timezone.localdate().year
        prefix = f'INC-{year}-'
        last = (
            cls.objects.filter(reference__startswith=prefix)
            .order_by('-reference').values_list('reference', flat=True).first()
        )
        seq = int(last.rsplit('-', 1)[1]) + 1 if last else 1
        return f'{prefix}{seq:04d}'

    def _stamp_lifecycle_dates(self):
        """Keep the timeline columns consistent with ``status``.

        Moving forward stamps the timestamp the first time the stage is
        reached; moving back clears it again so the timeline always matches
        the status column.
        """
        progress = [s for s, _ in self.STATUS_CHOICES]  # detected .. closed
        try:
            reached = progress.index(self.status)
        except ValueError:
            return
        now = timezone.now()
        for stage, field in (
            ('triaged', 'triaged_at'),
            ('contained', 'contained_at'),
            ('mitigated', 'resolved_at'),
            ('closed', 'closed_at'),
        ):
            if progress.index(stage) <= reached:
                if not getattr(self, field):
                    setattr(self, field, now)
            else:
                setattr(self, field, None)

    # -- derived properties ------------------------------------------------

    @property
    def is_open(self):
        return self.status != 'closed'

    @property
    def is_breach(self):
        """Personal-data breach under GDPR chapter IV."""
        return self.incident_type == 'data_breach'

    @property
    def breaching_event(self):
        """Deadline timestamp for the Art. 33 notification: aware + 72 hours."""
        if not (self.is_breach and self.regulatory_notification_required):
            return None
        if self.regulatory_notified_at:
            return None
        return self.detected_at + _dt.timedelta(hours=BREACH_NOTIFICATION_HOURS)

    @property
    def breaching_hours_left(self):
        """Hours left on the regulatory clock (negative = already late)."""
        deadline = self.breaching_event
        if deadline is None:
            return None
        return round((deadline - timezone.now()).total_seconds() / 3600, 1)

    @property
    def nis2_submissions(self):
        """Phase -> datetime for the Article 23 reports already filed."""
        return {
            phase: getattr(self, field)
            for phase, field in SUBMISSION_FIELDS.items()
        }

    @property
    def nis2_clocks(self):
        """The three Article 23 phase clocks, derived from ``detected_at``."""
        return phase_clocks(self.detected_at, self.nis2_submissions)

    @property
    def nis2_phase(self):
        """The next report owed, or ``complete``."""
        return derive_phase(self.nis2_submissions)

    @property
    def nis2_breach(self):
        """The first phase whose deadline has passed without a report."""
        return next(
            (clock for clock in self.nis2_clocks if clock.state == 'breached'),
            None,
        )

    @property
    def nis2_status(self):
        """Aggregate state for list badges; None when Article 23 does not apply."""
        if not self.nis2_significant:
            return None
        clocks = self.nis2_clocks
        states = {clock.state for clock in clocks}
        if 'breached' in states:
            return 'breached'
        if 'due_soon' in states:
            return 'due_soon'
        if states == {'submitted'}:
            return 'complete'
        return 'open'

    @property
    def sla_breached(self):
        """Triage deadline for the severity missed while still untriaged."""
        if self.status != 'detected' or not self.detected_at:
            return False
        hours = TRIAGE_SLA_HOURS.get(self.severity, 24)
        return self.age_hours > hours

    @property
    def age_hours(self):
        if not self.detected_at:
            return 0
        return round((timezone.now() - self.detected_at).total_seconds() / 3600, 1)

    @property
    def response_hours(self):
        """Detection-to-resolution. None while the incident is still open."""
        if not (self.detected_at and self.resolved_at):
            return None
        return round((self.resolved_at - self.detected_at).total_seconds() / 3600, 1)

    @property
    def containment_hours(self):
        """Detection-to-containment: the number response teams are judged on."""
        if not (self.detected_at and self.contained_at):
            return None
        return round((self.contained_at - self.detected_at).total_seconds() / 3600, 1)

    @property
    def status_badge(self):
        """Bootstrap badge class for the status pill."""
        return {
            'detected': 'bg-warning',
            'triaged': 'bg-info',
            'contained': 'bg-info',
            'mitigated': 'bg-success',
            'closed': 'bg-secondary',
        }.get(self.status, 'bg-secondary')

    @property
    def severity_badge(self):
        return {
            'critical': 'bg-danger',
            'high': 'bg-warning',
            'medium': 'bg-info',
            'low': 'bg-secondary',
        }.get(self.severity, 'bg-secondary')


class Nis2DeadlineAlert(models.Model):
    """Dispatch ledger for Article 23 deadline alerts.

    One row per incident, phase and kind. The unique constraint is what makes
    an hourly sweep idempotent across retries and concurrent runs; the row
    also stays as evidence after its notification has been read or cleared.
    """

    KIND_CHOICES = [
        ('pre_deadline', 'Pre-deadline warning'),
        ('breach', 'Deadline missed'),
    ]

    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name='nis2_alerts'
    )
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'NIS2 deadline alert'
        constraints = [
            models.UniqueConstraint(
                fields=('incident', 'phase', 'kind'),
                name='nis2_alert_once_per_phase_kind',
            ),
        ]

    def __str__(self):
        return f'{self.incident_id} {self.phase} {self.kind}'


def open_incidents(dept=None):
    """Unclosed incidents, most urgent first, scoped to ``dept`` if given."""
    qs = Incident.objects.filter(status__in=_OPEN_STATUSES + ('mitigated',))
    if dept is not None:
        qs = qs.filter(owner_dept=dept)
    return qs.order_by('-severity', 'detected_at')
