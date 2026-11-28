from django.db import models
from simple_history.models import HistoricalRecords


class Framework(models.Model):
    name = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} {self.version}".strip()


class FrameworkControl(models.Model):
    framework = models.ForeignKey(
        Framework, on_delete=models.CASCADE, related_name='controls'
    )
    code = models.CharField(max_length=50)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = ('framework', 'code')
        ordering = ['framework', 'code']

    def __str__(self):
        return f"{self.framework.name} {self.code}"

from django.db import models as _dj_models
from simple_history.models import HistoricalRecords as _HR
from core.models import Department


class ComplianceAssessment(_dj_models.Model):
    """
    A readiness assessment of the organization against a specific framework.
    Auto-populates one item per FrameworkControl when created.
    """
    STATUS_CHOICES = [
        ('draft',       'Draft'),
        ('in_progress', 'In Progress'),
        ('under_review','Under Review'),
        ('completed',   'Completed'),
        ('archived',    'Archived'),
    ]

    assessment_id = _dj_models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like CMP-0001.'
    )
    framework = _dj_models.ForeignKey(
        'frameworks.Framework', on_delete=_dj_models.CASCADE,
        related_name='assessments'
    )
    name = _dj_models.CharField(
        max_length=300,
        help_text='e.g. ISO 27001 Readiness Assessment Q4 2026'
    )
    description = _dj_models.TextField(blank=True)
    status = _dj_models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='draft'
    )
    assessor = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='compliance_assessments'
    )
    owner_dept = _dj_models.ForeignKey(
        Department, on_delete=_dj_models.PROTECT,
        related_name='compliance_assessments'
    )
    assessment_date = _dj_models.DateField(
        help_text='When this assessment started'
    )
    target_completion_date = _dj_models.DateField(null=True, blank=True)
    completed_date = _dj_models.DateField(null=True, blank=True)
    notes = _dj_models.TextField(blank=True)

    created_at = _dj_models.DateTimeField(auto_now_add=True)
    updated_at = _dj_models.DateTimeField(auto_now=True)
    created_by = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='created_assessments', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='updated_assessments', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = _HR()

    class Meta:
        ordering = ['-assessment_date']
        verbose_name = 'Compliance assessment'
        verbose_name_plural = 'Compliance assessments'

    def __str__(self):
        return f"{self.assessment_id or 'NEW'} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.assessment_id:
            last = ComplianceAssessment.objects.exclude(assessment_id__isnull=True).exclude(assessment_id='').order_by('-id').first()
            next_num = 1
            if last and last.assessment_id:
                try:
                    next_num = int(last.assessment_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = ComplianceAssessment.objects.count() + 1
            while ComplianceAssessment.objects.filter(assessment_id=f'CMP-{next_num:04d}').exists():
                next_num += 1
            self.assessment_id = f'CMP-{next_num:04d}'
        super().save(*args, **kwargs)

    # ---------- Computed stats ----------
    @property
    def total_items(self):
        return self.items.count()

    @property
    def compliant_count(self):
        return self.items.filter(status='compliant').count()

    @property
    def partial_count(self):
        return self.items.filter(status='partial').count()

    @property
    def non_compliant_count(self):
        return self.items.filter(status='non_compliant').count()

    @property
    def na_count(self):
        return self.items.filter(status='na').count()

    @property
    def not_assessed_count(self):
        return self.items.filter(status='not_assessed').count()

    @property
    def readiness_percent(self):
        """Compliant + partial (weighted 0.5) / total applicable.

        Returns ``None`` when every requirement is marked N/A so templates can
        display ``N/A`` rather than a misleading ``100%``.
        """
        total = self.total_items
        if not total:
            return 0
        na = self.na_count
        applicable = total - na
        if not applicable:
            return None
        weighted = self.compliant_count + (self.partial_count * 0.5)
        return round((weighted / applicable) * 100)

    @property
    def status_color(self):
        return {
            'draft': '#6B7280',
            'in_progress': '#0284C7',
            'under_review': '#D97706',
            'completed': '#059669',
            'archived': '#374151',
        }.get(self.status, '#6B7280')


class ComplianceAssessmentItem(_dj_models.Model):
    """
    One checklist line — a single FrameworkControl being assessed.
    """
    STATUS_CHOICES = [
        ('not_assessed',  'Not Assessed'),
        ('compliant',     'Compliant'),
        ('partial',       'Partially Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('na',            'Not Applicable'),
    ]

    assessment = _dj_models.ForeignKey(
        ComplianceAssessment, on_delete=_dj_models.CASCADE,
        related_name='items'
    )
    framework_control = _dj_models.ForeignKey(
        'frameworks.FrameworkControl', on_delete=_dj_models.CASCADE,
        related_name='assessment_items'
    )
    status = _dj_models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='not_assessed'
    )
    notes = _dj_models.TextField(blank=True)
    owner_user = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='compliance_items'
    )
    evidence = _dj_models.ManyToManyField(
        'audits.EvidenceItem', blank=True,
        related_name='compliance_items',
        help_text='Evidence supporting this assessment decision'
    )
    target_remediation_date = _dj_models.DateField(
        null=True, blank=True,
        help_text='If not compliant, when will this be addressed?'
    )

    created_at = _dj_models.DateTimeField(auto_now_add=True)
    updated_at = _dj_models.DateTimeField(auto_now=True)
    created_by = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='created_assessment_items', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = _dj_models.ForeignKey(
        'core.User', on_delete=_dj_models.SET_NULL, null=True, blank=True,
        related_name='updated_assessment_items', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = _HR()

    class Meta:
        unique_together = ('assessment', 'framework_control')
        ordering = ['framework_control__code']
        verbose_name = 'Compliance assessment item'
        verbose_name_plural = 'Compliance assessment items'

    def __str__(self):
        return f"{self.assessment.assessment_id} — {self.framework_control.code}"

    @property
    def status_color(self):
        return {
            'not_assessed':  '#6B7280',
            'compliant':     '#059669',
            'partial':       '#D97706',
            'non_compliant': '#DC2626',
            'na':            '#94A3B8',
        }.get(self.status, '#6B7280')
