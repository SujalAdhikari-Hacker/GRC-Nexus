"""Views for object-level sharing and per-user saved list views.

Kept out of ``core.views`` (the dashboard/admin module) so the surface is small
and easy to audit: every endpoint here is POST-only, CSRF-protected and checks
authorization before touching guardian's tables.
"""
from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .input_validation import choice, identifier, positive_int, string_list, text
from .models import SavedView
from .permissions import (
    SHARE_PERMS,
    can_manage_sharing,
    grant_object_perms,
    revoke_object_perms,
)


def _redirect_back(request):
    """Return to the referring page, but never to an off-site URL."""
    candidate = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if (
        candidate
        and len(candidate) <= 2000
        and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return redirect(candidate)
    return redirect('core:dashboard')


@login_required
@require_POST
def share_object(request, app_label, model_name, pk):
    """Grant or revoke object-level permissions on a single record."""
    model = apps.get_model(app_label, model_name)
    if model is None:
        raise PermissionDenied
    obj = get_object_or_404(model, pk=pk)

    if not can_manage_sharing(request.user, obj):
        raise PermissionDenied

    action = choice(request.POST.get('action'), {'grant', 'revoke'}, 'action')
    perms = string_list(
        request.POST.getlist('perms'), 'perms',
        allowed=set(SHARE_PERMS), max_items=len(SHARE_PERMS),
    )
    if not perms:
        perms = list(SHARE_PERMS)

    principal_type = choice(
        request.POST.get('principal_type'), {'user', 'group'}, 'principal_type',
    )
    principal_id = positive_int(
        request.POST.get('principal_id'), 'principal_id'
    )
    if principal_type == 'group':
        principal = get_object_or_404(Group, pk=principal_id)
        target = {'group': principal}
    else:
        principal = get_object_or_404(
            get_user_model(), pk=principal_id
        )
        target = {'user': principal}

    if action == 'grant':
        if getattr(principal, 'pk', None) == request.user.pk and 'user' in target:
            messages.error(request, "You already have access to this record.")
        else:
            grant_object_perms(obj, perms=perms, **target)
            messages.success(request, f'Shared this record with {principal}.')
    else:
        revoke_object_perms(obj, perms=perms, **target)
        messages.success(request, f'Removed access for {principal}.')

    return _redirect_back(request)


@login_required
@require_POST
def saved_view_save(request):
    """Create or update a named view for the current list."""
    name = text(
        request.POST.get('name'), 'name', 120,
        allow_blank=False, strip=True,
    )
    model_label = identifier(request.POST.get('model_label'), 'model_label')
    query_string = text(
        request.POST.get('query_string'), 'query_string', 1000,
        allow_blank=True, strip=True,
    )

    view, created = SavedView.objects.update_or_create(
        user=request.user,
        model_label=model_label,
        name=name,
        defaults={'query_string': query_string},
    )
    verb = 'Saved' if created else 'Updated'
    messages.success(request, f'{verb} view “{view.name}”.')
    return _redirect_back(request)


@login_required
@require_POST
def saved_view_delete(request, pk):
    """Delete one of the current user's saved views."""
    view = get_object_or_404(SavedView, pk=pk, user=request.user)
    name = view.name
    view.delete()
    messages.success(request, f'Deleted view “{name}”.')
    return _redirect_back(request)
