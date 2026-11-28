from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department
from core.sla import SLA_DAYS as SLA_LADDER


class Vulnerability(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high',     'High'),
        ('medium',   'Medium'),
        ('low',      'Low'),
        ('none',     'None'),
    ]
    SOURCE_CHOICES = [
        ('manual',        'Manual Entry'),
        ('nvd',           'NVD API'),
        ('cisa',          'CISA Feed'),
        ('circl',         'CIRCL Feed'),
        ('threatcluster', 'ThreatCluster'),
    ]

    cve_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    cvss_score = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    cvss_vector = models.CharField(max_length=200, blank=True)
    cvss_severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, default='medium'
    )
    epss_score = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    epss_percentile = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    kev_status = models.BooleanField(default=False, verbose_name='In CISA KEV')
    kev_due_date = models.DateField(null=True, blank=True)
    published_date = models.DateField(null=True, blank=True)
    references = models.TextField(blank=True)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='manual',
        help_text='Where this CVE record came from'
    )
    last_enriched = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_vulnerabilities', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_vulnerabilities', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-cvss_score', 'cve_id']
        verbose_name_plural = 'Vulnerabilities'
        constraints = [
            models.CheckConstraint(
                check=models.Q(cvss_score__gte=0, cvss_score__lte=10),
                name='vulnerability_cvss_between_0_and_10',
            ),
        ]

    def __str__(self):
        return self.cve_id or self.title[:60]

    @property
    def is_actively_exploited(self):
        return self.kev_status or (self.epss_score and self.epss_score >= 0.5)

    @property
    def cve_url(self):
        if not self.cve_id:
            return None
        return f'https://www.cve.org/CVERecord?id={self.cve_id}'

    @property
    def nvd_url(self):
        if not self.cve_id:
            return None
        return f'https://nvd.nist.gov/vuln/detail/{self.cve_id}'

    @property
    def mitre_url(self):
        if not self.cve_id:
            return None
        return f'https://cve.mitre.org/cgi-bin/cvename.cgi?name={self.cve_id}'


class Finding(models.Model):
    """
    A vulnerability instance on an asset — either auto-discovered via CVE feed
    or manually logged by an analyst.
    """
    STATUS_CHOICES = [
        ('new',                  'New'),
        ('triaged',              'Triaged'),
        ('in_progress',          'In Progress'),
        ('pending_verification', 'Pending Verification'),
        ('remediated',           'Remediated'),
        ('accepted',             'Risk Accepted'),
        ('false_positive',       'False Positive'),
    ]
    CLOSED_STATUSES = ('remediated', 'accepted', 'false_positive')

    # Shared with audit findings and tickets: 7/14/30/60/90 by severity.
    SLA_DAYS = SLA_LADDER

    vulnerability = models.ForeignKey(
        Vulnerability, on_delete=models.CASCADE, related_name='findings'
    )
    asset = models.ForeignKey(
        'assets.Asset', on_delete=models.CASCADE, related_name='findings'
    )
    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='findings'
    )

    port = models.CharField(max_length=20, blank=True)
    evidence = models.TextField(blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    discovered_date = models.DateField()
    remediated_date = models.DateField(null=True, blank=True)
    verified_date = models.DateField(null=True, blank=True)

    # Assignment
    assigned_to = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_findings',
        verbose_name='Assigned user'
    )
    assigned_team = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_findings',
        verbose_name='Assigned team'
    )

    # SLA
    sla_due_date = models.DateField(
        null=True, blank=True,
        help_text='Target remediation date. Auto-computed from severity if left blank.'
    )

    # Solution / remediation
    solution = models.TextField(
        blank=True, help_text='Recommended fix or solution'
    )
    remediation_notes = models.TextField(blank=True)

    composite_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_findings', editable=False,
        help_text='User who created this record (auto-set).'
    )
    updated_by = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='updated_findings', editable=False,
        help_text='User who last updated this record (auto-set).'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-composite_score', '-discovered_date']
        unique_together = ('vulnerability', 'asset', 'port')
        constraints = [
            models.CheckConstraint(
                check=models.Q(composite_score__gte=0, composite_score__lte=100),
                name='finding_composite_between_0_and_100',
            ),
        ]

    def __str__(self):
        return f"{self.vulnerability} on {self.asset.name}"

    def save(self, *args, **kwargs):
        if self.asset_id and not self.owner_dept_id:
            self.owner_dept = self.asset.owner_dept

        # Auto-compute SLA if not set
        if not self.sla_due_date and self.discovered_date:
            from datetime import timedelta
            sev = (self.vulnerability.cvss_severity if self.vulnerability_id else 'medium') or 'medium'
            days = self.SLA_DAYS.get(sev, 90)
            self.sla_due_date = self.discovered_date + timedelta(days=days)

        # Auto-set dates when status transitions
        from django.utils import timezone
        today = timezone.localdate()
        if self.status == 'remediated' and not self.remediated_date:
            self.remediated_date = today
        if self.status == 'remediated' and not self.verified_date:
            self.verified_date = today

        self.composite_score = compute_composite_score(self)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        if self.status in self.CLOSED_STATUSES:
            return False
        if not self.sla_due_date:
            return False
        from django.utils import timezone
        return self.sla_due_date < timezone.localdate()

    @property
    def is_due_soon(self):
        if self.status in self.CLOSED_STATUSES:
            return False
        if not self.sla_due_date:
            return False
        from django.utils import timezone
        days_left = (self.sla_due_date - timezone.localdate()).days
        return 0 <= days_left <= 3

    @property
    def days_until_due(self):
        if not self.sla_due_date:
            return None
        from django.utils import timezone
        return (self.sla_due_date - timezone.localdate()).days

    @property
    def sla_breached(self):
        """The severity SLA date has passed and the finding is still open."""
        return self.is_overdue

    @property
    def status_color(self):
        return {
            'new':                  '#DC2626',
            'triaged':              '#D97706',
            'in_progress':          '#0284C7',
            'pending_verification': '#7C3AED',
            'remediated':           '#059669',
            'accepted':             '#6B7280',
            'false_positive':       '#94A3B8',
        }.get(self.status, '#6B7280')

    @property
    def severity_color(self):
        if not self.vulnerability_id:
            return '#6B7280'
        return {
            'critical': '#DC2626',
            'high':     '#EA580C',
            'medium':   '#D97706',
            'low':      '#059669',
            'none':     '#94A3B8',
        }.get(self.vulnerability.cvss_severity, '#6B7280')


def composite_score_breakdown(finding):
    """Return the weighted component breakdown behind ``compute_composite_score``."""
    if not finding.vulnerability_id or not finding.asset_id:
        return {
            'cvss': 0.0, 'severity_pts': 0.0,
            'asset_crit': 0, 'asset_pts': 0.0,
            'epss': 0.0, 'kev': False, 'threat_pts': 0.0,
            'total': 0.0,
        }

    cvss = float(finding.vulnerability.cvss_score or 0)
    severity = max(0.0, min(1.0, cvss / 10.0))

    crit_map = {1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}
    asset_crit = finding.asset.criticality
    asset_factor = crit_map.get(asset_crit, 0.5)

    epss = float(finding.vulnerability.epss_score or 0)
    kev = bool(finding.vulnerability.kev_status)
    threat = epss + (0.5 if kev else 0.0)
    threat = max(0.0, min(1.0, threat))

    severity_pts = round(55.0 * severity, 2)
    asset_pts = round(30.0 * asset_factor, 2)
    threat_pts = round(15.0 * threat, 2)
    return {
        'cvss': round(cvss, 1),
        'severity_pts': severity_pts,
        'asset_crit': asset_crit,
        'asset_pts': asset_pts,
        'epss': round(epss * 100.0, 1),
        'kev': kev,
        'threat_pts': threat_pts,
        'total': round(severity_pts + asset_pts + threat_pts, 2),
    }


def compute_composite_score(finding):
    """Blend CVSS, asset criticality and threat intel into a 0–100 score.

    The old version multiplied an already-0–100 base (CVSS × 10) by up to
    ×3.0 of amplifiers and then clamped at 100, so any half-serious finding
    saturated at exactly 100 and could no longer be ranked. This weighted
    model is bounded by construction and every input is normalised to 0–1
    before weighting:

        composite = 100 × (0.55·severity + 0.30·asset + 0.15·threat)

      * severity = CVSS / 10
      * asset    = asset criticality, mapped 1→0.25 … 4→1.0
      * threat   = EPSS (0–1), +0.5 if the CVE is on the KEV list, capped at 1
    """
    if not finding.vulnerability_id or not finding.asset_id:
        return 0.0

    cvss = float(finding.vulnerability.cvss_score or 0)
    severity = max(0.0, min(1.0, cvss / 10.0))

    crit_map = {1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}
    asset_factor = crit_map.get(finding.asset.criticality, 0.5)

    threat = float(finding.vulnerability.epss_score or 0)
    if finding.vulnerability.kev_status:
        threat += 0.5
    threat = max(0.0, min(1.0, threat))

    score = 100.0 * (0.55 * severity + 0.30 * asset_factor + 0.15 * threat)
    return round(score, 2)
