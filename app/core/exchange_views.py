"""Bulk spreadsheet import/export for the records people keep in spreadsheets.

The page is one place for the whole round-trip: download a workbook (or the
blank template) for a record type, edit it, upload it back as .xlsx or .csv.
Exports are scoped to the rows the user may see; an import can only touch rows
they may already change.
"""
from django.http import Http404
from django.views import View
from django.views.generic import TemplateView

from .excel_io import (
    ENTITIES, MAX_UPLOAD_BYTES, export_csv, export_workbook, import_csv,
    import_rows, table_rows,
)
from .mixins import HODOrSuperuserMixin, scope_queryset


def _scoped(entity, user):
    if entity.scope_field is None:
        return entity.model.objects.all().order_by('pk')
    return scope_queryset(
        entity.model.objects.all(), user, field=entity.scope_field,
    ).order_by('pk')


class DataExchangeView(HODOrSuperuserMixin, TemplateView):
    template_name = 'core/data_exchange.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cards'] = [
            {'entity': entity, 'count': _scoped(entity, self.request.user).count()}
            for entity in ENTITIES.values()
        ]
        return context

    def post(self, request, *args, **kwargs):
        entity = ENTITIES.get(request.POST.get('entity', ''))
        if entity is None:
            raise Http404('Unknown record type')

        upload = request.FILES.get('file')
        name = (upload.name if upload else '').lower()
        if upload is None:
            result = {'error': 'Choose an .xlsx or .csv file first.'}
        elif upload.size > MAX_UPLOAD_BYTES:
            result = {'error': 'The file is larger than 5 MB.'}
        elif name.endswith('.csv'):
            try:
                result = import_csv(entity, upload, request.user)
            except Exception as exc:  # unreadable file, wrong encoding, ...
                result = {'error': f'Could not read the CSV file: {exc}'}
        elif name.endswith('.xlsx'):
            try:
                from openpyxl import load_workbook

                workbook = load_workbook(upload, read_only=True, data_only=True)
                result = import_rows(entity, workbook, request.user)
            except Exception as exc:  # unreadable file, missing sheet, ...
                result = {'error': f'Could not read the workbook: {exc}'}
        else:
            result = {'error': 'Only .xlsx or .csv files are accepted.'}

        result['entity'] = entity
        return self.render_to_response(self.get_context_data(result=result))


class DataExportView(HODOrSuperuserMixin, View):
    def get(self, request, entity):
        definition = ENTITIES.get(entity)
        if definition is None:
            raise Http404('Unknown record type')

        queryset = _scoped(definition, request.user)
        fmt = request.GET.get('format', 'xlsx').lower()
        if fmt == 'csv':
            return export_csv(definition, queryset)
        if fmt == 'pdf':
            return self._pdf(request, definition, queryset)
        template = request.GET.get('template') == '1'
        return export_workbook(definition, queryset, include_rows=not template)

    @staticmethod
    def _pdf(request, entity, queryset):
        from django.utils import timezone

        from .reports import render_pdf

        headers, rows = table_rows(entity, queryset)
        return render_pdf(
            request,
            'core/entity_pdf.html',
            {
                'entity': entity,
                'headers': headers,
                'rows': rows,
                'count': len(rows),
            },
            f'{entity.key}_{timezone.localdate():%Y%m%d}.pdf',
        )
