"""
Report generation utilities: PDF (WeasyPrint) + Excel (openpyxl) + ReportMixin for ListViews.
"""
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string


# ============================================================
# PDF RENDERING
# ============================================================

def render_pdf(request, template_name, context, filename):
    """Render a Django template to PDF."""
    from weasyprint import HTML
    from django.utils import timezone

    context['request'] = request
    context['generated_at'] = timezone.now()
    context['generated_by'] = getattr(request, 'user', None)

    html_string = render_to_string(template_name, context, request=request)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
    pdf_bytes = html.write_pdf()

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================================
# EXCEL RENDERING
# ============================================================

def render_excel(title, headers, rows, filename, sheet_name=None, column_widths=None):
    """Render tabular data to an Excel workbook."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from django.utils import timezone

    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_name or title)[:31]

    header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='0B1220', end_color='0B1220', fill_type='solid')
    title_font = Font(name='Calibri', size=16, bold=True, color='0B1220')
    meta_font = Font(name='Calibri', size=10, color='6B7280')
    border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB'),
    )

    max_cols = max(len(headers), 1)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_cols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = title_font
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 28

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_cols)
    c = ws.cell(row=2, column=1,
                value=f'Generated {timezone.now().strftime("%Y-%m-%d %H:%M")} · Aegis GRC Platform')
    c.font = meta_font

    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col_idx, value=header)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal='left', vertical='center')
        c.border = border
    ws.row_dimensions[header_row].height = 20

    for row_idx, row_data in enumerate(rows, start=header_row + 1):
        for col_idx, value in enumerate(row_data, start=1):
            c = ws.cell(row=row_idx, column=col_idx, value=value)
            c.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            c.border = border
            c.font = Font(name='Calibri', size=10)

    if column_widths:
        for col_idx, width in enumerate(column_widths, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width
    else:
        for col_idx in range(1, len(headers) + 1):
            max_len = len(str(headers[col_idx - 1]))
            for row in rows:
                if col_idx <= len(row):
                    cell_len = len(str(row[col_idx - 1] or ''))
                    if cell_len > max_len:
                        max_len = cell_len
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 2, 12), 50)

    ws.freeze_panes = f'A{header_row + 1}'

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================================
# REPORT MIXIN
# ============================================================

class ReportMixin:
    """Adds ?format=pdf / ?format=xlsx dispatch to any ListView."""
    report_title = 'Report'
    report_filename_base = 'report'
    pdf_template = None

    def get(self, request, *args, **kwargs):
        fmt = request.GET.get('format')
        if fmt == 'pdf':
            return self._render_pdf_report()
        if fmt in ('xlsx', 'excel'):
            return self._render_excel_report()
        return super().get(request, *args, **kwargs)

    def build_rows(self):
        raise NotImplementedError('Subclass must define build_rows() returning (headers, rows)')

    def build_pdf_context(self):
        return {'title': self.report_title}

    def _render_pdf_report(self):
        from django.utils import timezone
        ctx = self.build_pdf_context()
        ctx['title'] = self.report_title
        ctx['generated_at'] = timezone.now()
        ctx['generated_by'] = self.request.user
        filename = f'{self.report_filename_base}_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'
        return render_pdf(self.request, self.pdf_template, ctx, filename)

    def _render_excel_report(self):
        from django.utils import timezone
        headers, rows = self.build_rows()
        filename = f'{self.report_filename_base}_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx'
        return render_excel(
            title=self.report_title,
            headers=headers,
            rows=rows,
            filename=filename,
            sheet_name=self.report_filename_base[:31],
        )
