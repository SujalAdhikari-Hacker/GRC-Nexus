from django.db.models import Q
from django.views.generic import ListView, DetailView

from core.mixins import DepartmentScopedMixin, CsvExportMixin
from core.correlation import get_full_asset_context
from .models import Asset, AssetCategory


class AssetListView(DepartmentScopedMixin, CsvExportMixin, ListView):
    model = Asset
    template_name = 'assets/asset_list.html'
    context_object_name = 'assets'
    paginate_by = 20

    csv_filename = 'assets.csv'
    csv_fields = [
        ('Name', 'name'),
        ('Category', lambda a: a.category.name),
        ('Department', lambda a: a.owner_dept.name),
        ('Criticality', 'get_criticality_display'),
        ('Confidentiality', 'confidentiality'),
        ('Integrity', 'integrity'),
        ('Availability', 'availability'),
        ('CIA Avg', 'cia_score'),
        ('Value', 'value'),
        ('Active', lambda a: 'Yes' if a.is_active else 'No'),
        ('Risk Count', lambda a: a.risks.count()),
        ('Created', lambda a: a.created_at.strftime('%Y-%m-%d')),
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        cat = self.request.GET.get('category')
        if cat:
            qs = qs.filter(category_id=cat)
        crit = self.request.GET.get('criticality')
        if crit:
            qs = qs.filter(criticality=crit)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = AssetCategory.objects.all()
        ctx['search_query'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_criticality'] = self.request.GET.get('criticality', '')
        return ctx


class AssetDetailView(DepartmentScopedMixin, DetailView):
    model = Asset
    template_name = 'assets/asset_detail.html'
    context_object_name = 'asset'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_full_asset_context(self.object))
        return ctx