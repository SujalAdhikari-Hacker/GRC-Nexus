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

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect

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


def user_can_access(user, obj, field='owner_dept'):
    """Object-level counterpart to :func:`scope_queryset`."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if getattr(obj, 'is_shared', False):
        return True
    obj_dept_id = getattr(obj, f'{field}_id', None)
    if user.department_id and obj_dept_id == user.department_id:
        return True

    from .permissions import user_has_object_perm

    return user_has_object_perm(user, obj)


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


class HODOrSuperuserMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Only department heads and superusers."""

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_hod)


class DepartmentCreateMixin:
    """Pin a created record's ``owner_dept`` to the creator's department.

    Non-superusers could otherwise pick any department from the form's
    dropdown and write data into a department they do not belong to. Place
    this *before* other mixins in the MRO so its ``form_valid`` runs.
    """

    def form_valid(self, form):
        user = self.request.user
        if (
            not getattr(user, 'is_superuser', False)
            and hasattr(form.instance, 'owner_dept_id')
        ):
            form.instance.owner_dept = user.department
        return super().form_valid(form)


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

        queryset = self.get_queryset().filter(pk__in=request.POST.getlist('selected'))
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
        value = request.POST.get('bulk_value', '')
        if value not in allowed:
            messages.error(request, 'That value is not allowed for this action.')
            return redirect(request.get_full_path())

        updated = queryset.update(**{field: value})
        plural = '' if updated == 1 else 's'
        messages.success(request, f'Updated {updated} record{plural}.')
        return redirect(request.get_full_path())
