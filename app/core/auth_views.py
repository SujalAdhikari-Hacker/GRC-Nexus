"""Authentication views that add product-level security behaviour."""
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy


class SecurePasswordChangeView(PasswordChangeView):
    """Clear the forced-rotation flag once the new password is accepted."""

    success_url = reverse_lazy('core:settings')

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if getattr(user, 'must_change_password', False):
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
        messages.success(self.request, 'Your password has been changed.')
        return response
