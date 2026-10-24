"""Login view wired to the sign-in throttle.

The throttling itself lives in :mod:`core.login_throttle` (form-level); this
view only clears the failure counter once sign-in succeeds.
"""
import logging

from django.contrib.auth.views import LoginView as DjangoLoginView

from .login_throttle import clear_failures

logger = logging.getLogger(__name__)


class ThrottledLoginView(DjangoLoginView):
    def get_form_class(self):
        from .login_throttle import ThrottledAuthenticationForm
        return ThrottledAuthenticationForm

    def form_valid(self, form):
        clear_failures(
            form.cleaned_data.get('username') or '',
            self.request.META.get('REMOTE_ADDR', ''),
        )
        return super().form_valid(form)
