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

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse

# Characters that spreadsheet programs treat as the start of a formula.
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r', '\n')
# ...but a plain number ('-2', '+5.5') or a bare dash is inert in Excel, and
# those are exactly what people type into "not applicable" fields. Escaping them
# would corrupt real data (a value of "-" must export as "-", not "'-").
_INERT_CELL = re.compile(r'^(?:[+-]?\d+(?:\.\d+)?|\.\d+|-+)$')


def scope_queryset(queryset, user, field='owner_dept'):
    """Return ``queryset`` limited to the rows ``user`` is allowed to see."""
    if not getattr(user, 'is_authenticated', False):
        return queryset.none()
    if user.is_superuser:
        return queryset
    if not getattr(user, 'department_id', None):
        return queryset.none()

    model = getattr(queryset, 'model', None)
    if model is not None and hasattr(model, 'is_shared'):
        return queryset.filter(Q(**{field: user.department}) | Q(is_shared=True))
    return queryset.filter(**{field: user.department})


def user_can_access(user, obj, field='owner_dept'):
    """Object-level counterpart to :func:`scope_queryset`."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if getattr(obj, 'is_shared', False):
        return True
    obj_dept_id = getattr(obj, f'{field}_id', None)
    return bool(user.department_id) and obj_dept_id == user.department_id


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
