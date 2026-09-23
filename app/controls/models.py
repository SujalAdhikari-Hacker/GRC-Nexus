from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from frameworks.models import FrameworkControl


class Control(models.Model):
    TYPE_CHOICES = [
        ('preventive', 'Preventive'),
        ('detective',  'Detective'),
        ('corrective', 'Corrective'),
    ]
    CATEGORY_CHOICES = [
        ('technical',      'Technical'),
        ('administrative', 'Administrative'),
        ('physical',       'Physical'),
    ]
    STATUS_CHOICES = [
        ('planned',         'Planned'),
        ('implemented',     'Implemented'),
        ('not_implemented', 'Not Implemented'),
        ('not_applicable',  'Not Applicable'),
    ]
    EFFECTIVENESS_CHOICES = [
        (0, 'Not Assessed'),
        (1, 'Very Low'),
        (2, 'Low'),
        (3, 'Medium'),
        (4, 'High'),
        (5, 'Very High'),
    ]

    name = models.CharField(max_length=300)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    control_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='preventive')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='technical')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    effectiveness = models.PositiveSmallIntegerField(
        choices=EFFECTIVENESS_CHOICES, default=0
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='controls'
    )
    is_shared = models.BooleanField(default=False)
    implementation_notes = models.TextField(blank=True)
    last_tested = models.DateField(null=True, blank=True)
    next_test_date = models.DateField(null=True, blank=True)
    framework_controls = models.ManyToManyField(
        FrameworkControl, blank=True, related_name='controls'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def effectiveness_ratio(self):
        if self.effectiveness == 0:
            return 0.0
        return self.effectiveness / 5.0


class ControlEvidence(models.Model):
    control = models.ForeignKey(
        Control, on_delete=models.CASCADE, related_name='evidence'
    )
    file = models.FileField(upload_to='control_evidence/')
    description = models.CharField(max_length=300, blank=True)
    uploaded_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_evidence'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = 'Control evidence'

    def __str__(self):
        return f"Evidence for {self.control.code}"