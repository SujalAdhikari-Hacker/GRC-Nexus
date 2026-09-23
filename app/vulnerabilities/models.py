from django.db import models
from simple_history.models import HistoricalRecords
from core.models import Department


class Vulnerability(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high',     'High'),
        ('medium',   'Medium'),
        ('low',      'Low'),
        ('none',     'None'),
    ]

    cve_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    cvss_score = models.DecimalField(max_digits=3, decimal_places=1, default=0)
    cvss_vector = models.CharField(max_length=200, blank=True)
    cvss_severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    epss_score = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    epss_percentile = models.DecimalField(max_digits=6, decimal_places=5, null=True, blank=True)
    kev_status = models.BooleanField(default=False, verbose_name='In CISA KEV')
    kev_due_date = models.DateField(null=True, blank=True)
    published_date = models.DateField(null=True, blank=True)
    references = models.TextField(blank=True)
    last_enriched = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-cvss_score', 'cve_id']
        verbose_name_plural = 'Vulnerabilities'

    def __str__(self):
        return self.cve_id or self.title[:60]

    @property
    def is_actively_exploited(self):
        return self.kev_status or (self.epss_score and self.epss_score >= 0.5)


class Finding(models.Model):
    STATUS_CHOICES = [
        ('open',           'Open'),
        ('in_progress',    'In Progress'),
        ('remediated',     'Remediated'),
        ('accepted',       'Risk Accepted'),
        ('false_positive', 'False Positive'),
    ]

    vulnerability = models.ForeignKey(Vulnerability, on_delete=models.CASCADE, related_name='findings')
    asset = models.ForeignKey('assets.Asset', on_delete=models.CASCADE, related_name='findings')
    owner_dept = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='findings')

    port = models.CharField(max_length=20, blank=True)
    evidence = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    discovered_date = models.DateField()
    remediated_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_findings')

    composite_score = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)

    remediation_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-composite_score', '-discovered_date']
        unique_together = ('vulnerability', 'asset', 'port')

    def __str__(self):
        return f"{self.vulnerability} on {self.asset.name}"

    def save(self, *args, **kwargs):
        if self.asset_id and not self.owner_dept_id:
            self.owner_dept = self.asset.owner_dept
        self.composite_score = compute_composite_score(self)
        super().save(*args, **kwargs)


def compute_composite_score(finding):
    vuln = finding.vulnerability
    asset = finding.asset
    base = float(vuln.cvss_score or 0) * 10.0
    crit_map = {1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}
    crit_mult = crit_map.get(asset.criticality, 0.5)
    epss = float(vuln.epss_score or 0)
    epss_mult = 1.0 + epss
    kev_mult = 1.5 if vuln.kev_status else 1.0
    score = base * crit_mult * epss_mult * kev_mult
    return round(min(score, 100.0), 2)
