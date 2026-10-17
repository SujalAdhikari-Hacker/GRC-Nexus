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
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(is_active=True).order_by('username')


@register.simple_tag
def shareable_groups():
    from django.contrib.auth.models import Group

    return Group.objects.all().order_by('name')
