"""Login view wired to the sign-in throttle.

The throttling itself lives in :mod:`core.login_throttle` (form-level); this
view only clears the failure counter once sign-in succeeds.
"""
import logging

from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect

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
        response = super().form_valid(form)

        # The middleware ran while this request was anonymous. Refresh the RLS
        # context now that authentication has succeeded, otherwise the MFA
        # lookup below runs with an empty app.user_id and sees no MFA row.
        from core.middleware import RLSMiddleware

        user = self.request.user
        RLSMiddleware.activate_for_user(user)

        # The password is correct at this point, but an MFA-enabled account is
        # not fully signed in until the second factor is verified. The session
        # is authenticated (so the verifier can identify the user) but the MFA
        # middleware blocks every other route.
        mfa = getattr(user, 'mfa', None)
        if mfa and mfa.enabled:
            self.request.session['mfa_verified'] = False
            self.request.session['mfa_next'] = self.get_success_url()
            return redirect('core:mfa_verify')
        self.request.session['mfa_verified'] = True
        return response
