from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from assets.models import Asset
from controls.models import Control


# ==================================================================
# RISK CATEGORY
# ==================================================================

class RiskCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Risk categories'
        ordering = ['name']

    def __str__(self):
        return self.name


# ==================================================================
# RISK APPETITE
# ==================================================================

class RiskAppetite(models.Model):
    """
    Defines the level of risk the organization is willing to accept.
    Set and approved by the Board.
    """
    APPETITE_LEVEL_CHOICES = [
        ('averse',   'Averse'),
        ('cautious', 'Cautious'),
        ('moderate', 'Moderate'),
        ('open',     'Open'),
        ('hungry',   'Hungry'),
    ]

    category = models.ForeignKey(
        RiskCategory, on_delete=models.CASCADE, related_name='appetites',
        null=True, blank=True,
        help_text='Leave empty for all categories'
    )
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name='appetites',
        null=True, blank=True,
        help_text='Leave empty for org-wide appetite'
    )

    appetite_level = models.CharField(
        max_length=20, choices=APPETITE_LEVEL_CHOICES, default='moderate',
        help_text='Overall willingness to accept risk'
    )
    appetite_statement = models.TextField(
        blank=True,
        help_text='Formal statement of the organization\'s risk appetite'
    )

    max_inherent_score = models.PositiveSmallIntegerField(
        default=15, help_text='Max acceptable inherent score (1-25)'
    )
    max_residual_score = models.PositiveSmallIntegerField(
        default=8, help_text='Max acceptable residual score (1-25) — Risk Tolerance'
    )
    risk_capacity = models.PositiveSmallIntegerField(
        default=20,
        help_text='Maximum risk the organization can absorb before significant failure (1-25)'
    )

    board_approved = models.BooleanField(default=False)
    review_date = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_appetites'
    )

    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = 'Risk appetites'
        ordering = ['department', 'category']

    def __str__(self):
        scope = self.department.name if self.department else 'Org-wide'
        cat = self.category.name if self.category else 'all categories'
        return f"{scope} / {cat}"


# ==================================================================
# RISK
# ==================================================================

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

    # Risk statement format: [Threat] exploits [Vulnerability], causing [Impact] to [Asset]
    threat = models.CharField(
        max_length=300, blank=True,
        help_text='e.g. Ransomware actor'
    )
    vulnerability = models.CharField(
        max_length=300, blank=True,
        help_text='e.g. unpatched file server'
    )
    impact_description = models.TextField(
        blank=True,
        help_text='e.g. loss of production data and 48-hour outage'
    )

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
    escalated = models.BooleanField(
        default=False,
        help_text='Risk exceeds tolerance and has been escalated'
    )
    escalated_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def risk_statement(self):
        """Full risk statement in [Threat] exploits [Vulnerability], causing [Impact] to [Asset] format."""
        if not (self.threat and self.vulnerability and self.impact_description):
            return ''
        asset = self.assets.first()
        asset_name = asset.name if asset else 'organizational assets'
        return f"{self.threat} exploits {self.vulnerability}, causing {self.impact_description} to {asset_name}."


# ==================================================================
# RISK TREATMENT
# ==================================================================

class RiskTreatment(models.Model):
    """
    Defines how each risk is addressed.
    Links to the controls used to reduce the associated risk.
    """
    STATUS_CHOICES = [
        ('planned',     'Planned'),
        ('in_progress', 'In Progress'),
        ('completed',   'Completed'),
        ('cancelled',   'Cancelled'),
    ]
    STRATEGY_CHOICES = [
        ('mitigate', 'Mitigate'),
        ('accept',   'Accept'),
        ('transfer', 'Transfer'),
        ('avoid',    'Avoid'),
    ]

    risk = models.ForeignKey(Risk, on_delete=models.CASCADE, related_name='treatments')
    strategy = models.CharField(
        max_length=20, choices=STRATEGY_CHOICES, default='mitigate'
    )
    action_plan = models.TextField(help_text='Plan / description of the treatment')
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='treatments'
    )
    controls = models.ManyToManyField(
        Control, blank=True, related_name='treatments',
        help_text='Controls that implement this treatment'
    )
    due_date = models.DateField(null=True, blank=True, verbose_name='Target date')
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"Treatment for {self.risk.title}"
class RiskException(models.Model):
    """
    Formal acceptance of a risk, with expiry and approver.
    Used when a risk cannot be mitigated within appetite and is consciously accepted.
    """
    STATUS_CHOICES = [
        ('pending',  'Pending Approval'),
        ('active',   'Active'),
        ('expired',  'Expired'),
        ('revoked',  'Revoked'),
    ]

    exception_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated like EXC-0001.'
    )
    risk = models.ForeignKey(
        Risk, on_delete=models.CASCADE, related_name='exceptions'
    )
    title = models.CharField(
        max_length=300,
        help_text='Short description of what is being excepted'
    )
    justification = models.TextField(
        help_text='Why is this risk being accepted instead of mitigated? (min 30 chars)'
    )

    requested_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requested_exceptions'
    )
    approver = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_exceptions',
        help_text='Who is formally accepting this risk on behalf of the organization'
    )
    approval_date = models.DateField(
        null=True, blank=True,
        help_text='When the exception was approved'
    )
    expiry_date = models.DateField(
        help_text='When this exception expires and the risk must be re-evaluated'
    )
    review_date = models.DateField(
        null=True, blank=True,
        help_text='Optional intermediate review date'
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )

    compensating_controls = models.ManyToManyField(
        'controls.Control', blank=True, related_name='exceptions',
        help_text='Additional controls put in place to compensate'
    )
    conditions = models.TextField(
        blank=True,
        help_text='Any conditions or limitations attached to this exception'
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Risk exception'
        verbose_name_plural = 'Risk exceptions'

    def __str__(self):
        return f"{self.exception_id or 'NEW'} — {self.title[:60]}"

    def save(self, *args, **kwargs):
        if not self.exception_id:
            last = RiskException.objects.exclude(exception_id__isnull=True).exclude(exception_id='').order_by('-id').first()
            next_num = 1
            if last and last.exception_id:
                try:
                    next_num = int(last.exception_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    next_num = RiskException.objects.count() + 1
            while RiskException.objects.filter(exception_id=f'EXC-{next_num:04d}').exists():
                next_num += 1
            self.exception_id = f'EXC-{next_num:04d}'

        # Auto-status transitions based on dates
        from django.utils import timezone
        today = timezone.now().date()
        if self.status == 'active' and self.expiry_date and self.expiry_date < today:
            self.status = 'expired'

        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if not self.title or len(self.title.strip()) < 5:
            errors['title'] = 'Title must be at least 5 characters.'
        if not self.justification or len(self.justification.strip()) < 30:
            errors['justification'] = 'Justification must be at least 30 characters.'
        if not self.expiry_date:
            errors['expiry_date'] = 'Expiry date is required.'
        if errors:
            raise ValidationError(errors)

    @property
    def days_until_expiry(self):
        from django.utils import timezone
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days

    @property
    def is_expired(self):
        d = self.days_until_expiry
        return d is not None and d < 0

    @property
    def is_expiring_soon(self):
        d = self.days_until_expiry
        return d is not None and 0 <= d <= 30

    @property
    def status_color(self):
        return {
            'pending': '#D97706',
            'active': '#059669',
            'expired': '#DC2626',
            'revoked': '#6B7280',
        }.get(self.status, '#6B7280')