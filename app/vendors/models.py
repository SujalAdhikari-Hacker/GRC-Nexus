from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from core.models import Department


class Vendor(models.Model):
    TIER_CHOICES = [
        (1, 'Tier 1 — Critical'),
        (2, 'Tier 2 — Important'),
        (3, 'Tier 3 — Standard'),
    ]
    SENSITIVITY_CHOICES = [
        (1, 'Public'),
        (2, 'Internal'),
        (3, 'Confidential'),
        (4, 'Restricted'),
    ]
    SERVICE_CHOICES = [
        ('cloud', 'Cloud Hosting / Infrastructure'),
        ('saas', 'Software / SaaS'),
        ('managed', 'Managed Services'),
        ('consulting', 'Consulting / Professional Services'),
        ('audit', 'Auditing / Compliance'),
        ('payments', 'Payment Processing'),
        ('hardware', 'Hardware / Equipment'),
        ('logistics', 'Logistics / Facilities'),
        ('staffing', 'Staffing / Recruiting'),
        ('marketing', 'Marketing / Communications'),
        ('legal', 'Legal Services'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('onboarding', 'Onboarding'),
        ('active', 'Active'),
        ('under_review', 'Under Review'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
    ]

    vendor_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like VEN-0001.'
    )
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    service = models.CharField(
        max_length=20, choices=SERVICE_CHOICES, default='saas'
    )
    tier = models.PositiveSmallIntegerField(
        choices=TIER_CHOICES, default=3,
        verbose_name='Criticality',
        help_text='Tier 1 = Critical · Tier 2 = Important · Tier 3 = Standard'
    )
    data_sensitivity = models.PositiveSmallIntegerField(
        choices=SENSITIVITY_CHOICES, default=2
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='active'
    )

    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='vendors'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_vendors'
    )

    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)

    contract_start = models.DateField(null=True, blank=True)
    contract_renewal_date = models.DateField(null=True, blank=True)

    compliance_attestations = models.ManyToManyField(
        'frameworks.Framework', blank=True, related_name='attesting_vendors',
        help_text='Frameworks this vendor has attested compliance to'
    )
    compliance_notes = models.TextField(
        blank=True,
        help_text='Details about the attestation, certificates, expiry dates, etc.'
    )
    notes = models.TextField(
        blank=True, help_text='General notes about this vendor'
    )

    provides_assets = models.ManyToManyField(
        'assets.Asset', blank=True, related_name='vendors'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='vendors_created',
        help_text='Who created this vendor record'
    )
    updated_by = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='vendors_updated',
        help_text='Who last modified this vendor record'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['vendor_id']
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'

    def __str__(self):
        return f"{self.vendor_id or 'NEW'} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.vendor_id:
            last = Vendor.objects.exclude(vendor_id__isnull=True).exclude(vendor_id='').order_by('-id').first()
            next_num = 1
            if last and last.vendor_id:
                try:
                    next_num = int(last.vendor_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = Vendor.objects.count() + 1
            while Vendor.objects.filter(vendor_id=f'VEN-{next_num:04d}').exists():
                next_num += 1
            self.vendor_id = f'VEN-{next_num:04d}'
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if not self.name or len(self.name.strip()) < 3:
            errors['name'] = 'Vendor name must be at least 3 characters.'
        if not self.contact_name and not self.contact_email:
            errors['contact_email'] = 'Provide at least a contact name or email.'
        if errors:
            raise ValidationError(errors)

    @property
    def latest_score(self):
        latest = self.assessments.order_by('-assessment_date').first()
        return latest.overall_score if latest else None

    @property
    def latest_assessment(self):
        return self.assessments.order_by('-assessment_date').first()


class VendorAssessment(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('in_review', 'In Review'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
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

    vendor_tier = models.PositiveSmallIntegerField(
        choices=Vendor.TIER_CHOICES, default=3,
        help_text='Auto-filled from vendor. Snapshot at assessment time.'
    )

    # 5 risk dimensions, each 0-25
    security_score = models.PositiveSmallIntegerField(
        default=0, help_text='0-25. Security posture risk.'
    )
    compliance_score = models.PositiveSmallIntegerField(
        default=0, help_text='0-25. Regulatory / standard adherence risk.'
    )
    financial_score = models.PositiveSmallIntegerField(
        default=0, help_text='0-25. Financial stability risk.'
    )
    reputation_score = models.PositiveSmallIntegerField(
        default=0, help_text='0-25. Reputation and brand impact risk.'
    )
    operational_score = models.PositiveSmallIntegerField(
        default=0, help_text='0-25. Service delivery / operational risk.'
    )

    # Auto-computed
    overall_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, editable=False,
        help_text='Total score 0-100 — sum of the 5 dimensions.'
    )
    overall_risk_rating = models.CharField(
        max_length=20, choices=OVERALL_RATING_CHOICES, default='low', editable=False
    )

    recommended_mitigation = models.TextField(blank=True)
    key_findings = models.TextField(blank=True)

    assessment_date = models.DateField()
    next_assessment_date = models.DateField(null=True, blank=True)
    assessor = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendor_assessments'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')

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
        if not self.assessment_id:
            last = VendorAssessment.objects.exclude(assessment_id__isnull=True).exclude(assessment_id='').order_by('-id').first()
            next_num = 1
            if last and last.assessment_id:
                try:
                    next_num = int(last.assessment_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = VendorAssessment.objects.count() + 1
            while VendorAssessment.objects.filter(assessment_id=f'VRA-{next_num:04d}').exists():
                next_num += 1
            self.assessment_id = f'VRA-{next_num:04d}'

        # Snapshot the vendor's tier at assessment time (only when the
        # assessment is first created — edits must not rewrite history).
        if self.vendor_id and not self.pk:
            self.vendor_tier = self.vendor.tier

        # Clamp each dimension to 0-25
        for f in ['security_score', 'compliance_score', 'financial_score', 'reputation_score', 'operational_score']:
            val = getattr(self, f) or 0
            if val < 0:
                val = 0
            if val > 25:
                val = 25
            setattr(self, f, val)

        # Total = sum of 5 dimensions (0-100)
        total = (
            self.security_score + self.compliance_score + self.financial_score
            + self.reputation_score + self.operational_score
        )
        self.overall_score = total

        # Rating bands
        if total >= 76:
            self.overall_risk_rating = 'critical'
        elif total >= 51:
            self.overall_risk_rating = 'high'
        elif total >= 26:
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
        for f in ['security_score', 'compliance_score', 'financial_score', 'reputation_score', 'operational_score']:
            val = getattr(self, f) or 0
            if val < 0 or val > 25:
                errors[f] = 'Each dimension must be between 0 and 25.'
        if errors:
            raise ValidationError(errors)

    @property
    def risk_rating_color(self):
        return {
            'low': '#059669', 'medium': '#D97706',
            'high': '#EA580C', 'critical': '#DC2626',
        }.get(self.overall_risk_rating, '#6B7280')

    @property
    def risk_rating_percent(self):
        """Total score as percent (0-100)."""
        return int(self.overall_score or 0)
