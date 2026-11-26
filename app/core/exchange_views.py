"""Bulk Excel import/export for the records people keep in spreadsheets.

The page is one place for the whole round-trip: download the workbook for a
record type, edit it, upload it back. Exports are department-scoped, and an
import can only touch rows the user may already change.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.views import View
from django.views.generic import TemplateView

from .excel_io import ENTITIES, MAX_UPLOAD_BYTES, export_workbook, import_rows
from .mixins import scope_queryset


class DataExchangeView(LoginRequiredMixin, TemplateView):
    template_name = 'core/data_exchange.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cards'] = [
            {
                'entity': entity,
                'count': scope_queryset(
                    entity.model.objects.all(), self.request.user
                ).count(),
            }
            for entity in ENTITIES.values()
        ]
        return context

    def post(self, request, *args, **kwargs):
        entity = ENTITIES.get(request.POST.get('entity', ''))
        if entity is None:
            raise Http404('Unknown record type')

        upload = request.FILES.get('file')
        if upload is None:
            result = {'error': 'Choose an .xlsx file first.'}
        elif not upload.name.lower().endswith('.xlsx'):
            result = {'error': 'Only .xlsx workbooks are accepted.'}
        elif upload.size > MAX_UPLOAD_BYTES:
            result = {'error': 'The file is larger than 5 MB.'}
        else:
            try:
                from openpyxl import load_workbook

                workbook = load_workbook(upload, read_only=True, data_only=True)
                result = import_rows(entity, workbook, request.user)
            except Exception as exc:  # unreadable file, missing sheet, ...
                result = {'error': f'Could not read the workbook: {exc}'}

        result['entity'] = entity
        return self.render_to_response(self.get_context_data(result=result))


class DataExportView(LoginRequiredMixin, View):
    def get(self, request, entity):
        definition = ENTITIES.get(entity)
        if definition is None:
            raise Http404('Unknown record type')

        queryset = scope_queryset(
            definition.model.objects.all(), request.user
        ).order_by('pk')
        return export_workbook(definition, queryset)
