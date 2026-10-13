from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from risks.models import Risk, RiskAppetite


class KRI(models.Model):
    """
    Key Risk Indicator — monitors leading/lagging signals against
    risk appetite and tolerance thresholds. RAG status computed from value
    vs amber/red thresholds.
    """

    CATEGORY_CHOICES = [
        ('cybersecurity', 'Cybersecurity'),
        ('operational',   'Operational'),
        ('financial',     'Financial'),
        ('compliance',    'Compliance'),
        ('third_party',   'Third Party'),
        ('people',        'People'),
        ('technology',    'Technology'),
    ]
    TYPE_CHOICES = [
        ('leading',  'Leading'),
        ('lagging',  'Lagging'),
    ]
    DIRECTION_CHOICES = [
        ('higher_worse',  'Higher is worse'),
        ('higher_better', 'Higher is better'),
    ]
    FREQUENCY_CHOICES = [
        ('daily',     'Daily'),
        ('weekly',    'Weekly'),
        ('monthly',   'Monthly'),
        ('quarterly', 'Quarterly'),
    ]
    TREND_CHOICES = [
        ('stable',     'Stable'),
        ('increasing', 'Increasing'),
        ('decreasing', 'Decreasing'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='cybersecurity')
    kri_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='leading')

    current_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit = models.CharField(
        max_length=30, blank=True,
        help_text='e.g. %, days, count, incidents'
    )

    direction = models.CharField(
        max_length=20, choices=DIRECTION_CHOICES, default='higher_worse',
        help_text='Whether higher values are worse or better'
    )
    amber_threshold = models.DecimalField(max_digits=12, decimal_places=2)
    red_threshold = models.DecimalField(max_digits=12, decimal_places=2)

    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    trend = models.CharField(max_length=20, choices=TREND_CHOICES, default='stable')

    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_kris'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='kris'
    )

    linked_risks = models.ManyToManyField(
        Risk, blank=True, related_name='kris',
        help_text='Risks this indicator monitors'
    )
    linked_appetites = models.ManyToManyField(
        RiskAppetite, blank=True, related_name='kris',
        help_text='Appetite statements this indicator relates to'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_kris', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_kris', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['category', 'name']
        verbose_name = 'Key Risk Indicator'
        verbose_name_plural = 'Key Risk Indicators'

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    @property
    def rag_status(self):
        """
        Green = within appetite
        Amber = approaching tolerance
        Red = tolerance breached
        """
        v = float(self.current_value)
        amber = float(self.amber_threshold)
        red = float(self.red_threshold)

        if self.direction == 'higher_worse':
            # value climbing is bad
            if v >= red:
                return 'red'
            if v >= amber:
                return 'amber'
            return 'green'
        else:
            # higher_better: value dropping is bad
            # red_threshold is lower bound, amber_threshold is upper bound
            if v <= red:
                return 'red'
            if v <= amber:
                return 'amber'
            return 'green'

    @property
    def rag_label(self):
        return {'green': 'Within appetite', 'amber': 'Approaching tolerance', 'red': 'Tolerance breached'}[self.rag_status]

    @property
    def rag_color(self):
        return {'green': '#059669', 'amber': '#D97706', 'red': '#DC2626'}[self.rag_status]

    @property
    def rag_percent(self):
        """0-100 scale position of current value between thresholds."""
        v = float(self.current_value)
        amber = float(self.amber_threshold)
        red = float(self.red_threshold)
        if amber == red:
            return 0
        if self.direction == 'higher_worse':
            pct = ((v - amber) / (red - amber)) * 100 if red > amber else 0
        else:
            pct = ((amber - v) / (amber - red)) * 100 if amber > red else 0
        return max(0, min(100, round(pct)))

    @property
    def latest_reading(self):
        return self.readings.order_by('-reading_date').first()


class KRIReading(models.Model):
    """Historical value of a KRI at a point in time."""
    kri = models.ForeignKey(KRI, on_delete=models.CASCADE, related_name='readings')
    reading_date = models.DateField()
    value = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kri_readings'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-reading_date']

    def __str__(self):
        return f"{self.kri.name} @ {self.reading_date}: {self.value}"
