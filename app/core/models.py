import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.crypto import salted_hmac
from simple_history.models import HistoricalRecords


class Department(models.Model):
    name = models.CharField(max_length=200, unique=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='children'
    )
    has_org_read_oversight = models.BooleanField(
        default=False,
        help_text=(
            'Members of this department have read-only visibility across all '
            'departments (e.g. Internal Audit, Compliance).'
        ),
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
    # Seeded/default-password accounts must rotate before using the app.
    must_change_password = models.BooleanField(default=False)
    session_nonce = models.CharField(
        max_length=32,
        default='',
        blank=True,
        editable=False,
        help_text='Rotated to immediately invalidate all active sessions for this user.',
    )

    history = HistoricalRecords()

    def __str__(self):
        return self.username

    def get_session_auth_hash(self):
        if not self.session_nonce:
            return super().get_session_auth_hash()
        return salted_hmac(
            'core.models.User.get_session_auth_hash',
            f'{self.password}:{self.session_nonce}',
            secret=settings.SECRET_KEY,
            algorithm='sha256',
        ).hexdigest()

    def revoke_sessions(self):
        """Invalidate every active session for this user across all devices."""
        self.session_nonce = secrets.token_hex(16)
        self.save(update_fields=['session_nonce'])
        try:
            from django.contrib.sessions.models import Session

            user_id_str = str(self.pk)
            pks_to_delete = []
            for sess in Session.objects.all().iterator():
                try:
                    data = sess.get_decoded()
                except Exception:
                    continue
                if str(data.get('_auth_user_id', '')) == user_id_str:
                    pks_to_delete.append(sess.pk)
            if pks_to_delete:
                Session.objects.filter(pk__in=pks_to_delete).delete()
        except Exception:
            # Non-DB session engines still drop sessions immediately because
            # session_nonce invalidates get_session_auth_hash().
            pass


def real_users(queryset=None):
    """Return real application users, excluding django-guardian's AnonymousUser."""
    from django.conf import settings
    anon_name = getattr(settings, 'ANONYMOUS_USER_NAME', 'AnonymousUser')
    qs = queryset if queryset is not None else User.objects.all()
    if anon_name:
        qs = qs.exclude(username=anon_name)
    return qs


class UserMFA(models.Model):
    """Per-user TOTP second factor and hashed one-time backup codes."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='mfa'
    )
    secret = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    backup_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'MFA for {self.user.username} ({"on" if self.enabled else "off"})'


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
    board_report_enabled = models.BooleanField(
        default=True,
        help_text='Enable scheduled monthly executive PDF board-report delivery.',
    )
    board_report_recipients = models.TextField(
        blank=True,
        help_text='Additional recipient emails (comma or newline separated) for the monthly board pack.',
    )
    last_board_report_sent_at = models.DateTimeField(
        null=True, blank=True, editable=False,
        help_text='Timestamp when the automated board-report pack was last emailed.',
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


class SavedView(models.Model):
    """A named, reusable list filter, private to the user who saved it.

    A saved view stores only the querystring for a given list (model label), so
    it stays valid as records come and go — it re-runs the filter rather than
    freezing a set of IDs.
    """

    user = models.ForeignKey(
        'core.User', on_delete=models.CASCADE, related_name='saved_views'
    )
    name = models.CharField(max_length=120)
    model_label = models.CharField(max_length=100, db_index=True)
    query_string = models.CharField(max_length=1000, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['model_label', 'name']
        verbose_name = 'Saved view'
        verbose_name_plural = 'Saved views'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'model_label', 'name'],
                name='unique_saved_view_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.model_label})'


class ServiceRun(models.Model):
    """One invocation of a scheduled service (a management command).

    The cron jobs are the only part of the system that can fail with nobody
    watching: they run unattended, print a summary to a terminal nobody reads
    and leave no trace. This row is that trace - what ran, when, whether it
    succeeded, and the counts it reported - so an operator can answer "did
    last night's escalation sweep actually run?" without shell access.

    A run that never finishes (the process was killed) stays ``running``; that
    is the visible signal that something stopped mid-flight.
    """

    STATUS_CHOICES = [
        ('running', 'Running'),
        ('ok', 'OK'),
        ('failed', 'Failed'),
    ]

    service = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Service run'
        verbose_name_plural = 'Service runs'

    def __str__(self):
        return f'{self.service} at {self.started_at:%Y-%m-%d %H:%M} ({self.status})'

    @property
    def duration_seconds(self):
        if self.finished_at is None:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 1)

    def finish(self, status, message=''):
        self.status = status
        self.message = (message or '')[:2000]
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'message', 'finished_at', 'counts'])


# Import for Django model discovery
from .settings_model import UserPreference  # noqa
