from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from frameworks.models import Framework, FrameworkControl


class Control(models.Model):
    """
    Define and manage controls across frameworks.
    Controls should be reusable and mapped across multiple frameworks.
    """
    TYPE_CHOICES = [
        ('preventive', 'Preventive'),
        ('detective',  'Detective'),
        ('corrective', 'Corrective'),
    ]
    CATEGORY_CHOICES = [
        ('access_control',   'Access Control'),
        ('asset_management', 'Asset Management'),
        ('data_protection',  'Data Protection'),
        ('network_security', 'Network Security'),
        ('incident_mgmt',    'Incident Mgmt.'),
        ('risk_management',  'Risk Management'),
        ('compliance',       'Compliance'),
        ('logging',          'Logging'),
        ('technical',        'Technical'),
        ('administrative',   'Administrative'),
        ('physical',         'Physical'),
    ]
    STATUS_CHOICES = [
        ('planned',         'Planned'),
        ('implemented',     'Implemented'),
        ('not_implemented', 'Not Implemented'),
        ('not_applicable',  'Not Applicable'),
    ]
    EFFECTIVENESS_RATING_CHOICES = [
        ('not_tested',          'Not Tested'),
        ('ineffective',         'Ineffective'),
        ('partially_effective', 'Partially Effective'),
        ('effective',           'Effective'),
    ]
    FREQUENCY_CHOICES = [
        ('continuous', 'Continuous'),
        ('daily',      'Daily'),
        ('weekly',     'Weekly'),
        ('monthly',    'Monthly'),
        ('quarterly',  'Quarterly'),
        ('annual',     'Annual'),
    ]
    LIFECYCLE_CHOICES = [
        ('proposed',     'Proposed'),
        ('designed',     'Designed'),
        ('implemented',  'Implemented'),
        ('operational',  'Operational'),
        ('monitored',    'Monitored'),
        ('reviewed',     'Reviewed'),
        ('retired',      'Retired'),
    ]

    # Rating → numeric score mapping for calculations
    EFFECTIVENESS_SCORES = {
        'not_tested':          0,
        'ineffective':         1,
        'partially_effective': 3,
        'effective':           5,
    }

    name = models.CharField(max_length=300)
    code = models.CharField(
        max_length=50, unique=True,
        help_text='Control ID, e.g. CTL-AC-001'
    )
    description = models.TextField(blank=True)

    control_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='preventive')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='technical')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    lifecycle_status = models.CharField(
        max_length=20, choices=LIFECYCLE_CHOICES, default='proposed',
        help_text='Lifecycle stage of this control'
    )

    effectiveness_rating = models.CharField(
        max_length=30, choices=EFFECTIVENESS_RATING_CHOICES, default='not_tested'
    )
    # Numeric score derived from effectiveness_rating (kept for calculations)
    effectiveness = models.PositiveSmallIntegerField(
        default=0, editable=False,
        help_text='Derived from effectiveness_rating: 0/1/3/5'
    )

    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, default='continuous'
    )

    primary_framework = models.ForeignKey(
        Framework, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='primary_controls',
        help_text='Main framework this control is designed for'
    )
    reference = models.CharField(
        max_length=200, blank=True,
        help_text='Reference (e.g. internal doc ID, URL)'
    )

    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='controls'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_controls'
    )

    is_shared = models.BooleanField(
        default=False,
        help_text='Org-wide control shared across departments'
    )
    implementation_notes = models.TextField(blank=True)
    last_tested = models.DateField(null=True, blank=True)
    next_test_date = models.DateField(null=True, blank=True)

    framework_controls = models.ManyToManyField(
        FrameworkControl, blank=True, related_name='controls',
        help_text='Framework requirements this control satisfies'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_controls', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_controls', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # Auto-sync numeric effectiveness from rating
        self.effectiveness = self.EFFECTIVENESS_SCORES.get(self.effectiveness_rating, 0)
        super().save(*args, **kwargs)

    @property
    def effectiveness_ratio(self):
        """0.0 to 1.0"""
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


class ControlFrameworkMapping(models.Model):
    """
    Enhanced mapping of a control to a framework requirement, with relationship type.
    Supports: Equal, Subset, Superset, Intersects, Functional Partial.
    """
    RELATIONSHIP_CHOICES = [
        ('equal',              'Equal — Full satisfaction'),
        ('subset',             'Subset — Part of a broader requirement'),
        ('superset',           'Superset — Control exceeds requirement'),
        ('intersects',         'Intersects — Partial overlap'),
        ('functional_partial', 'Functional Partial — Partial functional coverage'),
    ]

    control = models.ForeignKey(
        Control, on_delete=models.CASCADE, related_name='framework_mappings'
    )
    framework_control = models.ForeignKey(
        FrameworkControl, on_delete=models.CASCADE, related_name='control_mappings'
    )
    relationship = models.CharField(
        max_length=30, choices=RELATIONSHIP_CHOICES, default='equal'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = ('control', 'framework_control')
        ordering = ['control', 'framework_control']

    def __str__(self):
        return f"{self.control.code} → {self.framework_control}"
