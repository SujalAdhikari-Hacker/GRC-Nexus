from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_control_context
from .models import Control


class ControlListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Control
    template_name = 'controls/control_list.html'
    context_object_name = 'controls'
    paginate_by = 25

    csv_filename = 'controls.csv'
    csv_fields = [
        ('Code', 'code'),
        ('Name', 'name'),
        ('Type', 'get_control_type_display'),
        ('Category', 'get_category_display'),
        ('Status', 'get_status_display'),
        ('Effectiveness', 'effectiveness'),
        ('Department', lambda c: c.owner_dept.name),
        ('Shared', lambda c: 'Yes' if c.is_shared else 'No'),
        ('Frameworks', lambda c: ', '.join(f'{fc.framework.name} {fc.code}' for fc in c.framework_controls.all())),
        ('Risk Count', lambda c: c.risks.count()),
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs.order_by('code')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['statuses'] = Control.STATUS_CHOICES
        ctx['categories_choices'] = Control.CATEGORY_CHOICES
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        return ctx


class ControlDetailView(DepartmentScopedMixin, DetailView):
    model = Control
    template_name = 'controls/control_detail.html'
    context_object_name = 'control'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_control_context(self.object))
        return ctx
