from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from simple_history.models import HistoricalRecords
from core.models import Department

# A continuity test older than this counts as stale.
CONTINUITY_TEST_VALID_DAYS = 365

# Only business-critical assets are held to the BIA / BCP / DRP checks.
CONTINUITY_CRITICALITY_MIN = 3


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
    CLOUD_PROVIDER_CHOICES = [
        ('aws',         'AWS'),
        ('azure',       'Microsoft Azure'),
        ('gcp',         'Google Cloud'),
        ('oracle',      'Oracle Cloud'),
        ('ibm',         'IBM Cloud'),
        ('alibaba',     'Alibaba Cloud'),
        ('digitalocean','DigitalOcean'),
        ('linode',      'Linode'),
        ('vultr',       'Vultr'),
        ('on_prem',     'On-Premises (no cloud)'),
        ('other',       'Other'),
    ]
    OS_FAMILY_CHOICES = [
        ('linux',     'Linux'),
        ('windows',   'Windows'),
        ('macos',     'macOS'),
        ('unix',      'Unix (AIX/Solaris/BSD)'),
        ('ios',       'iOS'),
        ('android',   'Android'),
        ('network',   'Network OS (Cisco/Juniper/etc.)'),
        ('embedded',  'Embedded / Firmware'),
        ('other',     'Other'),
    ]

    # ---------- Identification ----------
    asset_id = models.CharField(
        max_length=20, unique=True, null=True, blank=True, db_index=True,
        help_text='Auto-generated reference ID like AST-0001.'
    )
    name = models.CharField(max_length=200)
    hostname = models.CharField(
        max_length=200, blank=True,
        help_text='DNS or system hostname (e.g. web-prod-01.corp.local)'
    )
    ip_address = models.GenericIPAddressField(
        null=True, blank=True,
        help_text='Primary IPv4 or IPv6 address'
    )
    fqdn = models.CharField(
        max_length=300, blank=True,
        help_text='Fully qualified domain name'
    )

    # ---------- Classification ----------
    asset_type = models.CharField(max_length=20, choices=ASSET_TYPE_CHOICES, default='hardware')
    hosting = models.CharField(max_length=20, choices=HOSTING_CHOICES, default='on_prem')
    cloud_provider = models.CharField(
        max_length=20, choices=CLOUD_PROVIDER_CHOICES, default='on_prem',
        blank=True,
        help_text='Which cloud provider hosts this asset'
    )
    cloud_region = models.CharField(
        max_length=100, blank=True,
        help_text='Cloud region or availability zone, e.g. us-east-1, eu-west-2'
    )
    location = models.CharField(
        max_length=200, blank=True,
        help_text='Physical location or country, e.g. Kathmandu DC-1, Nepal'
    )
    os_family = models.CharField(
        max_length=20, choices=OS_FAMILY_CHOICES, default='linux', blank=True
    )
    os_version = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. Ubuntu 22.04 LTS, Windows Server 2019'
    )

    vendor = models.ForeignKey(
        'vendors.Vendor', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assets'
    )
    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES, default='internal')

    owner_dept = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name='assets'
    )
    owner_user = models.ForeignKey(
        'core.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_assets'
    )
    environment = models.CharField(max_length=20, choices=ENVIRONMENT_CHOICES, default='production')
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, related_name='assets',
        null=True, blank=True
    )

    # ---------- Risk ratings ----------
    criticality = models.PositiveSmallIntegerField(choices=CRITICALITY_CHOICES, default=2)
    confidentiality = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    integrity = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    availability = models.PositiveSmallIntegerField(choices=CIA_CHOICES, default=2)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    policies = models.ManyToManyField('policies.Policy', blank=True, related_name='assets')
    depends_on = models.ManyToManyField(
        'self', symmetrical=False, blank=True, related_name='dependents',
        help_text=(
            'Other assets this one needs to function (e.g. an application '
            'depends on its database). Used to understand outage blast radius.'
        ),
    )

    # ---------- Business impact analysis (BIA) ----------
    # RTO/RPO/MTPD in hours. Blank means the BIA has not been completed, which
    # is itself a gap the continuity report raises.
    rto_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Recovery Time Objective: how long this asset may be down.',
    )
    rpo_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Recovery Point Objective: how much data loss is tolerable.',
    )
    mtpd_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Maximum Tolerable Period of Disruption.',
    )
    bcp_policy = models.ForeignKey(
        'policies.Policy', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bcp_assets',
        help_text='Business continuity plan covering this asset.',
    )
    drp_policy = models.ForeignKey(
        'policies.Policy', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='drp_assets',
        help_text='Disaster recovery plan covering this asset.',
    )
    last_continuity_test = models.DateField(
        null=True, blank=True,
        help_text='When continuity was last exercised (failover, restore, DR drill).',
    )

    # ---------- Audit trail ----------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assets_created',
        help_text='Who created this asset'
    )
    updated_by = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='assets_updated',
        help_text='Who last modified this asset'
    )

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
            while Asset.objects.filter(asset_id=f'AST-{num:04d}').exists():
                num += 1
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

    @property
    def host_line(self):
        """Compact identifier for tables and lists."""
        bits = [b for b in [self.hostname, self.ip_address] if b]
        return ' · '.join(bits) if bits else ''

    # ---------- Continuity gaps ----------

    @property
    def continuity_test_stale(self):
        """No test on record, or the last one is more than a year old."""
        if not self.last_continuity_test:
            return True
        age = (timezone.localdate() - self.last_continuity_test).days
        return age > CONTINUITY_TEST_VALID_DAYS

    @property
    def continuity_gaps(self):
        """Everything missing or contradictory on this asset's continuity plan."""
        gaps = []
        if self.rto_hours is None:
            gaps.append('RTO not set')
        if self.rpo_hours is None:
            gaps.append('RPO not set')
        if self.mtpd_hours is None:
            gaps.append('MTPD not set')
        if (
            self.rto_hours is not None
            and self.mtpd_hours is not None
            and self.rto_hours > self.mtpd_hours
        ):
            gaps.append('RTO exceeds MTPD')
        if not self.bcp_policy_id:
            gaps.append('No BCP linked')
        if not self.drp_policy_id:
            gaps.append('No DRP linked')
        if self.continuity_test_stale:
            gaps.append('No continuity test in the last 12 months')
        return gaps

    @property
    def continuity_complete(self):
        return not self.continuity_gaps