import csv
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class DepartmentScopedMixin(LoginRequiredMixin):
    department_field = 'owner_dept'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        if not user.department_id:
            return qs.none()
        return qs.filter(**{self.department_field: user.department})


class HODOrSuperuserMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_hod)


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
                if val is None:
                    val = ''
                row.append(str(val))
            writer.writerow(row)
        return response