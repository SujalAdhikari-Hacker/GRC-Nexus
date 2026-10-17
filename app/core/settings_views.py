from django.contrib import messages
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
        'today_preview': timezone.now().date(),
        'user_timezone': timezone.get_current_timezone(),
        'server_timezone': timezone.get_default_timezone(),
    }
    return render(request, 'core/settings.html', ctx)
