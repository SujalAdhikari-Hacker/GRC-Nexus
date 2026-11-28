"""Authentication views that add product-level security behaviour."""
from django import forms
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy


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
