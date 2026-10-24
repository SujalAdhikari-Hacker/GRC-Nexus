from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

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
        'today_preview': timezone.localdate(),
        'user_timezone': timezone.get_current_timezone(),
        'server_timezone': timezone.get_default_timezone(),
    }
    return render(request, 'core/settings.html', ctx)


@login_required
@require_POST
def send_test_email(request):
    """Email the signed-in user a sample digest so they can verify delivery."""
    from .emails import email_for, send_digest_email

    address = email_for(request.user)
    if not address:
        messages.error(request, 'Add an email address to your account first.')
        return redirect(reverse('core:settings'))

    sample = [
        {
            'title': 'Example — "Phishing on Finance" breached its appetite',
            'meta': 'Escalation · sample message',
            'url': '/risks/',
            'severity': 'danger',
        },
        {
            'title': 'Example — "CTL-ACC-001" is due for testing',
            'meta': 'Escalation · sample message',
            'url': '/notifications/',
            'severity': 'warning',
        },
    ]
    delivered = send_digest_email(
        request.user, sample, overdue_count=1, window_label='today (test message)',
    )
    if delivered:
        messages.success(request, f'Test email sent to {address}.')
    else:
        messages.error(
            request,
            'Could not send the test email — check the server log for details.',
        )
    return redirect(reverse('core:settings'))
