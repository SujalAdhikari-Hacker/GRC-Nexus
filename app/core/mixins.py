"""
Shared view mixins and queryset scoping helpers.

Authorization rules live here so every view applies them the same way:

* superusers see everything;
* a user with a department sees their own department's records, plus any
  record explicitly flagged ``is_shared`` (where the model supports it);
* a user without a department sees nothing.

Never hand-roll ``if not user.is_superuser and user.department_id:`` in a
view — that pattern silently grants full visibility to department-less
accounts. Always call :func:`scope_queryset`.
"""
import csv
import re

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect

from .input_validation import id_list, text

# Characters that spreadsheet programs treat as the start of a formula.
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r', '\n')
# ...but a plain number ('-2', '+5.5') or a bare dash is inert in Excel, and
# those are exactly what people type into "not applicable" fields. Escaping them
# would corrupt real data (a value of "-" must export as "-", not "'-").
_INERT_CELL = re.compile(r'^(?:[+-]?\d+(?:\.\d+)?|\.\d+|-+)$')


def _granted_pks(model, user):
    """PKs the user was explicitly granted object access to, memoised per request.

    ``scope_queryset`` runs on nearly every list and dashboard query, so the
    guardian lookup is cached on the (per-request) user object. Only the small
    set of shareable models is consulted; everything else returns ``None`` and
    is skipped entirely, keeping the common case at zero extra queries.
    """
    from .permissions import granted_object_ids, is_shareable

    if model is None or not is_shareable(model):
        return None
    cache = getattr(user, '_grc_shared_pks', None)
    if cache is None:
        cache = {}
        try:
            user._grc_shared_pks = cache
        except (AttributeError, TypeError):
            return None
    key = model._meta.label_lower
    if key not in cache:
        try:
            cache[key] = list(
                granted_object_ids(model, user).values_list('pk', flat=True)
            )
        except Exception:
            cache[key] = []
    return cache[key]


_OVERSIGHT_EXCLUDED_MODELS = {'core.usermfa', 'core.notification'}


def user_has_org_read(user):
    """True when ``user`` has org-wide read-only oversight (superusers or Audit/Compliance)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    dept = getattr(user, 'department', None)
    return bool(dept and getattr(dept, 'has_org_read_oversight', False))


def scope_queryset(queryset, user, field='owner_dept'):
    """Return ``queryset`` limited to the rows ``user`` is allowed to see.

    Visibility is the union of: the user's own department, any record flagged
    ``is_shared`` (where the model supports it), and any record explicitly
    granted to the user or one of their groups via django-guardian.
    """
    if not getattr(user, 'is_authenticated', False):
        return queryset.none()
    if user.is_superuser:
        return queryset

    model = getattr(queryset, 'model', None)
    if (
        user_has_org_read(user)
        and (model is None or model._meta.label_lower not in _OVERSIGHT_EXCLUDED_MODELS)
    ):
        return queryset
    condition = Q()

    if getattr(user, 'department_id', None):
        condition = Q(**{field: user.department})
        if model is not None and hasattr(model, 'is_shared'):
            condition |= Q(is_shared=True)

    granted = _granted_pks(model, user)
    if granted:
        condition |= Q(pk__in=granted)

    if not condition:
        return queryset.none()
    return queryset.filter(condition)


def writable_queryset(queryset, user, field='owner_dept'):
    """Narrow ``queryset`` to rows ``user`` may *change*.

    Unlike :func:`scope_queryset`, this excludes read-only shares and the
    org-wide ``is_shared`` flag: those widen *visibility*, not authority.
    Keep in sync with :func:`user_can_change`.
    """
    if not getattr(user, 'is_authenticated', False):
        return queryset.none()
    if user.is_superuser:
        return queryset
    model = getattr(queryset, 'model', None)

    condition = Q()
    if getattr(user, 'department_id', None):
        condition |= Q(**{field: user.department})
    if model is not None:
        from .permissions import granted_object_ids

        change_pks = list(
            granted_object_ids(model, user, perms=('change',)).values_list(
                'pk', flat=True
            )
        )
        if change_pks:
            condition |= Q(pk__in=change_pks)

    if not condition:
        return queryset.none()
    return queryset.filter(condition)


def user_can_access(user, obj, field='owner_dept'):
    """Object-level counterpart to :func:`scope_queryset` (read access)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if (
        user_has_org_read(user)
        and obj._meta.label_lower not in _OVERSIGHT_EXCLUDED_MODELS
    ):
        return True
    if getattr(obj, 'is_shared', False):
        return True
    obj_dept_id = getattr(obj, f'{field}_id', None)
    if user.department_id and obj_dept_id == user.department_id:
        return True

    from .permissions import user_has_object_perm

    return user_has_object_perm(user, obj)


def user_can_change(user, obj, field='owner_dept'):
    """Object-level **write** counterpart to :func:`user_can_access`.

    Writing requires membership of the record's own department, or an explicit
    ``change`` object grant. Two things deliberately do **not** grant write:

    * a read-only (``view``) share — "share for visibility" must never silently
      hand over edit rights; and
    * the org-wide ``is_shared`` read flag, which exists so a shared control can
      be *seen* across departments, not edited by them.

    Global model permissions are ignored: this answers "may *this user* change
    *this object*?", and department membership already covers the normal case.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    obj_dept_id = getattr(obj, f'{field}_id', None)
    if user.department_id and obj_dept_id == user.department_id:
        return True

    from .permissions import user_has_object_perm

    return user_has_object_perm(user, obj, perms=('change',))


def exclude_anonymous_user_from_form(form):
    """Strip django-guardian's AnonymousUser from every User choice field on ``form``."""
    from .models import User, real_users

    for field in form.fields.values():
        if isinstance(field, forms.ModelChoiceField) and field.queryset is not None:
            if field.queryset.model is User:
                field.queryset = real_users(field.queryset)
    return form


def csv_safe(value):
    """Neutralise spreadsheet formula injection in exported cells.

    A leading ``=``, ``@``, tab or line break always starts a formula, as do
    ``+`` and ``-`` — unless the cell is just a number or a bare dash, which
    cannot execute anything.
    """
    if value is None:
        return ''
    text = str(value)
    stripped = text.lstrip()
    if not stripped:
        return text
    head = stripped[:1]
    if head in _FORMULA_PREFIXES:
        if head in ('+', '-') and _INERT_CELL.match(stripped):
            return text
        return "'" + text
    return text


class DepartmentScopedMixin(LoginRequiredMixin):
    department_field = 'owner_dept'

    def get_queryset(self):
        return scope_queryset(
            super().get_queryset(), self.request.user, self.department_field
        )

    def get_paginate_by(self, queryset):
        """Respect the user's items_per_page preference if set."""
        try:
            pref = getattr(self.request.user, 'preference', None)
            if pref and pref.items_per_page:
                return pref.items_per_page
        except Exception:
            pass
        return super().get_paginate_by(queryset)


class ChangeScopedMixin(DepartmentScopedMixin):
    """Scope *write* views (update / delete) to objects the user may change.

    ``DepartmentScopedMixin`` unions in read-only shares and ``is_shared``,
    which is correct for lists and detail pages but wrong for a mutation: a
    view-only share must never open an edit form, a delete confirmation, or a
    status endpoint. This narrows the queryset to the user's own department
    plus explicit ``change`` grants.
    """

    def get_queryset(self):
        return writable_queryset(
            super().get_queryset(), self.request.user, self.department_field
        )


class HODOrSuperuserMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only department heads and superusers."""

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_hod)


class DepartmentPinnedMixin:
    """Keep a record's owning department under the server's control.

    On **create**, a non-superuser's record is pinned to their own department,
    so a crafted form cannot write into another team's data.

    On **update**, the department recorded in the database is restored, so an
    edit can never *re-parent* a record. A field that let a user move a record
    (and therefore hide it from its real owners) is a data-integrity bug, not a
    feature.

    The original value is snapshotted in ``get_object`` — *before* form
    validation — because ``form.instance`` **is** ``self.object`` on an
    ``UpdateView``, so by ``form_valid`` time it already holds the tampered
    value.

    Handles both the usual ``owner_dept`` field and the ``department`` field
    used by e.g. risk appetites. Place this *before* other view mixins in the
    MRO so its ``form_valid`` runs.
    """

    dept_fields = ('owner_dept', 'department')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return exclude_anonymous_user_from_form(form)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)
        field = next((f for f in self.dept_fields if hasattr(obj, f'{f}_id')), None)
        self._pinned_field = field
        self._pinned_original_id = getattr(obj, f'{field}_id') if field else None
        return obj

    def form_valid(self, form):
        user = self.request.user
        if not getattr(user, 'is_superuser', False):
            field = getattr(self, '_pinned_field', None)
            if field is not None:
                # Update: restore the department that was in the database.
                setattr(form.instance, f'{field}_id', self._pinned_original_id)
            else:
                # Create: pin to the creator's own department.
                instance = form.instance
                field = next(
                    (f for f in self.dept_fields if hasattr(instance, f'{f}_id')),
                    None,
                )
                if field is not None:
                    setattr(instance, field, user.department)
        return super().form_valid(form)


# Back-compat alias — the mixin now guards updates as well as creates, so every
# existing ``DepartmentCreateMixin`` create view inherits the stricter rules.
DepartmentCreateMixin = DepartmentPinnedMixin


class SuperuserOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only superusers."""

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser


class CsvExportMixin:
    csv_filename = 'export.csv'
    csv_fields = []

    def get(self, request, *args, **kwargs):
        if request.GET.get('export') == 'csv':
            return self.export_csv()
        return super().get(request, *args, **kwargs)

    def export_csv(self):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{self.csv_filename}"'
        response.write('\ufeff')

        writer = csv.writer(response)
        writer.writerow([h for h, _ in self.csv_fields])

        for obj in self.get_queryset():
            row = []
            for _, attr in self.csv_fields:
                if callable(attr):
                    val = attr(obj)
                else:
                    val = getattr(obj, attr, '')
                    # Model methods referenced by name (e.g. 'get_status_display')
                    # resolve to a callable - call it, otherwise Django's
                    # ``partialmethod``-based ``get_FOO_display`` helpers would be
                    # written out as their ``functools.partial(...)`` repr.
                    if callable(val):
                        val = val()
                row.append(csv_safe(val))
            writer.writerow(row)
        return response


class SavedViewsMixin:
    """Expose a user's saved list filters on a ``ListView``.

    The chrome lives in ``base.html`` (guarded by ``supports_saved_views``), so a
    list page only needs to add this mixin — no template edits. The model is
    taken from ``self.model`` unless ``saved_view_model`` overrides it.
    """

    def saved_view_key(self):
        model = getattr(self, 'saved_view_model', None) or getattr(self, 'model', None)
        if model is None:
            return None
        return model._meta.label_lower

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        key = self.saved_view_key()
        user = getattr(self.request, 'user', None)
        if not key or user is None or not user.is_authenticated:
            return ctx

        from .models import SavedView

        params = self.request.GET.copy()
        params.pop('page', None)
        ctx['supports_saved_views'] = True
        ctx['saved_view_key'] = key
        ctx['saved_view_current_query'] = params.urlencode()
        ctx['saved_view_list'] = SavedView.objects.filter(
            user=user, model_label=key
        ).order_by('name')
        return ctx


class BulkActionsMixin:
    """Handle checkbox-driven bulk updates posted from a list page.

    Subclasses declare ``bulk_actions``::

        bulk_actions = {
            'set_status': {
                'label': 'Set status',
                'field': 'status',
                'choices': Model.STATUS_CHOICES,   # or a callable
            },
            'delete': {'label': 'Delete', 'delete': True},
        }

    The toolbar posts ``bulk_action`` (the key), ``bulk_value`` (for field
    actions) and repeated ``selected`` checkboxes. Rows come from the same
    department-scoped queryset the list uses, so a crafted POST can never touch
    a record the user cannot already see. Only server-declared field names and
    choice values are ever written.
    """

    bulk_actions = {}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.bulk_actions:
            defs = []
            for key, spec in self.bulk_actions.items():
                choices = spec.get('choices', [])
                if callable(choices):
                    choices = choices()
                is_delete = bool(spec.get('delete'))
                defs.append({
                    'key': key,
                    'label': spec['label'],
                    'delete': is_delete,
                    'has_value': bool(choices) and not is_delete,
                    'choices': list(choices),
                })
            ctx['bulk_action_defs'] = defs
        return ctx

    def post(self, request, *args, **kwargs):
        key = request.POST.get('bulk_action')
        spec = self.bulk_actions.get(key)
        if not spec:
            messages.error(request, 'Unknown bulk action.')
            return redirect(request.get_full_path())

        selected_ids = id_list(
            request.POST.getlist('selected'), 'selected', max_items=1000,
        )
        queryset = writable_queryset(
            self.get_queryset(), request.user, self.department_field
        ).filter(pk__in=selected_ids)
        if not queryset.exists():
            messages.warning(request, 'No records were selected.')
            return redirect(request.get_full_path())

        if spec.get('delete'):
            deleted = queryset.count()
            queryset.delete()
            plural = '' if deleted == 1 else 's'
            messages.success(request, f'Deleted {deleted} record{plural}.')
            return redirect(request.get_full_path())

        field = spec['field']
        choices = spec.get('choices', [])
        if callable(choices):
            choices = choices()
        allowed = {str(value) for value, _ in choices}
        value = text(
            request.POST.get('bulk_value', ''), 'bulk_value', 100,
            allow_blank=True, strip=True,
        )
        if value not in allowed:
            messages.error(request, 'That value is not allowed for this action.')
            return redirect(request.get_full_path())

        updated = queryset.update(**{field: value})
        plural = '' if updated == 1 else 's'
        messages.success(request, f'Updated {updated} record{plural}.')
        return redirect(request.get_full_path())
