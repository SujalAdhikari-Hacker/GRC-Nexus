from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department


class Audit(models.Model):
    """
    Plan, track, and close out internal, external, and self-assessment audits
    with full lifecycle visibility.
    """
    TYPE_CHOICES = [
        ('external', 'External'),
        ('internal', 'Internal'),
        ('self_assessment', 'Self-Assessment'),
    ]
    STATUS_CHOICES = [
        ('planned',     'Planned'),
        ('planning',    'Planning'),
        ('in_progress', 'In Progress'),
        ('complete',    'Complete'),
    ]

    name = models.CharField(max_length=300)
    audit_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='internal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')

    auditor_lead = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='led_audits'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='audits'
    )

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    scope = models.TextField(blank=True, help_text='What this audit covers')

    frameworks = models.ManyToManyField(
        'frameworks.Framework', blank=True, related_name='audits'
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_audits', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_audits', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-start_date', 'name']

    def __str__(self):
        return self.name

    @property
    def finding_count(self):
        return self.findings.count()

    @property
    def open_finding_count(self):
        return self.findings.exclude(status__in=['resolved', 'closed', 'accepted']).count()


class EvidenceItem(models.Model):
    """
    Collect, organize, and link audit evidence — screenshots, exports,
    configs, logs — to the controls they prove.
    """
    TYPE_CHOICES = [
        ('screenshot',    'Screenshot'),
        ('document',      'Document'),
        ('report',        'Report'),
        ('export',        'Export'),
        ('configuration', 'Configuration'),
        ('log',           'Log'),
    ]

    title = models.CharField(max_length=300)
    evidence_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='document')
    related_control = models.ForeignKey(
        'controls.Control', on_delete=models.CASCADE, related_name='audit_evidence',
        null=True, blank=True,
        help_text='The control this evidence proves'
    )
    audit = models.ForeignKey(
        Audit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='evidence_items'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_evidence'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='evidence_items'
    )

    url_location = models.CharField(
        max_length=500, blank=True,
        help_text='External URL or file path if not uploaded'
    )
    attachment = models.FileField(
        upload_to='audit_evidence/', null=True, blank=True
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_evidence', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_evidence', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Evidence item'
        verbose_name_plural = 'Evidence items'

    def __str__(self):
        return self.title

    @property
    def score(self):
        return getattr(self, 'scoring', None)


class EvidenceScore(models.Model):
    """
    Evaluate evidence across 5 dimensions: Relevance, Completeness,
    Timeliness, Reliability, Sufficiency. Each 0-20. Total 0-100.
    """
    evidence = models.OneToOneField(
        EvidenceItem, on_delete=models.CASCADE, related_name='scoring'
    )

    relevance = models.PositiveSmallIntegerField(
        default=0, help_text='Does it directly support the control? (0-20)'
    )
    completeness = models.PositiveSmallIntegerField(
        default=0, help_text='Is it comprehensive enough? (0-20)'
    )
    timeliness = models.PositiveSmallIntegerField(
        default=0, help_text='Is it current and within audit period? (0-20)'
    )
    reliability = models.PositiveSmallIntegerField(
        default=0, help_text='Is the source trustworthy? (0-20)'
    )
    sufficiency = models.PositiveSmallIntegerField(
        default=0, help_text='Enough to satisfy the auditor? (0-20)'
    )

    total_score = models.PositiveSmallIntegerField(default=0, editable=False)

    assessor = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='evidence_scores'
    )
    assessor_notes = models.TextField(blank=True)
    scored_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Evidence score'
        verbose_name_plural = 'Evidence scores'

    def __str__(self):
        return f"Score for {self.evidence.title}: {self.total_score}/100"

    def save(self, *args, **kwargs):
        self.total_score = (
            (self.relevance or 0)
            + (self.completeness or 0)
            + (self.timeliness or 0)
            + (self.reliability or 0)
            + (self.sufficiency or 0)
        )
        super().save(*args, **kwargs)

    @property
    def rating(self):
        s = self.total_score
        if s >= 90:
            return 'excellent'
        if s >= 75:
            return 'good'
        if s >= 50:
            return 'partial'
        return 'weak'


class ControlTest(models.Model):
    """
    Document test procedures, results, and evidence for each control —
    untested controls give zero assurance.
    """
    RESULT_CHOICES = [
        ('pass',                   'Pass'),
        ('partial',                'Partial'),
        ('fail',                   'Fail'),
        ('self_audit',             'Self Audit'),
        ('customer_complaint',     'Customer Complaint'),
        ('continuous_complaint',   'Continuous Complaint'),
        ('continuous_monitoring',  'Continuous Monitoring'),
        ('other',                  'Other'),
    ]

    control = models.ForeignKey(
        'controls.Control', on_delete=models.CASCADE, related_name='audit_tests'
    )
    test_date = models.DateField()
    result = models.CharField(max_length=30, choices=RESULT_CHOICES, default='pass')
    tester = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='performed_tests'
    )
    procedure_notes = models.TextField(blank=True, help_text='Procedure / Notes')

    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='control_tests'
    )
    audit = models.ForeignKey(
        Audit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='control_tests'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-test_date']
        verbose_name = 'Control test'
        verbose_name_plural = 'Control tests'

    def __str__(self):
        return f"{self.control.code} · {self.test_date} · {self.get_result_display()}"


class AuditFinding(models.Model):
    """
    Track gaps, deficiencies, and recommendations from audits through to
    remediation and closure.
    """
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high',     'High'),
        ('medium',   'Medium'),
        ('low',      'Low'),
    ]
    STATUS_CHOICES = [
        ('open',        'Open'),
        ('in_progress', 'In Progress'),
        ('resolved',    'Resolved'),
        ('accepted',    'Risk Accepted'),
        ('closed',      'Closed'),
    ]
    SOURCE_CHOICES = [
        ('internal_audit',        'Internal Audit'),
        ('external_audit',        'External Audit'),
        ('self_assessment',       'Self-Assessment'),
        ('customer_complaint',    'Customer Complaint'),
        ('continuous_monitoring', 'Continuous Monitoring'),
        ('other',                 'Other'),
    ]

    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='internal_audit')

    audit = models.ForeignKey(
        Audit, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='findings'
    )
    related_control = models.ForeignKey(
        'controls.Control', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_findings'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_findings'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='audit_findings'
    )

    due_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)

    description = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_audit_findings', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_audit_findings', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit finding'
        verbose_name_plural = 'Audit findings'

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"


class ActionItem(models.Model):
    """
    Remediation task under an audit finding.
    Multiple items can exist per finding, each with its own owner, due date, and status.
    """
    STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('blocked',     'Blocked'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
    ]

    action_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like ACT-0001.'
    )
    finding = models.ForeignKey(
        'audits.AuditFinding', on_delete=models.CASCADE,
        related_name='action_items'
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='action_items'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT,
        related_name='action_items'
    )

    priority = models.PositiveSmallIntegerField(
        choices=PRIORITY_CHOICES, default=2
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='not_started'
    )

    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    progress_percent = models.PositiveSmallIntegerField(
        default=0, help_text='0-100. Auto-set to 100 when completed.'
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['due_date', '-priority']
        verbose_name = 'Action item'
        verbose_name_plural = 'Action items'

    def __str__(self):
        return f"{self.action_id or 'NEW'} — {self.title[:60]}"

    def save(self, *args, **kwargs):
        # Auto-generate ID
        if not self.action_id:
            last = ActionItem.objects.exclude(action_id__isnull=True).exclude(action_id='').order_by('-id').first()
            next_num = 1
            if last and last.action_id:
                try:
                    next_num = int(last.action_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = ActionItem.objects.count() + 1
            while ActionItem.objects.filter(action_id=f'ACT-{next_num:04d}').exists():
                next_num += 1
            self.action_id = f'ACT-{next_num:04d}'

        # Auto-complete behaviors
        if self.status == 'completed':
            self.progress_percent = 100
            if not self.completed_date:
                from django.utils import timezone
                self.completed_date = timezone.now().date()
        elif self.status == 'cancelled':
            if not self.completed_date:
                from django.utils import timezone
                self.completed_date = timezone.now().date()

        # Clamp progress
        if self.progress_percent < 0:
            self.progress_percent = 0
        if self.progress_percent > 100:
            self.progress_percent = 100

        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if not self.title or len(self.title.strip()) < 5:
            errors['title'] = 'Title must be at least 5 characters.'
        if self.status == 'completed' and self.progress_percent != 100:
            self.progress_percent = 100
        if errors:
            raise ValidationError(errors)

    @property
    def status_color(self):
        return {
            'not_started': '#6B7280',
            'in_progress': '#0284C7',
            'blocked':     '#EA580C',
            'completed':   '#059669',
            'cancelled':   '#94A3B8',
        }.get(self.status, '#6B7280')

    @property
    def priority_color(self):
        return {
            1: '#6B7280',
            2: '#0284C7',
            3: '#D97706',
            4: '#DC2626',
        }.get(self.priority, '#6B7280')

    @property
    def days_until_due(self):
        from django.utils import timezone
        if not self.due_date:
            return None
        return (self.due_date - timezone.now().date()).days

    @property
    def is_overdue(self):
        if self.status in ('completed', 'cancelled'):
            return False
        d = self.days_until_due
        return d is not None and d < 0

    @property
    def is_due_soon(self):
        if self.status in ('completed', 'cancelled'):
            return False
        d = self.days_until_due
        return d is not None and 0 <= d <= 7
