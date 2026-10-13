from django.db import models
from simple_history.models import HistoricalRecords


class Tactic(models.Model):
    """MITRE ATT&CK tactic (e.g. Initial Access, Execution)."""
    attack_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    shortname = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text='Kill chain order')
    url = models.URLField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Tactic'
        verbose_name_plural = 'Tactics'

    def __str__(self):
        return f"{self.attack_id} — {self.name}"


class Technique(models.Model):
    """MITRE ATT&CK technique (e.g. T1059 Command and Scripting Interpreter)."""
    attack_id = models.CharField(max_length=20, unique=True, db_index=True)
    stix_id = models.CharField(max_length=128, blank=True)
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    tactics = models.ManyToManyField(
        Tactic, blank=True, related_name='techniques',
        help_text='Which tactics this technique maps to (via kill_chain_phases)'
    )
    platforms = models.JSONField(default=list, blank=True)
    is_subtechnique = models.BooleanField(default=False)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='subtechniques'
    )
    detection = models.TextField(blank=True)
    url = models.URLField(blank=True)
    deprecated = models.BooleanField(default=False)

    history = HistoricalRecords()

    class Meta:
        ordering = ['attack_id']
        verbose_name = 'Technique'
        verbose_name_plural = 'Techniques'

    def __str__(self):
        return f"{self.attack_id} — {self.name}"


class ThreatActor(models.Model):
    """MITRE ATT&CK intrusion-set (APT group)."""
    attack_id = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    aliases = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    techniques = models.ManyToManyField(
        Technique, blank=True, related_name='threat_actors'
    )
    url = models.URLField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['name']
        verbose_name = 'Threat actor'
        verbose_name_plural = 'Threat actors'

    def __str__(self):
        return f"{self.name} ({self.attack_id})"


class IOC(models.Model):
    """
    Indicator of Compromise — IP, domain, URL, hash, etc.
    Sourced from OTX, ThreatFox, or manually entered.
    """
    IOC_TYPE_CHOICES = [
        ('ipv4',          'IPv4 Address'),
        ('ipv6',          'IPv6 Address'),
        ('domain',        'Domain'),
        ('url',           'URL'),
        ('md5',           'MD5 Hash'),
        ('sha1',          'SHA1 Hash'),
        ('sha256',        'SHA256 Hash'),
        ('email',         'Email'),
        ('cve',           'CVE'),
        ('mutex',         'Mutex'),
        ('filepath',      'File Path'),
        ('registry',      'Registry Key'),
        ('user_agent',    'User-Agent'),
    ]
    THREAT_TYPE_CHOICES = [
        ('malware',         'Malware'),
        ('ransomware',      'Ransomware'),
        ('c2',              'Command & Control'),
        ('phishing',        'Phishing'),
        ('botnet',          'Botnet'),
        ('exploit',         'Exploit'),
        ('scanner',         'Scanner'),
        ('apt',             'APT Activity'),
        ('cryptominer',     'Cryptominer'),
        ('unknown',         'Unknown'),
    ]
    CONFIDENCE_CHOICES = [
        (1, 'Low'),
        (2, 'Medium'),
        (3, 'High'),
        (4, 'Confirmed'),
    ]

    value = models.CharField(max_length=500, db_index=True)
    ioc_type = models.CharField(max_length=20, choices=IOC_TYPE_CHOICES, default='ipv4')
    threat_type = models.CharField(
        max_length=20, choices=THREAT_TYPE_CHOICES, default='unknown'
    )
    confidence = models.PositiveSmallIntegerField(
        choices=CONFIDENCE_CHOICES, default=2
    )

    source = models.CharField(
        max_length=50, blank=True,
        help_text='e.g. OTX, ThreatFox, Manual'
    )
    source_id = models.CharField(max_length=200, blank=True)
    first_seen = models.DateTimeField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    malware_family = models.CharField(max_length=200, blank=True)
    threat_actor = models.ForeignKey(
        ThreatActor, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='iocs'
    )
    techniques = models.ManyToManyField(
        Technique, blank=True, related_name='iocs',
        help_text='ATT&CK techniques this IOC is associated with'
    )
    related_cves = models.ManyToManyField(
        'vulnerabilities.Vulnerability', blank=True, related_name='iocs'
    )

    notes = models.TextField(blank=True)
    is_whitelisted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-first_seen', '-created_at']
        unique_together = ('value', 'ioc_type', 'source')
        indexes = [
            models.Index(fields=['ioc_type', 'is_active']),
            models.Index(fields=['-first_seen']),
        ]
        verbose_name = 'Indicator of Compromise'
        verbose_name_plural = 'Indicators of Compromise'

    def __str__(self):
        return f"{self.ioc_type}:{self.value}"

    @property
    def confidence_color(self):
        return {1: '#6B7280', 2: '#D97706', 3: '#0284C7', 4: '#DC2626'}.get(self.confidence, '#6B7280')

    @property
    def threat_type_color(self):
        return {
            'ransomware':  '#DC2626',
            'malware':     '#EA580C',
            'c2':          '#7C3AED',
            'phishing':    '#D97706',
            'botnet':      '#0284C7',
            'exploit':     '#B91C1C',
            'apt':         '#0B1220',
            'cryptominer': '#059669',
            'scanner':     '#6B7280',
            'unknown':     '#94A3B8',
        }.get(self.threat_type, '#6B7280')


class IOCFeedSync(models.Model):
    """Log of every feed sync run."""
    SOURCE_CHOICES = [
        ('otx',           'AlienVault OTX'),
        ('threatfox',     'abuse.ch ThreatFox'),
        ('threatcluster', 'ThreatCluster'),
        ('manual',        'Manual'),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_fetched = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)
    items_skipped = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default='running')
    error_message = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'IOC feed sync'
        verbose_name_plural = 'IOC feed syncs'

    def __str__(self):
        return f"{self.source} @ {self.started_at:%Y-%m-%d %H:%M}"
