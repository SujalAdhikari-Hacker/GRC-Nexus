from django.db import models
from simple_history.models import HistoricalRecords


def _tz_choices():
    return [
        ('UTC', 'UTC'),
        ('Asia/Kathmandu', 'Asia/Kathmandu (NPT, +5:45)'),
        ('Asia/Kolkata', 'Asia/Kolkata (IST, +5:30)'),
        ('Asia/Dubai', 'Asia/Dubai (GST, +4)'),
        ('Asia/Singapore', 'Asia/Singapore (SGT, +8)'),
        ('Asia/Shanghai', 'Asia/Shanghai (CST, +8)'),
        ('Asia/Tokyo', 'Asia/Tokyo (JST, +9)'),
        ('Asia/Seoul', 'Asia/Seoul (KST, +9)'),
        ('Australia/Sydney', 'Australia/Sydney (AEDT, +11)'),
        ('Europe/London', 'Europe/London (GMT/BST)'),
        ('Europe/Paris', 'Europe/Paris (CET, +1)'),
        ('Europe/Berlin', 'Europe/Berlin (CET, +1)'),
        ('Europe/Moscow', 'Europe/Moscow (MSK, +3)'),
        ('Africa/Cairo', 'Africa/Cairo (EET, +2)'),
        ('Africa/Lagos', 'Africa/Lagos (WAT, +1)'),
        ('America/New_York', 'America/New_York (EST/EDT)'),
        ('America/Chicago', 'America/Chicago (CST/CDT)'),
        ('America/Denver', 'America/Denver (MST/MDT)'),
        ('America/Los_Angeles', 'America/Los_Angeles (PST/PDT)'),
        ('America/Sao_Paulo', 'America/Sao_Paulo (BRT, -3)'),
    ]


class UserPreference(models.Model):
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('en-gb', 'English (UK)'),
        ('en-us', 'English (US)'),
        ('ne', 'Nepali'),
        ('hi', 'Hindi'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('zh-hans', 'Chinese (Simplified)'),
        ('ja', 'Japanese'),
    ]

    DATE_FORMAT_CHOICES = [
        ('Y-m-d', 'YYYY-MM-DD — 2026-10-13'),
        ('d/m/Y', 'DD/MM/YYYY — 13/10/2026'),
        ('m/d/Y', 'MM/DD/YYYY — 10/13/2026'),
        ('d.m.Y', 'DD.MM.YYYY — 13.10.2026'),
        ('j M Y', 'D Mon YYYY — 13 Oct 2026'),
        ('M j, Y', 'Mon D, YYYY — Oct 13, 2026'),
        ('j F Y', 'D Month YYYY — 13 October 2026'),
    ]

    TIME_FORMAT_CHOICES = [
        ('H:i', '24-hour — 14:30'),
        ('H:i:s', '24-hour with seconds — 14:30:45'),
        ('g:i A', '12-hour — 2:30 PM'),
        ('g:i:s A', '12-hour with seconds — 2:30:45 PM'),
    ]

    THEME_CHOICES = [
        ('system', 'Follow system default'),
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]

    ITEMS_PER_PAGE_CHOICES = [
        (10, '10 per page'),
        (20, '20 per page'),
        (25, '25 per page'),
        (50, '50 per page'),
        (100, '100 per page'),
    ]

    user = models.OneToOneField(
        'core.User', on_delete=models.CASCADE, related_name='preference'
    )

    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='en')
    timezone = models.CharField(max_length=64, choices=_tz_choices(), default='UTC')
    date_format = models.CharField(max_length=20, choices=DATE_FORMAT_CHOICES, default='Y-m-d')
    time_format = models.CharField(max_length=20, choices=TIME_FORMAT_CHOICES, default='H:i')

    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='system')
    items_per_page = models.PositiveSmallIntegerField(choices=ITEMS_PER_PAGE_CHOICES, default=25)

    email_notifications_enabled = models.BooleanField(
        default=True,
        help_text='Receive email notifications for alerts and assignments',
    )
    email_on_ticket_assigned = models.BooleanField(default=True)
    email_on_risk_breach = models.BooleanField(default=True)
    email_on_audit_finding = models.BooleanField(default=True)
    email_on_kri_red = models.BooleanField(default=True)
    email_on_vuln_sla = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = 'User preference'
        verbose_name_plural = 'User preferences'

    def __str__(self):
        return f'Preferences — {self.user.username}'

    @classmethod
    def get_for(cls, user):
        if not user or not user.is_authenticated:
            return None
        pref, _ = cls.objects.get_or_create(user=user)
        return pref
