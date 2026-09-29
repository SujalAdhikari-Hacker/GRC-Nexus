from django.db import models
from django.core.exceptions import ValidationError
from simple_history.models import HistoricalRecords
from core.models import Department


class AssetCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Asset categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Asset(models.Model):
    ASSET_TYPE_CHOICES = [
        ('hardware', 'Hardware'),
        ('software', 'Software'),
        ('data', 'Data'),
        ('network', 'Network'),
        ('people', 'People'),
        ('facility', 'Facility'),
        ('service', 'Service'),
    ]
    HOSTING_CHOICES = [
        ('on_prem', 'On-Premises'),
        ('cloud', 'Cloud'),
        ('hybrid', 'Hybrid'),
        ('third_party', 'Third-Party Hosted'),
    ]
    CLASSIFICATION_CHOICES = [
        ('public', 'Public'),
        ('internal', 'Internal'),
        ('confidential', 'Confidential'),
        ('restricted', 'Restricted'),
    ]
    ENVIRONMENT_CHOICES = [
        ('production', 'Production'),
        ('staging', 'Staging'),
        ('development', 'Development'),
        ('test', 'Test'),
        ('dr', 'Disaster Recovery'),
    ]
    CRITICALITY_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Critical'),
    ]
    CIA_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
    ]

    asset_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='...'
    )
    name = models.CharField(max_length=200)
    asset_type = models.CharField(
        max_length=20, choices=ASSET_TYPE_CHOICES, default='hardware'
    )
    hosting = models.CharField(
        max_length=20, choices=HOSTING_CHOICES, default='on_prem'
    )
    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assets'
    )
    classification = models.CharField(
        max_length=20, choices=CLASSIFICATION_CHOICES, default='internal'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='assets'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_assets'
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENT_CHOICES, default='production'
    )
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name='assets',
        null=True, blank=True
    )

    criticality = models.PositiveSmallIntegerField(
        choices=CRITICALITY_CHOICES, default=2
    )
    confidentiality = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    integrity = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    availability = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    is_active = models.BooleanField(default=True)
    policies = models.ManyToManyField(
        'policies.Policy', blank=True, related_name='assets'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['asset_id']

    def __str__(self):
        return f"{self.asset_id or 'NO-ID'} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_id:
            last = Asset.objects.exclude(asset_id__isnull=True).exclude(asset_id='').order_by('-id').first()
            if last and last.asset_id:
                try:
                    num = int(last.asset_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    num = Asset.objects.count() + 1
            else:
                num = Asset.objects.count() + 1
            self.asset_id = f'AST-{num:04d}'
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if not self.name or len(self.name.strip()) < 3:
            errors['name'] = 'Asset name must be at least 3 characters.'
        if not self.description or len(self.description.strip()) < 20:
            errors['description'] = 'Description must be at least 20 characters.'
        if errors:
            raise ValidationError(errors)

    @property
    def cia_score(self):
        return round((self.confidentiality + self.integrity + self.availability) / 3, 2)

    @property
    def display_label(self):
        return f"{self.asset_id or 'NO-ID'} - {self.name[:40]}"
