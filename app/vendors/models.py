from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from assets.models import Asset


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

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES, default=3)
    data_sensitivity = models.PositiveSmallIntegerField(
        choices=SENSITIVITY_CHOICES, default=2
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='vendors'
    )
    provides_assets = models.ManyToManyField(
        Asset, blank=True, related_name='vendors'
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
        return latest.score if latest else None


class VendorAssessment(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('in_review', 'In Review'),
        ('completed', 'Completed'),
        ('failed',    'Failed'),
    ]

    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name='assessments'
    )
    assessment_date = models.DateField()
    score = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    findings = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendor_assessments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-assessment_date']

    def __str__(self):
        return f"{self.vendor.name} - {self.assessment_date} ({self.score})"