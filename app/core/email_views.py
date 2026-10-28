"""Superuser-only email delivery configuration."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .email_config import describe, send_test_message
from .mixins import SuperuserOnlyMixin
from .settings_forms import EmailSettingsForm
from .settings_model import EmailSettings


class EmailSettingsView(SuperuserOnlyMixin, View):
    """Configure the organisation-wide SMTP relay."""

    template_name = 'core/email_settings.html'

    def _context(self, form):
        cfg = EmailSettings.get_solo()
        return {
            'form': form,
            'cfg': cfg,
            'status': describe(),
            'has_password': bool(cfg.password_encrypted),
        }

    def get(self, request):
        cfg = EmailSettings.get_solo()
        form = EmailSettingsForm(instance=cfg)
        return render(request, self.template_name, self._context(form))

    def post(self, request):
        cfg = EmailSettings.get_solo()
        form = EmailSettingsForm(request.POST, instance=cfg)
        if form.is_valid():
            obj = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password:
                obj.set_password(password)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, 'Email delivery settings saved.')
            return redirect(reverse('core:email_settings'))

        messages.error(request, 'Please fix the errors below.')
        return render(request, self.template_name, self._context(form))


class SendSMTPTestView(SuperuserOnlyMixin, View):
    """Send a test message through the saved SMTP configuration."""

    def post(self, request):
        recipient = (request.POST.get('recipient') or request.user.email or '').strip()
        try:
            validate_email(recipient)
        except ValidationError:
            messages.error(request, 'Enter a valid recipient email address.')
            return redirect(reverse('core:email_settings'))

        cfg = EmailSettings.get_solo()
        if not (cfg.is_enabled and cfg.host):
            messages.error(
                request,
                'Enable SMTP delivery and save the settings before sending a test.',
            )
            return redirect(reverse('core:email_settings'))

        delivered = send_test_message(recipient)
        if delivered:
            messages.success(request, f'Test email sent to {recipient}.')
        else:
            messages.error(
                request,
                'The test email could not be sent. Check the server log for the '
                'SMTP error, then verify the host, port, security mode and '
                'credentials.',
            )
        return redirect(reverse('core:email_settings'))
