from django.contrib.auth.models import AbstractUser
from django.db import models
from simple_history.models import HistoricalRecords


class Department(models.Model):
    name = models.CharField(max_length=200, unique=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='children'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.name


class User(AbstractUser):
    department = models.ForeignKey(
        Department, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='users'
    )
    is_hod = models.BooleanField(default=False)

    history = HistoricalRecords()

    def __str__(self):
        return self.username


class OrganisationProfile(models.Model):
    """
    Single-instance model holding organisation-wide facts that don't come
    from other data — used to build the Business Position summary in the
    executive report.
    """
    executive_sponsor = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sponsored_org',
        help_text='Executive-level sponsor for security (e.g. CFO, COO)'
    )
    security_committee_chair = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='chaired_committee',
        help_text='Chair of the security steering committee'
    )
    last_board_report_date = models.DateField(
        null=True, blank=True,
        help_text='Date of the most recent board security briefing'
    )

    annual_revenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=0,
        help_text='Total annual revenue'
    )
    annual_security_budget = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Total annual security budget'
    )

    total_employees = models.PositiveIntegerField(default=0)
    security_headcount = models.PositiveIntegerField(default=0)
    grc_headcount = models.PositiveIntegerField(default=0)

    posture_statement = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'core.User', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='updated_org_profile'
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = 'Organisation profile'
        verbose_name_plural = 'Organisation profile'

    def __str__(self):
        return 'Organisation Profile'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
