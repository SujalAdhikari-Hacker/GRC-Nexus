"""Authentication views that add product-level security behaviour."""
from django import forms
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST

from .models import real_users


class NoReusePasswordChangeForm(PasswordChangeForm):
    """Reject setting the new password to the account's current password."""

    def clean_new_password1(self):
        new_password = self.cleaned_data.get('new_password1')
        if new_password and self.user.check_password(new_password):
            raise forms.ValidationError(
                'Your new password cannot be the same as your current password.',
                code='password_reused',
            )
        return new_password


class SecurePasswordChangeView(PasswordChangeView):
    """Clear the forced-rotation flag once the new password is accepted."""

    form_class = NoReusePasswordChangeForm
    success_url = reverse_lazy('core:settings')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['forced_rotation'] = bool(
            getattr(self.request.user, 'must_change_password', False)
        )
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if getattr(user, 'must_change_password', False):
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
        messages.success(self.request, 'Your password has been changed.')
        return response


@login_required
@require_POST
def sign_out_all_devices(request):
    """Revoke every active session belonging to the signed-in user."""
    request.user.revoke_sessions()
    auth.logout(request)
    return redirect(f"{reverse(settings.LOGIN_URL)}?signed_out_all=1")


@login_required
@require_POST
def revoke_user_sessions(request, pk):
    """Superuser-only: immediately revoke all active sessions for a user."""
    if not request.user.is_superuser:
        raise PermissionDenied('Only superadmins can revoke another user\'s sessions.')
    target = get_object_or_404(real_users(), pk=pk)
    target.revoke_sessions()
    if target.pk == request.user.pk:
        auth.logout(request)
        return redirect(f"{reverse(settings.LOGIN_URL)}?signed_out_all=1")
    messages.success(
        request,
        f'All active sessions for {target.username} have been revoked.',
    )
    return redirect('core:users_list')
