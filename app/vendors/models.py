from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from core.models import Department


class Vendor(models.Model):
    TIER_CHOICES = [
        (1, 'Tier 1 - Critical'),
        (2, 'Tier 2 - Important'),
        (3, 'Tier 3 - Standard'),
    ]
    SENSITIVITY_CHOICES = [
        (1, 'Public'),
        (2, 'Internal'),
        (3, 'Confidential'),
        (4, 'Restricted'),
    ]
    CRITICALITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
    ]

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES, default=3)
    vendor_criticality = models.PositiveSmallIntegerField(
        choices=CRITICALITY_CHOICES, default=2,
        help_text='Overall criticality of this vendor to the organization'
    )
    data_sensitivity = models.PositiveSmallIntegerField(
        choices=SENSITIVITY_CHOICES, default=2
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='vendors'
    )
    provides_assets = models.ManyToManyField(
        'assets.Asset', blank=True, related_name='vendors'
    )
    contract_start = models.DateField(null=True, blank=True)
    contract_end = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def latest_score(self):
        latest = self.assessments.order_by('-assessment_date').first()
        return latest.overall_score if latest else None

    @property
    def latest_assessment(self):
        return self.assessments.order_by('-assessment_date').first()


class VendorAssessment(models.Model):
    """
    Vendor risk assessment across 5 dimensions.
    Each dimension scored 1-5 (1=Low risk, 5=Critical risk).
    Overall = average, mapped to a rating.
    """
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('in_review', 'In Review'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
    ]
    RISK_LEVEL_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
        (5, 'Very Critical'),
    ]
    OVERALL_RATING_CHOICES = [
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]

    assessment_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like VRA-0001.'
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name='assessments'
    )

    # Vendor's criticality snapshot at assessment time (auto-filled from vendor)
    vendor_criticality = models.PositiveSmallIntegerField(
        choices=Vendor.CRITICALITY_CHOICES, default=2,
        help_text='Auto-filled from vendor record'
    )

    # Five risk dimensions, each scored 1-5
    financial_risk = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=1,
        help_text='Financial stability and exposure'
    )
    operational_risk = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=1,
        help_text='Service delivery and operational dependency'
    )
    regulatory_risk = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=1,
        help_text='Regulatory and compliance exposure'
    )
    cybersecurity_risk = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=1,
        help_text='Information security and data protection posture'
    )
    reputational_risk = models.PositiveSmallIntegerField(
        choices=RISK_LEVEL_CHOICES, default=1,
        help_text='Impact on organizational reputation'
    )

    # Auto-computed
    overall_score = models.DecimalField(
        max_digits=4, decimal_places=2, default=0, editable=False,
        help_text='Average of the 5 risk dimensions (1.00 to 5.00)'
    )
    overall_risk_rating = models.CharField(
        max_length=20, choices=OVERALL_RATING_CHOICES, default='low',
        editable=False
    )

    recommended_mitigation = models.TextField(
        blank=True, help_text='Recommended actions to reduce vendor risk'
    )
    key_findings = models.TextField(
        blank=True, help_text='Key findings from the assessment'
    )

    assessment_date = models.DateField()
    next_assessment_date = models.DateField(
        null=True, blank=True,
        help_text='When this vendor should be re-assessed'
    )
    assessor = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendor_assessments'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='completed'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-assessment_date']
        verbose_name = 'Vendor assessment'
        verbose_name_plural = 'Vendor assessments'

    def __str__(self):
        return f"{self.assessment_id or 'NEW'} — {self.vendor.name}"

    def save(self, *args, **kwargs):
        # Auto-generate assessment ID using a race-safe max lookup
        if not self.assessment_id:
            last = (
                VendorAssessment.objects
                .exclude(assessment_id__isnull=True)
                .exclude(assessment_id='')
                .order_by('-id')
                .first()
            )
            next_num = 1
            if last and last.assessment_id:
                try:
                    next_num = int(last.assessment_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = VendorAssessment.objects.count() + 1

            # Ensure uniqueness even if the counter guesses wrong
            while VendorAssessment.objects.filter(assessment_id=f'VRA-{next_num:04d}').exists():
                next_num += 1

            self.assessment_id = f'VRA-{next_num:04d}'

        # Auto-fill vendor criticality from vendor if not set
        if self.vendor_id and not self.vendor_criticality:
            self.vendor_criticality = self.vendor.vendor_criticality

        # Compute overall score (average of 5 dimensions)
        dimensions = [
            self.financial_risk,
            self.operational_risk,
            self.regulatory_risk,
            self.cybersecurity_risk,
            self.reputational_risk,
        ]
        self.overall_score = round(sum(dimensions) / len(dimensions), 2)

        s = float(self.overall_score)
        if s >= 4.5:
            self.overall_risk_rating = 'critical'
        elif s >= 3.5:
            self.overall_risk_rating = 'high'
        elif s >= 2.5:
            self.overall_risk_rating = 'medium'
        else:
            self.overall_risk_rating = 'low'

        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if not self.recommended_mitigation or len(self.recommended_mitigation.strip()) < 20:
            errors['recommended_mitigation'] = 'Recommended mitigation must be at least 20 characters.'
        if not self.key_findings or len(self.key_findings.strip()) < 20:
            errors['key_findings'] = 'Key findings must be at least 20 characters.'
        if errors:
            raise ValidationError(errors)

    @property
    def risk_rating_color(self):
        return {
            'low': '#059669',
            'medium': '#D97706',
            'high': '#EA580C',
            'critical': '#DC2626',
        }.get(self.overall_risk_rating, '#6B7280')
