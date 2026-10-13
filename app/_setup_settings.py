import os

# ============================================================
# 1) core/settings_model.py
# ============================================================
MODEL = '''from django.db import models
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
'''

with open('/app/core/settings_model.py', 'w', encoding='utf-8') as f:
    f.write(MODEL)
print('1. core/settings_model.py created')


# ============================================================
# 2) core/settings_forms.py
# ============================================================
FORM = '''from django import forms
from .settings_model import UserPreference


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            'language', 'timezone', 'date_format', 'time_format',
            'theme', 'items_per_page',
            'email_notifications_enabled',
            'email_on_ticket_assigned', 'email_on_risk_breach',
            'email_on_audit_finding', 'email_on_kri_red', 'email_on_vuln_sla',
        ]
        widgets = {
            'theme': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-check-input')
'''

with open('/app/core/settings_forms.py', 'w', encoding='utf-8') as f:
    f.write(FORM)
print('2. core/settings_forms.py created')


# ============================================================
# 3) core/settings_views.py
# ============================================================
VIEWS = '''from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .settings_model import UserPreference
from .settings_forms import UserPreferenceForm


@login_required
def settings_view(request):
    pref = UserPreference.get_for(request.user)

    if request.method == 'POST':
        form = UserPreferenceForm(request.POST, instance=pref)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved.')
            return redirect(reverse('core:settings'))
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = UserPreferenceForm(instance=pref)

    ctx = {
        'form': form,
        'pref': pref,
        'timezone_now': timezone.now(),
        'user_timezone': timezone.get_current_timezone(),
    }
    return render(request, 'core/settings.html', ctx)
'''

with open('/app/core/settings_views.py', 'w', encoding='utf-8') as f:
    f.write(VIEWS)
print('3. core/settings_views.py created')


# ============================================================
# 4) core/middleware.py
# ============================================================
MIDDLEWARE = '''"""Apply the logged-in user's timezone preference per request."""
from django.utils import timezone


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                pref = getattr(request.user, 'preference', None)
                if pref and pref.timezone:
                    timezone.activate(pref.timezone)
            except Exception:
                pass
        return self.get_response(request)
'''

with open('/app/core/middleware.py', 'w', encoding='utf-8') as f:
    f.write(MIDDLEWARE)
print('4. core/middleware.py created')


# ============================================================
# 5) Patch apps.py — ensure settings_model loads
# ============================================================
apps_path = '/app/core/apps.py'
with open(apps_path, encoding='utf-8') as f:
    apps_src = f.read()

if 'settings_model' not in apps_src:
    if 'def ready(' in apps_src:
        import re
        apps_src = re.sub(
            r'(def ready\(self\):\n)',
            r'\1        import core.settings_model  # noqa\n',
            apps_src,
            count=1,
        )
    else:
        apps_src = apps_src.rstrip() + (
            '\n\n    def ready(self):\n'
            '        import core.settings_model  # noqa\n'
        )
    with open(apps_path, 'w', encoding='utf-8') as f:
        f.write(apps_src)
    print('5. core/apps.py — settings_model auto-loaded')
else:
    print('5. core/apps.py — already loads settings_model')


# ============================================================
# 6) Patch core/urls.py — add /settings/
# ============================================================
urls_path = '/app/core/urls.py'
with open(urls_path, encoding='utf-8') as f:
    urls_src = f.read()

if 'settings_view' not in urls_src:
    # Add import
    urls_src = urls_src.replace(
        'from .notification_views import (',
        'from .settings_views import settings_view\n'
        'from .notification_views import (',
        1,
    )
    # Add route
    pattern_block = "    path('settings/', settings_view, name='settings'),\n"
    last_bracket = urls_src.rfind(']')
    urls_src = urls_src[:last_bracket] + pattern_block + urls_src[last_bracket:]
    with open(urls_path, 'w', encoding='utf-8') as f:
        f.write(urls_src)
    print('6. core/urls.py — /settings/ route added')
else:
    print('6. core/urls.py — settings route already present')


# ============================================================
# 7) Patch settings for middleware
# ============================================================
settings_path = '/app/config/settings/base.py'
with open(settings_path, encoding='utf-8') as f:
    s = f.read()

if 'UserTimezoneMiddleware' not in s:
    needle = "    'django.middleware.clickjacking.XFrameOptionsMiddleware',\n"
    if needle in s:
        s = s.replace(
            needle,
            needle + "    'core.middleware.UserTimezoneMiddleware',\n",
            1,
        )
        with open(settings_path, 'w', encoding='utf-8') as f:
            f.write(s)
        print('7. settings — UserTimezoneMiddleware registered')
    else:
        print('7. WARNING: clickjacking middleware line not found')
else:
    print('7. settings — middleware already registered')


# ============================================================
# 8) Patch base.html — gear icon → /settings/
# ============================================================
base_path = '/app/templates/base.html'
with open(base_path, encoding='utf-8') as f:
    base = f.read()

old_gear = '<a href="/admin/" class="topbar-btn" title="Admin">'
new_gear = '<a href="{% url \'core:settings\' %}" class="topbar-btn" title="Settings">'
if old_gear in base:
    base = base.replace(old_gear, new_gear, 1)
    with open(base_path, 'w', encoding='utf-8') as f:
        f.write(base)
    print('8. base.html — gear icon now points to /settings/')
else:
    print('8. base.html — gear anchor not found (may already be updated)')

# Add Settings to user dropdown
if base.count('core:settings') < 2:
    old_menu = '<div class="user-menu-divider"></div>\n                        <form method="post" action="{% url \'logout\' %}"'
    new_menu = (
        '<a href="{% url \'core:settings\' %}" class="user-menu-item">'
        '<i class="bi bi-gear"></i><span>Settings</span></a>\n'
        '                        <div class="user-menu-divider"></div>\n'
        '                        <form method="post" action="{% url \'logout\' %}"'
    )
    if old_menu in base:
        base = base.replace(old_menu, new_menu, 1)
        with open(base_path, 'w', encoding='utf-8') as f:
            f.write(base)
        print('9. base.html — Settings link added to user dropdown')
    else:
        print('9. base.html — dropdown pattern not found')
else:
    print('9. base.html — Settings link already in dropdown')


# ============================================================
# 10) Create the settings template
# ============================================================
TEMPLATE = '''{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block breadcrumb %}
<nav aria-label="breadcrumb">
  <ol class="breadcrumb mb-0">
    <li class="breadcrumb-item">Account</li>
    <li class="breadcrumb-item active">Settings</li>
  </ol>
</nav>
{% endblock %}

{% block content %}
<div class="row g-3">
    <div class="col-md-8">
        <form method="post">
            {% csrf_token %}
            {% if form.non_field_errors %}<div class="alert alert-danger">{{ form.non_field_errors }}</div>{% endif %}

            {# ─── Regional ─── #}
            <div class="card mb-3">
                <div class="card-header bg-white"><strong><i class="bi bi-globe2"></i> Regional</strong></div>
                <div class="card-body">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">Language</label>
                            {{ form.language }}
                            <div class="form-text small">Interface language (translation support coming soon)</div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Timezone</label>
                            {{ form.timezone }}
                            <div class="form-text small">
                                Server time now: <strong>{{ timezone_now|date:"Y-m-d H:i:s" }}</strong>
                                · Your timezone: <strong>{{ user_timezone }}</strong>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Date format</label>
                            {{ form.date_format }}
                            <div class="form-text small">Today preview: <strong>{% now "Y-m-d" %}</strong></div>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">Time format</label>
                            {{ form.time_format }}
                        </div>
                    </div>
                </div>
            </div>

            {# ─── Interface ─── #}
            <div class="card mb-3">
                <div class="card-header bg-white"><strong><i class="bi bi-palette2"></i> Interface</strong></div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">Theme</label>
                        <div class="d-flex flex-wrap gap-3">
                            {% for radio in form.theme %}
                                <div class="form-check">
                                    {{ radio.tag }}
                                    <label class="form-check-label" for="{{ radio.id_for_label }}">
                                        {{ radio.choice_label }}
                                    </label>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                    <div>
                        <label class="form-label">Items per page</label>
                        {{ form.items_per_page }}
                        <div class="form-text small">Applied to all list views</div>
                    </div>
                </div>
            </div>

            {# ─── Notifications ─── #}
            <div class="card mb-3">
                <div class="card-header bg-white"><strong><i class="bi bi-bell"></i> Notifications</strong></div>
                <div class="card-body">
                    <div class="form-check form-switch mb-3">
                        {{ form.email_notifications_enabled }}
                        <label class="form-check-label" for="{{ form.email_notifications_enabled.id_for_label }}">
                            <strong>Enable email notifications</strong>
                        </label>
                        <div class="form-text small">Master switch for all emails from GRC Nexus</div>
                    </div>

                    <hr>
                    <p class="text-muted small mb-2">Send me an email when:</p>

                    <div class="form-check mb-2">
                        {{ form.email_on_ticket_assigned }}
                        <label class="form-check-label" for="{{ form.email_on_ticket_assigned.id_for_label }}">
                            A ticket is assigned to me
                        </label>
                    </div>
                    <div class="form-check mb-2">
                        {{ form.email_on_risk_breach }}
                        <label class="form-check-label" for="{{ form.email_on_risk_breach.id_for_label }}">
                            A risk breaches its appetite threshold
                        </label>
                    </div>
                    <div class="form-check mb-2">
                        {{ form.email_on_audit_finding }}
                        <label class="form-check-label" for="{{ form.email_on_audit_finding.id_for_label }}">
                            A new audit finding is created
                        </label>
                    </div>
                    <div class="form-check mb-2">
                        {{ form.email_on_kri_red }}
                        <label class="form-check-label" for="{{ form.email_on_kri_red.id_for_label }}">
                            A KRI crosses into red
                        </label>
                    </div>
                    <div class="form-check mb-2">
                        {{ form.email_on_vuln_sla }}
                        <label class="form-check-label" for="{{ form.email_on_vuln_sla.id_for_label }}">
                            A vulnerability passes its SLA deadline
                        </label>
                    </div>
                </div>
            </div>

            <button type="submit" class="btn btn-dark">Save Settings</button>
        </form>
    </div>

    <div class="col-md-4">
        {# ─── Account card ─── #}
        <div class="card sticky-top" style="top:1rem;">
            <div class="card-header bg-white"><strong>Your account</strong></div>
            <ul class="list-group list-group-flush">
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Username</span>
                    <strong>{{ user.username }}</strong>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Name</span>
                    <span>{{ user.get_full_name|default:"—" }}</span>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Email</span>
                    <span><small>{{ user.email|default:"—" }}</small></span>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Department</span>
                    <span>{{ user.department.name|default:"—" }}</span>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Role</span>
                    <span>
                        {% if user.is_superuser %}<span class="badge bg-danger">Superadmin</span>
                        {% elif user.is_hod %}<span class="badge bg-info text-dark">HOD</span>
                        {% else %}<span class="badge bg-secondary">User</span>{% endif %}
                    </span>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Joined</span>
                    <small>{{ user.date_joined|date:"Y-m-d" }}</small>
                </li>
                <li class="list-group-item d-flex justify-content-between">
                    <span class="text-muted">Last login</span>
                    <small>{{ user.last_login|date:"Y-m-d H:i"|default:"—" }}</small>
                </li>
            </ul>
        </div>

        {# ─── Security card ─── #}
        <div class="card mt-3">
            <div class="card-header bg-white"><strong>Security</strong></div>
            <ul class="list-group list-group-flush">
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>Password</strong>
                        <div class="small text-muted">Change your login password</div>
                    </div>
                    <a href="{% url 'password_change' %}" class="btn btn-sm btn-outline-dark">Change</a>
                </li>
            </ul>
        </div>

        {# ─── System card ─── #}
        <div class="card mt-3">
            <div class="card-header bg-white"><strong>System</strong></div>
            <ul class="list-group list-group-flush">
                <li class="list-group-item d-flex justify-content-between"><span class="text-muted">App</span><span>GRC Nexus</span></li>
                <li class="list-group-item d-flex justify-content-between"><span class="text-muted">Version</span><code>v2.2.0</code></li>
                <li class="list-group-item d-flex justify-content-between"><span class="text-muted">Server timezone</span><code>UTC</code></li>
            </ul>
        </div>
    </div>
</div>
{% endblock %}
'''

with open('/app/templates/core/settings.html', 'w', encoding='utf-8') as f:
    f.write(TEMPLATE)
print('10. templates/core/settings.html created')

print('')
print('Setup complete. Next:')
print('  docker compose restart web')
print('  docker compose exec web python manage.py makemigrations core')
print('  docker compose exec web python manage.py migrate core')