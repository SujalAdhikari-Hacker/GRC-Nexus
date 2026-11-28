"""Template helpers for object-level sharing."""
from django import template

from core.permissions import SHARE_PERMS, can_manage_sharing, object_shares

register = template.Library()


@register.simple_tag
def can_share(user, obj):
    """True when the current user may grant/revoke access on ``obj``."""
    return can_manage_sharing(user, obj)


@register.simple_tag
def share_url(obj):
    """The share endpoint for ``obj`` (template access can't read ``_meta``)."""
    from django.urls import reverse

    return reverse(
        'core:object_share',
        args=[obj._meta.app_label, obj._meta.model_name, obj.pk],
    )


@register.simple_tag
def shares_for(obj):
    """Current shares on ``obj`` as a list of {type, name, perms}."""
    return object_shares(obj)


@register.simple_tag
def share_perm_choices():
    """The permission options a share can carry, for form checkboxes."""
    return SHARE_PERMS


@register.simple_tag
def shareable_users():
    """Active users who can be granted access to a record."""
    from core.models import real_users

    return real_users().filter(is_active=True).order_by('username')


@register.simple_tag
def shareable_groups():
    from django.contrib.auth.models import Group

    return Group.objects.all().order_by('name')


@register.filter
def can_access(obj, user):
    """True when ``user`` may open ``obj`` — used to avoid linking gated records.

    Department-scoped detail views return 404 for another department's record, so
    rendering that record as a link would be a dead end. Falls back through the
    common parent relations used by evidence, findings and control tests.
    """
    from core.mixins import user_can_access

    return _resolve_access(obj, user, user_can_access)


@register.filter
def can_change(obj, user):
    """True when ``user`` may edit ``obj`` — hides actions that would 403."""
    from core.mixins import user_can_change

    return _resolve_access(obj, user, user_can_change)


def _resolve_access(obj, user, check):
    if obj is None:
        return False
    for field in ('owner_dept', 'department'):
        if hasattr(obj, f'{field}_id'):
            return check(user, obj, field=field)
    for attr in ('audit', 'risk', 'control', 'vendor', 'policy', 'asset'):
        parent = getattr(obj, attr, None)
        if parent is not None and parent is not obj:
            return _resolve_access(parent, user, check)
    return check(user, obj)


@register.filter
def url_allowed(url, user):
    """True when a stored ``action_url`` points at a record the user can open.

    Notifications outlive permission changes, so a link can become a dead end.
    Resolve the URL to its model view and apply the same department scoping as
    the view itself; unknown routes are left to the normal 404 handling.
    """
    from urllib.parse import urlsplit

    from django.urls import Resolver404, resolve

    from core.mixins import user_can_access

    if not url:
        return False
    try:
        match = resolve(urlsplit(url).path)
    except Resolver404:
        return True
    view = getattr(match.func, 'view_class', None)
    model = getattr(view, 'model', None)
    pk = match.kwargs.get('pk')
    if model is None or pk is None:
        return True
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return False
    return _resolve_access(obj, user, user_can_access)
