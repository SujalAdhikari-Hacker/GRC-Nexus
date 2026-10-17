"""
Object-level permissions and sharing, backed by django-guardian.

Department scoping (``core.mixins``) decides what a user sees *by default*.
This module adds an explicit, per-object grant on top: a Head of Department (or
superuser) can share one specific record — a single risk, policy, audit — with
another user or group without widening their whole department view.

Nothing here trusts the UI: :func:`grant_object_perms` is only ever called from
a view that has already checked :func:`can_manage_sharing`. The scoping helpers
in ``core.mixins`` consult :func:`granted_object_ids` so a granted object is
actually visible, not just listed somewhere.
"""
from django.contrib.auth import get_user_model

# Only these models participate in object-level sharing. Restricting the set
# keeps guardian's per-object tables focused and makes the scope-union query in
# ``scope_queryset`` cheap (it is skipped entirely for everything else).
SHAREABLE_MODELS = frozenset({
    'assets.asset',
    'risks.risk',
    'policies.policy',
    'controls.control',
    'vendors.vendor',
    'audits.audit',
    'audits.auditfinding',
    'vulnerabilities.vulnerability',
    'vulnerabilities.finding',
    'kris.kri',
    'tickets.ticket',
})

# The two permissions a share can carry. A share may grant either one: "view"
# is read-only, "change" additionally permits edits (see
# ``core.mixins.user_can_change``).
SHARE_PERMS = ('view', 'change')


def model_perm_codenames(model):
    """Map ``view``/``change`` to the model's real permission codenames."""
    name = model._meta.model_name
    return {'view': f'view_{name}', 'change': f'change_{name}'}


def is_shareable(model):
    return model is not None and model._meta.label_lower in SHAREABLE_MODELS


def can_manage_sharing(user, obj):
    """Who may (un)share ``obj``: superusers, or the owning department's HOD."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    owner_dept_id = getattr(obj, 'owner_dept_id', None)
    return bool(
        getattr(user, 'is_hod', False)
        and user.department_id
        and owner_dept_id == user.department_id
    )


def grant_object_perms(obj, *, user=None, group=None, perms=SHARE_PERMS):
    """Grant ``perms`` on ``obj`` to ``user`` and/or ``group``."""
    from guardian.shortcuts import assign_perm

    codenames = model_perm_codenames(type(obj))
    for perm in perms:
        codename = codenames.get(perm)
        if not codename:
            continue
        if user is not None:
            assign_perm(codename, user, obj)
        if group is not None:
            assign_perm(codename, group, obj)


def revoke_object_perms(obj, *, user=None, group=None, perms=SHARE_PERMS):
    """Revoke ``perms`` on ``obj`` from ``user`` and/or ``group``."""
    from guardian.shortcuts import remove_perm

    codenames = model_perm_codenames(type(obj))
    for perm in perms:
        codename = codenames.get(perm)
        if not codename:
            continue
        if user is not None:
            remove_perm(codename, user, obj)
        if group is not None:
            remove_perm(codename, group, obj)


def user_has_object_perm(user, obj, perms=SHARE_PERMS):
    """True if ``user`` holds any of ``perms`` on ``obj`` via an object grant.

    Global permissions are ignored on purpose — this answers "was this specific
    object shared with them?", not "are they allowed to change things in
    general?". Department access is handled separately in ``core.mixins``.

    ``accept_global_perms=False`` is essential here: ``user.has_perm(codename,
    obj)`` alone would return ``True`` for anyone holding the *global*
    ``change_x`` permission, silently turning an object check into a
    model-wide one.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    model = type(obj)
    if not is_shareable(model):
        return False
    codenames = model_perm_codenames(model)
    wanted = [codenames[perm] for perm in perms if perm in codenames]
    if not wanted:
        return False

    from guardian.shortcuts import get_objects_for_user

    return get_objects_for_user(
        user,
        wanted,
        klass=model,
        any_perm=True,
        accept_global_perms=False,
    ).filter(pk=obj.pk).exists()


def granted_object_ids(model, user, perms=SHARE_PERMS):
    """PKs of ``model`` this user was explicitly granted object access to.

    ``accept_global_perms=False`` is important: without it, a user holding the
    *global* ``change_x`` permission would be handed every row. Pass
    ``perms=('change',)`` to ask "which rows may this user *write*?".
    """
    if not is_shareable(model):
        return model.objects.none()
    codenames = model_perm_codenames(model)
    wanted = [codenames[perm] for perm in perms if perm in codenames]
    if not wanted:
        return model.objects.none()
    from guardian.shortcuts import get_objects_for_user

    return get_objects_for_user(
        user,
        wanted,
        klass=model,
        any_perm=True,
        accept_global_perms=False,
    )


def object_shares(obj):
    """Describe current shares of ``obj`` for display.

    Returns a list of dicts: ``{'type': 'user'|'group', 'name': str,
    'perms': ['view', 'change'], 'id': int}``.
    """
    from guardian.shortcuts import get_groups_with_perms, get_users_with_perms

    codenames = model_perm_codenames(type(obj))
    reverse = {v: k for k, v in codenames.items()}

    shares = []
    users = get_users_with_perms(obj, attach_perms=True, with_group_users=False)
    for user, perms in users.items():
        shares.append({
            'type': 'user',
            'id': user.pk,
            'name': user.get_full_name() or user.username,
            'perms': sorted(reverse[p].capitalize() for p in perms if p in reverse),
        })
    groups = get_groups_with_perms(obj, attach_perms=True)
    for group, perms in groups.items():
        shares.append({
            'type': 'group',
            'id': group.pk,
            'name': group.name,
            'perms': sorted(reverse[p].capitalize() for p in perms if p in reverse),
        })
    shares.sort(key=lambda s: (s['type'], s['name'].lower()))
    return shares


def shareable_user_choices(obj):
    """Users who could be granted access, excluding the object's own owner."""
    User = get_user_model()
    qs = User.objects.filter(is_active=True).order_by('username')
    return qs
