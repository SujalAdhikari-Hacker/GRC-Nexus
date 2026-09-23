from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from assets.models import Asset
from controls.models import Control


class RiskCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Risk categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class RiskAppetite(models.Model):
    category = models.ForeignKey(
        RiskCategory, on_delete=models.CASCADE, related_name='appetites',
        null=True, blank=True
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name='appetites',
        null=True, blank=True
    )
    max_inherent_score = models.PositiveSmallIntegerField(default=15)
    max_residual_score = models.PositiveSmallIntegerField(default=8)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Risk appetites'
        ordering = ['department', 'category']

    def __str__(self):
        scope = self.department.name if self.department else 'Org-wide'
        cat = self.category.name if self.category else 'all categories'
        return f"{scope} / {cat}"


class Risk(models.Model):
    STATUS_CHOICES = [
        ('identified', 'Identified'),
        ('assessed',   'Assessed'),
        ('treating',   'Treating'),
        ('monitored',  'Monitored'),
        ('closed',     'Closed'),
    ]
    TREATMENT_CHOICES = [
        ('accept',   'Accept'),
        ('mitigate', 'Mitigate'),
        ('transfer', 'Transfer'),
        ('avoid',    'Avoid'),
    ]
    LIKELIHOOD_CHOICES = [(i, str(i)) for i in range(1, 6)]
    IMPACT_CHOICES = [(i, str(i)) for i in range(1, 6)]

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        RiskCategory, on_delete=models.PROTECT, related_name='risks'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='risks'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_risks'
    )
    likelihood = models.PositiveSmallIntegerField(choices=LIKELIHOOD_CHOICES, default=3)
    impact = models.PositiveSmallIntegerField(choices=IMPACT_CHOICES, default=3)
    inherent_score = models.PositiveSmallIntegerField(default=0, editable=False)
    residual_score = models.PositiveSmallIntegerField(default=0, editable=False)
    appetite_breached = models.BooleanField(default=False, editable=False)
    treatment_strategy = models.CharField(
        max_length=20, choices=TREATMENT_CHOICES, default='mitigate'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='identified')
    assets = models.ManyToManyField(Asset, blank=True, related_name='risks')
    controls = models.ManyToManyField(Control, blank=True, related_name='risks')
    identified_date = models.DateField(null=True, blank=True)
    target_close_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-inherent_score', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.inherent_score = self.likelihood * self.impact
        super().save(*args, **kwargs)


class RiskTreatment(models.Model):
    STATUS_CHOICES = [
        ('planned',     'Planned'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name='treatments')
    action_plan = models.TextField()
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='treatments'
    )
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"Treatment for {self.risk.title}"