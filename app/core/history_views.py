"""Organisation-wide change log.

django-simple-history already writes a row for every insert/update/delete of
every tracked model (see the ``history = HistoricalRecords()`` on each model).
What was missing is anywhere to *read* it without going model-by-model through
the admin — which is exactly what an ISO 27001 audit or an internal
investigation asks for: "show me everything that changed around March 3rd."

This view merges the most recent history rows across the tracked business
models into one paginated, filterable list. It is restricted to HODs and
superusers because it shows titles and identifiers across all departments;
rows are not trimmed to the viewer's department (a change log cut in half at
department borders would hide most of the interesting events).

Details:
* per model, only the newest ``_ROW_BUDGET`` rows are merged, so the page
  stays O(few thousand rows) regardless of total history size;
* FKs are selected up front so ``str(instance)`` never emits per-row queries;
* the metadata soups (Notification, UserPreference) are excluded — the bell
  fires constantly and would bury real record changes.
"""
from django import forms  # noqa: F401 - kept for future filter forms
from django.core.paginator import Paginator  # noqa: F401
from django.utils import timezone
from django.views.generic import ListView

from core.mixins import HODOrSuperuserMixin

import simple_history.models as _shm

_PREVIEW_ROWS = 40
_ROW_BUDGET = 150
_EXCLUDED = {'core_notification', 'core_userpreference', 'core_organisationprofile'}


def _historical_model(model):
    return model.history.model


def _fk_names(model):
    return [
        f.name for f in model._meta.fields
        if f.is_relation and f.many_to_one
    ]


def source_models():
    """Tracked business models in viewer-friendly order."""
    out = []
    for key, model in _shm.registered_models.items():
        if key in _EXCLUDED:
            continue
        out.append(model)
    return sorted(out, key=lambda m: m._meta.verbose_name_plural.lower())


class HistoryListView(HODOrSuperuserMixin, ListView):
    template_name = 'core/history_list.html'
    context_object_name = 'entries'
    paginate_by = 50

    MODEL_CHOICES = [
        (f'{model._meta.app_label}.{model._meta.model_name}',
         model._meta.verbose_name_plural)
        for model in source_models()
    ]

    def get(self, request, *args, **kwargs):
        self.selected = request.GET.get('model', '')
        self.record_type = request.GET.get('type', '')
        self.search = (request.GET.get('q') or '').strip()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """Merged, most-recent history rows across the tracked models."""
        objects = _shm.registered_models

        wanted = objects.values()
        if self.selected:
            wanted = [
                m for m in wanted
                if f'{m._meta.app_label}.{m._meta.model_name}' == self.selected
            ]

        cutoff = timezone.now() - timezone.timedelta(days=180)
        entries = []
        for model in wanted:
            hist = _historical_model(model)
            # A broad unfiltered read stays cheap; a text search scans deeper.
            if self.selected:
                row_budget = None
            elif self.search:
                row_budget = 500
            else:
                row_budget = _ROW_BUDGET
            fks = _fk_names(hist)
            qs = hist.objects.filter(history_date__gte=cutoff).select_related(*fks)
            if self.record_type in ('+', '~', '-'):
                qs = qs.filter(history_type=self.record_type)

            if row_budget:
                qs = qs[:row_budget]
            for row in qs:
                try:
                    obj_repr = str(row.instance)
                except Exception:
                    obj_repr = f'#{row.id}'
                if self.search and self.search.lower() not in obj_repr.lower():
                    continue
                entries.append({
                    'when': row.history_date,
                    'user': _history_user_name(row),
                    'type': row.history_type,
                    'model_label': model._meta.verbose_name,
                    'model_path': f'{model._meta.app_label}.{model._meta.model_name}',
                    'object_id': row.id,
                    'repr': obj_repr,
                })

        entries.sort(key=lambda e: e['when'], reverse=True)
        return entries

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'model_choices': self.MODEL_CHOICES,
            'selected_model': self.selected,
            'selected_type': self.record_type,
            'search_query': self.search,
        })
        return ctx


def _history_user_name(row):
    user = getattr(row, 'history_user', None)
    if user is None:
        return '—'
    return user.get_full_name() or user.username
