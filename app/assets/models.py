from django.db import models
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

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name='assets'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='assets'
    )
    criticality = models.PositiveSmallIntegerField(
        choices=CRITICALITY_CHOICES, default=2
    )
    confidentiality = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    integrity = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    availability = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    value = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Estimated monetary value (for risk quantification)'
    )
    is_active = models.BooleanField(default=True)
    policies = models.ManyToManyField(
        'policies.Policy', blank=True, related_name='assets',
        help_text='Policies that govern this asset specifically'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def cia_score(self):
        return round((self.confidentiality + self.integrity + self.availability) / 3, 2)